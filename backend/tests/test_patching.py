from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.models import TaskStatus
from app.agents.patching import (
    PatchConflictError,
    PatchEdit,
    PatchRejectedError,
    PatchProposal,
    PatchWorkflow,
    apply_proposal,
    capture_originals,
    parse_patch_proposal,
    resolve_repository_root,
    validate_proposal,
)
from app.agents.service import AgentOrchestrator
from app.core.llm import LLMMalformedResponseError


def _settings(root: Path) -> SimpleNamespace:
    return SimpleNamespace(repositories_dir=root.parent)


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _repo(root: Path) -> SimpleNamespace:
    return SimpleNamespace(local_path=str(root))


def _edit(path: str, operation: str, old: bytes, new: bytes, old_hash: str | None = None) -> PatchEdit:
    from_name = "/dev/null" if operation == "create" else f"a/{path}"
    to_name = "/dev/null" if operation == "delete" else f"b/{path}"
    diff = "".join(difflib.unified_diff(old.decode().splitlines(keepends=True), new.decode().splitlines(keepends=True), fromfile=from_name, tofile=to_name))
    return PatchEdit(path=path, operation=operation, old_content_hash=old_hash, diff=diff)


def _proposal(path: str, operation: str, old: bytes, new: bytes, old_hash: str | None = None) -> PatchProposal:
    return PatchProposal(patches=[_edit(path, operation, old, new, old_hash or (_hash(old) if operation != "create" else None))])


class PatchLLM:
    provider_name = SimpleNamespace(value="omniroute")
    model_name = "auto/best-free"

    def __init__(self, proposals: list[dict]) -> None:
        self.proposals = proposals
        self.calls = 0

    async def generate(self, request):
        proposal = self.proposals[min(self.calls, len(self.proposals) - 1)]
        self.calls += 1
        return SimpleNamespace(answer=json.dumps(proposal))


class ReasoningThenPatchLLM:
    provider_name = SimpleNamespace(value="omniroute")
    model_name = "auto/best-free"

    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        if self.calls == 1:
            raise LLMMalformedResponseError("OmniRoute returned an empty response.")
        if self.answer is None:
            raise LLMMalformedResponseError("OmniRoute returned an empty response.")
        return SimpleNamespace(answer=self.answer)


def test_analyze_mode_does_not_modify_files(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    target.write_text("answer = 1\n")
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))

    class Retriever:
        def retrieve(self, query):
            return SimpleNamespace(assembled_context="File: main.py\nanswer = 1")

    class LLM:
        async def generate_answer(self, retrieval):
            return SimpleNamespace(answer="read-only")

    result = asyncio.run(AgentOrchestrator(Retriever(), LLM()).run(1, "Explain main.py", 3, workspace_id="test-workspace"))
    assert result.status is TaskStatus.COMPLETED
    assert target.read_text() == "answer = 1\n"


def test_modify_mode_requires_repository_metadata(tmp_path) -> None:
    class Retriever:
        def retrieve(self, query):
            return SimpleNamespace(assembled_context="File: main.py")

    class LLM:
        pass

    with pytest.raises(ValueError, match="Repository metadata"):
        asyncio.run(AgentOrchestrator(Retriever(), LLM()).run(1, "improve", 3, mode="modify", workspace_id="test-workspace"))


