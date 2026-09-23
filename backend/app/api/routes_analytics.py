"""Repository analytics endpoints backed by indexed and repository data."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from git import Repo
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.graph_builder import GraphNotFoundError, NodeType, get_graph_service
from app.core.auth import get_workspace_id
from app.core.vector_store import CollectionNotFoundError, VectorStoreService
from app.db import crud
from app.db.database import get_db
from app.core.workspace import ensure_workspace
from app.models.db_models import Repository
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(ensure_workspace)])


@lru_cache(maxsize=1)
def get_analytics_vector_store() -> VectorStoreService:
    """Provide one process-wide vector store for analytics reads."""
    return VectorStoreService()


class LanguageDistributionItem(BaseModel):
    language: str
    fileCount: int = Field(ge=0)
    percentage: float = Field(ge=0)


class ChunkStatistics(BaseModel):
    totalChunks: int = Field(ge=0)
    embeddedChunks: int = Field(ge=0)
    pendingChunks: int = Field(ge=0)
    failedChunks: int = Field(ge=0)
    averageChunkSize: float = Field(ge=0)


class StorageBreakdown(BaseModel):
    sourceFilesBytes: int = Field(ge=0)
    embeddingsBytes: int = Field(ge=0)
    metadataBytes: int = Field(ge=0)
    graphDataBytes: int = Field(ge=0)
    totalBytes: int = Field(ge=0)


class RepositoryMetricsData(BaseModel):
    totalRepositories: int = Field(ge=0)
    totalFiles: int = Field(ge=0)
    totalFolders: int = Field(ge=0)
    totalSymbols: int = Field(ge=0)
    linesOfCode: int = Field(ge=0)
    languagesDetected: int = Field(ge=0)
    aiChunks: int = Field(ge=0)
    embeddings: int = Field(ge=0)
    dependencyNodes: int = Field(ge=0)
    repositorySizeBytes: int = Field(ge=0)
    indexedRepositories: int = Field(ge=0)
    pendingRepositories: int = Field(ge=0)
    failedRepositories: int = Field(ge=0)


class CommitActivityDataPoint(BaseModel):
    date: str
    commits: int = Field(ge=0)


class AnalyticsResponse(BaseModel):
    repositoryId: str
    languageDistribution: list[LanguageDistributionItem]
    chunkStatistics: ChunkStatistics
    storageBreakdown: StorageBreakdown
    metrics: RepositoryMetricsData
    commitActivity: list[CommitActivityDataPoint]
    generatedAt: datetime


def _repositories(db: Session, repository_id: str | None, workspace_id: str) -> list[Repository]:
    if repository_id is None:
        return list(crud.list_repositories(db, limit=100_000, workspace_id=workspace_id))
    repository = crud.get_repository(db, repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")
    return [repository]


def _graph_counts(repository: Repository) -> tuple[int, int, int, int]:
    try:
        graph = get_graph_service().get_graph(str(repository.id))
    except GraphNotFoundError:
        return 0, 0, 0, 0
    nodes = graph.all_nodes()
    symbol_types = {NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD}
    symbols = sum(node.node_type in symbol_types for node in nodes)
    folders = sum(node.node_type is NodeType.DIRECTORY for node in nodes)
    return len(nodes), symbols, folders, len(graph.all_edges())


def _commit_activity(repository: Repository) -> tuple[list[CommitActivityDataPoint], int]:
    if not repository.local_path:
        return [], 0
    path = Path(repository.local_path)
    if not path.is_dir():
        return [], 0
    try:
        commits = list(Repo(path).iter_commits(max_count=500))
    except Exception as exc:  # noqa: BLE001 - analytics must not break indexing data.
        logger.warning("Commit analytics unavailable repository_id=%s error=%s", repository.id, exc)
        return [], 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    counts: Counter[str] = Counter()
    for commit in commits:
        committed = commit.committed_datetime
        if committed.tzinfo is None:
            committed = committed.replace(tzinfo=timezone.utc)
        if committed >= cutoff:
            counts[committed.date().isoformat()] += 1
    return [CommitActivityDataPoint(date=day, commits=counts[day]) for day in sorted(counts)], len(commits)


def _build_analytics(
    repositories: list[Repository], vector_store: VectorStoreService
) -> AnalyticsResponse:
    files = [file for repository in repositories for file in repository.indexed_files]
    language_counts = Counter(file.programming_language or "unknown" for file in files)
    total_files = len(files)
    languages = [
        LanguageDistributionItem(
            language=language,
            fileCount=count,
            percentage=(count / total_files) * 100 if total_files else 0,
        )
        for language, count in sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    total_chunks = sum(file.chunk_count or 0 for file in files)
    embedded_chunks = sum(repository.total_embeddings or 0 for repository in repositories)
    source_bytes = sum(file.file_size or 0 for file in files)
    metadata_bytes = sum(
        len(json.dumps({"path": file.relative_path, "checksum": file.checksum})) for file in files
    )
    graph_bytes = 0
    total_nodes = total_symbols = total_folders = 0
    commits: Counter[str] = Counter()
    commit_count = 0
    vector_count = 0
    for repository in repositories:
        nodes, symbols, folders, _edges = _graph_counts(repository)
        total_nodes += nodes
        total_symbols += symbols
        total_folders += folders
        try:
            vector_count += vector_store.get_repository_stats(str(repository.id), repository.workspace_id).vector_count
        except CollectionNotFoundError:
            pass
        activity, count = _commit_activity(repository)
        commit_count += count
        for point in activity:
            commits[point.date] += point.commits
        try:
            graph_bytes += len(json.dumps(get_graph_service().serialize(str(repository.id))))
        except GraphNotFoundError:
            pass

    storage = StorageBreakdown(
        sourceFilesBytes=source_bytes,
        embeddingsBytes=vector_count * 384 * 4,
        metadataBytes=metadata_bytes,
        graphDataBytes=graph_bytes,
        totalBytes=source_bytes + vector_count * 384 * 4 + metadata_bytes + graph_bytes,
    )
    metrics = RepositoryMetricsData(
        totalRepositories=len(repositories),
        totalFiles=total_files,
        totalFolders=total_folders,
        totalSymbols=total_symbols,
        linesOfCode=0,
        languagesDetected=len(languages),
        aiChunks=total_chunks,
        embeddings=vector_count or embedded_chunks,
        dependencyNodes=total_nodes,
        repositorySizeBytes=source_bytes,
        indexedRepositories=sum(repository.indexing_status == "ready" for repository in repositories),
        pendingRepositories=sum(repository.indexing_status not in {"ready", "index_failed", "failed_import"} for repository in repositories),
        failedRepositories=sum(repository.indexing_status in {"index_failed", "failed_import", "failed"} for repository in repositories),
    )
    return AnalyticsResponse(
        repositoryId=str(repositories[0].id) if len(repositories) == 1 else "all",
        languageDistribution=languages,
        chunkStatistics=ChunkStatistics(
            totalChunks=total_chunks,
            embeddedChunks=vector_count or embedded_chunks,
            pendingChunks=max(0, total_chunks - (vector_count or embedded_chunks)),
            failedChunks=0,
            averageChunkSize=(source_bytes / total_chunks) if total_chunks else 0,
        ),
        storageBreakdown=storage,
        metrics=metrics,
        commitActivity=[CommitActivityDataPoint(date=day, commits=commits[day]) for day in sorted(commits)],
        generatedAt=datetime.now(timezone.utc),
    )


@router.get("", response_model=AnalyticsResponse)
def get_analytics(
    db: Session = Depends(get_db),
    vector_store: VectorStoreService = Depends(get_analytics_vector_store),
    workspace_id: str = Depends(get_workspace_id),
) -> AnalyticsResponse:
    """Return aggregate analytics across all repositories."""
    return _build_analytics(_repositories(db, None, workspace_id), vector_store)


@router.get("/{repository_id}", response_model=AnalyticsResponse)
def get_repository_analytics(
    repository_id: str,
    db: Session = Depends(get_db),
    vector_store: VectorStoreService = Depends(get_analytics_vector_store),
    workspace_id: str = Depends(get_workspace_id),
) -> AnalyticsResponse:
    """Return analytics for one repository."""
    return _build_analytics(_repositories(db, repository_id, workspace_id), vector_store)
