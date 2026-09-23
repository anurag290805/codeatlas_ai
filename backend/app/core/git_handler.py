"""Git repository management for CodeAtlas AI.

This module is the single interface through which the rest of the
backend performs Git operations. It validates GitHub repository URLs,
clones and updates repositories on local disk, and reports repository
metadata and status — all independent of parsing, embedding, vector
storage, and API routing, which live in other modules.

Callers interact exclusively through `GitRepositoryHandler`; no other
module should import GitPython or touch cloned repositories on disk
directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
from git.exc import GitError

from app.config import get_settings
from app.utils.file_utils import (
    ensure_directory_exists,
    remove_directory,
    safely_generate_repository_directory,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Matches HTTPS GitHub URLs of the form https://github.com/<owner>/<repo>,
# with an optional trailing slash and an optional ".git" suffix. Private
# repository / authenticated URL formats (git@github.com:..., tokens in
# the URL) are intentionally out of scope for now but can be added as
# additional accepted patterns without changing the public interface.
_GITHUB_HTTPS_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

# Wall-clock deadline (seconds) applied to every network-bound Git subprocess
# (clone, fetch, pull). A stalled remote must never pin a worker thread
# indefinitely -- otherwise a wedged import sits in "indexing" forever and the
# in-process worker cannot be reaped. On expiry GitPython SIGKILLs the
# subprocess and raises GitCommandError, which callers translate to
# RepositoryOperationError, so the pipeline records a clean failure instead of
# hanging. Value is generous enough for normal large clones; long-lived runs
# stay alive via the indexing heartbeat, not by relaxing this deadline.
GIT_OPERATION_TIMEOUT_SECONDS = 300


class RepositoryStatus(str, Enum):
    """Lifecycle status of a repository on local disk.

    Distinct from the indexing status stored in the database
    (`app.models.db_models.Repository.indexing_status`): this enum
    describes the state of the Git working copy itself, not whether it
    has been parsed and embedded.
    """

    NOT_CLONED = "not_cloned"
    CLONING = "cloning"
    CLONED = "cloned"
    UPDATING = "updating"
    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    FAILED = "failed"


@dataclass(frozen=True)
class RepositoryIdentity:
    """Parsed identity of a GitHub repository derived from its URL."""

    owner: str
    name: str
    full_name: str
    canonical_url: str


@dataclass(frozen=True)
class RepositoryMetadata:
    """Metadata describing a repository's state on local disk."""

    identity: RepositoryIdentity
    local_path: Path
    default_branch: str
    current_commit_hash: str
    status: RepositoryStatus


class InvalidRepositoryUrlError(ValueError):
    """Raised when a repository URL is missing, malformed, or unsupported."""


class RepositoryOperationError(RuntimeError):
    """Raised when a Git operation fails after a repository has been located."""


