"""Small, bounded in-process indexing queue.

The database is the durable source of truth.  The queue only provides a
bounded executor for the current web process; pending jobs are recovered on
startup, so a Render restart does not lose an import.
"""

from __future__ import annotations

from dataclasses import dataclass
from queue import Full, Queue
from threading import Lock, Thread

from app.db.database import db_session
from app.utils.logger import get_logger

logger = get_logger(__name__)

# How often the reaper wakes up to look for stale indexing jobs.
REAP_INTERVAL_SECONDS = 60
# A job is stale if it has been in ``indexing`` for this long without a fresh
# heartbeat. Must be strictly greater than HEARTBEAT_INTERVAL_SECONDS so a
# live run (bumping every HEARTBEAT_INTERVAL_SECONDS) is never reaped.
STALE_AFTER_SECONDS = 120

# Render Free provides 512 MB RAM. A repository indexing run retains its
# parsed chunks, graph, and embedding metadata in memory, so concurrent runs
# can exceed the process limit even though each individual run is bounded.
_MAX_WORKERS = 1
_MAX_QUEUED_JOBS = 32


@dataclass(frozen=True)
class IndexingJob:
    repository_id: str
    clone_url: str
    is_update: bool
    workspace_id: str


_jobs: Queue[IndexingJob] = Queue(maxsize=_MAX_QUEUED_JOBS)
_started = False
_active_ids: set[str] = set()
_active_lock = Lock()


def _worker() -> None:
    while True:
        job = _jobs.get()
        try:
            # Imports are intentionally lazy: routes_repo imports this module.
            from app.api.routes_repo import _run_indexing_pipeline, get_embedding_service, get_git_repository_manager, get_repository_parser, get_vector_store_service

            with db_session() as db:
                _run_indexing_pipeline(
                    repository_id=job.repository_id,
                    clone_url=job.clone_url,
                    is_update=job.is_update,
                    db=db,
                    git_manager=get_git_repository_manager(),
                    parser=get_repository_parser(),
                    embedding_service=get_embedding_service(),
                    vector_store_service=get_vector_store_service(),
                    workspace_id=job.workspace_id,
                )
        except Exception:  # the pipeline records domain failures itself
            logger.exception("Indexing worker crashed repository_id=%s", job.repository_id)
            try:
                from app.db import crud
                from app.models import schemas
                with db_session() as failure_db:
                    crud.update_repository_status(
                        failure_db,
                        job.repository_id,
                        schemas.RepositoryStatus.FAILED_IMPORT,
                        workspace_id=job.workspace_id,
                        indexing_stage="worker_error",
                        error_message="Indexing worker stopped unexpectedly; retry this import.",
                    )
            except Exception:
                logger.exception("Could not persist worker failure repository_id=%s", job.repository_id)
        finally:
            with _active_lock:
                _active_ids.discard(job.repository_id)
            _jobs.task_done()


def start_workers() -> None:
    global _started
    if _started:
        return
    _started = True
    for index in range(_MAX_WORKERS):
        Thread(target=_worker, name=f"codeatlas-indexer-{index}", daemon=True).start()
    _start_reaper()
    logger.info("Indexing workers started workers=%d queue_capacity=%d", _MAX_WORKERS, _MAX_QUEUED_JOBS)


_reaper_started = False
_reaper_lock = Lock()


def _start_reaper() -> None:
    """Start the single stale-job reaper daemon thread (idempotent)."""
    global _reaper_started
    with _reaper_lock:
        if _reaper_started:
            return
        _reaper_started = True
    Thread(target=_reaper_loop, name="codeatlas-indexing-reaper", daemon=True).start()
    logger.info(
        "Indexing stale-job reaper started interval=%ss stale_after=%ss",
        REAP_INTERVAL_SECONDS,
        STALE_AFTER_SECONDS,
    )


