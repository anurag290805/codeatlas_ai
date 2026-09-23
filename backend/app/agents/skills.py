"""Concrete skill executors. Text skills use the existing LLMService only."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import asyncio
import base64
import json
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any

from app.core.llm import LLMRequest, LLMService, LLMServiceError, ResponseFormat
from app.core.skill_registry import SkillName


@dataclass(frozen=True)
class PlaywrightAction:
    kind: str
    value: str = ""
    label: str = ""


_SAFE_SELECTORS = {
    "dashboard heading": "h1",
    "repository selector": "[role='combobox'], select",
    "chat input": "textarea",
    "send button": "button[type='submit']",
}
_MAX_BROWSER_ERRORS = 100
_MAX_BROWSER_ERROR_LENGTH = 1000
_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024


class SkillExecutor:
    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    async def execute(self, skill: SkillName, task: str, context: str, prior: str, acceptance_criteria: list[str], image_data_url: str | None = None, route: str | None = None) -> dict[str, Any]:
        if skill is SkillName.PLAYWRIGHT_CLI:
            return await asyncio.to_thread(self._playwright, task, acceptance_criteria, route)
        prompt = self._prompt(skill, task, context, prior, bool(image_data_url))
        try:
            response = await self.llm.generate(LLMRequest(query=prompt, context=context, response_format=ResponseFormat.MARKDOWN, max_tokens=700, image_data_url=image_data_url if skill is SkillName.IMAGE_TO_CODE else None))
        except LLMServiceError as exc:
            if skill is SkillName.IMAGE_TO_CODE and image_data_url:
                return {"skill": skill.value, "image_supplied": True, "image_analysis_status": "vision_unavailable", "message": str(exc), "findings": [], "component_candidates": [], "typography_observations": [], "spacing_observations": [], "color_observations": [], "responsive_considerations": [], "implementation_recommendations": []}
            raise
        structured = _structured_answer(response.answer)
        structured.update({"skill": skill.value, "provider": response.provider.value, "model": response.model})
        if skill is SkillName.IMAGE_TO_CODE:
            structured["image_supplied"] = bool(image_data_url)
            structured["image_analysis_status"] = "completed" if image_data_url else "not_supplied"
            structured.setdefault("detected_layout", [])
            structured.setdefault("component_candidates", [])
            structured.setdefault("typography_observations", [])
            structured.setdefault("spacing_observations", [])
            structured.setdefault("color_observations", [])
            structured.setdefault("responsive_considerations", [])
            structured.setdefault("implementation_recommendations", structured.get("recommendations", []))
            if not image_data_url:
                structured["image_evidence"] = "No image was supplied; visual analysis was unavailable."
        return structured

    @staticmethod
    def _prompt(skill: SkillName, task: str, context: str, prior: str, image_supplied: bool = False) -> str:
        evidence = "Source code is the only evidence; label code-derived findings and do not invent visual observations." if skill is SkillName.TASTE else "Use the supplied repository context and preserve existing frontend conventions."
        image_instruction = "Analyze the supplied image and populate visual fields only from what is visible." if image_supplied else "No image was supplied; leave visual fields empty and state that visual analysis was unavailable."
        return f"""Act as the CodeAtlas {skill.value} specialist. {evidence}
