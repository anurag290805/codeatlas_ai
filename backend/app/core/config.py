"""Pydantic Settings configuration for CodeAtlas AI."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _PROJECT_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_ENV_FILES = (_PROJECT_ROOT / ".env", _PROJECT_ROOT / "backend" / ".env")


class Settings(BaseSettings):
    """Validated application configuration loaded from ``.env`` and env vars."""

    model_config = SettingsConfigDict(
        # Load the root file first, then the backend-local file. Shell
        # environment variables still override both files.
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
        populate_by_name=True,
    )

    # Application
    app_name: str = Field(default="CodeAtlas AI", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    app_description: str = Field(default="AI-powered code intelligence platform.")
    environment: str = Field(default="development", min_length=1)
    debug: bool = False
    host: str = Field(default="127.0.0.1", min_length=1)
    port: Annotated[int, Field(ge=1, le=65_535)] = 8000
    api_prefix: str = "/api"
    # Production may override this via CORS_ALLOWED_ORIGINS. The default covers
    # the Vite dev server and the deployed Vercel frontend (which is a separate
    # origin from the Render backend). With allow_credentials enabled, "*" is
    # rejected by the validator below.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "https://codeatlas-ai-frontend.vercel.app",
        ]
    )
    cors_allow_credentials: bool = True
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    workspace_session_secret: str | None = Field(
        default=None,
        min_length=32,
        validation_alias=AliasChoices("WORKSPACE_SESSION_SECRET"),
    )

    # Database
    database_url: str = Field(
        default=f"sqlite:///{(_DATA_DIR / 'app.db').as_posix()}", min_length=1
    )
    repositories_dir: Path = _DATA_DIR / "repos"

    # Gemini (server-side only)
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.6-flash", min_length=1)
    gemini_timeout_seconds: Annotated[float, Field(gt=0)] = 60.0
    gemini_temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    gemini_max_tokens: Annotated[int, Field(gt=0)] = 512

    # Active LLM provider. Gemini is the default for production deployments.
    llm_provider: str = Field(default="gemini", min_length=1)

    # OmniRoute (OpenAI-compatible local gateway)
    omniroute_base_url: str = Field(
        default="http://localhost:20128/v1",
        min_length=1,
    )
    omniroute_model: str = Field(
        default="auto/best-free",
        min_length=1,
    )
    omniroute_api_key: str = Field(default="", validation_alias="OMNIROUTE_API_KEY")
    omniroute_timeout_seconds: Annotated[float, Field(gt=0)] = 60.0



    # Embeddings
    embedding_provider: str = Field(default="gemini", min_length=1)
    embedding_model: str = Field(default="gemini-embedding-2", min_length=1)
    embedding_batch_size: Annotated[int, Field(gt=0)] = 32
    embedding_dimension: Annotated[int, Field(gt=0, le=3072)] = 768
    embedding_max_input_tokens: Annotated[int, Field(gt=0)] = 256

    # Logging
    log_level: str = "INFO"
    log_file: Path = _PROJECT_ROOT / "logs" / "app.log"

    # ChromaDB
    chroma_persist_directory: Path = Field(
        default=_DATA_DIR / "vector_store",
        validation_alias=AliasChoices("CHROMA_PERSIST_DIRECTORY", "CHROMA_DB_PATH"),
    )
    chroma_collection_prefix: str = Field(default="codeatlas_repo", min_length=1)

    # Tree-sitter
    # Optional override for a project-local compiled grammar library. When
    # absent or unavailable, the parser uses the portable grammars bundled
    # by the tree-sitter-languages package.
    tree_sitter_languages_dir: Path = _DATA_DIR / "tree_sitter_languages"

    # Parser
    # Maximum source file size to parse, in bytes. Files larger than this
    # limit are skipped (counted as skipped, not failed) to avoid OOM on
    # minified bundles or binary blobs with source extensions. Default ~1 MB.
    parser_max_file_bytes: Annotated[int, Field(gt=0)] = 1_048_576

    # Shared service limits
    retrieval_top_k: Annotated[int, Field(gt=0, le=200)] = 5
    retrieval_token_budget: Annotated[int, Field(gt=0)] = 1200
    graph_max_traversal_depth: Annotated[int, Field(gt=0, le=100)] = 10

    @field_validator("environment", "embedding_provider", "llm_provider", mode="before")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_value(cls, value: object) -> object:
        """Accept common deployment labels in addition to boolean values."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "false", "no", "off", "0"}:
                return False
            if normalized in {"development", "dev", "debug", "true", "yes", "on", "1"}:
                return True
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return normalized

    @field_validator("workspace_session_secret", mode="before")
    @classmethod
    def normalize_workspace_session_secret(cls, value: object) -> object:
        """Trim the canonical signing secret without accepting an alias."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("api_prefix", mode="before")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        prefix = str(value).strip()
        if not prefix:
            raise ValueError("api_prefix must not be empty")
        return "/" + prefix.strip("/") if prefix != "/" else ""

    @field_validator("cors_allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def parse_csv_values(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        url = str(value).strip()
        if "://" not in url:
            raise ValueError("database_url must be a valid SQLAlchemy URL")

        # Render commonly exposes its managed PostgreSQL connection string
        # with the legacy ``postgres://`` scheme. SQLAlchemy expects the
        # dialect name to be ``postgresql://`` (and the psycopg driver is
        # installed for that dialect), so normalize it once at the settings
        # boundary before the engine is constructed.
        if url.startswith("postgres://"):
            url = "postgresql://" + url.removeprefix("postgres://")

        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            sqlite_path = Path(url.removeprefix("sqlite:///"))
            if sqlite_path.as_posix() != ":memory:" and not sqlite_path.is_absolute():
                url = f"sqlite:///{(_PROJECT_ROOT / sqlite_path).resolve().as_posix()}"
        return url

    @field_validator(
        "log_file",
        "repositories_dir",
        "chroma_persist_directory",
        "tree_sitter_languages_dir",
        mode="before",
    )
    @classmethod
    def resolve_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return (path if path.is_absolute() else _PROJECT_ROOT / path).resolve()

    @model_validator(mode="after")
    def validate_cors_configuration(self) -> "Settings":
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError(
                "cors_allowed_origins cannot contain '*' when credentials are enabled"
            )
        return self

    @model_validator(mode="after")
    def validate_workspace_session_secret(self) -> "Settings":
        """Require the canonical secret whenever cookies are persistent."""
        if self.environment not in {"development", "dev", "test"} and not self.workspace_session_secret:
            raise ValueError(
                "WORKSPACE_SESSION_SECRET must be configured outside development"
        )
        return self

    # Compatibility properties for existing modules using the old names.
    @property
    def LOG_LEVEL(self) -> str:
        return self.log_level

    @property
    def LOG_FILE(self) -> Path:
        return self.log_file

    @property
    def TREE_SITTER_LANGUAGES_DIR(self) -> Path:
        return self.tree_sitter_languages_dir

    @property
    def REPOSITORIES_DIR(self) -> Path:
        return self.repositories_dir

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide singleton settings instance."""
    return Settings()


settings = get_settings()
