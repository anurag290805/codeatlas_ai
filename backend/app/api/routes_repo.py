"""
REST API routes for repository lifecycle management in CodeAtlas AI.

This router exposes endpoints for importing, listing, inspecting,
updating, re-indexing, and deleting repositories. It orchestrates the
existing backend services -- GitRepositoryManager, RepositoryParser,
EmbeddingService, VectorStoreService, and the CRUD layer -- without
containing any business logic of its own.

Long-running indexing work (clone, parse, embed, upsert) runs via
FastAPI BackgroundTasks so request handlers remain non-blocking. The
orchestration function is isolated so it can later be moved to a
dedicated task queue (e.g. Celery, arq) without changing the API
contract exposed to clients.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import threading
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.embeddings import EmbeddingGenerationError, EmbeddingService
from app.core.auth import get_workspace_id
from app.core.git_handler import GitRepositoryManager, RepositoryOperationError
from app.core.graph_builder import get_graph_service
from app.core.indexing_queue import enqueue_indexing_job, release_indexing_job
from app.core.parser import RepositoryParseError, RepositoryParser
from app.core.vector_store import VectorStoreError, VectorStoreService
from app.core.workspace import ensure_workspace
from app.db import crud
from app.db.database import db_session, get_db
from app.models.db_models import Repository
from app.models import schemas
from app.utils.logger import get_logger

logger = get_logger(__name__)

# `ensure_workspace` materializes the Workspace row for the request-scoped
# workspace before any handler runs. Every other router depends on it; this
# one previously did not, so importing a repository INSERTed a row with a
# workspace_id that had no matching row in `workspaces`, violating the
# foreign key on PostgreSQL and returning HTTP 500.
router = APIRouter(
    prefix="/repositories",
    tags=["repositories"],
    dependencies=[Depends(ensure_workspace)],
)


# =========================================================================
# Service dependency providers
#
# Services are constructed once per process and reused across requests.
# Each provider is a plain FastAPI dependency, keeping the door open for
# future overrides (e.g. authenticated/tenant-scoped service instances)
# without changing endpoint signatures.
# =========================================================================


@lru_cache
def get_git_repository_manager() -> GitRepositoryManager:
    """Provide a shared GitRepositoryManager instance."""
    return GitRepositoryManager()


@lru_cache
def get_repository_parser() -> RepositoryParser:
    """Provide a shared RepositoryParser instance."""
    return RepositoryParser()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Provide a shared EmbeddingService instance."""
    return EmbeddingService()


@lru_cache
def get_vector_store_service() -> VectorStoreService:
    """Provide a shared VectorStoreService instance."""
    return VectorStoreService()


# =========================================================================
# Run ownership & liveness
#
# Indexing is concurrent: a retry, a reaper recovery, or a manual reindex can
# start a newer run for the same repository while an older run is still
# winding down (e.g. unblocking from a long git call). To keep these from
# corrupting each other, every run owns a repository row through a *run epoch*
# (``indexing_started_at``) and re-checks that ownership at every authoritative
# terminal write (failure and commit). A run that lost ownership backs off and
# leaves the newer run to drive the row. A per-run heartbeat thread keeps the
# row alive so the reaper can tell a live-but-slow run from a wedged/dead one.
# =========================================================================

HEARTBEAT_INTERVAL_SECONDS = 20


class _Heartbeat:
    """Bump ``indexing_heartbeat_at`` on a daemon thread while a run lives."""

    def __init__(
        self,
        repository_id: str,
        workspace_id: str | None,
        this_run_started_at: object | None,
    ) -> None:
        self._repository_id = repository_id
        self._workspace_id = workspace_id
        self._this_run_started_at = this_run_started_at
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="indexing-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS + 5)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(HEARTBEAT_INTERVAL_SECONDS)
            if self._stop.is_set():
                break
            try:
                if not _bump_heartbeat(self._repository_id, self._workspace_id, self._this_run_started_at):
                    # Run no longer owns the row (reaper/retry took over). Stop
                    # heartbeating so we never mask the replacement run's staleness.
                    logger.info("Heartbeat lost ownership repository_id=%s", self._repository_id)
                    break
            except Exception:  # noqa: BLE001 - liveness is best-effort
                logger.exception("Heartbeat update failed repository_id=%s", self._repository_id)


