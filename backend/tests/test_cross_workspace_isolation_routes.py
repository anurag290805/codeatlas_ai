"""Regression tests for cross-workspace access on the query and
intelligence routers.

Motivation: the repository router (``routes_repo``) scopes every lookup by
``workspace_id``, but the query router (``routes_query``) fetched the
repository by its bare global integer id (``crud.get_repository(db, id)``
with no workspace filter) and built ``RetrievalQuery`` without
``workspace_id``; the intelligence router (``routes_intelligence``) fetched
the repository with no workspace filter either. Because repository ids are
global auto-increment integers shared across all workspaces, an anonymous
browser in workspace B could read another workspace's repository metadata,
dependencies, security scan, and run RAG queries over its indexed code --
real IDOR / cross-workspace data exposure.

These tests reproduce the IDOR at the HTTP layer and assert it is blocked
after the fix (the request 404s because the repository does not belong to
the caller's workspace).
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes_intelligence, routes_query
from app.core.workspace import _sign
from app.db import crud
from app.db.database import get_db
from app.models import db_models
from app.models.db_models import Workspace

WORKSPACE_COOKIE = "codeatlas_workspace"

# One shared in-memory engine (StaticPool keeps a single connection so the
# schema and rows are visible to every request the TestClient issues).
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
db_models.Base.metadata.create_all(_engine)


def _new_session() -> Session:
    return Session(_engine)


@pytest.fixture()
def client() -> TestClient:
    """Build an app exposing the query and intelligence routers over the
    shared in-memory database.

    Heavy upstream services (retriever, LLM) never run: the fixed routes
    404 on the repository-lookup step before those dependencies execute.
    """
    app = FastAPI()
    app.include_router(routes_query.router)
    app.include_router(routes_intelligence.router)

    def _override_get_db():
        session = _new_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _workspace_cookie(workspace_id: str) -> str:
    issued_at = int(time.time())
    return f"{workspace_id}.{issued_at}.{_sign(workspace_id, issued_at)}"


def _seed_owner_repository(seed: int = 0) -> int:
    """Create workspace-a and workspace-b plus a fresh repo owned only by A.

    Idempotent across tests: the shared engine persists between tests, so
    the workspace rows are inserted once, while each call creates a distinct
    owned repository (unique ``workspace_id``+``repository_url`` per seed).
    """
    session = _new_session()
    if session.get(Workspace, "a" * 32) is None:
        session.add_all([Workspace(id="a" * 32), Workspace(id="b" * 32)])
        session.commit()
    name = f"owner_a/secret_{seed}"
    repo = crud.create_repository(
        session,
        repository_name=name,
        repository_url=f"https://github.com/{name}",
        workspace_id="a" * 32,
    )
    session.close()
    return repo.id


def _as(client: TestClient, workspace_ch: str) -> None:
    client.headers["Cookie"] = f"{WORKSPACE_COOKIE}={_workspace_cookie(workspace_ch * 32)}"


def test_intelligence_dependencies_are_workspace_scoped(client: TestClient) -> None:
    repo_id = _seed_owner_repository(seed=1)
    _as(client, "b")
    response = client.get(f"/repositories/{repo_id}/dependencies")
    assert response.status_code == 404


def test_intelligence_security_scan_is_workspace_scoped(client: TestClient) -> None:
    repo_id = _seed_owner_repository(seed=2)
    _as(client, "b")
    response = client.get(f"/repositories/{repo_id}/security")
    assert response.status_code == 404


def test_intelligence_github_metadata_is_workspace_scoped(client: TestClient) -> None:
    repo_id = _seed_owner_repository(seed=3)
    _as(client, "b")
    response = client.get(f"/repositories/{repo_id}/github")
    assert response.status_code == 404


def test_query_on_foreign_repository_is_workspace_scoped(client: TestClient) -> None:
    repo_id = _seed_owner_repository(seed=4)
    _as(client, "b")
    response = client.post(
        "/query",
        json={"repository_id": str(repo_id), "query": "how does auth work", "top_k": 5},
    )
    assert response.status_code == 404


def test_repository_scoped_query_is_workspace_scoped(client: TestClient) -> None:
    repo_id = _seed_owner_repository(seed=5)
    _as(client, "b")
    response = client.post(
        f"/repositories/{repo_id}/query",
        json={"query": "how does auth work", "top_k": 5},
    )
    assert response.status_code == 404


def test_owner_can_still_read_own_repository(client: TestClient) -> None:
    """The fix must not block legitimate same-workspace access."""
    repo_id = _seed_owner_repository()
    _as(client, "a")
    # Owned by workspace-a: the lookup passes, so the request must NOT 404.
    # It fails later (unindexed retrieval) rather than at the isolation edge.
    response = client.post(
        "/query",
        json={"repository_id": str(repo_id), "query": "how does auth work", "top_k": 5},
    )
    assert response.status_code != 404