"""Task planning, shared context, sequential execution, and graceful failure."""

from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass

from app.agents.models import AgentTaskResult, SkillResult, TaskStatus
from app.agents.router import route_task
from app.agents.skills import SkillExecutor
from app.core.llm import LLMService
from app.core.retriever import RetrievalQuery, RetrieverService
from app.core.skill_registry import SkillName
from app.agents.patching import PatchWorkflow


@dataclass
class PlannedModification:
    """A validated but NOT-yet-applied patch, ready for human review/approval."""

    repository_id: int
    task: str
    context: str
    route: str | None
    acceptance_criteria: list[str]
    proposal: object
    changed_paths: list[str]


class AgentOrchestrator:
    def __init__(self, retriever: RetrieverService, llm: LLMService) -> None:
        self.retriever = retriever
        self.executor = SkillExecutor(llm)

    async def run(self, repository_id: int, task: str, top_k: int, acceptance_criteria: list[str] | None = None, image_data_url: str | None = None, route: str | None = None, mode: str = "analyze", repository: object | None = None, *, workspace_id: str) -> AgentTaskResult:
        started = time.perf_counter()
        skills = route_task(task)
        if mode == "modify":
            if repository is None:
                raise ValueError("Repository metadata is required for modify mode.")
            retrieval = await asyncio.to_thread(self.retriever.retrieve, RetrievalQuery(text=f"frontend implementation context for requested change: {task}", repository_id=str(repository_id), top_k=top_k, workspace_id=workspace_id))
            modification = await PatchWorkflow(self.executor.llm).run(repository, task, retrieval.assembled_context, route, acceptance_criteria or [])
            return AgentTaskResult(task, skills, TaskStatus.COMPLETED if modification.status == "completed" else TaskStatus.FAILED, modification.summary, [], time.perf_counter() - started, modification.errors, _modification_dict(modification), mode)
        if not skills:
            retrieval = await asyncio.to_thread(self.retriever.retrieve, RetrievalQuery(text=task, repository_id=str(repository_id), top_k=top_k, workspace_id=workspace_id))
            answer = await self.executor.llm.generate_answer(retrieval)
            return AgentTaskResult(task, [], TaskStatus.COMPLETED, answer.answer, [], time.perf_counter() - started)
        retrieval = await asyncio.to_thread(self.retriever.retrieve, RetrievalQuery(text=f"frontend UI conventions and implementation context: {task}", repository_id=str(repository_id), top_k=top_k, workspace_id=workspace_id))
        context = retrieval.assembled_context
        results: list[SkillResult] = []
        prior = ""
        for skill in skills:
            skill_started = time.perf_counter()
            try:
                output = await self.executor.execute(skill, task, context, prior, acceptance_criteria or [], image_data_url, route)
                summary = output.get("message") or output.get("analysis") or output.get("answer", "Skill completed")
                tool_unavailable = skill is SkillName.PLAYWRIGHT_CLI and output.get("tool_available") is False
                verification_failed = skill is SkillName.PLAYWRIGHT_CLI and output.get("tool_available") is True and output.get("verified") is False
                result_status = TaskStatus.SKIPPED if tool_unavailable else TaskStatus.FAILED if verification_failed else TaskStatus.COMPLETED
                result_errors = [str(summary)] if verification_failed else []
                result = SkillResult(skill, result_status, str(summary)[:500], output, result_errors, time.perf_counter() - skill_started)
                prior += f"\n[{skill.value}]\n{summary}"
            except Exception as exc:  # one specialist must not corrupt task state
                result = SkillResult(skill, TaskStatus.FAILED, f"{skill.value} failed", {}, [str(exc)], time.perf_counter() - skill_started)
                results.append(result)
                if skill is not SkillName.PLAYWRIGHT_CLI:
                    continue
                continue
            results.append(result)
        failures = [error for result in results for error in result.errors]
        final = prior.strip() or "No specialist produced an output."
        status = TaskStatus.FAILED if failures and all(result.status is not TaskStatus.COMPLETED for result in results) else TaskStatus.COMPLETED
        return AgentTaskResult(task, skills, status, final, results, time.perf_counter() - started, failures, None, mode)

    async def plan_modify(self, repository_id: int, task: str, top_k: int, route: str | None, acceptance_criteria: list[str] | None, repository: object, *, workspace_id: str) -> PlannedModification:
        """Plan a modify-mode change WITHOUT writing any file or executing code.

        Returns a validated proposal that must be explicitly approved (by a human
        via the approval endpoint) before ``apply_modify`` may run.
        """
        retrieval = await asyncio.to_thread(self.retriever.retrieve, RetrievalQuery(text=f"frontend implementation context for requested change: {task}", repository_id=str(repository_id), top_k=top_k, workspace_id=workspace_id))
        context = retrieval.assembled_context
        proposal, changed_paths = await PatchWorkflow(self.executor.llm).plan(repository, task, context, route, acceptance_criteria or [])
        return PlannedModification(repository_id, task, context, route, acceptance_criteria or [], proposal, changed_paths)

    async def apply_modify(self, repository_id: int, task: str, context: str, proposal: object, changed_paths: list[str], route: str | None, acceptance_criteria: list[str] | None, repository: object) -> AgentTaskResult:
        """Apply an already human-approved, validated proposal (hash-checked, atomic, rollback-aware)."""
        started = time.perf_counter()
        modification = await PatchWorkflow(self.executor.llm).apply_approved(repository, task, proposal, changed_paths, context, route, acceptance_criteria or [])
        result_status = TaskStatus.COMPLETED if modification.status == "completed" else TaskStatus.FAILED
        return AgentTaskResult(task, [], result_status, modification.summary, [], time.perf_counter() - started, modification.errors, _modification_dict(modification), "modify")


def _modification_dict(modification) -> dict:
    return {
        "status": modification.status,
        "files_changed": modification.files_changed,
        "operations": [{"path": item.path, "operation": item.operation, "old_content_hash": item.old_content_hash} for item in modification.operations],
        "validation": {"status": modification.validation.status, "checks": [{"name": item.name, "status": item.status, "summary": item.summary} for item in modification.validation.checks]},
        "attempts": modification.attempts,
        "summary": modification.summary,
        "errors": modification.errors,
        "playwright": modification.playwright,
    }