def _run_owns_row(
    db: Session,
    repository_id: str,
    workspace_id: str | None,
    this_run_started_at: object | None,
) -> bool:
    """True if the run identified by ``this_run_started_at`` still owns the row.

    Ownership means the row is still ``indexing`` and its ``indexing_started_at``
    epoch is unchanged. This is the single guard used by both the failure path
    and the commit path so a stale worker -- one recovered by the reaper, or a
    newer retry already running -- can never publish stale data, mark READY,
    mark a newer run FAILED, or overwrite a newer run's metadata.

    If the row does not exist (e.g. deleted), we return True so the failure path
    proceeds to attempt the terminal write (which will be a no-op or will create
    a new row, but won't overwrite a newer run because no row exists).
    """
    current = crud.get_repository(db, repository_id, workspace_id=workspace_id) if workspace_id else crud.get_repository(db, repository_id)
    if current is None:
        return True
    still_indexing = str(getattr(current, "indexing_status", "")) == schemas.RepositoryStatus.INDEXING.value
    same_run = this_run_started_at is None or getattr(current, "indexing_started_at", None) == this_run_started_at
    return still_indexing and same_run


def _bump_heartbeat(
    repository_id: str,
    workspace_id: str | None,
    this_run_started_at: object | None,
) -> bool:
    """Refresh ``indexing_heartbeat_at`` iff this run still owns the row.

    Opens its own session (the heartbeat runs on a separate thread), performs a
    guarded write, and returns whether the heartbeat should continue.
    """
    with db_session() as db:
        if not _run_owns_row(db, repository_id, workspace_id, this_run_started_at):
            return False
        repo = crud.get_repository(db, repository_id, workspace_id=workspace_id) if workspace_id else crud.get_repository(db, repository_id)
        if repo is None:
            return False
        repo.indexing_heartbeat_at = datetime.now(timezone.utc)
        db.commit()
        return True


def _discard_staged_indexing(
    vector_store_service: VectorStoreService | None,
    staged_collection: str | None,
    staged_clone: Path | None,
) -> None:
    """Best-effort removal of artifacts staged by a run that is backing off."""
    if vector_store_service is not None and staged_collection:
        try:
            vector_store_service.discard_staged_collection(staged_collection)
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.exception("Indexing rollback failed stage=vector_store_cleanup error=%s", cleanup_exc)
    if staged_clone is not None:
        try:
            import shutil
            shutil.rmtree(staged_clone, ignore_errors=True)
        except Exception:  # noqa: BLE001
            logger.exception("Indexing rollback failed stage=clone_cleanup")


# =========================================================================
# Indexing orchestration
#
# This function coordinates the full indexing pipeline. It is invoked
# from request handlers via BackgroundTasks and never called directly
# from a synchronous request path, so client requests return immediately
# with a PENDING status while indexing proceeds asynchronously.
# =========================================================================


