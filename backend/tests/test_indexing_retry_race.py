"""Regression test for the retry/enqueue race.

Covers:
- A failed indexing job releases its _active_ids slot BEFORE committing
  the terminal status, so a retry is actually queued (not silently dropped).
- The failed run's terminal write is guarded by a run-epoch so it never
  overwrites the status of a newly queued/started retry.
- Normal duplicate-job protection and the successful import path are unchanged.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.api import routes_repo
from app.core import indexing_queue
from app.models import schemas


class _RecordingQueue:
    """Fake queue that records enqueued jobs for deterministic inspection."""

    def __init__(self) -> None:
        self.jobs: list[indexing_queue.IndexingJob] = []

    def put_nowait(self, job: indexing_queue.IndexingJob) -> None:
        self.jobs.append(job)

    def qsize(self) -> int:
        return len(self.jobs)

    def task_done(self) -> None:
        pass


def _reset_queue_state() -> None:
    """Fresh queue state for each test."""
    indexing_queue._started = True
    indexing_queue._jobs = _RecordingQueue()
    indexing_queue._active_ids = set()


def test_retry_after_failure_is_queued_not_dropped() -> None:
    """After a failure, the _active_ids slot is released before FAILED is
    visible, so an immediate retry is actually enqueued."""
    _reset_queue_state()

    db = Mock()
    vector_store_service = Mock()

    T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # --- Phase 0: job A is active (simulating a running import) ---
    assert indexing_queue.enqueue_indexing_job(7, "https://github.com/owner/repo", is_update=False, workspace_id="ws-a")
    assert "7" in indexing_queue._active_ids
    assert len(indexing_queue._jobs.jobs) == 1

    # --- Phase 1: job A fails ---
    repo_row = SimpleNamespace(
        id=7,
        indexing_status="indexing",
        indexing_started_at=T0,
        total_files=0,
        total_chunks=0,
        total_embeddings=0,
    )
    with patch.object(routes_repo.crud, "get_repository", return_value=repo_row), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status:
        routes_repo._mark_indexing_failed(
            db,
            "7",
            "vector_store",
            RuntimeError("boom"),
            vector_store_service,
            None,
            None,
            "ws-a",
            this_run_started_at=T0,
        )

    # Slot released before terminal status was committed
    assert "7" not in indexing_queue._active_ids, "active slot must be released before FAILED is visible"
    update_status.assert_called_once()
    assert update_status.call_args.kwargs["status"] is schemas.RepositoryStatus.FAILED_IMPORT

    # --- Phase 2: repository is retryable; retry A is requested at the boundary ---
    # The enqueue call must actually queue a new job (not return True with no queueing).
    assert indexing_queue.enqueue_indexing_job(7, "https://github.com/owner/repo", is_update=False, workspace_id="ws-a")
    assert "7" in indexing_queue._active_ids
    assert len(indexing_queue._jobs.jobs) == 2, "retry was silently dropped; it must be queued"

    # The second queued job has the expected fields
    retry_job = indexing_queue._jobs.jobs[1]
    assert retry_job.repository_id == "7"
    assert retry_job.workspace_id == "ws-a"
    assert retry_job.is_update is False


def test_failed_run_cannot_clobber_retry_status() -> None:
    """If a retry has already advanced the row (reset to pending, or a new
    run started with a new epoch), the old failure must not overwrite it."""
    _reset_queue_state()

    db = Mock()
    vector_store_service = Mock()

    T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    T1 = datetime(2026, 1, 2, tzinfo=timezone.utc)

    # --- Phase 1: job A fails with epoch T0 ---
    repo_row_t0 = SimpleNamespace(
        id=7,
        indexing_status="indexing",
        indexing_started_at=T0,
        total_files=0,
        total_chunks=0,
        total_embeddings=0,
    )
    with patch.object(routes_repo.crud, "get_repository", return_value=repo_row_t0), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status:
        routes_repo._mark_indexing_failed(
            db,
            "7",
            "vector_store",
            RuntimeError("boom"),
            vector_store_service,
            None,
            None,
            "ws-a",
            this_run_started_at=T0,
        )
    # First failure wrote FAILED_IMPORT (row still owned by this run)
    update_status.assert_called_once()
    assert update_status.call_args.kwargs["status"] is schemas.RepositoryStatus.FAILED_IMPORT
    update_status.reset_mock()

    # --- Phase 2: retry resets to pending (import_repository does this via crud) ---
    # Per the crud change, setting status=pending resets indexing_started_at = None.
    repo_after_retry_reset = SimpleNamespace(
        id=7,
        indexing_status="pending",
        indexing_started_at=None,  # reset by crud when status -> pending
    )
    with patch.object(routes_repo.crud, "get_repository", return_value=repo_after_retry_reset), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status:
        # Old run (epoch T0) tries to write terminal status AGAIN
        routes_repo._mark_indexing_failed(
            db,
            "7",
            "vector_store",
            RuntimeError("boom"),
            vector_store_service,
            None,
            None,
            "ws-a",
            this_run_started_at=T0,
        )

    # Must NOT overwrite: row is no longer in indexing OR epoch differs
    update_status.assert_not_called()

    # --- Phase 3: new run already started (new epoch T1) ---
    repo_new_run = SimpleNamespace(
        id=7,
        indexing_status="indexing",
        indexing_started_at=T1,  # new run established its own epoch
        total_files=10,
        total_chunks=50,
        total_embeddings=100,
    )
    with patch.object(routes_repo.crud, "get_repository", return_value=repo_new_run), \
         patch.object(routes_repo.crud, "update_repository_status") as update_status:
        routes_repo._mark_indexing_failed(
            db,
            "7",
            "vector_store",
            RuntimeError("boom"),
            vector_store_service,
            None,
            None,
            "ws-a",
            this_run_started_at=T0,
        )

    # Must NOT overwrite: row is indexing but epoch differs (newer run owns it)
    update_status.assert_not_called()


def test_normal_duplicate_enqueue_protection_preserved() -> None:
    """Concurrent enqueues of the same active repository are still deduplicated."""
    _reset_queue_state()

    # First enqueue
    assert indexing_queue.enqueue_indexing_job(7, "https://github.com/owner/repo", is_update=False, workspace_id="ws-a")
    assert len(indexing_queue._jobs.jobs) == 1
    assert "7" in indexing_queue._active_ids

    # Second enqueue while first is still active -> dedup, no new job
    assert indexing_queue.enqueue_indexing_job(7, "https://github.com/owner/repo", is_update=False, workspace_id="ws-a")
    assert len(indexing_queue._jobs.jobs) == 1, "duplicate enqueue must be collapsed"


def test_successful_import_pipeline_reaches_ready() -> None:
    """Ordinary successful import path is unchanged and reaches READY."""
    db = Mock()
    git_manager = Mock()
    parser = Mock()
    embedding_service = Mock()
    vector_store_service = Mock()

    # --- Git manager returns a staged clone ---
    from pathlib import Path
    identity = SimpleNamespace(
        owner="owner",
        name="repo",
        full_name="owner/repo",
        canonical_url="https://github.com/owner/repo",
    )
    staged_path = Path("/tmp/.repo.indexing-abc123")
    live_path = Path("/tmp/repo")
    metadata = SimpleNamespace(
        local_path=staged_path,
        default_branch="main",
        current_commit_hash="abc123",
    )

    git_manager.validate_repository_url.return_value = identity
    git_manager.resolve_local_path.return_value = live_path
    git_manager.clone_repository.return_value = metadata
    git_manager.promote_repository_clone.return_value = live_path

    # --- Parser returns chunks and files ---
    mock_chunk_1 = Mock()
    mock_chunk_1.chunk_id = "chunk-1"
    mock_chunk_2 = Mock()
    mock_chunk_2.chunk_id = "chunk-2"
    parse_result = SimpleNamespace(
        repository_id=7,
        files_parsed=2,
        files_skipped=0,
        files_failed=0,
        chunks=[mock_chunk_1, mock_chunk_2],
        files=[
            SimpleNamespace(
                relative_path="a.py",
                language="python",
                checksum="sha1",
                chunk_count=1,
                file_size=100,
            ),
            SimpleNamespace(
                relative_path="b.py",
                language="python",
                checksum="sha2",
                chunk_count=1,
                file_size=200,
            ),
        ],
        errors=[],
    )
    parser.parse_repository.return_value = parse_result

    # --- Graph service is fully mocked (real one writes to disk) ---
    mock_graph = Mock()
    mock_graph.statistics.return_value = SimpleNamespace(total_nodes=10, total_edges=5)
    mock_graph.repository_id = "7"
    mock_graph_service = Mock()
    mock_graph_service.build_staged_graph.return_value = mock_graph
    mock_graph_service.publish_graph = Mock()

    with patch("app.api.routes_repo.get_graph_service", return_value=mock_graph_service):
        # --- Embedding service ---
        embedding_service.generate_embeddings.return_value = SimpleNamespace(embeddings=[[0.1]*384, [0.2]*384])

        # --- Vector store ---
        vector_store_service.stage_embeddings.return_value = "codeatlas_legacy_7_abc"
        vector_store_service.publish_staged_collection.return_value = None

        # --- CRUD ---
        # The pipeline re-reads the row's run epoch via get_repository and
        # re-checks ownership at commit (it must still own the row to publish and
        # mark READY). Provide a stable, owned row so the run completes.
        T_owned = datetime(2026, 1, 1, tzinfo=timezone.utc)
        owned_row = SimpleNamespace(
            id=7,
            indexing_status="indexing",
            indexing_started_at=T_owned,
            indexing_heartbeat_at=None,
            total_files=0,
            total_chunks=0,
            total_embeddings=0,
        )
        with patch.object(routes_repo.crud, "get_repository", return_value=owned_row), \
             patch.object(routes_repo.crud, "update_repository_status") as update_status, \
             patch.object(routes_repo.crud, "update_repository") as update_repo, \
             patch.object(routes_repo.crud, "replace_indexed_files") as replace_files:

            routes_repo._run_indexing_pipeline(
                repository_id="7",
                clone_url="https://github.com/owner/repo",
                is_update=False,
                db=db,
                git_manager=git_manager,
                parser=parser,
                embedding_service=embedding_service,
                vector_store_service=vector_store_service,
                workspace_id="ws-a",
            )

    # Final status is READY
    final_call = update_status.call_args_list[-1]
    assert final_call.kwargs["status"] is schemas.RepositoryStatus.READY
    assert final_call.kwargs["total_files"] == 2
    assert final_call.kwargs["total_chunks"] == 2
    assert final_call.kwargs["total_embeddings"] == 2

    # Replace_indexed_files called with parsed files
    replace_files.assert_called_once()

    # Graph was published
    mock_graph_service.publish_graph.assert_called_once_with(mock_graph)

    # Repo metadata updated (local_path, default_branch, commit)
    update_repo.assert_called_once()


def test_import_repository_fresh_enqueues_once() -> None:
    """Fresh import request enqueues exactly one job and returns 202."""
    _reset_queue_state()

    db = Mock()
    background_tasks = Mock()
    git_manager = Mock()
    git_manager.validate_repository_url.return_value = SimpleNamespace(
        full_name="owner/repo",
        canonical_url="https://github.com/owner/repo",
    )

    new_repo = SimpleNamespace(
        id=7,
        repository_name="owner/repo",
        repository_url="https://github.com/owner/repo",
        url="https://github.com/owner/repo",
        default_branch="main",
        status=schemas.RepositoryStatus.PENDING.value,
        files_indexed=0,
        chunks_generated=0,
        embeddings_generated=0,
        last_indexed_at=None,
    )

    with patch.object(routes_repo.crud, "get_repository_by_url", return_value=None), \
         patch.object(routes_repo.crud, "create_repository", return_value=new_repo):
        response = routes_repo.import_repository(
            schemas.RepositoryCreate(url="https://github.com/owner/repo"),
            background_tasks,
            db,
            git_manager,
            "ws-a",
        )

    assert response.id == 7
    assert len(indexing_queue._jobs.jobs) == 1
    assert indexing_queue._jobs.jobs[0].repository_id == "7"
    assert indexing_queue._jobs.jobs[0].workspace_id == "ws-a"