Return ONLY a JSON object with string-array keys: findings, priority, recommendations, and acceptance_criteria. Base every item on the repository context or task. Do not claim tools or screenshots you did not receive.
{image_instruction}
Task: {task}
Previous specialist outputs (may be empty): {prior or '(none)'}
Repository context is supplied separately."""

    @staticmethod
    def _playwright(task: str, acceptance_criteria: list[str] | None = None, route: str | None = None) -> dict[str, Any]:
        executable = shutil.which("playwright")
        if not executable:
            return {"tool_available": False, "message": "Playwright CLI is unavailable; browser verification was not run.", "passed_criteria": [], "failed_criteria": acceptance_criteria or [], "warnings": ["Install the Playwright CLI and browser binaries to enable verification."]}
        route = route or next((word for word in task.split() if urlparse(word).scheme in {"http", "https"}), None)
        parsed_route = urlparse(route) if route else None
        if route and (parsed_route.hostname not in {"localhost", "127.0.0.1"} or parsed_route.username or parsed_route.password):
            return {"tool_available": True, "verified": False, "message": "Rejected: browser verification only targets localhost or 127.0.0.1 URLs.", "passed_criteria": [], "failed_criteria": acceptance_criteria or [], "warnings": ["Non-localhost URL rejected."]}
        if not route:
            return {"tool_available": True, "verified": False, "message": "Playwright is installed, but no localhost route was supplied.", "passed_criteria": [], "failed_criteria": acceptance_criteria or [], "warnings": ["Supply a localhost URL in the task."]}
        actions, unsupported = _controlled_actions(acceptance_criteria or [])
        with tempfile.TemporaryDirectory(prefix="codeatlas-playwright-") as directory:
            result_path = Path(directory) / "result.json"
            screenshot_path = Path(directory) / "page.png"
            spec_path = Path(directory) / "codeatlas.spec.mjs"
            spec_path.write_text(_playwright_spec(route, actions, result_path, screenshot_path), encoding="utf-8")
            try:
                completed = subprocess.run([executable, "test", str(spec_path), "--reporter=line"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"tool_available": True, "verified": False, "message": f"Playwright could not complete: {exc}", "passed_criteria": [], "failed_criteria": acceptance_criteria or [], "warnings": unsupported}
            if not result_path.exists():
                return {"tool_available": True, "verified": False, "message": "Playwright did not produce a verification result.", "passed_criteria": [], "failed_criteria": acceptance_criteria or [], "warnings": unsupported}
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if screenshot_path.exists():
                screenshot_bytes = screenshot_path.read_bytes()
                if len(screenshot_bytes) <= _MAX_SCREENSHOT_BYTES:
                    result["screenshot_base64"] = base64.b64encode(screenshot_bytes).decode("ascii")
                else:
                    result.setdefault("warnings", []).append("Screenshot exceeded the 5 MiB response limit and was omitted.")
        result["tool_available"] = True
        result["warnings"] = unsupported + result.get("warnings", [])
        result["verified"] = bool(result.get("route_exists")) and not result.get("failed_criteria") and not result.get("console_errors") and not result.get("runtime_errors")
        result["message"] = "Browser verification completed." if result["verified"] else "Browser verification found failures."
        return result


def _controlled_actions(criteria: list[str]) -> tuple[list[PlaywrightAction], list[str]]:
    actions = [PlaywrightAction("screenshot"), PlaywrightAction("title"), PlaywrightAction("visible_text"), PlaywrightAction("console_errors"), PlaywrightAction("runtime_errors")]
    unsupported: list[str] = []
    for criterion in criteria:
        normalized = criterion.casefold().strip()
        if normalized in {"no browser console errors", "no console errors"}:
            actions.append(PlaywrightAction("console_empty", label=criterion))
        elif normalized in {"no page runtime errors", "no runtime errors", "no browser runtime errors"}:
            actions.append(PlaywrightAction("runtime_empty", label=criterion))
        elif normalized.startswith("title contains:"):
            actions.append(PlaywrightAction("title_contains", criterion.split(":", 1)[1].strip(), criterion))
        elif normalized.startswith("visible text:"):
            actions.append(PlaywrightAction("visible_text_contains", criterion.split(":", 1)[1].strip(), criterion))
        elif any(label in normalized for label in _SAFE_SELECTORS) and ("visible" in normalized or "exist" in normalized or "present" in normalized):
            label = next(label for label in _SAFE_SELECTORS if label in normalized)
            actions.append(PlaywrightAction("selector_visible", label, criterion))
        else:
            unsupported.append(f"Unsupported acceptance criterion: {criterion}")
    return actions, unsupported


def _playwright_spec(route: str, actions: list[PlaywrightAction], result_path: Path, screenshot_path: Path) -> str:
    serialized_actions = json.dumps([{"kind": action.kind, "value": action.value, "label": action.label} for action in actions])
    route_json = json.dumps(route)
    result_json = json.dumps(str(result_path))
    screenshot_json = json.dumps(str(screenshot_path))
    selectors_json = json.dumps(_SAFE_SELECTORS)
    return f"""import {{ test }} from '@playwright/test';
