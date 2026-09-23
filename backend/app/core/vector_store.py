"""
Vector storage service for CodeAtlas AI.

This module is the sole point of contact between the backend and the
underlying vector database. It persists and retrieves the embedding vectors
produced by ``app.core.embeddings`` and exposes structured, database-agnostic
result types to the rest of the application.

No other module may communicate with ChromaDB directly. Migrating to a
different vector database (Pinecone, Weaviate, Qdrant, Milvus, etc.) should
require changes only within this module: concrete storage engines implement
``AbstractVectorStore``, and the rest of the backend depends exclusively on
``VectorStoreService``.
"""

from __future__ import annotations

import json
import uuid
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.core.embeddings import ChunkEmbedding
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Collection name prefix applied to every repository-scoped collection. This
# keeps the naming strategy scalable and namespaced as new collection types
# (e.g. cross-repository indexes) are introduced in the future.
#
# ChromaDB rejects collection names longer than 63 characters (and only
# allows alphanumerics, underscores, and hyphens). Every component below is
# sized so a fully qualified name -- including the staged-generation suffix
# appended by ``stage_embeddings`` -- always stays well under that limit.
_COLLECTION_NAME_PREFIX = "codeatlas"
# Length of the per-workspace namespace hash embedded in each collection name.
# 9 hex characters (36 bits) is enough to isolate workspaces while keeping
# the qualified name short. A 10-char namespace pushes the fully qualified
# staged name (with 32-char UUID suffix) to 64 chars, exceeding ChromaDB's
# 63-char limit. 9 chars brings it to exactly 63.
_NAMESPACE_HASH_LENGTH = 9

# Metadata key used to store non-scalar chunk metadata as a JSON string,
# since most vector database backends only accept flat scalar metadata.
_METADATA_JSON_KEY = "metadata_json"

# Reserved metadata keys with dedicated storage fields. These are excluded
# from the JSON-encoded metadata blob to avoid duplication.
_RESERVED_METADATA_KEYS = frozenset(
    {
        "repository_id",
        "chunk_id",
        "file_path",
        "symbol_name",
        "symbol_type",
        "language",
        "start_line",
        "end_line",
        "code",
    }
)


class VectorStoreError(Exception):
    """Base exception for all vector storage failures."""


class UnsupportedVectorStoreError(VectorStoreError):
    """Raised when the configured vector store backend is not recognized."""


class CollectionNotFoundError(VectorStoreError):
    """Raised when an operation targets a collection that does not exist."""


class VectorInsertionError(VectorStoreError):
    """Raised when inserting or updating vectors fails."""


class VectorSearchError(VectorStoreError):
    """Raised when a similarity search fails."""


class VectorDeletionError(VectorStoreError):
    """Raised when deleting vectors or a collection fails."""


class VectorStorePersistenceError(VectorStoreError):
    """Raised when the underlying vector database is unavailable or corrupted."""


@dataclass(frozen=True)
class StoredVectorRecord:
    """Metadata describing a single vector persisted in the vector store."""

    chunk_id: str
    repository_id: str
    file_path: str
    symbol_name: str | None
    symbol_type: str | None
    language: str
    start_line: int | None
    end_line: int | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorSearchResult:
    """A single similarity search match, ranked by relevance."""

    record: StoredVectorRecord
    similarity_score: float


@dataclass(frozen=True)
class SearchFilters:
    """Optional constraints applied to a similarity search."""

    language: str | None = None
    symbol_type: str | None = None
    metadata_equals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionStats:
    """Aggregate statistics describing a repository's vector collection."""

    collection_name: str
    repository_id: str
    vector_count: int


def _chunk_embedding_to_record(embedding: ChunkEmbedding) -> StoredVectorRecord:
    """Derive the persisted metadata record for a ``ChunkEmbedding``."""
    metadata = embedding.metadata or {}
    return StoredVectorRecord(
        chunk_id=embedding.chunk_id,
        repository_id=embedding.repository_id,
        file_path=embedding.file_path,
        symbol_name=embedding.symbol_name,
        symbol_type=embedding.symbol_type,
        language=embedding.language,
        start_line=metadata.get("start_line"),
        end_line=metadata.get("end_line"),
        metadata=metadata,
    )


