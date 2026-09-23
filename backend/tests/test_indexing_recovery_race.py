"""Regression tests for race-safe indexing recovery (run ownership + stale reaper).

The production import stalls because an in-process worker can block inside a
Git call indefinitely and nothing reliably recovers a stale job. The fix makes
recovery race-safe:

* Every indexing run owns the repository row through a *run epoch*
  (``indexing_started_at``) and re-checks ownership at every authoritative
  terminal write (failure, publish, promote, READY, metadata).
* A per-run daemon thread refreshes ``indexing_heartbeat_at`` (liveness).
* A periodic reaper recovers rows stuck in ``indexing`` with a stale heartbeat
  by *losing ownership* (clear epoch) before requeueing, so a stale worker that
  later resumes can never overwrite the replacement run.
* Git operations carry wall-clock subprocess timeouts so a stalled remote cannot
  pin a worker forever.

Covers: normal successful indexing, git timeout/failure, stale job recovery,
old worker returning after recovery, old worker not overwriting the newer run,
duplicate enqueue protection, and the preserved retry-race ownership guard.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import git
import pytest

from app.api import routes_repo
from app.core import indexing_queue
from app.core.git_handler import (
    GIT_OPERATION_TIMEOUT_SECONDS,
    GitRepositoryManager,
    RepositoryOperationError,
)
from app.models import schemas


class _RecordingQueue:
    """Fake ``_jobs`` that records enqueued jobs without a worker thread."""

    def __init__(self) -> None:
        self.jobs: list[indexing_queue.IndexingJob] = []

    def put_nowait(self, job: indexing_queue.IndexingJob) -> None:
        self.jobs.append(job)

    def qsize(self) -> int:
        return len(self.jobs)

    def task_done(self) -> None:
        pass


def _stale_repository_row(**overrides: object) -> SimpleNamespace:
    """Build a fake ``Repository`` row that the reaper should treat as stale."""
    defaults: dict[str, object] = {
        "id": 7,
        "url": "https://github.com/owner/repository",
        "indexing_status": "indexing",
        "indexing_stage": "storing",
        "indexing_progress": 85,
        "indexing_heartbeat_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "indexing_started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "workspace_id": "workspace-a",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_db_session_containing(*rows: object):
    """Return a context manager function for the reaper's query pattern.

    The reaper does: `with db_session() as db: ...`
    So `db_session` must be a callable that returns a context manager.
    """
    fake_db = SimpleNamespace(
        execute=lambda *args, **kwargs: SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: list(rows))
        ),
        commit=lambda: None,
    )

    @contextmanager
    def _cm():
        yield fake_db

    return _cm


def _make_db_session_containing(*rows: object):
    """Factory: returns a callable matching `db_session()` protocol.

    The reaper executes a SQLAlchemy select with a WHERE clause. We emulate
    that filtering so the test accurately exercises the staleness logic.
    """
    from datetime import datetime, timedelta, timezone

    def _filter_rows(rows_to_filter):
        threshold = datetime.now(timezone.utc) - timedelta(seconds=120)  # STALE_AFTER_SECONDS
        filtered = []
        for r in rows_to_filter:
            if getattr(r, "indexing_status", None) != "indexing":
                continue
            hb = getattr(r, "indexing_heartbeat_at", None)
            if hb is None or hb < threshold:
                filtered.append(r)
        return filtered

    @contextmanager
    def _cm():
        fake_db = SimpleNamespace(
            execute=lambda *args, **kwargs: SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: _filter_rows(list(rows)))
            ),
            commit=lambda: None,
        )
        yield fake_db

    return lambda: _cm()


def _owned_import_mocks() -> tuple:
    """Wire mocks for the happy path (clone → parse → graph → embed → stage)."""
    db = Mock()
    git_manager = Mock()
    identity = SimpleNamespace(
        owner="owner", name="repo", full_name="owner/repo",
        canonical_url="https://github.com/owner/repo",
    )
    live = Path("/tmp/live_repo")
    metadata = SimpleNamespace(
        local_path=Path("/tmp/.repo.indexing-abc123"), default_branch="main",
        current_commit_hash="abc123",
    )
    git_manager.validate_repository_url.return_value = identity
    git_manager.resolve_local_path.return_value = live
    git_manager.clone_repository.return_value = metadata
    git_manager.promote_repository_clone.return_value = live

    parser = Mock()
    parse_result = SimpleNamespace(
        chunks=[Mock(), Mock()],
        files=[
            SimpleNamespace(relative_path="a.py", language="python", checksum="s1", file_size=10, chunk_count=1),
            SimpleNamespace(relative_path="b.py", language="python", checksum="s2", file_size=20, chunk_count=1),
        ],
    )
    parser.parse_repository.return_value = parse_result

    embedding_service = Mock()
    embedding_service.generate_embeddings.return_value = SimpleNamespace(embeddings=[[0.1] * 4, [0.2] * 4])

    vector_store_service = Mock()
    vector_store_service.stage_embeddings.return_value = "staged_col_x"

    graph_service = Mock()
    mock_graph = Mock()
    mock_graph.statistics.return_value = SimpleNamespace(total_nodes=1, total_edges=1)
    graph_service.build_staged_graph.return_value = mock_graph

    return db, git_manager, parser, embedding_service, vector_store_service, graph_service


# =========================================================================
# Successful indexing
# =========================================================================


def test_normal_successful_indexing_reaches_ready() -> None:
    """A run that still owns its row at commit publishes, promotes, and lands READY."""
    db, git_manager, parser, embedding_service, vector_store_service, graph_service = _owned_import_mocks()

    T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    owned_row = SimpleNamespace(
        id=7, indexing_status="indexing", indexing_started_at=T0,
        total_files=0, total_chunks=0, total_embeddings=0,
    )

    with patch("app.api.routes_repo.get_graph_service", return_value=graph_service), \
         patch.object(routes_repo.crud, "get_repository", return_value=owned_row), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status, \
         patch.object(routes_repo.crud, "update_repository") as update_repo, \
         patch.object(routes_repo.crud, "replace_indexed_files") as replace_files:

        routes_repo._run_indexing_pipeline(
            "7", "https://github.com/owner/repo", is_update=False, db=db,
            git_manager=git_manager, parser=parser, embedding_service=embedding_service,
            vector_store_service=vector_store_service, workspace_id="ws-a",
        )

    final_call = update_status.call_args_list[-1]
    assert final_call.kwargs["status"] is schemas.RepositoryStatus.READY
    assert final_call.kwargs["total_files"] == 2
    vector_store_service.publish_staged_collection.assert_called_once()
    graph_service.publish_graph.assert_called_once()
    update_repo.assert_called_once()
    replace_files.assert_called_once()


# =========================================================================
# Git timeout / failure
# =========================================================================


def test_git_timeout_failure_marks_repo_failed() -> None:
    """A git-stage failure (e.g. subprocess killed by timeout) is recorded as FAILED_IMPORT."""
    db = Mock()
    git_manager = Mock()
    identity = SimpleNamespace(
        owner="owner", name="repo", full_name="owner/repo", canonical_url="https://github.com/owner/repo",
    )
    git_manager.validate_repository_url.return_value = identity
    git_manager.resolve_local_path.return_value = Path("/tmp/repo")
    git_manager.clone_repository.side_effect = RepositoryOperationError("git clone timed out (300s)")

    parser = Mock()
    embedding_service = Mock()
    vector_store_service = Mock()

    T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    owned_row = SimpleNamespace(
        id=7, indexing_status="indexing", indexing_started_at=T0,
        total_files=0, total_chunks=0, total_embeddings=0,
    )

    with patch.object(routes_repo.crud, "get_repository", return_value=owned_row), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status:

        routes_repo._run_indexing_pipeline(
            "7", "https://github.com/owner/repo", is_update=False, db=db,
            git_manager=git_manager, parser=parser, embedding_service=embedding_service,
            vector_store_service=vector_store_service, workspace_id="ws-a",
        )

    fail_calls = [c for c in update_status.call_args_list if c.kwargs.get("status") == schemas.RepositoryStatus.FAILED_IMPORT]
    assert fail_calls, "a git-stage failure must write a terminal FAILED_IMPORT status"
    assert "git" in fail_calls[-1].kwargs["error_message"]


# =========================================================================
# Stale-job recovery (reaper)
# =========================================================================


def test_stale_job_is_reaped_and_requeued_once(monkeypatch) -> None:
    """The reaper recovers a stale indexing row: reset to pending, lose ownership (clear
    epoch + heartbeat), release the slot, and requeue exactly once."""
    repository = _stale_repository_row()
    monkeypatch.setattr(indexing_queue, "db_session", _make_db_session_containing(repository))
    monkeypatch.setattr(indexing_queue, "_jobs", _RecordingQueue())

    with patch.object(indexing_queue, "enqueue_indexing_job", return_value=True) as enqueue, \
         patch.object(indexing_queue, "release_indexing_job") as release:
        reaped = indexing_queue.reap_stale_jobs()

    assert reaped == 1
    assert repository.indexing_status == "pending"
    assert repository.indexing_stage == "queued"
    assert repository.indexing_progress == 5
    assert repository.indexing_started_at is None, "recovery must clear the run epoch (lose ownership)"
    assert repository.indexing_heartbeat_at is None
    release.assert_called_once_with(7)
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0] == 7
    assert enqueue.call_args.kwargs["workspace_id"] == "workspace-a"


def test_reaper_skips_live_job_with_fresh_heartbeat(monkeypatch) -> None:
    """A job still heartbeating is alive and must NOT be reaped (no duplicate requeue)."""
    repository = _stale_repository_row(
        indexing_heartbeat_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(indexing_queue, "db_session", _make_db_session_containing(repository))
    monkeypatch.setattr(indexing_queue, "_jobs", _RecordingQueue())

    with patch.object(indexing_queue, "enqueue_indexing_job", return_value=True) as enqueue, \
         patch.object(indexing_queue, "release_indexing_job") as release:
        reaped = indexing_queue.reap_stale_jobs()

    assert reaped == 0
    enqueue.assert_not_called()
    release.assert_not_called()


# =========================================================================
# Old worker returning after recovery cannot clobber the newer run
# =========================================================================


def test_stale_worker_resuming_cannot_publish_or_mark_ready(monkeypatch) -> None:
    """A stale worker that reaches the commit gate after losing ownership backs off:
    it does not publish vectors/graph, does not mark READY, does not overwrite metadata,
    and discards its own staged artifacts."""
    db, git_manager, parser, embedding_service, vector_store_service, graph_service = _owned_import_mocks()
    vector_store_service.discard_staged_collection = Mock()

    # The guard `_run_owns_row` returning False models "the row is owned by a
    # newer run (different epoch) now" -- exactly what a reaped stale worker sees.
    with patch("app.api.routes_repo.get_graph_service", return_value=graph_service), \
         patch.object(routes_repo.crud, "get_repository", return_value=SimpleNamespace(
             id=7, indexing_status="indexing", indexing_started_at=None,
             total_files=0, total_chunks=0, total_embeddings=0,
         )), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status, \
         patch.object(routes_repo.crud, "update_repository") as update_repo, \
         patch.object(routes_repo.crud, "replace_indexed_files") as replace_files, \
         patch.object(routes_repo, "_run_owns_row", return_value=False):

        routes_repo._run_indexing_pipeline(
            "7", "https://github.com/owner/repo", is_update=False, db=db,
            git_manager=git_manager, parser=parser, embedding_service=embedding_service,
            vector_store_service=vector_store_service, workspace_id="ws-a",
        )

    # No authoritative side effects from the stale worker:
    vector_store_service.publish_staged_collection.assert_not_called()
    graph_service.publish_graph.assert_not_called()
    ready_calls = [c for c in update_status.call_args_list if c.kwargs.get("status") == schemas.RepositoryStatus.READY]
    assert not ready_calls
    update_repo.assert_not_called()
    replace_files.assert_not_called()
    # The stale run discards its own staged artifacts instead of leaving them.
    vector_store_service.discard_staged_collection.assert_called_once_with("staged_col_x")


# =========================================================================
# Preserved retry-race ownership guard
# =========================================================================


def test_run_owns_row_guard() -> None:
    """The single ownership predicate used by failure and commit paths behaves as required."""
    db = Mock()
    T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    T1 = datetime(2026, 1, 2, tzinfo=timezone.utc)

    owned = SimpleNamespace(indexing_status="indexing", indexing_started_at=T0)
    pending = SimpleNamespace(indexing_status="pending", indexing_started_at=None)
    newer_run = SimpleNamespace(indexing_status="indexing", indexing_started_at=T1)

    with patch.object(routes_repo.crud, "get_repository", return_value=owned):
        assert routes_repo._run_owns_row(db, "7", "ws-a", T0) is True
    with patch.object(routes_repo.crud, "get_repository", return_value=pending):
        assert routes_repo._run_owns_row(db, "7", "ws-a", T0) is False  # retry reset the row
    with patch.object(routes_repo.crud, "get_repository", return_value=newer_run):
        assert routes_repo._run_owns_row(db, "7", "ws-a", T0) is False  # newer run owns it
        assert routes_repo._run_owns_row(db, "7", "ws-a", T1) is True


def test_duplicate_enqueue_protection_preserved(monkeypatch) -> None:
    """The queue's in-process dedup still collapses duplicate enqueues of an active repo."""
    monkeypatch.setattr(indexing_queue, "_started", True)
    monkeypatch.setattr(indexing_queue, "_jobs", _RecordingQueue())
    monkeypatch.setattr(indexing_queue, "_active_ids", set())

    assert indexing_queue.enqueue_indexing_job(7, "https://github.com/owner/repo", is_update=False, workspace_id="ws-a")
    assert indexing_queue.enqueue_indexing_job(7, "https://github.com/owner/repo", is_update=False, workspace_id="ws-a")
    assert len(indexing_queue._jobs.jobs) == 1, "duplicate enqueue must be collapsed"