def _run_indexing_pipeline(
    repository_id: str,
    clone_url: str,
    *,
    is_update: bool,
    db: Session,
    git_manager: GitRepositoryManager,
    parser: RepositoryParser,
    embedding_service: EmbeddingService,
    vector_store_service: VectorStoreService,
    workspace_id: str,
) -> None:
    """
    Execute the full repository indexing pipeline: clone/update, parse,
    embed, store vectors, and persist metadata. Repository status is
    updated at each stage so clients can poll progress.

    This function records failures because it is executed as a background
    task, but preserves the original exception in logs and removes partial
    index state so a failed repository remains safely retryable.
    """
    staged_collection: str | None = None
    staged_clone: Path | None = None
    # Run epoch: the repository's ``indexing_started_at`` that THIS run set on
    # its first INDEXING status write. It is compared against the row at both
    # failure time and commit time so a stale run can never overwrite the status
    # of a newer run (started_at is reset whenever a retry or the reaper flips
    # the row back to ``pending``).
    this_run_started_at: object | None = None
    heartbeat: _Heartbeat | None = None
    try:
        repository_numeric_id = int(repository_id)
        crud.update_repository_status(db, repository_id=repository_id, status=schemas.RepositoryStatus.INDEXING, workspace_id=workspace_id, indexing_stage="cloning", indexing_progress=5)
        this_run_started_at = _indexing_started_at(db, repository_id, workspace_id)
        heartbeat = _Heartbeat(repository_id, workspace_id, this_run_started_at)
        heartbeat.start()
        identity = git_manager.validate_repository_url(clone_url)
        if is_update:
            logger.info("Indexing stage started repository_id=%s stage=update", repository_id)
            metadata = git_manager.update_repository(clone_url)
            local_path = Path(metadata.local_path)
        else:
            live_path = git_manager.resolve_local_path(identity)
            staged_clone = live_path.parent / f".{live_path.name}.indexing-{uuid.uuid4().hex}"
            logger.info("Indexing stage started repository_id=%s stage=clone", repository_id)
            metadata = git_manager.clone_repository(clone_url, target_path=staged_clone)
            local_path = Path(metadata.local_path)
        logger.info("Indexing stage finished repository_id=%s stage=clone", repository_id)

        logger.info("Indexing stage started repository_id=%s stage=parse", repository_id)
        logger.info("Indexing stage started repository_id=%s stage=parsing", repository_id)
        crud.update_repository_status(db, repository_id=repository_id, status=schemas.RepositoryStatus.INDEXING, workspace_id=workspace_id, indexing_stage="parsing", indexing_progress=25)
        parse_result = parser.parse_repository(repository_numeric_id, local_path)

        logger.info("Indexing stage started repository_id=%s stage=graph", repository_id)
        graph_service = get_graph_service()
        graph = graph_service.build_staged_graph(parse_result)

        logger.info("Indexing stage started repository_id=%s stage=embedding", repository_id)
        crud.update_repository_status(db, repository_id=repository_id, status=schemas.RepositoryStatus.INDEXING, workspace_id=workspace_id, indexing_stage="embedding", indexing_progress=55)
        chunks = parse_result.chunks
        embeddings = embedding_service.generate_embeddings(chunks, repository_id=repository_id)
        embedding_items = list(getattr(embeddings, "embeddings", embeddings) or [])
        logger.info(
            "Embedding generation completed repository_id=%s chunks=%d embeddings=%d",
            repository_id,
            len(chunks),
            len(embedding_items),
        )

        logger.info("Indexing stage started repository_id=%s stage=metadata", repository_id)
        crud.update_repository_status(db, repository_id=repository_id, status=schemas.RepositoryStatus.INDEXING, workspace_id=workspace_id, indexing_stage="storing", indexing_progress=85)
        staged_collection = vector_store_service.stage_embeddings(
            repository_id, list(getattr(embeddings, "embeddings", embeddings) or []), workspace_id
        )

        # Ownership gate at commit time. This is the point of no return: publish,
        # graph publish, clone promotion, metadata write, and READY are all
        # authoritative and would overwrite a newer run if this run had been
        # superseded (reaper reset + a replacement run, or a retry with a fresh
        # epoch). A stale worker that was recovered must NOT publish its stale
        # data, mark READY, or overwrite the newer run's metadata. If ownership is
        # lost, discard only this run's staged artifacts and step aside.
        if not _run_owns_row(db, repository_id, workspace_id, this_run_started_at):
            logger.info(
                "Indexing run superseded; backing off repository_id=%s (commit skipped)",
                repository_id,
            )
            _discard_staged_indexing(vector_store_service, staged_collection, staged_clone)
            return

        logger.info("Indexing stage started repository_id=%s stage=commit", repository_id)
        vector_store_service.publish_staged_collection(repository_id, staged_collection, workspace_id)
        graph_service.publish_graph(graph)
        promoted_path = (
            local_path
            if is_update
            else git_manager.promote_repository_clone(identity, local_path)
        )
        crud.update_repository(
            db, repository_numeric_id, workspace_id=workspace_id, local_path=str(promoted_path),
            default_branch=metadata.default_branch or "main",
            current_commit_hash=metadata.current_commit_hash or None,
        )
        crud.replace_indexed_files(db, repository_id=repository_id, parsed_files=parse_result.files, workspace_id=workspace_id)
        crud.update_repository_status(
            db, repository_id=repository_id, status=schemas.RepositoryStatus.READY,
            total_files=len(parse_result.files), total_chunks=len(chunks),
            total_embeddings=len(embedding_items), workspace_id=workspace_id,
        )
        graph_stats = graph.statistics()
        logger.info(
            "Repository indexing committed repository_id=%s files=%d chunks=%d embeddings=%d nodes=%d edges=%d",
            repository_id, len(parse_result.files), len(chunks), len(embedding_items),
            graph_stats.total_nodes,
            graph_stats.total_edges,
        )

    except RepositoryOperationError as exc:
        _mark_indexing_failed(db, repository_id, "git", exc, vector_store_service, staged_collection, staged_clone, workspace_id, this_run_started_at=this_run_started_at)
    except RepositoryParseError as exc:
        _mark_indexing_failed(db, repository_id, "parser", exc, vector_store_service, staged_collection, staged_clone, workspace_id, this_run_started_at=this_run_started_at)
    except EmbeddingGenerationError as exc:
        _mark_indexing_failed(db, repository_id, "embedding", exc, vector_store_service, staged_collection, staged_clone, workspace_id, this_run_started_at=this_run_started_at)
    except VectorStoreError as exc:
        _mark_indexing_failed(db, repository_id, "vector_store", exc, vector_store_service, staged_collection, staged_clone, workspace_id, this_run_started_at=this_run_started_at)
    except Exception as exc:  # noqa: BLE001 - final safety net for a background task
        _mark_indexing_failed(db, repository_id, "unknown", exc, vector_store_service, staged_collection, staged_clone, workspace_id, this_run_started_at=this_run_started_at)
    finally:
        if heartbeat is not None:
            heartbeat.stop()