def _record_to_storage_metadata(record: StoredVectorRecord) -> dict[str, Any]:
    """
    Flatten a ``StoredVectorRecord`` into a scalar-only metadata mapping.

    Vector database backends commonly restrict stored metadata to primitive
    scalar types. Any additional, non-reserved metadata is preserved as a
    JSON-encoded string so no information is lost.
    """
    extra_metadata = {
        key: value
        for key, value in record.metadata.items()
        if key not in _RESERVED_METADATA_KEYS
    }

    storage_metadata: dict[str, Any] = {
        "repository_id": record.repository_id,
        "chunk_id": record.chunk_id,
        "file_path": record.file_path,
        "symbol_name": record.symbol_name or "",
        "symbol_type": record.symbol_type or "",
        "language": record.language,
        "start_line": record.start_line if record.start_line is not None else -1,
        "end_line": record.end_line if record.end_line is not None else -1,
        # Source code is a required retrieval field and Chroma supports it
        # as a scalar string. Store it explicitly rather than relying on the
        # auxiliary JSON blob, which keeps the schema queryable and makes the
        # contract with RetrieverService unambiguous.
        "code": str(record.metadata.get("code", "")),
        _METADATA_JSON_KEY: json.dumps(extra_metadata, default=str),
    }
    return storage_metadata


def _storage_metadata_to_record(
    chunk_id: str, storage_metadata: dict[str, Any]
) -> StoredVectorRecord:
    """Reconstruct a ``StoredVectorRecord`` from persisted flat metadata."""
    try:
        decoded_metadata = json.loads(storage_metadata.get(_METADATA_JSON_KEY, "{}"))
        extra_metadata = decoded_metadata if isinstance(decoded_metadata, dict) else {}
    except (TypeError, json.JSONDecodeError):
        extra_metadata = {}

    # New records store code as a dedicated field. The JSON fallback preserves
    # compatibility with any intermediate records that serialized code before
    # the dedicated field was introduced.
    if "code" in storage_metadata:
        extra_metadata["code"] = storage_metadata["code"]

    start_line = storage_metadata.get("start_line")
    end_line = storage_metadata.get("end_line")

    return StoredVectorRecord(
        chunk_id=chunk_id,
        repository_id=storage_metadata.get("repository_id", ""),
        file_path=storage_metadata.get("file_path", ""),
        symbol_name=storage_metadata.get("symbol_name") or None,
        symbol_type=storage_metadata.get("symbol_type") or None,
        language=storage_metadata.get("language", ""),
        start_line=None if start_line in (None, -1) else int(start_line),
        end_line=None if end_line in (None, -1) else int(end_line),
        metadata=extra_metadata,
    )


class AbstractVectorStore(ABC):
    """
    Abstract interface for a vector database backend.

    Implementations are responsible only for persistence and retrieval
    mechanics against a specific vector database engine. They must not
    contain repository-naming policy or application-level orchestration;
    that responsibility belongs to ``VectorStoreService``.
    """

    @abstractmethod
    def create_collection(self, collection_name: str) -> None:
        """Create a collection if it does not already exist."""

    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """Return whether ``collection_name`` currently exists."""

    @abstractmethod
    def delete_collection(self, collection_name: str) -> None:
        """Permanently delete a collection and all vectors within it."""

    @abstractmethod
    def reset_collection(self, collection_name: str) -> None:
        """Delete and immediately recreate an empty collection."""

    @abstractmethod
    def upsert_vectors(
        self, collection_name: str, embeddings: list[ChunkEmbedding]
    ) -> int:
        """Insert new vectors or overwrite existing ones by chunk identifier."""

    @abstractmethod
    def delete_vectors(self, collection_name: str, chunk_ids: list[str]) -> int:
        """Delete vectors identified by ``chunk_ids``."""

    @abstractmethod
    def delete_by_metadata(
        self, collection_name: str, field_name: str, value: str
    ) -> int:
        """Delete all vectors whose metadata field equals ``value``."""

    @abstractmethod
    def similarity_search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: SearchFilters | None,
    ) -> list[VectorSearchResult]:
        """Return the ``top_k`` vectors most similar to ``query_vector``."""

    @abstractmethod
    def count_vectors(self, collection_name: str) -> int:
        """Return the number of vectors currently stored in a collection."""


