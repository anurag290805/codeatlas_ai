"""Database CRUD operations for CodeAtlas AI.

This module is the only layer that communicates directly with the
SQLAlchemy ORM models defined in `app.models.db_models`. Every function
here receives an already-open `Session` and never creates or closes one
itself — session lifecycle is owned by `app.db.database`. No API logic,
parsing, embedding, or LLM interaction belongs in this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.db_models import IndexedFile, QueryHistory, Repository
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# =========================================================================
# Repository Operations
# =========================================================================


def create_repository(
    session: Session,
    *,
    repository_name: str | None = None,
    repository_url: str | None = None,
    default_branch: str = "main",
    local_path: str = "",
    current_commit_hash: str | None = None,
    obj_in: object | None = None,
    workspace_id: str | None = None,
) -> Repository:
    """Create and persist a new `Repository` record.

    Args:
        session: Active SQLAlchemy session.
        repository_name: Name of the repository, e.g. 'owner/repo'.
        repository_url: Public GitHub URL of the repository.
        default_branch: The repository's default branch.
        local_path: Filesystem path where the repository was cloned.
        current_commit_hash: Commit hash the local clone is at, if known.

    Returns:
        The newly created and refreshed `Repository` instance.

    Raises:
        IntegrityError: If a repository with the same URL already exists.
        SQLAlchemyError: For any other database failure.
    """
    if obj_in is not None:
        repository_url = str(getattr(obj_in, "url", getattr(obj_in, "repository_url", "")))
        repository_name = repository_name or str(getattr(obj_in, "repository_name", repository_url))
        default_branch = str(getattr(obj_in, "branch", default_branch) or default_branch)

    if not repository_name or not repository_url:
        raise ValueError("repository_name and repository_url are required")

    repository = Repository(
        repository_name=repository_name,
        repository_url=repository_url,
        default_branch=default_branch,
        local_path=local_path,
        current_commit_hash=current_commit_hash,
        workspace_id=workspace_id,
    )
    session.add(repository)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.error("Repository already exists for URL: %s", repository_url)
        raise
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to create repository: %s", repository_name)
        raise

    session.refresh(repository)
    logger.info("Created repository id=%s name=%s", repository.id, repository.repository_name)
    return repository


def get_repository_by_id(session: Session, repository_id: int, *, workspace_id: str | None = None) -> Repository | None:
    """Fetch a `Repository` by its primary key.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Primary key of the repository.

    Returns:
        The matching `Repository`, or None if not found.
    """
    repository = session.get(Repository, repository_id)
    return repository if workspace_id is None or (repository and repository.workspace_id == workspace_id) else None


def get_repository(session: Session, repository_id: int | str, *, workspace_id: str | None = None) -> Repository | None:
    """Fetch a repository using the route-layer repository identifier."""
    try:
        return get_repository_by_id(session, int(repository_id), workspace_id=workspace_id)
    except (TypeError, ValueError):
        return None


def get_repository_by_url(session: Session, repository_url: str, *, workspace_id: str | None = None) -> Repository | None:
    """Fetch a `Repository` by its unique GitHub URL.

    Args:
        session: Active SQLAlchemy session.
        repository_url: The repository's GitHub URL.

    Returns:
        The matching `Repository`, or None if not found.
    """
    statement = select(Repository).where(Repository.repository_url == repository_url)
    if workspace_id is not None:
        statement = statement.where(Repository.workspace_id == workspace_id)
    return session.execute(statement).scalar_one_or_none()


def get_repository_by_name(session: Session, repository_name: str) -> Repository | None:
    """Fetch a `Repository` by its name.

    Args:
        session: Active SQLAlchemy session.
        repository_name: Name of the repository, e.g. 'owner/repo'.

    Returns:
        The matching `Repository`, or None if not found. If multiple
        repositories share a name, the most recently created is returned.
    """
    statement = (
        select(Repository)
        .where(Repository.repository_name == repository_name)
        .order_by(Repository.created_at.desc())
    )
    return session.execute(statement).scalars().first()


def list_repositories(
    session: Session, *, limit: int = 50, offset: int = 0, skip: int | None = None, workspace_id: str | None = None
) -> Sequence[Repository]:
    """List repositories ordered by most recently created.

    Args:
        session: Active SQLAlchemy session.
        limit: Maximum number of repositories to return.
        offset: Number of repositories to skip, for pagination.

    Returns:
        A sequence of `Repository` instances.
    """
    if skip is not None:
        offset = skip
    statement = (
        select(Repository)
        .order_by(Repository.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if workspace_id is not None:
        statement = statement.where(Repository.workspace_id == workspace_id)
    return session.execute(statement).scalars().all()


def update_repository(
    session: Session, repository_id: int, *, workspace_id: str | None = None, **fields: object
) -> Repository | None:
    """Update arbitrary fields on a `Repository`.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Primary key of the repository to update.
        **fields: Attribute names and values to set on the repository.
            Only attributes that already exist on the model are applied;
            unknown keys are ignored.

    Returns:
        The updated `Repository`, or None if no repository with the
        given id exists.

    Raises:
        SQLAlchemyError: If the update fails.
    """
    repository = get_repository(session, repository_id, workspace_id=workspace_id)
    if repository is None:
        logger.warning("Attempted to update nonexistent repository id=%s", repository_id)
        return None

    for field_name, value in fields.items():
        if hasattr(repository, field_name):
            setattr(repository, field_name, value)

    repository.updated_at = _utcnow()

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to update repository id=%s", repository_id)
        raise

    session.refresh(repository)
    logger.info("Updated repository id=%s", repository_id)
    return repository


def update_repository_indexing_status(
    session: Session,
    repository_id: int,
    indexing_status: str,
    *,
    total_files: int | None = None,
    total_chunks: int | None = None,
    total_embeddings: int | None = None,
    mark_indexed_now: bool = False,
    workspace_id: str | None = None,
    indexing_stage: str | None = None,
    indexing_progress: int | None = None,
) -> Repository | None:
    """Update a repository's indexing status and related statistics.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Primary key of the repository to update.
        indexing_status: New indexing status value.
        total_files: Updated count of indexed files, if known.
        total_chunks: Updated count of generated chunks, if known.
        total_embeddings: Updated count of generated embeddings, if known.
        mark_indexed_now: If True, sets `last_indexed_at` to the current
            UTC timestamp.

    Returns:
        The updated `Repository`, or None if no repository with the
        given id exists.

    Raises:
        SQLAlchemyError: If the update fails.
    """
    repository = get_repository(session, repository_id, workspace_id=workspace_id)
    if repository is None:
        logger.warning(
            "Attempted to update indexing status for nonexistent repository id=%s",
            repository_id,
        )
        return None

    repository.indexing_status = indexing_status
    if total_files is not None:
        repository.total_files = total_files
    if total_chunks is not None:
        repository.total_chunks = total_chunks
    if total_embeddings is not None:
        repository.total_embeddings = total_embeddings
    if mark_indexed_now:
        repository.last_indexed_at = _utcnow()
    repository.last_index_attempt_at = _utcnow()
    if indexing_stage is not None:
        repository.indexing_stage = indexing_stage
    if indexing_progress is not None:
        repository.indexing_progress = max(0, min(100, int(indexing_progress)))
    normalized_status = str(getattr(indexing_status, "value", indexing_status))
    if normalized_status == "indexing":
        repository.indexing_heartbeat_at = _utcnow()
        repository.indexing_started_at = repository.indexing_started_at or _utcnow()
    elif normalized_status == "ready":
        repository.indexing_stage = "complete"
        repository.indexing_progress = 100
        repository.indexing_heartbeat_at = _utcnow()
    if normalized_status == "pending":
        # A retry or requeue starts a fresh run epoch: clear the start timestamp
        # so the next indexing run will establish a distinct ``indexing_started_at``.
        repository.indexing_started_at = None
    if hasattr(repository, "last_indexing_error"):
        repository.last_indexing_error = None
    repository.updated_at = _utcnow()

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to update indexing status for repository id=%s", repository_id)
        raise

    session.refresh(repository)
    logger.info(
        "Updated repository id=%s indexing_status=%s", repository_id, indexing_status
    )
    return repository


def delete_repository(session: Session, repository_id: int) -> bool:
    """Delete a `Repository` and its dependent records.

    Relies on the cascading delete configured in `db_models.Repository`
    to remove associated `IndexedFile` and `QueryHistory` rows.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Primary key of the repository to delete.

    Returns:
        True if a repository was found and deleted, False otherwise.

    Raises:
        SQLAlchemyError: If the deletion fails.
    """
    repository = session.get(Repository, repository_id)
    if repository is None:
        logger.warning("Attempted to delete nonexistent repository id=%s", repository_id)
        return False

    try:
        session.delete(repository)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to delete repository id=%s", repository_id)
        raise

    logger.info("Deleted repository id=%s", repository_id)
    return True


# =========================================================================
# IndexedFile Operations
# =========================================================================


def create_indexed_file(
    session: Session,
    *,
    repository_id: int,
    relative_path: str,
    programming_language: str | None,
    file_size: int,
    checksum: str,
    chunk_count: int = 0,
    last_modified: datetime | None = None,
) -> IndexedFile:
    """Create and persist a single `IndexedFile` record.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Owning repository's primary key.
        relative_path: File path relative to the repository root.
        programming_language: Detected language of the file, if known.
        file_size: Size of the file in bytes.
        checksum: Content hash used to detect changes on re-indexing.
        chunk_count: Number of chunks generated from this file.
        last_modified: Last-modified timestamp of the source file.

    Returns:
        The newly created and refreshed `IndexedFile` instance.

    Raises:
        IntegrityError: If a file with the same path already exists for
            the repository.
        SQLAlchemyError: For any other database failure.
    """
    indexed_file = IndexedFile(
        repository_id=repository_id,
        relative_path=relative_path,
        programming_language=programming_language,
        file_size=file_size,
        checksum=checksum,
        chunk_count=chunk_count,
        last_modified=last_modified,
    )
    session.add(indexed_file)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.error(
            "Indexed file already exists: repository_id=%s path=%s",
            repository_id,
            relative_path,
        )
        raise
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to create indexed file: %s", relative_path)
        raise

    session.refresh(indexed_file)
    logger.info(
        "Created indexed file id=%s repository_id=%s path=%s",
        indexed_file.id,
        repository_id,
        relative_path,
    )
    return indexed_file


def bulk_create_indexed_files(
    session: Session, indexed_files: Sequence[dict[str, object]]
) -> list[IndexedFile]:
    """Create multiple `IndexedFile` records in a single transaction.

    Args:
        session: Active SQLAlchemy session.
        indexed_files: A sequence of dictionaries, each containing the
            keyword arguments expected by the `IndexedFile` model
            (e.g. repository_id, relative_path, programming_language,
            file_size, checksum, chunk_count, last_modified).

    Returns:
        The list of newly created and refreshed `IndexedFile` instances,
        in the same order as the input.

    Raises:
        SQLAlchemyError: If the bulk insertion fails.
    """
    file_objects = [IndexedFile(**file_data) for file_data in indexed_files]
    session.add_all(file_objects)

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to bulk create %d indexed files", len(file_objects))
        raise

    for file_object in file_objects:
        session.refresh(file_object)

    logger.info("Bulk created %d indexed files", len(file_objects))
    return file_objects


def get_file_by_path(
    session: Session, repository_id: int, relative_path: str
) -> IndexedFile | None:
    """Fetch a single `IndexedFile` by its repository and relative path.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Owning repository's primary key.
        relative_path: File path relative to the repository root.

    Returns:
        The matching `IndexedFile`, or None if not found.
    """
    statement = select(IndexedFile).where(
        IndexedFile.repository_id == repository_id,
        IndexedFile.relative_path == relative_path,
    )
    return session.execute(statement).scalar_one_or_none()


def list_repository_files(
    session: Session, repository_id: int, *, limit: int = 500, offset: int = 0, workspace_id: str | None = None
) -> Sequence[IndexedFile]:
    """List indexed files belonging to a repository.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Owning repository's primary key.
        limit: Maximum number of files to return.
        offset: Number of files to skip, for pagination.

    Returns:
        A sequence of `IndexedFile` instances.
    """
    statement = (
        select(IndexedFile).join(Repository, Repository.id == IndexedFile.repository_id)
        .where(IndexedFile.repository_id == repository_id)
        .order_by(IndexedFile.relative_path.asc())
        .limit(limit)
        .offset(offset)
    )
    if workspace_id is not None:
        statement = statement.where(Repository.workspace_id == workspace_id)
    return session.execute(statement).scalars().all()


def update_file(session: Session, file_id: int, **fields: object) -> IndexedFile | None:
    """Update arbitrary fields on an `IndexedFile`.

    Args:
        session: Active SQLAlchemy session.
        file_id: Primary key of the file to update.
        **fields: Attribute names and values to set on the file. Only
            attributes that already exist on the model are applied;
            unknown keys are ignored.

    Returns:
        The updated `IndexedFile`, or None if no file with the given id
        exists.

    Raises:
        SQLAlchemyError: If the update fails.
    """
    indexed_file = session.get(IndexedFile, file_id)
    if indexed_file is None:
        logger.warning("Attempted to update nonexistent indexed file id=%s", file_id)
        return None

    for field_name, value in fields.items():
        if hasattr(indexed_file, field_name):
            setattr(indexed_file, field_name, value)

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to update indexed file id=%s", file_id)
        raise

    session.refresh(indexed_file)
    logger.info("Updated indexed file id=%s", file_id)
    return indexed_file


def delete_file(session: Session, file_id: int) -> bool:
    """Delete a single `IndexedFile` record.

    Args:
        session: Active SQLAlchemy session.
        file_id: Primary key of the file to delete.

    Returns:
        True if a file was found and deleted, False otherwise.

    Raises:
        SQLAlchemyError: If the deletion fails.
    """
    indexed_file = session.get(IndexedFile, file_id)
    if indexed_file is None:
        logger.warning("Attempted to delete nonexistent indexed file id=%s", file_id)
        return False

    try:
        session.delete(indexed_file)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to delete indexed file id=%s", file_id)
        raise

    logger.info("Deleted indexed file id=%s", file_id)
    return True


# =========================================================================
# QueryHistory Operations
# =========================================================================


def create_query_history(
    session: Session,
    *,
    repository_id: int,
    user_query: str,
    generated_answer: str,
    response_time_ms: int | None = None,
    model_used: str | None = None,
) -> QueryHistory:
    """Create and persist a `QueryHistory` record.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Repository the query was issued against.
        user_query: The natural-language question asked by the user.
        generated_answer: The answer generated by the RAG pipeline.
        response_time_ms: Time taken to generate the answer, in ms.
        model_used: Identifier of the LLM used to generate the answer.

    Returns:
        The newly created and refreshed `QueryHistory` instance.

    Raises:
        SQLAlchemyError: If the record cannot be created.
    """
    query_history = QueryHistory(
        repository_id=repository_id,
        user_query=user_query,
        generated_answer=generated_answer,
        response_time_ms=response_time_ms,
        model_used=model_used,
    )
    session.add(query_history)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to create query history for repository_id=%s", repository_id)
        raise

    session.refresh(query_history)
    logger.info(
        "Created query history id=%s repository_id=%s", query_history.id, repository_id
    )
    return query_history


def get_query_history(session: Session, query_id: int) -> QueryHistory | None:
    """Fetch a single `QueryHistory` record by its primary key.

    Args:
        session: Active SQLAlchemy session.
        query_id: Primary key of the query history record.

    Returns:
        The matching `QueryHistory`, or None if not found.
    """
    return session.get(QueryHistory, query_id)


def list_recent_queries(
    session: Session, repository_id: int, *, limit: int = 20
) -> Sequence[QueryHistory]:
    """List the most recent queries issued against a repository.

    Args:
        session: Active SQLAlchemy session.
        repository_id: Repository whose query history should be listed.
        limit: Maximum number of records to return.

    Returns:
        A sequence of `QueryHistory` instances, most recent first.
    """
    statement = (
        select(QueryHistory)
        .where(QueryHistory.repository_id == repository_id)
        .order_by(QueryHistory.created_at.desc())
        .limit(limit)
    )
    return session.execute(statement).scalars().all()


def delete_query_history(session: Session, query_id: int) -> bool:
    """Delete a single `QueryHistory` record.

    Args:
        session: Active SQLAlchemy session.
        query_id: Primary key of the query history record to delete.

    Returns:
        True if a record was found and deleted, False otherwise.

    Raises:
        SQLAlchemyError: If the deletion fails.
    """
    query_history = session.get(QueryHistory, query_id)
    if query_history is None:
        logger.warning("Attempted to delete nonexistent query history id=%s", query_id)
        return False

    try:
        session.delete(query_history)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to delete query history id=%s", query_id)
        raise

    logger.info("Deleted query history id=%s", query_id)
    return True


def count_repositories(session: Session, *, workspace_id: str | None = None) -> int:
    """Return the total number of registered repositories."""
    statement = select(func.count()).select_from(Repository)
    if workspace_id is not None:
        statement = statement.where(Repository.workspace_id == workspace_id)
    return int(session.scalar(statement) or 0)


def count_repositories_by_status(session: Session, *, status: str, workspace_id: str | None = None) -> int:
    """Count repositories in one indexing status."""
    return int(
        session.scalar(
            select(func.count()).select_from(Repository).where(Repository.indexing_status == status).where(
                Repository.workspace_id == workspace_id if workspace_id is not None else True
            )
        )
        or 0
    )


def update_repository_status(session: Session, repository_id: int | str, status: str, *, workspace_id: str | None = None, **fields: object) -> Repository | None:
    """Compatibility wrapper for status updates from orchestration routes."""
    repository = update_repository_indexing_status(
        session,
        int(repository_id),
        str(getattr(status, "value", status)),
        total_files=fields.get("total_files"),
        total_chunks=fields.get("total_chunks"),
        total_embeddings=fields.get("total_embeddings"),
        indexing_stage=fields.get("indexing_stage"),
        indexing_progress=fields.get("indexing_progress"),
        mark_indexed_now=str(getattr(status, "value", status)) == "ready",
        workspace_id=workspace_id,
    )
    if repository is not None and "error_message" in fields:
        repository.last_indexing_error = str(fields["error_message"])
        repository.updated_at = _utcnow()
        session.commit()
        session.refresh(repository)
    return repository


def replace_indexed_files(session: Session, repository_id: int | str, parsed_files: Sequence[object], *, workspace_id: str | None = None) -> list[IndexedFile]:
    """Replace file metadata for a repository after a successful parse."""
    repository_id = int(repository_id)
    existing = list_repository_files(session, repository_id, limit=100_000, workspace_id=workspace_id)
    for indexed_file in existing:
        session.delete(indexed_file)
    session.flush()

    records: list[dict[str, object]] = []
    for parsed_file in parsed_files:
        chunks = list(getattr(parsed_file, "chunks", []) or [])
        records.append(
            {
                "repository_id": repository_id,
                "relative_path": str(getattr(parsed_file, "relative_path", getattr(parsed_file, "file_path", ""))),
                "programming_language": str(getattr(parsed_file, "programming_language", getattr(parsed_file, "language", ""))),
                "file_size": int(getattr(parsed_file, "file_size", 0)),
                "checksum": str(getattr(parsed_file, "checksum", "")),
                "chunk_count": len(chunks),
            }
        )
    return bulk_create_indexed_files(session, records) if records else []


def clear_indexed_files(session: Session, repository_id: int | str) -> int:
    """Delete all indexed-file rows for a repository in one transaction."""
    repository_id = int(repository_id)
    statement = select(IndexedFile).where(IndexedFile.repository_id == repository_id)
    files = list(session.execute(statement).scalars().all())
    for indexed_file in files:
        session.delete(indexed_file)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("Failed to clear indexed files for repository_id=%s", repository_id)
        raise
    logger.info("Cleared %d indexed file(s) for repository_id=%s", len(files), repository_id)
    return len(files)
