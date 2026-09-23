"""Optional GitHub, package metadata, and OSV intelligence endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import crud
from app.db.database import get_db
from app.core.auth import get_workspace_id
from app.core.workspace import ensure_workspace
from app.integrations.dependencies import Dependency, extract_dependencies
from app.integrations.github import GithubClient
from app.integrations.npm import NpmClient
from app.integrations.osv import OsvClient
from app.integrations.pypi import PypiClient
from app.models import schemas

router = APIRouter(prefix="/repositories", tags=["intelligence"], dependencies=[Depends(ensure_workspace)])


def _repository(repository_id: int, db: Session, workspace_id: str | None):
    repository = crud.get_repository(db, repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repository_id}")
    return repository


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = re.match(r"^[v=]?([0-9]+(?:\.[0-9]+){0,2})", value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _status(installed: str | None, latest: str | None, vulnerabilities: list[schemas.VulnerabilityResponse]) -> str:
    if vulnerabilities:
        return "vulnerable"
    current, newest = _version_tuple(installed), _version_tuple(latest)
    if current and newest and newest > current:
        return "outdated"
    if current and newest:
        return "up-to-date"
    return "unknown"


def _vulnerabilities(item: Dependency, client: OsvClient) -> list[schemas.VulnerabilityResponse]:
    normalized: list[schemas.VulnerabilityResponse] = []
    for raw in client.vulnerabilities(item.ecosystem, item.name, item.installed_version):
        affected: list[str] = []
        fixed: list[str] = []
        for affected_record in raw.get("affected", []):
            for version in affected_record.get("versions", []):
                if isinstance(version, str):
                    affected.append(version)
            for range_record in affected_record.get("ranges", []):
                for event in range_record.get("events", []):
                    if isinstance(event, dict) and isinstance(event.get("fixed"), str):
                        fixed.append(event["fixed"])
        severity = "Unknown"
        for item_severity in raw.get("severity", []):
            if isinstance(item_severity, dict) and isinstance(item_severity.get("type"), str):
                score = str(item_severity.get("score", ""))
                severity = "Critical" if score.startswith("10") else "High" if score.startswith(("7", "8", "9")) else "Moderate" if score.startswith(("4", "5", "6")) else "Low"
                break
        references = [ref["url"] for ref in raw.get("references", []) if isinstance(ref, dict) and isinstance(ref.get("url"), str)]
        normalized.append(schemas.VulnerabilityResponse(id=str(raw.get("id", "Unknown")), summary=raw.get("summary"), severity=severity, affected_versions=affected, fixed_versions=fixed, references=references, ecosystem=item.ecosystem, package=item.name, installed_version=item.installed_version or "unknown"))
    return normalized


@router.get("/{repository_id}/github", response_model=schemas.GithubIntelligenceResponse, summary="Get GitHub repository intelligence")
def github_intelligence(repository_id: int, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)) -> schemas.GithubIntelligenceResponse:
    repository = _repository(repository_id, db, workspace_id)
    data = GithubClient().metadata(repository.url)
    if data is None:
        return schemas.GithubIntelligenceResponse(available=False, message="GitHub metadata could not be loaded. Core code analysis is still available.")
    return schemas.GithubIntelligenceResponse(available=True, **data)


@router.get("/{repository_id}/dependencies", response_model=schemas.DependenciesResponse, summary="Inspect repository dependencies")
def dependencies(repository_id: int, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)) -> schemas.DependenciesResponse:
    repository = _repository(repository_id, db, workspace_id)
    items = extract_dependencies(repository.local_path) if repository.local_path else []
    results: list[schemas.DependencyResponse] = []
    for item in items:
        metadata = NpmClient().metadata(item.name) if item.ecosystem == "npm" else PypiClient().metadata(item.name)
        latest = metadata.get("latest_version") if metadata else None
        results.append(schemas.DependencyResponse(ecosystem=item.ecosystem, name=item.name, installed_version=item.installed_version, requested_version=item.requested_version, latest_version=latest, description=metadata.get("description") if metadata else None, dependency_type=item.dependency_type, source_file=item.source_file, status=_status(item.installed_version, latest, [])))
    return schemas.DependenciesResponse(available=True, checked_at=datetime.now(timezone.utc), dependencies=results)


@router.get("/{repository_id}/security", response_model=schemas.SecurityResponse, summary="Scan dependencies with OSV")
def security(repository_id: int, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)) -> schemas.SecurityResponse:
    repository = _repository(repository_id, db, workspace_id)
    items = extract_dependencies(repository.local_path) if repository.local_path else []
    client = OsvClient()
    vulnerabilities = [v for item in items for v in _vulnerabilities(item, client)]
    counts: dict[str, int] = {}
    for item in vulnerabilities:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return schemas.SecurityResponse(available=True, checked_at=datetime.now(timezone.utc), dependencies_scanned=len(items), severity_counts=counts, vulnerabilities=vulnerabilities)