class GitRepositoryHandler:
    """Manages the full lifecycle of Git repositories used by CodeAtlas AI.

    Responsible for validating repository URLs, cloning and updating
    repositories into a configured local directory, and reporting
    repository metadata and status. Instances are lightweight and stateless
    beyond their configured storage directory, so a single instance can be
    reused (or safely instantiated per request) throughout the backend.
    """

    def __init__(self, repositories_dir: Path | None = None) -> None:
        """Initialize the handler with a base directory for cloned repositories.

        Args:
            repositories_dir: Directory under which repositories are
                cloned. Defaults to the path configured in application
                settings, allowing this to be overridden for tests
                without touching global configuration.
        """
        settings = get_settings()
        self._repositories_dir = repositories_dir or settings.REPOSITORIES_DIR
        ensure_directory_exists(self._repositories_dir)

    # ---------------------------------------------------------------
    # Repository Validation
    # ---------------------------------------------------------------

    @staticmethod
    def validate_repository_url(repository_url: str) -> RepositoryIdentity:
        """Validate a GitHub repository URL and extract its identity.

        Args:
            repository_url: The URL to validate.

        Returns:
            A `RepositoryIdentity` describing the owner, name, and
            canonical form of the URL.

        Raises:
            InvalidRepositoryUrlError: If the URL is empty, malformed, or
                not a supported HTTPS GitHub repository URL.
        """
        if not repository_url or not repository_url.strip():
            raise InvalidRepositoryUrlError("Repository URL must not be empty.")

        match = _GITHUB_HTTPS_URL_PATTERN.match(repository_url.strip())
        if match is None:
            raise InvalidRepositoryUrlError(
                f"Unsupported or malformed GitHub repository URL: {repository_url!r}"
            )

        owner = match.group("owner")
        name = match.group("name")
        full_name = f"{owner}/{name}"
        canonical_url = f"https://github.com/{full_name}"
        return RepositoryIdentity(
            owner=owner, name=name, full_name=full_name, canonical_url=canonical_url
        )

    # ---------------------------------------------------------------
    # Repository Path Resolution
    # ---------------------------------------------------------------

    def resolve_local_path(self, identity: RepositoryIdentity) -> Path:
        """Resolve the local filesystem path for a repository identity.

        Args:
            identity: The repository's parsed identity.

        Returns:
            The path under the configured repositories directory where
            this repository is (or would be) cloned.
        """
        return safely_generate_repository_directory(self._repositories_dir, identity.full_name)

    def repository_exists(self, identity: RepositoryIdentity) -> bool:
        """Check whether a repository has already been cloned locally.

        Args:
            identity: The repository's parsed identity.

        Returns:
            True if a valid Git working copy exists at the expected
            local path, False otherwise.
        """
        local_path = self.resolve_local_path(identity)
        return self._is_valid_git_repository(local_path)

    @staticmethod
    def _is_valid_git_repository(local_path: Path) -> bool:
        """Check whether a path contains a valid, non-bare Git repository."""
        if not local_path.is_dir():
            return False

        try:
            Repo(local_path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            return False

        return True

    # ---------------------------------------------------------------
    # Repository Cloning
    # ---------------------------------------------------------------

    def clone_repository(
        self,
        repository_url: str,
        *,
        branch: str | None = None,
        force_reclone: bool = False,
        target_path: Path | None = None,
    ) -> RepositoryMetadata:
        """Clone a repository, reusing an existing clone when possible.

        Args:
            repository_url: HTTPS GitHub repository URL to clone.
            branch: Specific branch to clone. Defaults to the
                repository's default branch when omitted.
            force_reclone: If True, delete any existing local clone
                before cloning fresh.

        Returns:
            Metadata describing the cloned repository's local state.

        Raises:
            InvalidRepositoryUrlError: If `repository_url` is invalid.
            RepositoryOperationError: If cloning fails.
        """
        identity = self.validate_repository_url(repository_url)
        local_path = Path(target_path) if target_path is not None else self.resolve_local_path(identity)

        if force_reclone and local_path.exists():
            logger.info("Force re-clone requested; removing existing clone: %s", local_path)
            remove_directory(local_path)

        if target_path is None and self._is_valid_git_repository(local_path):
            logger.info("Repository already cloned, reusing existing clone: %s", local_path)
            return self._build_metadata(identity, local_path, RepositoryStatus.CLONED)

        # Clean up any partial, invalid directory left over from a
        # previous interrupted clone before attempting a fresh clone.
        if local_path.exists():
            logger.warning("Removing invalid or partial repository directory: %s", local_path)
            remove_directory(local_path)

        ensure_directory_exists(self._repositories_dir)

        logger.info("Cloning repository %s into %s", identity.full_name, local_path)
        try:
            clone_kwargs = {"branch": branch} if branch else {}
            Repo.clone_from(
                identity.canonical_url,
                local_path,
                kill_after_timeout=GIT_OPERATION_TIMEOUT_SECONDS,
                **clone_kwargs,
            )
        except GitCommandError as exc:
            logger.error("Clone failed for repository %s: %s", identity.full_name, exc)
            remove_directory(local_path, missing_ok=True)
            raise RepositoryOperationError(
                f"Failed to clone repository {identity.full_name!r}: {exc}"
            ) from exc
        except GitError as exc:
            logger.error("Unexpected Git error while cloning %s: %s", identity.full_name, exc)
            remove_directory(local_path, missing_ok=True)
            raise RepositoryOperationError(
                f"Unexpected error cloning repository {identity.full_name!r}: {exc}"
            ) from exc

        if not self._is_valid_git_repository(local_path):
            remove_directory(local_path, missing_ok=True)
            raise RepositoryOperationError(
                f"Clone reported success but no valid repository was found at {local_path}"
            )

        logger.info("Clone completed for repository %s", identity.full_name)
        return self._build_metadata(identity, local_path, RepositoryStatus.CLONED)

    def promote_repository_clone(self, identity: RepositoryIdentity, staged_path: Path) -> Path:
        """Atomically promote a staged clone while retaining the live clone until then."""
        live_path = self.resolve_local_path(identity)
        backup_path = live_path.with_name(f".{live_path.name}.previous")
        try:
            if backup_path.exists():
                remove_directory(backup_path)
            if live_path.exists():
                live_path.replace(backup_path)
            Path(staged_path).replace(live_path)
            if backup_path.exists():
                remove_directory(backup_path)
        except OSError as exc:
            if live_path.exists() and not backup_path.exists():
                remove_directory(live_path, missing_ok=True)
            if backup_path.exists() and not live_path.exists():
                backup_path.replace(live_path)
            raise RepositoryOperationError(
                f"Failed to promote staged repository clone for {identity.full_name!r}: {exc}"
            ) from exc
        logger.info("Promoted staged clone repository=%s path=%s", identity.full_name, live_path)
        return live_path

    # ---------------------------------------------------------------
    # Repository Updating
    # ---------------------------------------------------------------

    def pull_latest_changes(self, identity: RepositoryIdentity) -> RepositoryMetadata:
        """Fetch and pull the latest changes for an already-cloned repository.

        Args:
            identity: The repository's parsed identity.

        Returns:
            Updated metadata reflecting the repository's state after the
            pull.

        Raises:
            RepositoryOperationError: If the repository has not been
                cloned, or if fetching/pulling fails.
        """
        local_path = self.resolve_local_path(identity)
        if not self._is_valid_git_repository(local_path):
            raise RepositoryOperationError(
                f"Cannot pull changes; repository {identity.full_name!r} is not cloned."
            )

        repo = Repo(local_path)
        try:
            logger.info("Fetching updates for repository %s", identity.full_name)
            origin = repo.remotes.origin
            origin.fetch(kill_after_timeout=GIT_OPERATION_TIMEOUT_SECONDS)
            origin.pull(kill_after_timeout=GIT_OPERATION_TIMEOUT_SECONDS)
        except GitCommandError as exc:
            logger.error("Pull failed for repository %s: %s", identity.full_name, exc)
            raise RepositoryOperationError(
                f"Failed to pull latest changes for {identity.full_name!r}: {exc}"
            ) from exc

        logger.info("Repository updated: %s", identity.full_name)
        return self._build_metadata(identity, local_path, RepositoryStatus.UP_TO_DATE)

    def requires_reindexing(
        self, identity: RepositoryIdentity, last_indexed_commit_hash: str
    ) -> bool:
        """Determine whether a repository has new commits since it was last indexed.

        Fetches remote updates (without merging them) to compare the
        remote's latest commit against the previously indexed commit,
        so callers can decide whether to pull and re-index without
        mutating the working copy.

        Args:
            identity: The repository's parsed identity.
            last_indexed_commit_hash: Commit hash the repository was at
                when it was last indexed.

        Returns:
            True if the remote has commits beyond `last_indexed_commit_hash`.

        Raises:
            RepositoryOperationError: If the repository has not been
                cloned, or if fetching fails.
        """
        local_path = self.resolve_local_path(identity)
        if not self._is_valid_git_repository(local_path):
            raise RepositoryOperationError(
                f"Cannot check for updates; repository {identity.full_name!r} is not cloned."
            )

        repo = Repo(local_path)
        try:
            origin = repo.remotes.origin
            fetch_info = origin.fetch()
        except GitCommandError as exc:
            logger.error("Fetch failed for repository %s: %s", identity.full_name, exc)
            raise RepositoryOperationError(
                f"Failed to fetch updates for {identity.full_name!r}: {exc}"
            ) from exc

        if not fetch_info:
            return False

        remote_commit_hash = fetch_info[0].commit.hexsha
        return remote_commit_hash != last_indexed_commit_hash

    # ---------------------------------------------------------------
    # Repository Management
    # ---------------------------------------------------------------

    def delete_repository(self, identity: RepositoryIdentity) -> bool:
        """Delete a repository's local clone from disk.

        Args:
            identity: The repository's parsed identity.

        Returns:
            True if a repository was found and deleted, False if there
            was nothing to delete.

        Raises:
            RepositoryOperationError: If deletion fails.
        """
        local_path = self.resolve_local_path(identity)
        if not local_path.exists():
            logger.warning("No local repository to delete at: %s", local_path)
            return False

        try:
            remove_directory(local_path, missing_ok=False)
        except OSError as exc:
            raise RepositoryOperationError(
                f"Failed to delete repository {identity.full_name!r}: {exc}"
            ) from exc

        logger.info("Deleted repository: %s", identity.full_name)
        return True

    def cleanup_failed_clone(self, identity: RepositoryIdentity) -> None:
        """Remove a partially-cloned or corrupted repository directory.

        Safe to call even when no directory exists or the directory is a
        valid repository; in the latter case this is a no-op to avoid
        destroying a working clone.

        Args:
            identity: The repository's parsed identity.
        """
        local_path = self.resolve_local_path(identity)
        if local_path.exists() and not self._is_valid_git_repository(local_path):
            logger.warning("Cleaning up failed/partial clone at: %s", local_path)
            remove_directory(local_path)

    # ---------------------------------------------------------------
    # Repository Metadata & Status
    # ---------------------------------------------------------------

    def get_metadata(self, identity: RepositoryIdentity) -> RepositoryMetadata:
        """Retrieve current metadata for a repository's local clone.

        Args:
            identity: The repository's parsed identity.

        Returns:
            Metadata describing the repository's local state. If the
            repository has not been cloned, returns metadata with
            `status=RepositoryStatus.NOT_CLONED` and empty branch/commit
            fields, rather than raising.
        """
        local_path = self.resolve_local_path(identity)
        if not self._is_valid_git_repository(local_path):
            return RepositoryMetadata(
                identity=identity,
                local_path=local_path,
                default_branch="",
                current_commit_hash="",
                status=RepositoryStatus.NOT_CLONED,
            )

        return self._build_metadata(identity, local_path, RepositoryStatus.CLONED)

    def _build_metadata(
        self, identity: RepositoryIdentity, local_path: Path, status: RepositoryStatus
    ) -> RepositoryMetadata:
        """Construct `RepositoryMetadata` by inspecting a cloned repository.

        Args:
            identity: The repository's parsed identity.
            local_path: Local filesystem path of the clone.
            status: Status to report for this metadata snapshot.

        Returns:
            Populated `RepositoryMetadata` for the repository.

        Raises:
            RepositoryOperationError: If repository metadata cannot be
                read from the local clone.
        """
        try:
            repo = Repo(local_path)
            default_branch = self._detect_default_branch(repo)
            current_commit_hash = repo.head.commit.hexsha
        except (GitError, ValueError) as exc:
            logger.error("Failed to read metadata for repository %s: %s", identity.full_name, exc)
            raise RepositoryOperationError(
                f"Failed to read metadata for repository {identity.full_name!r}: {exc}"
            ) from exc

        return RepositoryMetadata(
            identity=identity,
            local_path=local_path,
            default_branch=default_branch,
            current_commit_hash=current_commit_hash,
            status=status,
        )

    @staticmethod
    def _detect_default_branch(repo: Repo) -> str:
        """Determine the active branch name of a cloned repository.

        Falls back to a shortened commit hash when the repository is in
        a detached-HEAD state (e.g. a shallow clone of a specific
        commit), since `repo.active_branch` raises in that case.

        Args:
            repo: An open GitPython `Repo` instance.

        Returns:
            The best-available branch name for the repository.
        """
        try:
            return repo.active_branch.name
        except TypeError:
            return repo.head.commit.hexsha[:12]


class GitRepositoryManager(GitRepositoryHandler):
    """Compatibility facade exposing URL-oriented API service methods."""

    def update_repository(self, repository_url: str) -> RepositoryMetadata:
        identity = self.validate_repository_url(repository_url)
        return self.pull_latest_changes(identity)

    def remove_local_clone(self, repository_url: str) -> bool:
        identity = self.validate_repository_url(repository_url)
        return self.delete_repository(identity)
