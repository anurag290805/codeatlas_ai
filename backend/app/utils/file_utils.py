"""Reusable filesystem utilities for the CodeAtlas AI backend.

Every backend module should use these helpers instead of performing raw
filesystem operations directly, so that path handling, error handling,
and logging stay consistent across the codebase. This module is fully
generic: it knows nothing about git, Tree-sitter, embeddings, or the
database, and can be reused in any Python project.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_ENCODING = "utf-8"
_HASH_CHUNK_SIZE = 65536  # 64 KB, chosen to balance syscall count and memory use.
_SAFE_DIRECTORY_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


# =========================================================================
# Directory Operations
# =========================================================================


def directory_exists(directory_path: Path) -> bool:
    """Check whether a path exists and is a directory.

    Args:
        directory_path: Path to check.

    Returns:
        True if the path exists and is a directory, False otherwise.
    """
    return directory_path.is_dir()


def create_directory(directory_path: Path, *, parents: bool = True) -> Path:
    """Create a directory, optionally creating missing parent directories.

    Args:
        directory_path: Path of the directory to create.
        parents: If True, create any missing parent directories.

    Returns:
        The created directory path.

    Raises:
        OSError: If the directory cannot be created (e.g. permission
            denied, or a parent is missing and `parents` is False).
    """
    try:
        directory_path.mkdir(parents=parents, exist_ok=True)
    except OSError:
        logger.error("Failed to create directory: %s", directory_path)
        raise

    logger.info("Created directory: %s", directory_path)
    return directory_path


def ensure_directory_exists(directory_path: Path) -> Path:
    """Ensure a directory exists, creating it (and parents) if needed.

    Unlike `create_directory`, this function is silent when the directory
    already exists, making it suitable for frequent "make sure this is
    there" calls without noisy logging.

    Args:
        directory_path: Path of the directory to ensure exists.

    Returns:
        The directory path.

    Raises:
        OSError: If the directory does not exist and cannot be created.
    """
    if directory_path.is_dir():
        return directory_path
    return create_directory(directory_path)


def remove_directory(directory_path: Path, *, missing_ok: bool = True) -> None:
    """Recursively remove a directory and its contents.

    Args:
        directory_path: Path of the directory to remove.
        missing_ok: If True, do nothing when the directory does not
            exist. If False, raise `FileNotFoundError`.

    Raises:
        FileNotFoundError: If the directory does not exist and
            `missing_ok` is False.
        OSError: If removal fails for any other reason.
    """
    if not directory_path.exists():
        if missing_ok:
            return
        raise FileNotFoundError(f"Directory does not exist: {directory_path}")

    if not directory_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory_path}")

    try:
        shutil.rmtree(directory_path)
    except OSError:
        logger.error("Failed to remove directory: %s", directory_path)
        raise

    logger.info("Removed directory: %s", directory_path)


# =========================================================================
# File Operations
# =========================================================================


def file_exists(file_path: Path) -> bool:
    """Check whether a path exists and is a regular file.

    Args:
        file_path: Path to check.

    Returns:
        True if the path exists and is a regular file, False otherwise.
    """
    return file_path.is_file()


def delete_file(file_path: Path, *, missing_ok: bool = True) -> None:
    """Delete a single file.

    Args:
        file_path: Path of the file to delete.
        missing_ok: If True, do nothing when the file does not exist.
            If False, raise `FileNotFoundError`.

    Raises:
        FileNotFoundError: If the file does not exist and `missing_ok`
            is False.
        OSError: If deletion fails for any other reason.
    """
    try:
        file_path.unlink(missing_ok=missing_ok)
    except OSError:
        logger.error("Failed to delete file: %s", file_path)
        raise

    logger.info("Deleted file: %s", file_path)


def copy_file(source_path: Path, destination_path: Path, *, overwrite: bool = False) -> Path:
    """Copy a file, optionally creating the destination's parent directory.

    Args:
        source_path: Path of the file to copy.
        destination_path: Destination path for the copy.
        overwrite: If False and the destination already exists, raise
            `FileExistsError`.

    Returns:
        The destination path.

    Raises:
        FileNotFoundError: If `source_path` does not exist.
        FileExistsError: If the destination exists and `overwrite` is
            False.
        OSError: If the copy operation fails.
    """
    if not source_path.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")

    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"Destination file already exists: {destination_path}")

    ensure_directory_exists(destination_path.parent)

    try:
        shutil.copy2(source_path, destination_path)
    except OSError:
        logger.error("Failed to copy file from %s to %s", source_path, destination_path)
        raise

    logger.info("Copied file: %s -> %s", source_path, destination_path)
    return destination_path


def move_file(source_path: Path, destination_path: Path, *, overwrite: bool = False) -> Path:
    """Move a file, optionally creating the destination's parent directory.

    Args:
        source_path: Path of the file to move.
        destination_path: Destination path for the file.
        overwrite: If False and the destination already exists, raise
            `FileExistsError`.

    Returns:
        The destination path.

    Raises:
        FileNotFoundError: If `source_path` does not exist.
        FileExistsError: If the destination exists and `overwrite` is
            False.
        OSError: If the move operation fails.
    """
    if not source_path.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")

    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"Destination file already exists: {destination_path}")

    ensure_directory_exists(destination_path.parent)

    try:
        shutil.move(str(source_path), str(destination_path))
    except OSError:
        logger.error("Failed to move file from %s to %s", source_path, destination_path)
        raise

    logger.info("Moved file: %s -> %s", source_path, destination_path)
    return destination_path


def read_text_file(file_path: Path, *, encoding: str = _DEFAULT_ENCODING) -> str:
    """Read the full contents of a text file.

    Args:
        file_path: Path of the file to read.
        encoding: Text encoding to use. Defaults to UTF-8.

    Returns:
        The file's contents as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read.
        UnicodeDecodeError: If the file cannot be decoded with the given
            encoding.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    try:
        return file_path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError):
        logger.error("Failed to read text file: %s", file_path)
        raise


