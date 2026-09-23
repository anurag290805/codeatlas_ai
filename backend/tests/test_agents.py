from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.agents.router import route_task
from app.agents.service import AgentOrchestrator
from app.core.skill_registry import SkillName, get_skill
from app.core.llm import LLMRequest, OmniRouteProvider
from app.core.config import Settings
from app.models.schemas import AgentTaskRequest


def test_skill_registry_lookup() -> None:
    assert get_skill("taste").name is SkillName.TASTE
    assert get_skill(SkillName.PLAYWRIGHT_CLI).requires_external_tool


def test_intent_routing() -> None:
    assert route_task("Review the UI") == [SkillName.TASTE]
    assert route_task("Redesign the dashboard and verify the page") == [SkillName.TASTE, SkillName.WEB_DESIGN_GUIDELINES, SkillName.AWESOME_DESIGN, SkillName.PLAYWRIGHT_CLI]
    assert route_task("Where is authentication handled?") == []
    assert route_task("Convert this screenshot to code") == [SkillName.IMAGE_TO_CODE]


class FakeRetriever:
    def retrieve(self, query):
        return SimpleNamespace(assembled_context="File: frontend/src/App.tsx\nconst App = () => null", query=query, citations=[])


class FakeLLM:
    provider_name = SimpleNamespace(value="omniroute")
    model_name = "auto/best-free"

    def __init__(self):
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return SimpleNamespace(answer=f"analysis for {request.query[:30]}", provider=self.provider_name, model=self.model_name)

    async def generate_answer(self, retrieval):
        return SimpleNamespace(answer="normal repository answer")


def test_single_skill_orchestration() -> None:
    llm = FakeLLM()
    result = asyncio.run(AgentOrchestrator(FakeRetriever(), llm).run(1, "Review the UI", 3, workspace_id="test-workspace"))
    assert result.status.value == "completed"
    assert result.selected_skills == [SkillName.TASTE]
    assert result.skill_results[0].output["skill"] == "taste"
    assert "frontend/src/App.tsx" in llm.requests[0].context


def test_sequential_orchestration_and_normal_fallback() -> None:
    llm = FakeLLM()
    orchestrator = AgentOrchestrator(FakeRetriever(), llm)
    result = asyncio.run(orchestrator.run(1, "Redesign the dashboard and verify the page", 3, workspace_id="test-workspace"))
    assert result.selected_skills == [SkillName.TASTE, SkillName.WEB_DESIGN_GUIDELINES, SkillName.AWESOME_DESIGN, SkillName.PLAYWRIGHT_CLI]
    assert len(result.skill_results) == 4
    assert "analysis for" in llm.requests[1].query
    fallback = asyncio.run(orchestrator.run(1, "Where is authentication handled?", 3, workspace_id="test-workspace"))
    assert fallback.selected_skills == []
    assert fallback.final_result == "normal repository answer"


def test_playwright_unavailable_is_structured(monkeypatch) -> None:
    import app.agents.skills as skills

    monkeypatch.setattr(skills.shutil, "which", lambda _: None)
    output = skills.SkillExecutor(FakeLLM())._playwright("test the UI")
    assert output["tool_available"] is False
    assert "not run" in output["message"]


def test_playwright_captures_localhost_screenshot(monkeypatch) -> None:
    import app.agents.skills as skills

    monkeypatch.setattr(skills.shutil, "which", lambda _: "/usr/local/bin/playwright")

    def fake_run(command, **kwargs):
        directory = Path(command[2]).parent
        Path(directory / "result.json").write_text('{"route_exists":true,"passed_criteria":["Dashboard heading is visible"],"failed_criteria":[],"warnings":[],"console_errors":[],"runtime_errors":[]}', encoding="utf-8")
        Path(directory / "page.png").write_bytes(b"png-bytes")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(skills.subprocess, "run", fake_run)
    output = skills.SkillExecutor(FakeLLM())._playwright("verify http://localhost:5173/chat")
    assert output["verified"] is True
    assert output["screenshot_base64"] == "cG5nLWJ5dGVz"


def test_playwright_rejects_non_localhost_and_unknown_actions(monkeypatch) -> None:
    import app.agents.skills as skills

    monkeypatch.setattr(skills.shutil, "which", lambda _: "/usr/local/bin/playwright")
    output = skills.SkillExecutor(FakeLLM())._playwright("verify https://example.com", ["Run arbitrary JavaScript"])
    assert output["verified"] is False
    assert "Non-localhost URL rejected." in output["warnings"]
    output = skills.SkillExecutor(FakeLLM())._playwright("verify http://localhost:5173", ["Run arbitrary JavaScript"])
    assert "Unsupported acceptance criterion: Run arbitrary JavaScript" in output["warnings"]
    from pydantic import ValidationError

    try:
        AgentTaskRequest(repository_id=1, task="verify", route="http://user:pass@localhost:5173")
    except ValidationError:
        pass
    else:
        raise AssertionError("credential-bearing route was accepted")


