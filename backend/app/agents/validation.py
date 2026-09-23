"""Fixed, non-user-configurable validation profiles for applied patches."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    status: str
    summary: str


@dataclass(frozen=True)
class ValidationResult:
    status: str
    checks: list[ValidationCheck]


_PROFILES: dict[str, tuple[tuple[str, ...], ...]] = {
    "backend": ((sys.executable, "-m", "compileall", "-q", "app", "tests"), (sys.executable, "-m", "pytest", "-q")),
    "frontend": (("npm", "run", "lint"), ("npx", "tsc", "-b"), ("npm", "run", "build")),
}


def run_validation(workspace: Path, changed_paths: list[str]) -> ValidationResult:
    profiles = set()
    if any(path.startswith("backend/") for path in changed_paths):
        profiles.add("backend")
    if any(path.startswith("frontend/") for path in changed_paths):
        profiles.add("frontend")
    if not profiles:
        return ValidationResult(
            "passed",
            [ValidationCheck("scope", "passed", "No backend or frontend files changed; code validation was not applicable.")],
        )

    checks: list[ValidationCheck] = []
    for profile in ("backend", "frontend"):
        if profile not in profiles:
            continue
        cwd = workspace / profile
        for command in _PROFILES[profile]:
            check = _run_check(cwd, command)
            checks.append(check)
            if check.status == "failed":
                return ValidationResult("failed", checks)
    return ValidationResult("passed", checks)


def _run_check(cwd: Path, command: tuple[str, ...]) -> ValidationCheck:
    name = " ".join(command[1:] if command[0] == sys.executable else command)
    with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        try:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ValidationCheck(name, "failed", str(exc))
        if completed.returncode == 0:
            return ValidationCheck(name, "passed", "Command completed successfully.")
        stderr.seek(0)
        detail = stderr.read(4000).decode("utf-8", errors="replace").strip()
        if not detail:
            stdout.seek(0)
            detail = stdout.read(4000).decode("utf-8", errors="replace").strip()
        return ValidationCheck(name, "failed", detail or f"Command exited with status {completed.returncode}.")