class ChromaVectorStore(AbstractVectorStore):
    """``AbstractVectorStore`` implementation backed by ChromaDB."""

    def __init__(self, persist_directory: str) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        persist_directory = str(persist_directory)

        try:
            # Chroma 0.5.x still invokes its PostHog client even when the
            # setting disables telemetry. Disable the client explicitly as a
            # compatibility safeguard for newer posthog signatures.
            import posthog

            posthog.disabled = True
            self._client = chromadb.PersistentClient(
                path=persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a domain error
            raise VectorStorePersistenceError(
                f"Failed to initialize ChromaDB at '{persist_directory}'."
            ) from exc

        logger.info("ChromaDB client initialized at '%s'.", persist_directory)

    def create_collection(self, collection_name: str) -> None:
        try:
            self._client.get_or_create_collection(name=collection_name)
        except Exception as exc:
            logger.exception("Chroma collection creation failed")
            raise
        logger.info("Collection '%s' is ready.", collection_name)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            existing = {c.name for c in self._client.list_collections()}
        except Exception as exc:  # noqa: BLE001
            raise VectorStorePersistenceError(
                "Failed to list ChromaDB collections."
            ) from exc
        return collection_name in existing

    def delete_collection(self, collection_name: str) -> None:
        if not self.collection_exists(collection_name):
            raise CollectionNotFoundError(
                f"Collection '{collection_name}' does not exist."
            )
        try:
            self._client.delete_collection(name=collection_name)
        except Exception as exc:  # noqa: BLE001
            raise VectorDeletionError(
                f"Failed to delete collection '{collection_name}'."
            ) from exc
        logger.info("Collection '%s' deleted.", collection_name)

    def reset_collection(self, collection_name: str) -> None:
        if self.collection_exists(collection_name):
            self.delete_collection(collection_name)
        self.create_collection(collection_name)
        logger.info("Collection '%s' reset.", collection_name)

    def upsert_vectors(
        self, collection_name: str, embeddings: list[ChunkEmbedding]
    ) -> int:
        if not embeddings:
            return 0

        collection = self._get_collection(collection_name)
        records = [_chunk_embedding_to_record(embedding) for embedding in embeddings]

        try:
            collection.upsert(
                ids=[record.chunk_id for record in records],
                embeddings=[embedding.vector for embedding in embeddings],
                metadatas=[_record_to_storage_metadata(record) for record in records],
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorInsertionError(
                f"Failed to upsert {len(embeddings)} vector(s) into "
                f"collection '{collection_name}'."
            ) from exc

        logger.info(
            "Upserted %d vector(s) into collection '%s'.",
            len(embeddings),
            collection_name,
        )
        return len(embeddings)

    def delete_vectors(self, collection_name: str, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0

        collection = self._get_collection(collection_name)
        try:
            collection.delete(ids=chunk_ids)
        except Exception as exc:  # noqa: BLE001
            raise VectorDeletionError(
                f"Failed to delete {len(chunk_ids)} vector(s) from "
                f"collection '{collection_name}'."
            ) from exc

        logger.info(
            "Deleted %d vector(s) from collection '%s'.",
            len(chunk_ids),
            collection_name,
        )
        return len(chunk_ids)

    def delete_by_metadata(
        self, collection_name: str, field_name: str, value: str
    ) -> int:
        collection = self._get_collection(collection_name)
        try:
            matches = collection.get(where={field_name: value})
            matched_ids = matches.get("ids", [])
            if matched_ids:
                collection.delete(ids=matched_ids)
        except Exception as exc:  # noqa: BLE001
            raise VectorDeletionError(
                f"Failed to delete vectors where '{field_name}' == '{value}' "
                f"from collection '{collection_name}'."
            ) from exc

        logger.info(
            "Deleted %d vector(s) from collection '%s' where %s == '%s'.",
            len(matched_ids),
            collection_name,
            field_name,
            value,
        )
        return len(matched_ids)

    def similarity_search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: SearchFilters | None,
    ) -> list[VectorSearchResult]:
        collection = self._get_collection(collection_name)
        where_clause = _build_where_clause(filters)

        try:
            response = collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=where_clause if where_clause else None,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorSearchError(
                f"Similarity search failed against collection '{collection_name}'."
            ) from exc

        return _parse_query_response(response)

    def count_vectors(self, collection_name: str) -> int:
        collection = self._get_collection(collection_name)
        try:
            return collection.count()
        except Exception as exc:  # noqa: BLE001
            raise VectorStorePersistenceError(
                f"Failed to count vectors in collection '{collection_name}'."
            ) from exc

    def _get_collection(self, collection_name: str):
        try:
            return self._client.get_collection(name=collection_name)
        except Exception as exc:  # noqa: BLE001
            raise CollectionNotFoundError(
                f"Collection '{collection_name}' does not exist."
            ) from exc


def _build_where_clause(filters: SearchFilters | None) -> dict[str, Any]:
    """Translate ``SearchFilters`` into a ChromaDB ``where`` clause."""
    if filters is None:
        return {}

    conditions: dict[str, Any] = {}
    if filters.language:
        conditions["language"] = filters.language
    if filters.symbol_type:
        conditions["symbol_type"] = filters.symbol_type
    conditions.update(filters.metadata_equals)

    if len(conditions) <= 1:
        return conditions
    return {"$and": [{key: value} for key, value in conditions.items()]}


def _parse_query_response(response: dict[str, Any]) -> list[VectorSearchResult]:
    """Convert a raw ChromaDB query response into ``VectorSearchResult`` objects."""
    ids = (response.get("ids") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]

    results: list[VectorSearchResult] = []
    for chunk_id, metadata, distance in zip(ids, metadatas, distances, strict=True):
        record = _storage_metadata_to_record(chunk_id, metadata or {})
        # ChromaDB's default space is squared-L2 distance; convert to a
        # similarity score in a stable, human-interpretable direction where
        # higher values indicate greater similarity.
        similarity_score = 1.0 / (1.0 + distance)
        results.append(VectorSearchResult(record=record, similarity_score=similarity_score))

    return results


def _create_vector_store(backend_name: str, persist_directory: str) -> AbstractVectorStore:
    """Instantiate the vector store backend identified by ``backend_name``."""
    normalized = backend_name.strip().lower()

    if normalized == "chroma":
        return ChromaVectorStore(persist_directory=persist_directory)

    raise UnsupportedVectorStoreError(
        f"Vector store backend '{backend_name}' is not supported."
    )


class VectorStoreService:
    """
    Public interface for all vector persistence and retrieval operations.

    This is the only vector-storage type the rest of the backend should
    depend on. It owns the repository-to-collection naming strategy and
    delegates all persistence mechanics to an injected ``AbstractVectorStore``.
    """

    def __init__(self, store: AbstractVectorStore | None = None) -> None:
        """
        Args:
            store: An explicit ``AbstractVectorStore`` to use. When omitted,
                a store is constructed from application configuration.
        """
        self._store = store or self._build_store_from_settings()

    @staticmethod
    def _build_store_from_settings() -> AbstractVectorStore:
        settings = get_settings()
        return _create_vector_store(
            backend_name=getattr(settings, "vector_store_backend", "chroma"),
            persist_directory=settings.chroma_persist_directory,
        )

    @staticmethod
    def _collection_name_for(repository_id: str, workspace_id: str | None = None) -> str:
        """Derive the collection name for a repository's isolated index.

        Total length must stay under ChromaDB's 63-char limit. The pattern is:
        codeatlas_{10-char-ns}_{repo_id}_{staged-suffix}
        Where staged-suffix is appended by ``stage_embeddings`` (32-char hex UUID).
        Max: 8 + 1 + 10 + 1 + 10 (repo_id) + 1 + 32 = 63 chars exactly.
        """
        namespace = hashlib.sha256(workspace_id.encode()).hexdigest()[:_NAMESPACE_HASH_LENGTH] if workspace_id else "legacy"
        return f"{_COLLECTION_NAME_PREFIX}_{namespace}_{repository_id}"

    def _active_collection_name(self, repository_id: str, workspace_id: str | None = None) -> str:
        """Resolve the durable collection pointer, with legacy-name fallback."""
        settings = get_settings()
        namespace = hashlib.sha256(workspace_id.encode()).hexdigest()[:_NAMESPACE_HASH_LENGTH] if workspace_id else "legacy"
        pointer = settings.chroma_persist_directory / f"active_{namespace}_{repository_id}.json"
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
            name = str(payload.get("collection", ""))
            if name and self._store.collection_exists(name):
                return name
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        return self._collection_name_for(repository_id, workspace_id)

    def stage_embeddings(self, repository_id: str, embeddings: list[ChunkEmbedding], workspace_id: str | None = None) -> str:
        """Write a complete new generation without touching the active index."""
        collection_name = f"{self._collection_name_for(repository_id, workspace_id)}_{uuid.uuid4().hex}"
        self._store.create_collection(collection_name)
        try:
            self._store.upsert_vectors(collection_name, embeddings)
        except Exception:
            try:
                self._store.delete_collection(collection_name)
            except Exception:
                logger.exception("Failed to clean staged collection '%s'", collection_name)
            raise
        return collection_name

    def publish_staged_collection(self, repository_id: str, collection_name: str, workspace_id: str | None = None) -> None:
        """Publish a staged generation by atomically replacing its pointer."""
        settings = get_settings()
        settings.chroma_persist_directory.mkdir(parents=True, exist_ok=True)
        namespace = hashlib.sha256(workspace_id.encode()).hexdigest()[:_NAMESPACE_HASH_LENGTH] if workspace_id else "legacy"
        pointer = settings.chroma_persist_directory / f"active_{namespace}_{repository_id}.json"
        old_name = self._active_collection_name(repository_id, workspace_id)
        temporary = pointer.with_suffix(f".json.tmp-{uuid.uuid4().hex}")
        temporary.write_text(json.dumps({"collection": collection_name}), encoding="utf-8")
        temporary.replace(pointer)
        if old_name != collection_name and self._store.collection_exists(old_name):
            self._store.delete_collection(old_name)
        logger.info("Published vector generation repository_id=%s collection=%s", repository_id, collection_name)

    def discard_staged_collection(self, collection_name: str) -> None:
        """Remove only a staged collection."""
        if self._store.collection_exists(collection_name):
            self._store.delete_collection(collection_name)

    def ensure_repository_collection(self, repository_id: str, workspace_id: str | None = None) -> None:
        """Create the repository's collection if it does not already exist."""
        self._store.create_collection(self._collection_name_for(repository_id, workspace_id))

    def repository_collection_exists(self, repository_id: str, workspace_id: str | None = None) -> bool:
        """Return whether a collection exists for ``repository_id``."""
        return self._store.collection_exists(self._active_collection_name(repository_id, workspace_id))

    def index_embeddings(
        self, repository_id: str, embeddings: list[ChunkEmbedding], workspace_id: str | None = None
    ) -> int:
        """
        Persist a batch of embeddings for a repository.

        Insertion is idempotent: embeddings sharing a chunk identifier with
        an existing vector overwrite that vector rather than duplicating it,
        making this method safe to call for both initial indexing and
        re-indexing after a repository update.

        Args:
            repository_id: Identifier of the repository being indexed.
            embeddings: Embeddings produced by ``EmbeddingService``.

        Returns:
            The number of vectors written.
        """
        if not embeddings:
            logger.warning(
                "index_embeddings called with no embeddings for repository '%s'.",
                repository_id,
            )
            return 0

        collection_name = self._active_collection_name(repository_id, workspace_id)
        self.ensure_repository_collection(repository_id, workspace_id)
        return self._store.upsert_vectors(collection_name, embeddings)

    def update_embeddings(
        self, repository_id: str, embeddings: list[ChunkEmbedding], workspace_id: str | None = None
    ) -> int:
        """
        Update previously indexed embeddings for a repository.

        This is functionally identical to ``index_embeddings`` since
        insertion is idempotent; the distinct name documents intent at
        call sites that re-index modified files.
        """
        return self.index_embeddings(repository_id, embeddings, workspace_id)

    def search(
        self,
        repository_id: str,
        query_vector: list[float],
        top_k: int = 10,
        filters: SearchFilters | None = None, workspace_id: str | None = None,
    ) -> list[VectorSearchResult]:
        """
        Perform a similarity search scoped to a single repository.

        Args:
            repository_id: Repository whose collection should be searched.
            query_vector: The embedding vector to search against.
            top_k: Maximum number of results to return.
            filters: Optional language, symbol-type, or metadata constraints.

        Returns:
            Ranked ``VectorSearchResult`` objects, most similar first.

        Raises:
            CollectionNotFoundError: If the repository has not been indexed.
            VectorSearchError: If the underlying search fails.
        """
        if top_k <= 0:
            raise VectorSearchError("top_k must be a positive integer.")

        collection_name = self._active_collection_name(repository_id, workspace_id)
        logger.info(
            "Running similarity search on repository '%s' (top_k=%d).",
            repository_id,
            top_k,
        )
        return self._store.similarity_search(
            collection_name, query_vector, top_k, filters
        )

    def delete_chunk(self, repository_id: str, chunk_id: str) -> None:
        """Delete a single chunk's vector from a repository's collection."""
        self.delete_chunks(repository_id, [chunk_id])

    def delete_chunks(self, repository_id: str, chunk_ids: list[str]) -> int:
        """Delete a batch of chunk vectors from a repository's collection."""
        collection_name = self._active_collection_name(repository_id)
        return self._store.delete_vectors(collection_name, chunk_ids)

    def delete_repository(self, repository_id: str, workspace_id: str | None = None) -> None:
        """
        Permanently delete a repository's entire vector collection.

        This is a no-op, logged at warning level, if the repository has no
        existing collection rather than raising an error, since callers
        frequently invoke this as part of idempotent cleanup routines.
        """
        collection_name = self._active_collection_name(repository_id, workspace_id)
        if not self._store.collection_exists(collection_name):
            logger.warning(
                "delete_repository called for '%s' but no collection exists.",
                repository_id,
            )
            return
        self._store.delete_collection(collection_name)
        try:
            namespace = hashlib.sha256(workspace_id.encode()).hexdigest()[:_NAMESPACE_HASH_LENGTH] if workspace_id else "legacy"
            (get_settings().chroma_persist_directory / f"active_{namespace}_{repository_id}.json").unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove active collection pointer repository_id=%s", repository_id)

    def clear_repository(self, repository_id: str) -> None:
        """Remove all vectors for a repository while keeping its collection."""
        collection_name = self._collection_name_for(repository_id)
        self._store.reset_collection(collection_name)

    def get_repository_stats(self, repository_id: str, workspace_id: str | None = None) -> CollectionStats:
        """Return vector count statistics for a repository's collection."""
        collection_name = self._active_collection_name(repository_id, workspace_id)
        vector_count = self._store.count_vectors(collection_name)
        return CollectionStats(
            collection_name=collection_name,
            repository_id=repository_id,
            vector_count=vector_count,
        )

    # Compatibility names used by the repository indexing routes.
    def upsert_embeddings(
        self, repository_id: str, chunks: list[Any], embeddings: Any
    ) -> int:
        """Persist embeddings produced by either embedding service contract."""
        if hasattr(embeddings, "embeddings"):
            embeddings = embeddings.embeddings
        return self.index_embeddings(repository_id, list(embeddings or []))

    def delete_repository_embeddings(self, repository_id: str, workspace_id: str | None = None) -> None:
        """Compatibility alias for deleting a repository collection."""
        self.delete_repository(repository_id, workspace_id)
