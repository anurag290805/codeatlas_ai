"""Executable-skill contracts for the CodeAtlas agent layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SkillName(str, Enum):
    TASTE = "taste"
    WEB_DESIGN_GUIDELINES = "web_design_guidelines"
    AWESOME_DESIGN = "awesome_design"
    IMAGE_TO_CODE = "image_to_code"
    PLAYWRIGHT_CLI = "playwright_cli"


@dataclass(frozen=True)
class SkillDefinition:
    name: SkillName
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    requires_external_tool: bool = False


SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        SkillName.TASTE,
        "Evaluate visual hierarchy, consistency, accessibility, and product fit.",
        ("screenshots or UI code", "product context"),
        ("prioritized critique", "concrete design changes"),
    ),
    SkillDefinition(
        SkillName.WEB_DESIGN_GUIDELINES,
        "Turn a design brief into reusable web UI rules and component guidance.",
        ("design brief", "target viewport", "existing frontend conventions"),
        ("layout rules", "typography and color tokens", "component guidance"),
    ),
    SkillDefinition(
        SkillName.AWESOME_DESIGN,
        "Generate an implementation-ready page or component direction using the repo style.",
        ("feature brief", "design guidelines", "repository context"),
        ("responsive UI plan", "implementation checklist"),
    ),
    SkillDefinition(
        SkillName.IMAGE_TO_CODE,
        "Translate a supplied UI image into frontend structure and styling.",
        ("reference image", "target frontend stack"),
        ("component tree", "CSS or styling plan", "visual verification checklist"),
        requires_external_tool=True,
    ),
    SkillDefinition(
        SkillName.PLAYWRIGHT_CLI,
        "Exercise and verify the UI through browser flows and screenshots.",
        ("route or user flow", "acceptance criteria"),
        ("test result", "screenshots", "regression notes"),
        requires_external_tool=True,
    ),
)


def all_skill_names() -> tuple[SkillName, ...]:
    """Return the stable registry order used by routing and API clients."""
    return tuple(skill.name for skill in SKILLS)


def get_skill(name: SkillName | str) -> SkillDefinition:
    """Return a registered capability by enum value or string name."""
    normalized = name.value if isinstance(name, SkillName) else str(name).strip().lower()
    for skill in SKILLS:
        if skill.name.value == normalized:
            return skill
    raise KeyError(f"Unknown CodeAtlas skill: {name}")