def test_repository_root_and_path_boundaries(tmp_path, monkeypatch) -> None:
    managed = tmp_path / "repos"
    root = managed / "repo"
    root.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    assert resolve_repository_root(_repo(root)) == root.resolve()
    with pytest.raises(PatchRejectedError):
        validate_proposal(_proposal("../outside.txt", "create", b"", b"x"), root, "modify")
    with pytest.raises(PatchRejectedError):
        validate_proposal(_proposal(str(outside), "create", b"", b"x"), root, "modify")
    link = root / "link"
    try:
        link.symlink_to(tmp_path / "external", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    (tmp_path / "external").mkdir()
    with pytest.raises(PatchRejectedError):
        validate_proposal(_proposal("link/new.py", "create", b"", b"x"), root, "modify")
    with pytest.raises(PatchRejectedError):
        resolve_repository_root(_repo(tmp_path / "not-managed"))


@pytest.mark.parametrize("path", [".env", ".env.local", "private.pem", "private.key", "credentials.json", "secrets.yaml", "backend/requests/file.py", ".git/config", "backend/app/core/llm.py.backup"])
def test_protected_paths_rejected(tmp_path, path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(PatchRejectedError):
        validate_proposal(_proposal(path, "create", b"", b"x"), root, "modify")


def test_hash_conflict_create_modify_and_delete_authorization(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    original = b"answer = 1\n"
    target.write_bytes(original)
    modify = _proposal("main.py", "modify", original, b"answer = 2\n")
    originals = capture_originals(modify, root)
    target.write_text("human change\n")
    with pytest.raises(PatchConflictError):
        capture_originals(modify, root)
    target.write_bytes(original)
    apply_proposal(modify, root, capture_originals(modify, root))
    assert target.read_text() == "answer = 2\n"
    created = _proposal("new.py", "create", b"", b"created = True\n")
    validate_proposal(created, root, "add new.py")
    apply_proposal(created, root, capture_originals(created, root))
    assert (root / "new.py").read_text() == "created = True\n"
    target.write_text("human change\n")
    with pytest.raises(PatchRejectedError):
        validate_proposal(_proposal("main.py", "delete", b"human change\n", b""), root, "clean this up")
    delete = _proposal("main.py", "delete", b"human change\n", b"")
    validate_proposal(delete, root, "delete main.py")
    apply_proposal(delete, root, capture_originals(delete, root))
    assert not target.exists()
    assert originals["main.py"] == original


def test_malformed_patch_and_arbitrary_command_are_rejected(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(Exception):
        PatchProposal.model_validate({"patches": [{"path": "x.py", "operation": "modify", "command": "rm -rf /"}]})


def test_compact_patch_parser_accepts_fenced_json_and_rejects_malformed_diff(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    target.write_bytes(b"answer = 1\n")
    proposal = _proposal("main.py", "modify", b"answer = 1\n", b"answer = 2\n")
    parsed = parse_patch_proposal(f"```json\n{proposal.model_dump_json()}\n```")
    assert parsed.patches[0].diff == proposal.patches[0].diff
    malformed = PatchProposal(patches=[PatchEdit(path="main.py", operation="modify", old_content_hash=_hash(b"answer = 1\n"), diff="not a unified diff")])
    with pytest.raises(PatchRejectedError, match="Malformed or unsafe unified diff"):
        validate_proposal(malformed, root, "improve main.py")


def test_reasoning_only_response_retries_without_using_reasoning_as_patch(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    target.write_bytes(b"answer = 1\n")
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    proposal = _proposal("main.py", "modify", b"answer = 1\n", b"answer = 2\n").model_dump()
    llm = ReasoningThenPatchLLM(json.dumps(proposal))
    monkeypatch.setattr("app.agents.patching.run_validation", lambda workspace, changed: SimpleNamespace(status="passed", checks=[]))
    result = asyncio.run(PatchWorkflow(llm).run(_repo(root), "improve main.py", "File: main.py", None, []))
    assert result.status == "completed"
    assert result.attempts == 1
    assert llm.calls == 2
    assert target.read_bytes() == b"answer = 2\n"


def test_reasoning_only_retry_exhaustion_never_writes_reasoning(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    original = b"answer = 1\n"
    target.write_bytes(original)
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    llm = ReasoningThenPatchLLM(None)
    with pytest.raises(PatchRejectedError, match="bounded retry"):
        asyncio.run(PatchWorkflow(llm)._propose("improve main.py", "File: main.py", "", ""))
    assert llm.calls == 2
    assert target.read_bytes() == original


def test_multi_file_apply_rolls_back_on_failure(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    first, second = root / "a.txt", root / "b.txt"
    first.write_text("a\n")
    second.write_text("b\n")
    proposal = PatchProposal(patches=[_edit("a.txt", "modify", b"a\n", b"A\n", _hash(b"a\n")), _edit("b.txt", "modify", b"b\n", b"B\n", _hash(b"b\n"))])
    originals = capture_originals(proposal, root)
    real_replace = __import__("os").replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated apply failure")
        return real_replace(source, destination)

    monkeypatch.setattr("app.agents.patching.os.replace", fail_second)
    with pytest.raises(OSError):
        apply_proposal(proposal, root, originals)
    assert first.read_text() == "a\n"
    assert second.read_text() == "b\n"


def test_workflow_retries_validation_and_stops_at_three(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    target.write_text("answer = 1\n")
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    proposal = lambda content: _proposal("main.py", "modify", b"answer = 1\n", content.encode()).model_dump()
    validation_calls = 0

    def validate_once(workspace, changed):
        nonlocal validation_calls
        validation_calls += 1
        return SimpleNamespace(status="failed" if validation_calls == 1 else "passed", checks=[])

    monkeypatch.setattr("app.agents.patching.run_validation", validate_once)
    result = asyncio.run(PatchWorkflow(PatchLLM([proposal("bad"), proposal("good")])).run(_repo(root), "improve main.py", "File: main.py", None, []))
    assert result.status == "completed"
    assert result.attempts == 2
    assert target.read_text() == "good"

    target.write_text("answer = 1\n")
    monkeypatch.setattr("app.agents.patching.run_validation", lambda workspace, changed: SimpleNamespace(status="failed", checks=[]))
    result = asyncio.run(PatchWorkflow(PatchLLM([proposal("bad")])).run(_repo(root), "improve main.py", "File: main.py", None, []))
    assert result.status == "failed"
    assert result.attempts == 3
    assert target.read_text() == "answer = 1\n"


def test_plan_never_writes_to_disk(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    original = b"answer = 1\n"
    target.write_bytes(original)
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    proposal, changed = asyncio.run(PatchWorkflow(PatchLLM([_proposal("main.py", "modify", original, b"answer = 2\n").model_dump()])).plan(_repo(root), "improve main.py", "File: main.py", None, []))
    assert changed == ["main.py"]
    # The security invariant: planning a modify must never touch the filesystem.
    assert target.read_bytes() == original


def test_apply_approved_rolls_back_and_rehashes(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    original = b"answer = 1\n"
    target.write_bytes(original)
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    proposal = _proposal("main.py", "modify", original, b"answer = 2\n")

    # Approved apply that fails validation must roll the file back.
    monkeypatch.setattr("app.agents.patching.run_validation", lambda workspace, changed: SimpleNamespace(status="failed", checks=[SimpleNamespace(name="pytest", status="failed", summary="boom")]))
    result = asyncio.run(PatchWorkflow(PatchLLM([])).apply_approved(_repo(root), "improve main.py", proposal, ["main.py"], "File: main.py", None, []))
    assert result.status == "failed"
    assert target.read_bytes() == original

    # Approved apply whose file changed since approval must be rejected (hash conflict).
    target.write_bytes(b"answer = 9\n")
    monkeypatch.setattr("app.agents.patching.run_validation", lambda workspace, changed: SimpleNamespace(status="passed", checks=[]))
    try:
        asyncio.run(PatchWorkflow(PatchLLM([])).apply_approved(_repo(root), "improve main.py", proposal, ["main.py"], "File: main.py"))
    except PatchConflictError:
        pass
    else:
        raise AssertionError("apply_approved applied a proposal whose hash no longer matches")


def test_apply_approved_applies_when_validated(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "main.py"
    original = b"answer = 1\n"
    target.write_bytes(original)
    monkeypatch.setattr("app.agents.patching.get_settings", lambda: _settings(root))
    proposal = _proposal("main.py", "modify", original, b"answer = 2\n")
    monkeypatch.setattr("app.agents.patching.run_validation", lambda workspace, changed: SimpleNamespace(status="passed", checks=[]))
    result = asyncio.run(PatchWorkflow(PatchLLM([])).apply_approved(_repo(root), "improve main.py", proposal, ["main.py"], "File: main.py"))
    assert result.status == "completed"
    assert target.read_bytes() == b"answer = 2\n"