def write_text_file(
    file_path: Path, content: str, *, encoding: str = _DEFAULT_ENCODING
) -> Path:
    """Write text content to a file, creating parent directories as needed.

    Args:
        file_path: Path of the file to write.
        content: Text content to write.
        encoding: Text encoding to use. Defaults to UTF-8.

    Returns:
        The written file path.

    Raises:
        OSError: If the file cannot be written.
    """
    ensure_directory_exists(file_path.parent)

    try:
        file_path.write_text(content, encoding=encoding)
    except OSError:
        logger.error("Failed to write text file: %s", file_path)
        raise

    logger.info("Wrote text file: %s", file_path)
    return file_path


def read_binary_file(file_path: Path) -> bytes:
    """Read the full contents of a file in binary mode.

    Args:
        file_path: Path of the file to read.

    Returns:
        The file's contents as bytes.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    try:
        return file_path.read_bytes()
    except OSError:
        logger.error("Failed to read binary file: %s", file_path)
        raise


def write_binary_file(file_path: Path, content: bytes) -> Path:
    """Write binary content to a file, creating parent directories as needed.

    Args:
        file_path: Path of the file to write.
        content: Binary content to write.

    Returns:
        The written file path.

    Raises:
        OSError: If the file cannot be written.
    """
    ensure_directory_exists(file_path.parent)

    try:
        file_path.write_bytes(content)
    except OSError:
        logger.error("Failed to write binary file: %s", file_path)
        raise

    logger.info("Wrote binary file: %s", file_path)
    return file_path


# =========================================================================
# Repository Utilities
# =========================================================================


def safely_generate_repository_directory(base_path: Path, repository_name: str) -> Path:
    """Compute a filesystem-safe directory path for a cloned repository.

    Strips characters that are unsafe or ambiguous in directory names
    (e.g. slashes from an 'owner/repo' style name) so the result is a
    single, valid path segment nested under `base_path`.

    Args:
        base_path: Base directory under which repositories are stored.
        repository_name: Logical name of the repository, e.g. 'owner/repo'.

    Returns:
        A path under `base_path` safe to use as a clone destination.

    Raises:
        ValueError: If `repository_name` is empty or sanitizes to an
            empty string.
    """
    if not repository_name.strip():
        raise ValueError("repository_name must not be empty.")

    safe_name = _SAFE_DIRECTORY_NAME_PATTERN.sub("_", repository_name.strip())
    safe_name = safe_name.strip("._")

    if not safe_name:
        raise ValueError(f"repository_name sanitizes to an empty string: {repository_name!r}")

    return base_path / safe_name


def normalize_repository_path(repository_path: Path) -> Path:
    """Resolve a repository path to an absolute, normalized form.

    Args:
        repository_path: Path to normalize.

    Returns:
        The resolved absolute path. Does not require the path to exist.
    """
    return repository_path.expanduser().resolve()


def validate_repository_path(repository_path: Path) -> Path:
    """Validate that a path points to an existing repository directory.

    Args:
        repository_path: Path to validate.

    Returns:
        The normalized, validated path.

    Raises:
        FileNotFoundError: If the path does not exist.
        NotADirectoryError: If the path exists but is not a directory.
    """
    normalized_path = normalize_repository_path(repository_path)

    if not normalized_path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {normalized_path}")

    if not normalized_path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {normalized_path}")

    return normalized_path


# =========================================================================
# Path Utilities
# =========================================================================


def normalize_path(path: Path) -> Path:
    """Expand user (`~`) and resolve a path to its absolute, canonical form.

    Args:
        path: Path to normalize.

    Returns:
        The normalized, absolute path.
    """
    return path.expanduser().resolve()


def resolve_absolute_path(path: Path, *, base_path: Path | None = None) -> Path:
    """Resolve a possibly-relative path to an absolute path.

    Args:
        path: Path to resolve. May be relative or absolute.
        base_path: Base directory to resolve relative paths against.
            Defaults to the current working directory when omitted.

    Returns:
        The resolved absolute path.
    """
    if path.is_absolute():
        return path.resolve()

    base = base_path if base_path is not None else Path.cwd()
    return (base / path).resolve()


def relative_path(path: Path, base_path: Path) -> Path:
    """Compute a path relative to a given base directory.

    Args:
        path: Path to make relative.
        base_path: Base directory to compute the relative path against.

    Returns:
        `path` expressed relative to `base_path`.

    Raises:
        ValueError: If `path` is not located under `base_path`.
    """
    normalized_path = normalize_path(path)
    normalized_base = normalize_path(base_path)
    return normalized_path.relative_to(normalized_base)


def safe_join(base_path: Path, *segments: str) -> Path:
    """Join path segments onto a base path, preventing directory traversal.

    Args:
        base_path: Trusted base directory.
        *segments: Untrusted path segments to join onto `base_path`.

    Returns:
        The joined path, guaranteed to be located under `base_path`.

    Raises:
        ValueError: If the resulting path would escape `base_path`
            (e.g. via '..' segments or an absolute segment).
    """
    normalized_base = normalize_path(base_path)
    candidate_path = normalized_base.joinpath(*segments).resolve()

    if candidate_path != normalized_base and normalized_base not in candidate_path.parents:
        raise ValueError(
            f"Path traversal detected: {segments!r} escapes base path {normalized_base}"
        )

    return candidate_path


# =========================================================================
# Hash Utilities
# =========================================================================


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA-256 checksum of a file using streaming reads.

    Reads the file in fixed-size chunks so that large files can be
    hashed without loading their full contents into memory.

    Args:
        file_path: Path of the file to hash.

    Returns:
        The hexadecimal SHA-256 digest of the file's contents.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(_HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError:
        logger.error("Failed to compute checksum for file: %s", file_path)
        raise

    return digest.hexdigest()


def compute_sha256_of_text(content: str, *, encoding: str = _DEFAULT_ENCODING) -> str:
    """Compute the SHA-256 checksum of an in-memory string.

    Useful for hashing content that has already been read into memory
    (e.g. a chunk of source code) without writing it to disk first.

    Args:
        content: Text content to hash.
        encoding: Text encoding to use when converting to bytes.

    Returns:
        The hexadecimal SHA-256 digest of the encoded content.
    """
    return hashlib.sha256(content.encode(encoding)).hexdigest()


# =========================================================================
# Temporary Files
# =========================================================================


@contextmanager
def temporary_directory(prefix: str = "codeatlas_") -> Iterator[Path]:
    """Create a temporary directory that is automatically cleaned up.

    Args:
        prefix: Prefix applied to the generated directory name.

    Yields:
        The path of the created temporary directory.
    """
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        temp_path = Path(temp_dir)
        logger.info("Created temporary directory: %s", temp_path)
        try:
            yield temp_path
        finally:
            logger.info("Cleaning up temporary directory: %s", temp_path)


def create_temporary_file(
    *, prefix: str = "codeatlas_", suffix: str = "", directory: Path | None = None
) -> Path:
    """Create an empty temporary file and return its path.

    The caller is responsible for deleting the file (e.g. via
    `delete_file`) once it is no longer needed.

    Args:
        prefix: Prefix applied to the generated file name.
        suffix: Suffix applied to the generated file name.
        directory: Directory in which to create the file. Defaults to
            the system temporary directory when omitted.

    Returns:
        The path of the created temporary file.

    Raises:
        OSError: If the temporary file cannot be created.
    """
    try:
        file_descriptor, raw_path = tempfile.mkstemp(
            prefix=prefix, suffix=suffix, dir=str(directory) if directory else None
        )
    except OSError:
        logger.error("Failed to create temporary file with prefix: %s", prefix)
        raise

    import os

    os.close(file_descriptor)

    temp_file_path = Path(raw_path)
    logger.info("Created temporary file: %s", temp_file_path)
    return temp_file_path