def _mark_indexing_failed(
    db: Session,
    repository_id: str,
    stage: str,
    exc: Exception,
    vector_store_service: VectorStoreService | None = None,
    staged_collection: str | None = None,
    staged_clone: Path | None = None,
    workspace_id: str | None = None,
    this_run_started_at: object | None = None,
) -> None:
    """Record failure and remove only artifacts from this indexing attempt.

    Two race guards keep a failed run from interrupting a retry:

    * ``release_indexing_job`` frees the queue's ``_active_ids`` slot *before*
      the terminal status is committed, so an immediate retry of the just-``FAILED``
      repository is actually enqueued instead of being silently dropped by the
      duplicate-job guard while the worker is still tearing down.
    * The terminal status write is guarded by a run-epoch comparison: it only
      applies when the row is still owned by *this* run (``indexing_status ==
      "indexing"`` and ``indexing_started_at`` unchanged). If a retry has already
      reset the row to ``pending`` or a newer run has started indexing it, the
      failed run backs off so it can never overwrite the newer run's status.
    """
    logger.exception("Indexing failed repository_id=%s stage=%s error=%s", repository_id, stage, exc)
    release_indexing_job(repository_id)
    _discard_staged_indexing(vector_store_service, staged_collection, staged_clone)
    if not _run_owns_row(db, repository_id, workspace_id, this_run_started_at):
        # A retry has already reset the row to ``pending``, or a newer run
        # has started indexing it. The failed run must not clobber that
        # newer state; the retry's own pipeline drives it onward.
        logger.info(
            "Skipping terminal failure status repository_id=%s stage=%s (newer run owns the row)",
            repository_id,
            stage,
        )
        return
    current = crud.get_repository(db, repository_id, workspace_id=workspace_id) if workspace_id else crud.get_repository(db, repository_id)
    had_usable_index = bool(current and (current.total_embeddings or current.total_chunks or current.total_files))
    failure_status = schemas.RepositoryStatus.INDEX_FAILED if had_usable_index else schemas.RepositoryStatus.FAILED_IMPORT
    crud.update_repository_status(
        db,
        repository_id=repository_id,
        status=failure_status,
        error_message=f"Indexing failed at stage '{stage}': {exc}",
        workspace_id=workspace_id,
    )


# =========================================================================
# Endpoints
# =========================================================================


