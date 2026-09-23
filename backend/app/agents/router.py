"""Deterministic intent routing for agent tasks."""

from __future__ import annotations

from app.core.skill_registry import SkillName


def route_task(task: str) -> list[SkillName]:
    text = task.casefold()
    image = any(term in text for term in ("screenshot", "image to code", "reference image", "recreate this ui"))
    verify = any(term in text for term in ("playwright", "browser test", "verify the page", "test the ui", "check the dashboard"))
    taste = any(term in text for term in ("review the ui", "review the dashboard", "review dashboard design", "critique", "visual review", "make this look better", "design audit"))
    guidelines = any(term in text for term in ("design guideline", "spacing", "typography", "responsive layout", "accessibility"))
    redesign = any(term in text for term in ("redesign", "improve the dashboard", "make the chat page better", "implementation direction"))
    if image:
        return [SkillName.IMAGE_TO_CODE]
    skills: list[SkillName] = []
    if taste:
        skills.append(SkillName.TASTE)
    if guidelines:
        skills.append(SkillName.WEB_DESIGN_GUIDELINES)
    if redesign:
        for skill in (SkillName.TASTE, SkillName.WEB_DESIGN_GUIDELINES, SkillName.AWESOME_DESIGN):
            if skill not in skills:
                skills.append(skill)
    if verify:
        skills.extend(skill for skill in (SkillName.PLAYWRIGHT_CLI,) if skill not in skills)
    return skills
