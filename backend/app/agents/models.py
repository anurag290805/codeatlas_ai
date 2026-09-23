"""Typed state and result models for agent tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.skill_registry import SkillName


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SkillResult:
    skill: SkillName
    status: TaskStatus
    summary: str
    output: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class AgentTaskResult:
    task: str
    selected_skills: list[SkillName]
    status: TaskStatus
    final_result: str
    skill_results: list[SkillResult]
    duration_seconds: float
    errors: list[str] = field(default_factory=list)
    modification: dict[str, Any] | None = None
    mode: str = "analyze"