def _reaper_loop() -> None:
    while True:
        try:
            reap_stale_jobs()
        except Exception:  # noqa: BLE001 - a reaper pass must never kill the thread
            logger.exception("Indexing reaper pass failed")
        try:
            import time
            time.sleep(REAP_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.exception("Indexing reaper sleep interrupted")


def enqueue_indexing_job(repository_id: str | int, clone_url: str, *, is_update: bool, workspace_id: str) -> bool:
    start_workers()
    repository_key = str(repository_id)
    with _active_lock:
        if repository_key in _active_ids:
            return True
        _active_ids.add(repository_key)
    try:
        _jobs.put_nowait(IndexingJob(repository_key, clone_url, is_update, workspace_id))
        return True
    except Full:
        with _active_lock:
            _active_ids.discard(repository_key)
        logger.error("Indexing queue is full repository_id=%s", repository_id)
        return False


def release_indexing_job(repository_id: str | int) -> None:
    """Free the active-slot marker for ``repository_id`` if it is held.

    Idempotent (no-op when the repository has no active marker). The indexing
    pipeline calls this on the *failure* path before committing the terminal
    status so a retry issued against the just-failed repository is never
    silently dropped by the ``_active_ids`` dedup guard while the worker is
    still tearing down. The worker also discards the marker in its ``finally``,
    so releasing here is safe and redundant for the success path.
    """
    with _active_lock:
        _active_ids.discard(str(repository_id))


def queued_job_count() -> int:
    return _jobs.qsize()


def recover_indexing_jobs() -> int:
    """Requeue durable pending jobs and reset jobs interrupted by a restart.

    Recovery runs only during application startup, when this process's
    worker threads are brand new. Any repository still marked "pending" or
    "indexing" is therefore orphaned: the worker thread that owned it
    belonged to the previous process, which is gone. It must be re-enqueued
    or it stays stuck in "indexing" forever -- the UI would show an
    import that never completes and never fails.

    A heartbeat guard would be wrong here. A fresh heartbeat only proves
    the previous process was alive recently; it does not make that
    process's threads any more likely to still be running after a
    restart/deploy. (If the deployment ever runs more than one app
    instance, re-enqueuing a job another instance is actively processing
    is safe by construction: every generation writes to a uniquely named
    staged collection and publish is atomic, so the last publisher wins.)
    """
    from sqlalchemy import select
    from app.models.db_models import Repository

    recovered = 0
    with db_session() as db:
        rows = db.execute(select(Repository).where(Repository.indexing_status.in_(["pending", "indexing"]))).scalars().all()
        for repository in rows:
            if repository.indexing_status == "indexing":
                repository.indexing_status = "pending"
                repository.indexing_stage = "queued"
                repository.indexing_progress = min(repository.indexing_progress, 5)
                # Losing run ownership: reset the epoch so the requeued replacement
                # run establishes a distinct ``indexing_started_at``. Any still-alive
                # worker from a previous generation then fails the ownership guard.
                repository.indexing_started_at = None
                repository.indexing_heartbeat_at = None
            db.commit()
            if repository.workspace_id and enqueue_indexing_job(repository.id, repository.url, is_update=False, workspace_id=repository.workspace_id):
                recovered += 1
    logger.info("Recovered durable indexing jobs count=%d", recovered)
    return recovered


def reap_stale_jobs() -> int:
    """Recover jobs stuck in ``indexing`` whose worker is wedged or dead.

    Unlike startup recovery, this runs continuously. A repository is presumed
    stale when it has been ``indexing`` for longer than ``STALE_AFTER_SECONDS``
    without a fresh ``indexing_heartbeat_at`` (the live run's daemon thread
    refreshes it every ``HEARTBEAT_INTERVAL_SECONDS``).

    Recovery is race-safe with respect to a worker that merely *resumed*: the
    reaper clears ``indexing_started_at`` (loss of run ownership) *before* it
    releases the queue slot and requeues. A stale worker that later returns
    therefore fails the pipeline's ownership guard on every authoritative write
    (failure, publish, promote, READY, metadata) and backs off, so it can never
    publish stale data, mark the repository READY, mark a newer run failed, or
    overwrite a newer run's metadata -- only the replacement run commits.
    """
    from sqlalchemy import select
    from datetime import datetime, timedelta, timezone
    from app.models.db_models import Repository

    threshold = datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS)
    reaped = 0
    with db_session() as db:
        rows = db.execute(
            select(Repository).where(
                Repository.indexing_status == "indexing",
                (Repository.indexing_heartbeat_at.is_(None))
                | (Repository.indexing_heartbeat_at < threshold),
            )
        ).scalars().all()
        for repository in rows:
            logger.warning("Reaping stale indexing job repository_id=%s", repository.id)
            repository.indexing_status = "pending"
            repository.indexing_stage = "queued"
            repository.indexing_progress = min(repository.indexing_progress, 5)
            # Lose ownership BEFORE releasing the slot / requeueing, so a resumed
            # stale worker can never be mistaken for the replacement run.
            repository.indexing_started_at = None
            repository.indexing_heartbeat_at = None
            db.commit()
            release_indexing_job(repository.id)
            if repository.workspace_id and enqueue_indexing_job(repository.id, repository.url, is_update=False, workspace_id=repository.workspace_id):
                reaped += 1
    if reaped:
        logger.info("Reaped stale indexing jobs count=%d", reaped)
    return reaped