@router.post(
    "",
    response_model=schemas.RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import a new repository",
    description=(
        "Registers a public GitHub repository and schedules indexing "
        "(clone, parse, embed, and store) as a background task. The "
        "repository is returned immediately with a PENDING status."
    ),
)
def import_repository(
    payload: schemas.RepositoryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    git_manager: GitRepositoryManager = Depends(get_git_repository_manager),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryResponse:
    """Register a repository for indexing and schedule the indexing pipeline."""
    identity = git_manager.validate_repository_url(str(payload.url))
    canonical_url = identity.canonical_url
    existing = crud.get_repository_by_url(db, repository_url=canonical_url, workspace_id=workspace_id)
    if existing is None and str(payload.url) != canonical_url:
        # Accept legacy rows created before URL canonicalization was added.
        existing = crud.get_repository_by_url(db, repository_url=str(payload.url), workspace_id=workspace_id)
    if existing is not None:
        retryable_statuses = {
            schemas.RepositoryStatus.FAILED.value,
            schemas.RepositoryStatus.INDEX_FAILED.value,
            schemas.RepositoryStatus.FAILED_IMPORT.value,
        }
        if existing.status not in retryable_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Repository already registered: {canonical_url}",
            )
        repository = crud.update_repository_status(
            db,
            repository_id=existing.id,
            status=schemas.RepositoryStatus.PENDING,
            total_files=existing.files_indexed,
            total_chunks=existing.chunks_generated,
            total_embeddings=existing.embeddings_generated,
            workspace_id=workspace_id,
        )
        if repository is None:
            raise HTTPException(status_code=404, detail=f"Repository not found: {existing.id}")
        logger.info("Retrying failed repository import repository_id=%s url=%s", repository.id, canonical_url)
    else:
        try:
            repository = crud.create_repository(db, repository_name=identity.full_name, repository_url=canonical_url, default_branch=payload.branch or "main", workspace_id=workspace_id)
        except IntegrityError as exc:
            existing = crud.get_repository_by_url(db, canonical_url, workspace_id=workspace_id)
            if existing is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Repository already registered: {canonical_url}") from exc
            raise

    logger.info("Repository import scheduled repository_id=%s url=%s", repository.id, canonical_url)

    queued = enqueue_indexing_job(repository.id, canonical_url, is_update=False, workspace_id=workspace_id)
    if not queued:
        repository = crud.update_repository_status(
            db, repository.id, schemas.RepositoryStatus.FAILED_IMPORT,
            workspace_id=workspace_id, indexing_stage="queue_full", indexing_progress=0,
            error_message="Indexing queue is full; retry this import shortly.",
        ) or repository

    return schemas.RepositoryResponse.model_validate(repository)