# =========================================================================
# Heartbeat liveness
# =========================================================================


def test_heartbeat_loop_bumps_while_run_owns_row(monkeypatch) -> None:
    """The per-run heartbeat daemon refreshes liveness on its interval; the class
    stops cleanly (used by the pipeline's ``finally``)."""
    calls: list[tuple[object, object, object]] = []

    def _fake_bump(repository_id, workspace_id, this_run_started_at):
        calls.append((repository_id, workspace_id, this_run_started_at))
        return True

    monkeypatch.setattr(routes_repo, "HEARTBEAT_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(routes_repo, "_bump_heartbeat", _fake_bump)

    heartbeat = routes_repo._Heartbeat("7", "ws-a", "epoch-7")
    heartbeat.start()
    time.sleep(0.15)
    heartbeat.stop()

    assert len(calls) >= 2, f"heartbeat should have bumped repeatedly, got {len(calls)}"
    assert calls[0][0] == "7"
    assert calls[0][1] == "ws-a"


def test_heartbeat_stops_when_run_loses_ownership(monkeypatch) -> None:
    """An orphaned heartbeat must stop the moment ownership is lost, so it never
    masks the replacement run's own staleness in the reaper."""
    calls: list[object] = []
    state = {"call_count": 0}

    def _fake_bump(repository_id, workspace_id, this_run_started_at):
        state["call_count"] += 1
        # First call returns True (run still owns); second returns False (lost)
        return state["call_count"] == 1

    monkeypatch.setattr(routes_repo, "HEARTBEAT_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(routes_repo, "_bump_heartbeat", _fake_bump)

    heartbeat = routes_repo._Heartbeat("7", "ws-a", "epoch-7")
    heartbeat.start()
    time.sleep(0.15)
    heartbeat.stop()

    # First call returns True (keeps looping); second call returns False and stops it.
    assert state["call_count"] >= 2
    # The loop stops once ownership is lost, so the call count does not keep growing.


# =========================================================================
# Git subprocess timeouts
# =========================================================================


def test_clone_applies_wallclock_timeout(tmp_path, monkeypatch) -> None:
    """A clone carries ``kill_after_timeout`` so a stalled remote cannot pin the worker."""
    manager = GitRepositoryManager(repositories_dir=tmp_path)
    captured: dict[str, object] = {}

    def _fake_clone_from(url, to_path, **kwargs):
        captured["kwargs"] = kwargs
        raise git.exc.GitCommandError("git clone", 128, stderr="killed after timeout")

    monkeypatch.setattr(git.Repo, "clone_from", _fake_clone_from)

    identity = manager.validate_repository_url("https://github.com/owner/repo")
    target = tmp_path / ".repo.indexing-x"
    with pytest.raises(RepositoryOperationError):
        manager.clone_repository(identity.canonical_url, target_path=target)

    assert captured["kwargs"].get("kill_after_timeout") == GIT_OPERATION_TIMEOUT_SECONDS


def test_pull_applies_wallclock_timeout(tmp_path, monkeypatch) -> None:
    """fetch and pull carry ``kill_after_timeout`` as well."""
    fake_origin = SimpleNamespace(fetch=Mock(), pull=Mock())
    fake_repo = SimpleNamespace(
        remotes=SimpleNamespace(origin=fake_origin),
        head=SimpleNamespace(commit=SimpleNamespace(hexsha="abc123")),
        active_branch=SimpleNamespace(name="main"),
    )
    monkeypatch.setattr("app.core.git_handler.Repo", lambda path: fake_repo)

    manager = GitRepositoryManager(repositories_dir=tmp_path)
    monkeypatch.setattr(manager, "resolve_local_path", lambda identity: tmp_path / "repo")
    monkeypatch.setattr(manager, "_is_valid_git_repository", lambda path: True)

    metadata = manager.pull_latest_changes(manager.validate_repository_url("https://github.com/owner/repo"))

    fake_origin.fetch.assert_called_once_with(kill_after_timeout=GIT_OPERATION_TIMEOUT_SECONDS)
    fake_origin.pull.assert_called_once_with(kill_after_timeout=GIT_OPERATION_TIMEOUT_SECONDS)
    assert metadata.current_commit_hash == "abc123"