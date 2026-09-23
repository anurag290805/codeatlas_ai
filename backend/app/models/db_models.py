"""SQLAlchemy ORM models for CodeAtlas AI.

This module defines the relational schema used to track imported
repositories, the files parsed from them, and the history of natural
language queries issued against them. Vector embeddings themselves live
in ChromaDB, not here; this module only stores the relational metadata
needed to relate repositories, files, and queries to one another.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Repository(Base):
    """An imported GitHub repository and its indexing state.

    Acts as the root aggregate for a codebase: every parsed file and
    every query issued against the codebase is linked back to a single
    `Repository` row. The `owner_id` field is nullable today but reserved
    so that multi-user and private-repository support can be added later
    without altering the schema.
    """

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "repository_url", name="uq_repositories_workspace_url"),
        Index("ix_repositories_repository_name", "repository_name"),
        Index("ix_repositories_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    local_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    current_commit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Browser workspace/account identity. Null legacy rows are intentionally
    # not visible to new workspaces until explicitly claimed by migration.
    workspace_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("workspaces.id"), nullable=True, index=True)
    # Retained for compatibility with earlier deployments.
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_private: Mapped[bool] = mapped_column(default=False, nullable=False)

    indexing_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_embeddings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_index_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexing_stage: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    indexing_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexing_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    indexed_files: Mapped[list["IndexedFile"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    workspace: Mapped["Workspace | None"] = relationship(back_populates="repositories")
    query_history: Mapped[list["QueryHistory"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id} name={self.repository_name!r} status={self.indexing_status!r}>"

    @property
    def url(self) -> str:
        return self.repository_url

    @property
    def status(self) -> str:
        return self.indexing_status or "pending"

    @property
    def files_indexed(self) -> int:
        return self.total_files or 0

    @property
    def chunks_generated(self) -> int:
        return self.total_chunks or 0

    @property
    def embeddings_generated(self) -> int:
        return self.total_embeddings or 0

    @property
    def repository_id(self) -> int:
        return self.id


class Workspace(Base):
    """Opaque browser workspace used to isolate repository data."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    repositories: Mapped[list[Repository]] = relationship(back_populates="workspace")


class IndexedFile(Base):
    """A single source file parsed and chunked from a `Repository`.

    Tracks file-level metadata (language, size, checksum) needed to
    detect changes on re-indexing and to report per-file chunk counts,
    without storing the file's actual content or embeddings.
    """

    __tablename__ = "indexed_files"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "relative_path", name="uq_indexed_files_repository_path"
        ),
        Index("ix_indexed_files_relative_path", "relative_path"),
        Index("ix_indexed_files_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    programming_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    repository: Mapped["Repository"] = relationship(back_populates="indexed_files")

    def __repr__(self) -> str:
        return f"<IndexedFile id={self.id} path={self.relative_path!r} repository_id={self.repository_id}>"


class QueryHistory(Base):
    """A single natural-language query issued against a `Repository`.

    Persists the question, the generated answer, and basic performance
    metadata so that past queries can be reviewed, audited, or reused
    without re-invoking the RAG pipeline.
    """

    __tablename__ = "query_history"
    __table_args__ = (Index("ix_query_history_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )

    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    generated_answer: Mapped[str] = mapped_column(Text, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    repository: Mapped["Repository"] = relationship(back_populates="query_history")

    def __repr__(self) -> str:
        return f"<QueryHistory id={self.id} repository_id={self.repository_id} query={self.user_query[:50]!r}>"