@router.get(
    "",
    response_model=schemas.RepositoryListResponse,
    summary="List repositories",
    description="Returns a paginated list of all registered repositories.",
)
def list_repositories(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryListResponse:
    """Return a paginated collection of registered repositories."""
    repositories = crud.list_repositories(db, skip=skip, limit=limit, workspace_id=workspace_id)
    total = crud.count_repositories(db, workspace_id=workspace_id)
    return schemas.RepositoryListResponse(
        items=[schemas.RepositoryResponse.model_validate(repo) for repo in repositories],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{repository_id}",
    response_model=schemas.RepositoryResponse,
    summary="Get repository details",
    description="Returns full details for a single registered repository.",
)
def get_repository(
    repository_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryResponse:
    """Retrieve a single repository by identifier."""
    repository = _get_repository_or_404(db, repository_id, workspace_id)
    return schemas.RepositoryResponse.model_validate(repository)


@router.get(
    "/{repository_id}/status",
    response_model=schemas.RepositoryStatusResponse,
    summary="Get repository indexing status",
    description="Returns the current indexing status and progress metadata for a repository.",
)
def get_repository_status(
    repository_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryStatusResponse:
    """Retrieve the current indexing status for a repository."""
    repository = _get_repository_or_404(db, repository_id, workspace_id)
    return schemas.RepositoryStatusResponse.model_validate(repository)


@router.post(
    "/{repository_id}/reindex",
    response_model=schemas.RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-index a repository",
    description=(
        "Re-runs the full indexing pipeline against the repository's "
        "current cloned state without pulling new commits."
    ),
)
def reindex_repository(
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    git_manager: GitRepositoryManager = Depends(get_git_repository_manager),
    parser: RepositoryParser = Depends(get_repository_parser),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store_service: VectorStoreService = Depends(get_vector_store_service),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryResponse:
    """Schedule a full re-index of an already registered repository."""
    repository = _get_repository_or_404(db, repository_id, workspace_id)
    crud.update_repository_status(
        db, repository_id=repository_id, status=schemas.RepositoryStatus.INDEXING, workspace_id=workspace_id
    )
    logger.info("Repository reindex requested repository_id=%s", repository_id)

    if not enqueue_indexing_job(repository_id, repository.url, is_update=False, workspace_id=workspace_id):
        crud.update_repository_status(db, repository_id, schemas.RepositoryStatus.INDEX_FAILED, workspace_id=workspace_id, indexing_stage="queue_full", error_message="Indexing queue is full; retry shortly.")

    return schemas.RepositoryResponse.model_validate(repository)


@router.post(
    "/{repository_id}/update",
    response_model=schemas.RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pull latest changes and re-index",
    description=(
        "Pulls the latest commits for the repository and re-runs the "
        "full indexing pipeline against the updated source."
    ),
)
def update_repository(
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    git_manager: GitRepositoryManager = Depends(get_git_repository_manager),
    parser: RepositoryParser = Depends(get_repository_parser),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store_service: VectorStoreService = Depends(get_vector_store_service),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryResponse:
    """Schedule a git pull followed by a full re-index of the repository."""
    repository = _get_repository_or_404(db, repository_id, workspace_id)
    crud.update_repository_status(
        db, repository_id=repository_id, status=schemas.RepositoryStatus.INDEXING, workspace_id=workspace_id
    )
    logger.info("Repository update requested repository_id=%s", repository_id)

    if not enqueue_indexing_job(repository_id, repository.url, is_update=True, workspace_id=workspace_id):
        crud.update_repository_status(db, repository_id, schemas.RepositoryStatus.INDEX_FAILED, workspace_id=workspace_id, indexing_stage="queue_full", error_message="Indexing queue is full; retry shortly.")

    return schemas.RepositoryResponse.model_validate(repository)


@router.delete(
    "/{repository_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a repository",
    description=(
        "Removes a repository's metadata, indexed vectors, and local "
        "clone. This operation cannot be undone."
    ),
)
def delete_repository(
    repository_id: str,
    db: Session = Depends(get_db),
    git_manager: GitRepositoryManager = Depends(get_git_repository_manager),
    vector_store_service: VectorStoreService = Depends(get_vector_store_service),
    workspace_id: str = Depends(get_workspace_id),
) -> None:
    """Delete a repository and all associated indexed data."""
    repository = _get_repository_or_404(db, repository_id, workspace_id)
    repository_numeric_id = int(repository.id)
    crud.update_repository_status(db, repository_id=repository_numeric_id, status=schemas.RepositoryStatus.DELETING, workspace_id=workspace_id)

    try:
        identity = git_manager.validate_repository_url(repository.url)
        git_manager.delete_repository(identity)
    except RepositoryOperationError as exc:
        logger.exception("Local clone cleanup failed repository_id=%s", repository_id)
        raise HTTPException(status_code=502, detail="Failed to remove repository clone. Please retry.") from exc

    try:
        vector_store_service.delete_repository_embeddings(repository_id, workspace_id)
    except VectorStoreError as exc:
        logger.exception("Vector store deletion failed repository_id=%s", repository_id)
        raise HTTPException(status_code=502, detail="Failed to remove repository vectors. Please retry.") from exc

    get_graph_service().delete_persisted_graph(repository_id)

    crud.delete_repository(db, repository_id=repository_numeric_id)
    logger.info("Repository deleted repository_id=%s", repository_id)


@router.get(
    "/health/check",
    response_model=schemas.RepositoryHealthResponse,
    summary="Repository subsystem health check",
    description="Returns aggregate counts of repositories by indexing status.",
)
def repository_health_check(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryHealthResponse:
    """Return aggregate repository counts grouped by indexing status."""
    return schemas.RepositoryHealthResponse(
        total_repositories=crud.count_repositories(db, workspace_id=workspace_id),
        indexed=crud.count_repositories_by_status(db, status=schemas.RepositoryStatus.READY.value, workspace_id=workspace_id),
        failed=crud.count_repositories_by_status(db, status=schemas.RepositoryStatus.INDEX_FAILED.value, workspace_id=workspace_id),
        pending=crud.count_repositories_by_status(db, status=schemas.RepositoryStatus.INDEXING.value, workspace_id=workspace_id)
        + crud.count_repositories_by_status(db, status=schemas.RepositoryStatus.PENDING.value, workspace_id=workspace_id),
    )

@router.get(
    "/{repository_id}/files",
    response_model=schemas.RepositoryFilesResponse,
    summary="List repository files",
)
def list_repository_files(
    repository_id: int,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryFilesResponse:
    """
    Return all indexed files belonging to a repository.
    """
    repository = crud.get_repository(db, repository_id=repository_id, workspace_id=workspace_id)

    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repository_id}",
        )

    files = crud.list_repository_files(db, repository_id, workspace_id=workspace_id)

    return schemas.RepositoryFilesResponse(
        files=[
            schemas.RepositoryFileResponse(
                id=file.id,
                relative_path=file.relative_path,
                language=_language_value(file.programming_language),
                file_size_bytes=file.file_size,
                checksum_sha256=file.checksum,
                chunks_generated=file.chunk_count,
            )
            for file in files
        ]
    )


@router.get(
    "/{repository_id}/files/content",
    response_model=schemas.RepositoryFileContentResponse,
    summary="Get file content",
    description="Returns the content of a specific file in the repository.",
)
def get_repository_file_content(
    repository_id: int,
    path: str = Query(..., description="Relative path to the file within the repository."),
    db: Session = Depends(get_db),
    git_manager: GitRepositoryManager = Depends(get_git_repository_manager),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.RepositoryFileContentResponse:
    """
    Return the content of a specific file from a cloned repository.
    """
    repository = crud.get_repository(db, repository_id=repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repository_id}",
        )

    if not repository.local_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository has not been cloned yet.",
        )

    from pathlib import Path
    local_path = Path(repository.local_path)
    file_path = local_path / path

    # Security: ensure the path doesn't escape the repository root
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(local_path.resolve())):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: path outside repository root.",
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file path: {path}",
        ) from exc

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a file: {path}",
        )

    # Check if file is binary
    try:
        with open(file_path, "rb") as f:
            content_bytes = f.read()
            # Try to decode as UTF-8, if it fails it's likely binary
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Cannot preview binary file: {path}",
                )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read file: {exc}",
        ) from exc

    # Detect language from extension
    extension_to_language: dict[str, str] = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".r": "r",
        ".sql": "sql",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".xml": "xml",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".less": "less",
        ".md": "markdown",
        ".vue": "vue",
        ".svelte": "svelte",
    }
    extension = file_path.suffix.lower()
    language = extension_to_language.get(extension, "plaintext")

    return schemas.RepositoryFileContentResponse(
        path=path,
        content=content,
        language=language,
        size_bytes=len(content_bytes),
    )

# =========================================================================
# Helpers
# =========================================================================


def _indexing_started_at(db: Session, repository_id: str, workspace_id: str | None) -> object | None:
    """Return the repository's current ``indexing_started_at`` value (run epoch)."""
    repo = crud.get_repository(db, repository_id, workspace_id=workspace_id)
    return getattr(repo, "indexing_started_at", None) if repo is not None else None


def _language_value(language: object) -> str:
    """Normalize enum instances and legacy enum-repr database values."""
    value = getattr(language, "value", language)
    text = str(value)
    return text.rsplit(".", 1)[-1].lower()


def _get_repository_or_404(db: Session, repository_id: str, workspace_id: str | None = None) -> Repository:
    """Fetch a repository by identifier or raise a 404 HTTPException."""
    repository = crud.get_repository(db, repository_id=repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repository_id}",
        )
    return repository
