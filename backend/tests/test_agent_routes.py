"""Route-level tests for the agent API's approval gate and workspace scoping.

These verify the two security controls at the HTTP boundary:
1. modify-mode requests return a pending approval and never touch the filesystem;
2. repositories and approvals are scoped to the requesting workspace (no IDOR).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_agent, routes_query
from app.core import auth, workspace
from app.db.database import get_db
from app.models import schemas
from tests.test_patching import _settings  # repository-dir settings helper

CURRENT_WORKSPACE = "ws-a"
CURRENT_REPOSITORY_ID = 1
SECOND_REPOSITORY_ID = 2


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class _Workspace:
    def __init__(self) -> None:
        self.value = CURRENT_WORKSPACE

    def set(self, value: str) -> None:
        self.value = value


class FakeDB:
    """Minimal DB stand-in: repo lookups are workspace-scoped."""

    def __init__(self, root: Path):
        self._root = root

    def _repo(self, repository_id: int) -> SimpleNamespace:
        if repository_id == 1:
            self._root.mkdir(parents=True, exist_ok=True)
            target = self._root / "main.py"
            target.write_bytes(b"answer = 1\n")
            return SimpleNamespace(id=repository_id, status=schemas.RepositoryStatus.READY, workspace_id="ws-a", local_path=str(self._root))
        return SimpleNamespace(id=repository_id, status=schemas.RepositoryStatus.READY, workspace_id="ws-b", local_path=str(self._root))

    def get(self, model, repository_id):
        return self._repo(repository_id)

    def add(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None


def _target(root: Path) -> Path:
    return root / "main.py"


def _proposal_json(root: Path) -> str:
    from difflib import unified_diff

    original = _target(root).read_bytes()
    updated = b"answer = 2\n"
    diff = "".join(
        unified_diff(
            original.decode().splitlines(keepends=True),
            updated.decode().splitlines(keepends=True),
            fromfile="a/main.py",
            tofile="b/main.py",
        )
    )
    return json.dumps(
        {
            "patches": [
                {
                    "path": "main.py",
                    "operation": "modify",
                    "old_content_hash": _sha(original),
                    "diff": diff,
                }
            ]
        }
    )


class FakeRetriever:
    queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return SimpleNamespace(assembled_context="File: main.py\nanswer = 1")


class FakeLLM:
    provider_name = SimpleNamespace(value="omniroute")
    model_name = "auto/best-free"

    def __init__(self, root: Path):
        self._root = root

    async def generate(self, request):
        return SimpleNamespace(answer=_proposal_json(self._root), provider=self.provider_name, model=self.model_name)

    async def generate_answer(self, retrieval):
        return SimpleNamespace(answer="scoped repository answer")


def _build_client(db: FakeDB, workspace_holder: _Workspace, llm: FakeLLM) -> TestClient:
    app = FastAPI()
    app.include_router(routes_agent.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[routes_query.get_retriever_service] = FakeRetriever
    app.dependency_overrides[routes_query.get_llm_service] = lambda: llm
    app.dependency_overrides[auth.get_workspace_id] = lambda: workspace_holder.value
    app.dependency_overrides[workspace.ensure_workspace] = lambda: workspace_holder.value
    return TestClient(app)


def test_modify_mode_returns_pending_approval_without_writing(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repos" / "ws-a" / "repo"
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    db = FakeDB(root)
    holder = _Workspace()
    with _build_client(db, holder, FakeLLM(root)) as client:
        response = client.post(
            "/agent/tasks",
            json={"repository_id": CURRENT_REPOSITORY_ID, "task": "improve main.py", "mode": "modify"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["modification"]["approval_token"]
    # The security invariant: after planning, the target file is unchanged.
    assert _target(root).read_bytes() == b"answer = 1\n"


def test_agent_route_is_workspace_scoped_returns_404_for_foreign_repo(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repos" / "ws-a" / "repo"
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    db = FakeDB(root)
    holder = _Workspace()
    with _build_client(db, holder, FakeLLM(root)) as client:
        # repository_id=2 belongs to ws-b; a ws-a caller must be denied.
        response = client.post(
            "/agent/tasks",
            json={"repository_id": SECOND_REPOSITORY_ID, "task": "review", "mode": "analyze"},
        )
    assert response.status_code == 404


def test_agent_retrieval_preserves_repository_and_workspace_scope(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repos" / "ws-a" / "repo"
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    db = FakeDB(root)
    holder = _Workspace()
    FakeRetriever.queries.clear()

    with _build_client(db, holder, FakeLLM(root)) as client:
        response = client.post(
            "/agent/tasks",
            json={"repository_id": CURRENT_REPOSITORY_ID, "task": "review", "mode": "analyze"},
        )

    assert response.status_code == 200
    assert FakeRetriever.queries
    query = FakeRetriever.queries[-1]
    assert query.repository_id == str(CURRENT_REPOSITORY_ID)
    assert query.workspace_id == CURRENT_WORKSPACE


def test_approve_requires_same_workspace_and_is_single_use(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repos" / "ws-a" / "repo"
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    db = FakeDB(root)
    holder = _Workspace()

    with _build_client(db, holder, FakeLLM(root)) as client:
        planned = client.post(
            "/agent/tasks",
            json={"repository_id": CURRENT_REPOSITORY_ID, "task": "improve main.py", "mode": "modify"},
        )
        token = planned.json()["modification"]["approval_token"]

        # A different workspace must not be able to approve it.
        holder.set("ws-b")
        denied = client.post("/agent/tasks/approve", json={"approval_token": token})
        assert denied.status_code == 403

        # The owning workspace can approve exactly once.
        holder.set("ws-a")
        approved = client.post("/agent/tasks/approve", json={"approval_token": token})
        assert approved.status_code == 200
        assert approved.json()["status"] == "completed"
        assert _target(root).read_bytes() == b"answer = 2\n"

        # Reusing the same token must fail (single-use).
        reused = client.post("/agent/tasks/approve", json={"approval_token": token})
        assert reused.status_code == 403