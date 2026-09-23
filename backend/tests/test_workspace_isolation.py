"""Security regression tests for workspace ownership boundaries."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.vector_store import VectorStoreService
from app.db import crud
from app.models.db_models import Repository
from app.db.database import Base
from app.core.workspace import _decode, _set_cookie, _sign, _workspace_context
from app.core.config import Settings
import app.core.workspace as workspace
import time
from fastapi import Response
from starlette.requests import Request


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine)


def test_repository_listing_and_lookup_are_workspace_scoped() -> None:
    db = _session()
    first = crud.create_repository(db, repository_name="a/one", repository_url="https://github.com/a/one", workspace_id="workspace-a")
    second = crud.create_repository(db, repository_name="b/two", repository_url="https://github.com/b/two", workspace_id="workspace-b")

    assert [repo.id for repo in crud.list_repositories(db, workspace_id="workspace-a")] == [first.id]
    assert crud.get_repository(db, second.id, workspace_id="workspace-a") is None
    assert crud.count_repositories(db, workspace_id="workspace-a") == 1


def test_same_github_repository_can_be_owned_by_two_workspaces() -> None:
    db = _session()
    url = "https://github.com/shared/repository"
    first = crud.create_repository(db, repository_name="shared/repository", repository_url=url, workspace_id="workspace-a")
    second = crud.create_repository(db, repository_name="shared/repository", repository_url=url, workspace_id="workspace-b")
    assert first.id != second.id


def test_legacy_unassigned_rows_are_not_visible_to_any_workspace() -> None:
    db = _session()
    legacy = Repository(repository_name="legacy/repository", repository_url="https://github.com/legacy/repository", local_path="")
    db.add(legacy)
    db.commit()
    assert crud.list_repositories(db, workspace_id="new-workspace") == []
    assert crud.get_repository(db, legacy.id, workspace_id="new-workspace") is None


def test_workspace_cookie_signing_uses_canonical_settings_secret(monkeypatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    configured = Settings(_env_file=None, environment="production", workspace_session_secret="s" * 32)
    monkeypatch.setattr(workspace, "get_settings", lambda: configured)
    issued_at = int(time.time())
    signed = _sign("e" * 32, issued_at)
    assert signed
    assert workspace._decode(f"{'e' * 32}.{issued_at}.{signed}") == "e" * 32

    other = Settings(_env_file=None, environment="production", workspace_session_secret="t" * 32)
    monkeypatch.setattr(workspace, "get_settings", lambda: other)
    assert workspace._decode(f"{'e' * 32}.{issued_at}.{signed}") is None


def test_workspace_cookie_attributes_remain_intact(monkeypatch) -> None:
    configured = Settings(_env_file=None, environment="production", workspace_session_secret="s" * 32)
    monkeypatch.setattr(workspace, "get_settings", lambda: configured)
    request = Request({"type": "http", "scheme": "https", "path": "/", "headers": [], "query_string": b""})
    response = Response()
    _set_cookie(response, "f" * 32, request)
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header and "Secure" in header and "SameSite=none" in header


def test_vector_collection_names_are_workspace_isolated() -> None:
    first = VectorStoreService._collection_name_for("7", "workspace-a")
    second = VectorStoreService._collection_name_for("7", "workspace-b")
    assert first != second
    assert "workspace-a" not in first
    assert "workspace-b" not in second
