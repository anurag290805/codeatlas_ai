"""Dependency manifest extraction into a stable CodeAtlas model."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Dependency(BaseModel):
    ecosystem: str
    name: str
    installed_version: str | None = None
    requested_version: str | None = None
    dependency_type: str = "runtime"
    source_file: str


_VERSION = re.compile(r"(?:==|===|~=|>=|<=|>|<|=|\s+)?v?([0-9]+(?:\.[0-9]+){0,2}(?:[-+][0-9A-Za-z.-]+)?)")


def _version(value: Any) -> str | None:
    match = _VERSION.search(str(value or ""))
    return match.group(1) if match else None


def _npm_package_json(path: Path) -> list[Dependency]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    results: list[Dependency] = []
    for section, dependency_type in (("dependencies", "runtime"), ("devDependencies", "development"), ("peerDependencies", "peer")):
        for name, requested in (payload.get(section) or {}).items():
            results.append(Dependency(ecosystem="npm", name=name, requested_version=str(requested), source_file="package.json", dependency_type=dependency_type))
    return results


def _npm_lock(path: Path) -> list[Dependency]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    packages = payload.get("packages") or {}
    results: list[Dependency] = []
    for key, data in packages.items():
        if not key or key == "" or not isinstance(data, dict) or not data.get("version"):
            continue
        name = key.removeprefix("node_modules/")
        if "/node_modules/" in name:
            name = name.rsplit("/node_modules/", 1)[-1]
        results.append(Dependency(ecosystem="npm", name=name, installed_version=_version(data["version"]), requested_version=_version(data.get("resolved") or data.get("version")), source_file="package-lock.json"))
    return results


def _requirements(path: Path) -> list[Dependency]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    results: list[Dependency] = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http:" , "https:")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)$", line)
        if match:
            results.append(Dependency(ecosystem="PyPI", name=match.group(1), installed_version=_version(match.group(2)), requested_version=match.group(2) or None, source_file="requirements.txt"))
    return results


def _pyproject(path: Path) -> list[Dependency]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    sections = [payload.get("project", {}).get("dependencies", [])]
    poetry = payload.get("tool", {}).get("poetry", {})
    sections.append([f"{key} {value}" for key, value in (poetry.get("dependencies") or {}).items() if key.lower() != "python"])
    results: list[Dependency] = []
    for section in sections:
        for item in section:
            if isinstance(item, str):
                match = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)$", item)
                if match:
                    results.append(Dependency(ecosystem="PyPI", name=match.group(1), installed_version=_version(match.group(2)), requested_version=match.group(2) or None, source_file="pyproject.toml"))
    return results


def extract_dependencies(root: str | Path) -> list[Dependency]:
    directory = Path(root)
    candidates: list[Dependency] = []
    for filename, parser in (("package-lock.json", _npm_lock), ("package.json", _npm_package_json), ("requirements.txt", _requirements), ("pyproject.toml", _pyproject)):
        path = directory / filename
        if path.is_file():
            candidates.extend(parser(path))
    deduped: dict[tuple[str, str], Dependency] = {}
    for item in candidates:
        key = (item.ecosystem.lower(), item.name.lower())
        existing = deduped.get(key)
        if existing is None or (item.installed_version and not existing.installed_version) or item.source_file.endswith("lock.json"):
            deduped[key] = item
    return list(deduped.values())
