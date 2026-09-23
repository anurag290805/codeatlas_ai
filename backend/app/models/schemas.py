"""Pydantic request and response contracts for the CodeAtlas API."""

from __future__ import annotations

import re
import base64
from urllib.parse import urlparse
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GITHUB_URL_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$"
)


class RepositoryStatus(str, Enum):
    READY = "ready"
    INDEXING = "indexing"
    INDEX_FAILED = "index_failed"
    FAILED_IMPORT = "failed_import"
    DELETING = "deleting"
    # Legacy values kept in the wire contract for older clients.
    PENDING = "pending"
    CLONING = "cloning"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


IndexingStatus = RepositoryStatus


class RepositoryCreate(BaseModel):
    """Request to register a public GitHub repository."""

    url: str = Field(min_length=1)
    branch: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not _GITHUB_URL_PATTERN.fullmatch(value):
            raise ValueError("url must be a valid public GitHub repository URL")
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("branch must not be blank")
        return value.strip() if value else value


RepositoryImportRequest = RepositoryCreate


class RepositoryResponse(BaseModel):
    """Repository metadata returned by lifecycle endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_name: str
    url: str
    default_branch: str = "main"
    status: RepositoryStatus = RepositoryStatus.PENDING
    files_indexed: int = Field(default=0, ge=0)
    chunks_generated: int = Field(default=0, ge=0)
    embeddings_generated: int = Field(default=0, ge=0)
    last_indexed_at: datetime | None = None
    indexing_stage: str = "queued"
    indexing_progress: int = Field(default=0, ge=0, le=100)
    indexing_started_at: datetime | None = None
    indexing_heartbeat_at: datetime | None = None
    last_indexing_error: str | None = None

    @field_validator("default_branch", mode="before")
    @classmethod
    def default_branch_value(cls, value: str | None) -> str:
        return value or "main"

    @property
    def repository_id(self) -> int:
        return self.id


class RepositoryStatusResponse(RepositoryResponse):
    """Repository indexing state and progress."""

    pass


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse]
    total: int = Field(ge=0)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)


class RepositoryHealthResponse(BaseModel):
    total_repositories: int = Field(ge=0)
    indexed: int = Field(ge=0)
    failed: int = Field(ge=0)
    pending: int = Field(ge=0)


class GithubIntelligenceResponse(BaseModel):
    available: bool
    message: str | None = None
    full_name: str | None = None
    description: str | None = None
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    default_branch: str | None = None
    license: str | None = None
    html_url: str | None = None


class VulnerabilityResponse(BaseModel):
    id: str
    summary: str | None = None
    severity: str = "Unknown"
    affected_versions: list[str] = Field(default_factory=list)
    fixed_versions: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    ecosystem: str = "unknown"
    package: str = "unknown"
    installed_version: str = "unknown"


class DependencyResponse(BaseModel):
    ecosystem: str
    name: str
    installed_version: str | None = None
    requested_version: str | None = None
    latest_version: str | None = None
    description: str | None = None
    dependency_type: str
    source_file: str
    status: str = "unknown"
    vulnerabilities: list[VulnerabilityResponse] = Field(default_factory=list)


class DependenciesResponse(BaseModel):
    available: bool
    message: str | None = None
    checked_at: datetime
    dependencies: list[DependencyResponse] = Field(default_factory=list)


class SecurityResponse(BaseModel):
    available: bool
    message: str | None = None
    checked_at: datetime
    dependencies_scanned: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    vulnerabilities: list[VulnerabilityResponse] = Field(default_factory=list)


RepositoryImportResponse = RepositoryResponse


class CitationSchema(BaseModel):
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol_name: str | None = None

    @field_validator("end_line")
    @classmethod
    def validate_range(cls, value: int, info) -> int:
        start = info.data.get("start_line")
        if start is not None and value < start:
            raise ValueError("end_line must be greater than or equal to start_line")
        return value


Citation = CitationSchema


class QueryRequest(BaseModel):
    repository_id: int
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

    @property
    def question(self) -> str:
        return self.query


class RepositoryScopedQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class TokenUsageSchema(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class QueryResponse(BaseModel):
    repository_id: str | int
    query: str
    answer: str
    citations: list[CitationSchema] = Field(default_factory=list)
    provider: str
    model: str
    latency_seconds: float = Field(ge=0)
    token_usage: TokenUsageSchema | None = None


class QueryHealthResponse(BaseModel):
    status: str
    retriever_ready: bool
    provider_reachable: bool = False
    rag_status: str = "unavailable"
    provider_status: str = "unavailable"
    provider_configured: bool = False
    provider_healthy: bool = False
    model_available: bool = False
    llm_provider: str = "omniroute"
    llm_model: str = "auto/best-free"
    message: str = ""


class AgentTaskRequest(BaseModel):
    repository_id: int = Field(gt=0)
    task: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=20)
    image_data_url: str | None = Field(default=None, max_length=7_000_000)
    route: str | None = Field(default=None, max_length=2048)
    mode: str = Field(default="analyze", pattern="^(analyze|modify)$")

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("task must not be blank")
        return value

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 300 for value in cleaned):
            raise ValueError("acceptance criteria must be non-empty and at most 300 characters")
        return cleaned

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.username or parsed.password:
            raise ValueError("route must be an http(s) localhost or 127.0.0.1 URL")
        return value

    @field_validator("image_data_url")
    @classmethod
    def validate_image_data_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"data:(image/(?:png|jpeg|gif|webp));base64,([A-Za-z0-9+/=]+)", value.strip(), re.IGNORECASE)
        if not match:
            raise ValueError("image_data_url must be a base64 PNG, JPEG, GIF, or WebP data URL")
        try:
            decoded = base64.b64decode(match.group(2), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("image_data_url contains invalid base64") from exc
        if len(decoded) > 5 * 1024 * 1024:
            raise ValueError("image_data_url must not exceed 5 MiB")
        signatures = {
            "image/png": b"\x89PNG\r\n\x1a\n",
            "image/jpeg": b"\xff\xd8\xff",
            "image/gif": (b"GIF87a", b"GIF89a"),
            "image/webp": b"RIFF",
        }
        signature = signatures[match.group(1).lower()]
        valid = any(decoded.startswith(item) for item in signature) if isinstance(signature, tuple) else decoded.startswith(signature)
        if not valid:
            raise ValueError("image_data_url content does not match its declared image type")
        return value.strip()


class AgentSkillResult(BaseModel):
    skill: str
    status: str
    summary: str
    output: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(ge=0)


class AgentOperationResponse(BaseModel):
    path: str
    operation: str
    old_content_hash: str | None = None


class AgentValidationCheckResponse(BaseModel):
    name: str
    status: str
    summary: str


class AgentValidationResponse(BaseModel):
    status: str
    checks: list[AgentValidationCheckResponse] = Field(default_factory=list)


class AgentModificationResponse(BaseModel):
    status: str
    files_changed: list[str] = Field(default_factory=list)
    operations: list[AgentOperationResponse] = Field(default_factory=list)
    validation: AgentValidationResponse
    attempts: int = Field(ge=1, le=3)
    summary: str
    errors: list[str] = Field(default_factory=list)
    playwright: dict | None = None
    # Approval gate: present (status="pending_approval") until a human approves the patch.
    approval_token: str | None = None
    diff: str | None = None


class AgentApprovalRequest(BaseModel):
    approval_token: str = Field(min_length=1, max_length=128)


class AgentTaskResponse(BaseModel):
    task: str
    selected_skills: list[str]
    status: str
    final_result: str
    skill_results: list[AgentSkillResult] = Field(default_factory=list)
    duration_seconds: float = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    modification: AgentModificationResponse | None = None
    mode: str = "analyze"


class RepositoryFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relative_path: str
    language: str | None = None
    file_size_bytes: int
    checksum_sha256: str
    chunks_generated: int


class RepositoryFilesResponse(BaseModel):
    files: list[RepositoryFileResponse]


class RepositoryFileContentResponse(BaseModel):
    """Content of a single file from a repository."""

    path: str
    content: str
    language: str | None = None
    size_bytes: int = Field(ge=0)


# Names retained for callers that used the earlier schema vocabulary.
QueryRequest.model_rebuild()
