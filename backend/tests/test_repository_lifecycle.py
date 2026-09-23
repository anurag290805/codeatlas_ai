"""Regression tests for repository lifecycle orchestration."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.api import routes_repo
from app.core.graph_builder import GraphService, GraphBuilder
from app.core.parser import RepositoryParseResult
from app.models import schemas


def repository_stub(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        repository_name="owner/repository",
        repository_url="https://github.com/owner/repository",
        url="https://github.com/owner/repository",
        default_branch="main",
        status=status,
        files_indexed=0,
        chunks_generated=0,
        embeddings_generated=0,
        last_indexed_at=None,
    )


def test_failed_repository_import_is_retryable() -> None:
    existing = repository_stub(schemas.RepositoryStatus.FAILED.value)
    updated = repository_stub(schemas.RepositoryStatus.PENDING.value)
    db = Mock()
    background_tasks = Mock()
    git_manager = Mock()
    git_manager.validate_repository_url.return_value = SimpleNamespace(
        full_name="owner/repository",
        canonical_url="https://github.com/owner/repository",
    )
    parser = Mock()
    embedding_service = Mock()
    vector_store_service = Mock()

    with patch.object(routes_repo.crud, "get_repository_by_url", return_value=existing), patch.object(
        routes_repo.crud, "update_repository_status", return_value=updated
    ), patch.object(routes_repo, "enqueue_indexing_job", return_value=True) as enqueue:
        response = routes_repo.import_repository(
            schemas.RepositoryCreate(url="https://github.com/owner/repository"),
            background_tasks,
            db,
            git_manager,
            "workspace-a",
        )

    assert response.id == existing.id
    enqueue.assert_called_once_with(7, "https://github.com/owner/repository", is_update=False, workspace_id="workspace-a")


def test_active_duplicate_repository_is_rejected() -> None:
    db = Mock()
    git_manager = Mock()
    git_manager.validate_repository_url.return_value = SimpleNamespace(
        full_name="owner/repository",
        canonical_url="https://github.com/owner/repository",
    )
    existing = repository_stub(schemas.RepositoryStatus.INDEXED.value)

    with patch.object(routes_repo.crud, "get_repository_by_url", return_value=existing):
        with pytest.raises(HTTPException) as caught:
            # Signature after the queue refactor: payload, background_tasks,
            # db, git_manager, workspace_id. The earlier per-dependency
            # (parser, embedding_service, vector_store_service) parameters
            # were removed when indexing moved to the background queue.
            routes_repo.import_repository(
                schemas.RepositoryCreate(url="https://github.com/owner/repository"),
                Mock(),
                db,
                git_manager,
                "workspace-a",
            )

    assert caught.value.status_code == 409


def test_failed_indexing_discards_only_staged_artifacts() -> None:
    db = Mock()
    vector_store_service = Mock()

    with patch.object(routes_repo.crud, "get_repository", return_value=None), patch.object(
        routes_repo.crud, "update_repository_status"
    ) as update_status:
        routes_repo._mark_indexing_failed(
            db,
            "7",
            "vector_store",
            RuntimeError("collection unavailable"),
            vector_store_service,
        )

    vector_store_service.delete_repository_embeddings.assert_not_called()
    update_status.assert_called_once()
    assert update_status.call_args.kwargs["repository_id"] == "7"
    assert update_status.call_args.kwargs["status"] is schemas.RepositoryStatus.FAILED_IMPORT


def test_graph_service_normalizes_parser_repository_id(tmp_path: Path) -> None:
    service = GraphService(GraphBuilder(), graph_directory=tmp_path / "graphs")
    service.build_graph(
        RepositoryParseResult(
            repository_id=7,
            files_parsed=0,
            files_skipped=0,
            files_failed=0,
            files=[],
        )
    )

    assert service.has_graph("7")
    assert service.get_graph("7").repository_id == "7"