def test_playwright_maps_safe_criteria_and_reports_results(monkeypatch) -> None:
    import app.agents.skills as skills

    monkeypatch.setattr(skills.shutil, "which", lambda _: "/usr/local/bin/playwright")

    def fake_run(command, **kwargs):
        spec = Path(command[2]).read_text(encoding="utf-8")
        assert "Dashboard heading is visible" in spec
        assert "No browser console errors" in spec
        directory = Path(command[2]).parent
        Path(directory / "result.json").write_text('{"route_exists":true,"passed_criteria":["Dashboard heading is visible"],"failed_criteria":["No browser console errors"],"warnings":[],"console_errors":["boom"],"runtime_errors":[]}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(skills.subprocess, "run", fake_run)
    output = skills.SkillExecutor(FakeLLM())._playwright("verify http://127.0.0.1:5173", ["Dashboard heading is visible", "No browser console errors"])
    assert output["passed_criteria"] == ["Dashboard heading is visible"]
    assert output["failed_criteria"] == ["No browser console errors"]
    assert output["console_errors"] == ["boom"]
    assert output["verified"] is False


def test_image_contract_rejects_invalid_and_oversized_images() -> None:
    import pydantic

    try:
        AgentTaskRequest(repository_id=1, task="convert image", image_data_url="data:text/plain;base64,Zm9v")
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError("non-image data URL was accepted")
    try:
        AgentTaskRequest(repository_id=1, task="convert image", image_data_url="data:image/png;base64," + ("A" * 7_000_000))
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError("oversized image was accepted")


def test_image_skill_no_image_and_vision_unavailable(monkeypatch) -> None:
    import app.agents.skills as skills
    from app.core.llm import LLMVisionUnavailableError

    llm = FakeLLM()
    no_image = asyncio.run(skills.SkillExecutor(llm).execute(SkillName.IMAGE_TO_CODE, "convert image", "repo context", "", [], None))
    assert no_image["image_supplied"] is False
    assert no_image["image_analysis_status"] == "not_supplied"

    async def unavailable(request):
        raise LLMVisionUnavailableError("vision unavailable")

    monkeypatch.setattr(llm, "generate", unavailable)
    supplied = asyncio.run(skills.SkillExecutor(llm).execute(SkillName.IMAGE_TO_CODE, "convert image", "repo context", "", [], "data:image/png;base64,iVBORw0KGgo="))
    assert supplied["image_analysis_status"] == "vision_unavailable"
    assert supplied["findings"] == []


def test_image_skill_uses_image_capable_llm_when_available() -> None:
    import app.agents.skills as skills

    class VisionLLM(FakeLLM):
        async def generate(self, request):
            self.requests.append(request)
            return SimpleNamespace(answer='{"findings":["Card layout visible"],"priority":[],"recommendations":["Use a responsive card grid"],"acceptance_criteria":[]}', provider=self.provider_name, model=self.model_name)

    llm = VisionLLM()
    supplied = asyncio.run(skills.SkillExecutor(llm).execute(SkillName.IMAGE_TO_CODE, "convert image", "repo context", "", [], "data:image/png;base64,iVBORw0KGgo="))
    assert supplied["image_analysis_status"] == "completed"
    assert supplied["findings"] == ["Card layout visible"]
    assert llm.requests[0].image_data_url.startswith("data:image/png")


def test_omniroute_receives_multimodal_content_without_new_client() -> None:
    import httpx

    class FakeClient:
        def __init__(self):
            self.body = None

        async def post(self, url, **kwargs):
            self.body = kwargs["json"]
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        async def get(self, url, **kwargs):
            return httpx.Response(200, json={"data": []})

        async def aclose(self):
            pass

    client = FakeClient()
    provider = OmniRouteProvider(Settings(_env_file=None), client)
    asyncio.run(provider.generate(LLMRequest(query="describe image", image_data_url="data:image/png;base64,iVBORw0KGgo=")))
    assert client.body["messages"][1]["content"][1]["type"] == "image_url"
    assert "untrusted data" in provider._SYSTEM_PROMPT
