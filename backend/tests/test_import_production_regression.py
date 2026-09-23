"""Regression tests for the production repository-import failure.

Production facts that motivated these tests:
  * ``GET /api/repositories`` worked, but ``POST /api/repositories``
    (import) returned HTTP 500, which the browser surfaced as a generic
    "Network Error" because the error body carried no CORS headers.
  * Root cause: ``routes_repo`` was the only router without the
    ``ensure_workspace`` router dependency. ``get_workspace_id`` alone
    returns a signed workspace id but never creates the row in
    ``workspaces``. On PostgreSQL (FK enforced), inserting a
    ``Repository`` referencing a missing workspace row violates the
    foreign key ``repositories.workspace_id -> workspaces.id`` and the
    import raised IntegrityError -> 500. Local SQLite does not enforce
    FKs by default, which is why the bug only surfaced in production.

The tests below recreate both halves of the regression:
  1. Import succeeds on a FK-enforced database once the router runs
     ``ensure_workspace`` (the fix).
  2. Unhandled-exception responses carry CORS headers so the browser can
     read the real HTTP status instead of masking it as "Network Error".
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes_repo
from app.db.database import get_db
from app.main import _register_exception_handlers, _register_middleware
from app.models import db_models
from app.models.db_models import Workspace


def _fk_enforcing_session_factory() -> sessionmaker:
    """Return a session factory over a FK-enforcing DB (PostgreSQL-like).

    SQLite ignores foreign keys unless ``PRAGMA foreign_keys=ON`` is set
    per connection; PostgreSQL enforces them natively. Enabling the
    pragma reproduces the production constraint so the regression is
    caught locally. ``StaticPool`` keeps every request on the same
    in-memory connection so the schema created once is visible to all.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    db_models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def _build_import_app():
    """Build an app exposing the repo router over a FK-enforcing DB.

    Heavy services (git clone, indexing queue) are stubbed out; the point
    is to exercise the request path -- workspace materialization + repo
    INSERT -- not the clone pipeline. The ``enqueue_indexing_job`` stub
    stays active for the whole test so no real clone is scheduled.
    """
    session_factory = _fk_enforcing_session_factory()
    app = FastAPI()
    app.include_router(routes_repo.router)

    def _override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with patch.object(routes_repo, "enqueue_indexing_job", return_value=True):
        client = TestClient(app)
        yield client, session_factory


def test_import_repository_succeeds_when_workspace_row_is_materialized(_build_import_app) -> None:
    """POST /repositories must return 202, not 500, on a FK-enforcing DB."""
    client, session_factory = _build_import_app

    # No existing workspace cookie -> the router's ensure_workspace
    # dependency must create the Workspace row before the Repository
    # INSERT runs.
    response = client.post(
        "/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["repository_name"] == "octocat/Hello-World"
    assert payload["status"] == "pending"

    with session_factory() as session:
        assert session.query(Workspace).count() == 1
        repository = session.query(db_models.Repository).one()
        assert repository.workspace_id is not None
        assert session.get(Workspace, repository.workspace_id) is not None


def test_import_repository_uses_same_workspace_as_existing_cookie(_build_import_app) -> None:
    """A returning browser must import under its existing workspace."""
    client, session_factory = _build_import_app

    first = client.post(
        "/repositories",
        json={"url": "https://github.com/octocat/Hello-World"},
    )
    assert first.status_code == 202
    cookie = first.cookies.get("codeatlas_workspace")

    client.cookies.set("codeatlas_workspace", cookie)
    second = client.post(
        "/repositories",
        json={"url": "https://github.com/octocat/second-repo"},
    )
    assert second.status_code == 202, second.text

    with session_factory() as session:
        workspaces = session.query(Workspace).count()
        repositories = session.query(db_models.Repository).all()
        assert workspaces == 1, "A returning workspace must not create a new row"
        assert {r.repository_name for r in repositories} == {
            "octocat/Hello-World",
            "octocat/second-repo",
        }


def test_repo_router_registers_ensure_workspace_dependency() -> None:
    """Guard against reintroducing the missing router dependency."""
    dependencies = routes_repo.router.dependencies
    assert len(dependencies) == 1
    assert dependencies[0].dependency.__name__ == "ensure_workspace"


def test_unexpected_error_response_includes_cors_headers(monkeypatch) -> None:
    """A 500 from the generic exception handler must stay browser-readable.

    Before the fix, exception-handler responses bypassed the CORS
    middleware, so the browser blocked the cross-origin error body and
    axios surfaced a generic "Network Error".
    """
    settings = SimpleNamespace(
        cors_allowed_origins=["http://localhost:4173"],
        cors_allow_credentials=True,
        trusted_hosts=[],
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    app = FastAPI()
    _register_middleware(app)
    _register_exception_handlers(app)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"Origin": "http://localhost:4173"})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:4173"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert response.json()["error"] == "An unexpected error occurred."


def test_disallowed_origin_still_gets_no_cors_on_error(monkeypatch) -> None:
    """Error responses must not leak CORS headers to non-configured origins."""
    settings = SimpleNamespace(
        cors_allowed_origins=["http://localhost:4173"],
        cors_allow_credentials=True,
        trusted_hosts=[],
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    app = FastAPI()
    _register_middleware(app)
    _register_exception_handlers(app)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"Origin": "http://evil.test"})

    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers
