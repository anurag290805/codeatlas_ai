"""Regression coverage for queue safety independent of GitHub/Chroma."""

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.core import indexing_queue
from app.core.vector_store import VectorStoreService


def test_indexing_job_has_workspace_scoped_identity() -> None:
    job = indexing_queue.IndexingJob("12", "https://github.com/a/b", False, "workspace-a")
    assert job.repository_id == "12"
    assert job.workspace_id == "workspace-a"


def test_duplicate_repository_jobs_are_deduplicated(monkeypatch) -> None:
    class ImmediateQueue:
        def put_nowait(self, job):
            self.job = job

        def qsize(self):
            return 1

    queue = ImmediateQueue()
    monkeypatch.setattr(indexing_queue, "_jobs", queue)
    monkeypatch.setattr(indexing_queue, "_started", True)
    monkeypatch.setattr(indexing_queue, "_active_ids", set())

    assert indexing_queue.enqueue_indexing_job(12, "https://github.com/a/b", is_update=False, workspace_id="a")
    assert indexing_queue.enqueue_indexing_job(12, "https://github.com/a/b", is_update=False, workspace_id="a")
    assert queue.job.repository_id == "12"


def test_collection_name_stays_under_chromadb_limit() -> None:
    """ChromaDB rejects collection names longer than 63 characters.

    The production failure was: collection names like
    'codeatlas_repo_<24-char-hash>_<repo-id>_<32-char-uuid>'
    exceeded 63 chars. This test guards against regressions.
    """
    service = VectorStoreService()

    # Long workspace_id (simulating a signed cookie) + typical repo_id
    collection_name = service._collection_name_for("1234567890", "a" * 100)

    # The base name must be short enough that adding a 32-char UUID suffix
    # (done by stage_embeddings) still stays under 63 chars.
    staged_name = f"{collection_name}_" + "a" * 32
    assert len(staged_name) <= 63, f"Staged collection name too long: {len(staged_name)} > 63 ({staged_name})"
    assert all(c.isalnum() or c in "_-" for c in staged_name), "Invalid chars in collection name"

    # Also verify the active pointer filename stays reasonable
    active_pointer = f"active_{service._collection_name_for('1', 'w')}.json"
    assert len(active_pointer) <= 255  # filesystem limit


class _RecordingQueue:
    """Replacement ``_jobs`` that records enqueued jobs without a worker thread."""

    def __init__(self) -> None:
        self.jobs: list[indexing_queue.IndexingJob] = []

    def put_nowait(self, job: indexing_queue.IndexingJob) -> None:
        self.jobs.append(job)

    def qsize(self) -> int:
        return len(self.jobs)


def _repository_row(**overrides: object) -> SimpleNamespace:
    """Build a fake ``Repository`` row with the fields recovery reads."""
    defaults: dict[str, object] = {
        "id": 7,
        "url": "https://github.com/owner/repository",
        "indexing_status": "indexing",
        "indexing_stage": "storing",
        "indexing_progress": 85,
        "indexing_heartbeat_at": datetime.now(timezone.utc),
        "workspace_id": "workspace-a",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_recover_requeues_indexing_job_with_fresh_heartbeat(monkeypatch) -> None:
    """A repo left at ``indexing`` after a restart must be requeued.

    Production regression: the previous recovery implementation skipped any
    repository whose ``indexing_heartbeat_at`` was newer than 20 minutes.
    After a Render restart mid-import the newly-started process retried
    recovery within moments of the old process's last heartbeat, so the
    skip fired every time and the repo stayed at ``indexing`` (0 files /
    0 chunks / 0 embeddings) forever. Heartbeat freshness proves nothing
    about the *new* process's workers, so recovery must requeue every
    pending/indexing row on startup.
    """
    repository = _repository_row()  # fresh heartbeat, status=indexing, stage=storing
    queued: list[tuple[object, object, dict[str, object]]] = []

    @contextmanager
    def _fake_db_session():
        fake_db = SimpleNamespace(
            execute=lambda *_: SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [repository])),
            commit=lambda: None,
        )
        yield fake_db

    monkeypatch.setattr(indexing_queue, "db_session", _fake_db_session)
    monkeypatch.setattr(indexing_queue, "_jobs", _RecordingQueue())

    captured: dict[str, object] = {}

    def _fake_enqueue(repository_id, clone_url, *, is_update, workspace_id):
        captured.update(
            {
                "repository_id": repository_id,
                "clone_url": clone_url,
                "is_update": is_update,
                "workspace_id": workspace_id,
            }
        )
        return True

    with patch.object(indexing_queue, "enqueue_indexing_job", side_effect=_fake_enqueue) as enqueue:
        recovered = indexing_queue.recover_indexing_jobs()

    assert recovered == 1
    # The orphaned job was reset to a queued state and re-enqueued with the
    # authoritative workspace id from the Repository row, not a browser cookie.
    assert repository.indexing_status == "pending"
    assert repository.indexing_stage == "queued"
    assert repository.indexing_progress == 5
    assert captured == {
        "repository_id": 7,
        "clone_url": "https://github.com/owner/repository",
        "is_update": False,
        "workspace_id": "workspace-a",
    }
    enqueue.assert_called_once()


def test_recover_skips_repositories_without_workspace(monkeypatch) -> None:
    """Legacy pre-workspace rows must not be requeued under a random workspace."""
    repository = _repository_row(workspace_id=None)

    @contextmanager
    def _fake_db_session():
        fake_db = SimpleNamespace(
            execute=lambda *_: SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [repository])),
            commit=lambda: None,
        )
        yield fake_db

    monkeypatch.setattr(indexing_queue, "db_session", _fake_db_session)
    monkeypatch.setattr(indexing_queue, "_jobs", _RecordingQueue())

    with patch.object(indexing_queue, "enqueue_indexing_job") as enqueue:
        recovered = indexing_queue.recover_indexing_jobs()

    assert recovered == 0
    enqueue.assert_not_called()