import fs from 'node:fs';
const actions = {serialized_actions};
const selectors = {selectors_json};
const resultPath = {result_json};
const screenshotPath = {screenshot_json};
test('CodeAtlas controlled localhost verification', async ({{ page }}) => {{
  const result = {{ route_exists: false, title: '', visible_text: '', passed_criteria: [], failed_criteria: [], warnings: [], console_errors: [], runtime_errors: [] }};
  const addBounded = (list, value) => {{ if (list.length < {_MAX_BROWSER_ERRORS}) list.push(String(value).slice(0, {_MAX_BROWSER_ERROR_LENGTH})); }};
  const isLocalHttp = value => {{ try {{ const parsed = new URL(value); return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') && !parsed.username && !parsed.password; }} catch {{ return false; }} }};
  await page.route('**/*', async requestRoute => {{ if (!isLocalHttp(requestRoute.request().url())) {{ addBounded(result.warnings, 'Blocked non-local browser request.'); await requestRoute.abort(); }} else {{ await requestRoute.continue(); }} }});
  page.on('console', message => {{ if (message.type() === 'error') addBounded(result.console_errors, message.text()); }});
  page.on('pageerror', error => addBounded(result.runtime_errors, error.message));
  try {{
    const response = await page.goto({route_json}, {{ waitUntil: 'domcontentloaded', timeout: 30000 }});
    result.route_exists = Boolean(response && response.ok() && isLocalHttp(page.url()));
    if (!result.route_exists) addBounded(result.warnings, `Route returned ${{response ? response.status() : 'no response'}} or redirected outside localhost.`);
    if (result.route_exists) {{
      result.title = await page.title();
      result.visible_text = (await page.locator('body').innerText()).slice(0, 20000);
      await page.waitForTimeout(250);
      for (const action of actions) {{
        if (action.kind === 'screenshot') await page.screenshot({{ path: screenshotPath, fullPage: true }});
        if (action.kind === 'title_contains') (result.title.toLowerCase().includes(action.value.toLowerCase()) ? result.passed_criteria : result.failed_criteria).push(action.label);
        if (action.kind === 'visible_text_contains') (result.visible_text.toLowerCase().includes(action.value.toLowerCase()) ? result.passed_criteria : result.failed_criteria).push(action.label);
        if (action.kind === 'selector_visible') {{ const visible = await page.locator(selectors[action.value]).first().isVisible(); (visible ? result.passed_criteria : result.failed_criteria).push(action.label); }}
        if (action.kind === 'console_empty') (result.console_errors.length ? result.failed_criteria : result.passed_criteria).push(action.label);
        if (action.kind === 'runtime_empty') (result.runtime_errors.length ? result.failed_criteria : result.passed_criteria).push(action.label);
      }}
    }}
  }} catch (error) {{ addBounded(result.warnings, error); }}
  fs.writeFileSync(resultPath, JSON.stringify(result));
}});
"""


def _structured_answer(answer: str) -> dict[str, Any]:
    """Accept the requested structured contract without inventing findings."""
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        return {"analysis": answer, "findings": [answer], "priority": [], "recommendations": [], "acceptance_criteria": []}
    if not isinstance(parsed, dict):
        return {"analysis": answer, "findings": [answer], "priority": [], "recommendations": [], "acceptance_criteria": []}
    return {
        key: [str(item) for item in parsed.get(key, [])] if isinstance(parsed.get(key, []), list) else []
        for key in ("findings", "priority", "recommendations", "acceptance_criteria")
    }
