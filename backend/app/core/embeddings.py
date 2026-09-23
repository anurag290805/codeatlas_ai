"""Local, lazy, and thread-safe sentence-transformer embeddings.

No network or paid embedding provider is used.  The model is loaded only on
the first embedding request and is protected by a re-entrant lock so one
process does not create multiple heavyweight model instances under load.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

import numpy as np
from loguru import logger

from app.config import get_settings

DEFAULT_EMBEDDING_MODEL = "models/text-embedding-004"
CHARS_PER_TOKEN_ESTIMATE = 4


class EmbeddingError(Exception):
    """Base exception for embedding failures."""


class EmptyTextError(EmbeddingError):
    """Raised when an embedding request contains blank text."""


class EmbeddingGenerationError(EmbeddingError):
    """Raised when the local model cannot generate an embedding."""


class EmbeddingDimensionError(EmbeddingError):
    """Raised when vectors in one batch have inconsistent dimensions."""


class EmbeddingInputError(EmbeddingError):
    """Raised when input types or batch sizes are invalid."""


@dataclass(frozen=True)
class ChunkEmbedding:
    """Embedding plus metadata required by downstream vector storage."""

    chunk_id: str
    repository_id: str
    file_path: str
    vector: np.ndarray
    model_name: str
    provider_name: str
    symbol_name: str | None
    symbol_type: str | None
    language: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingBatchResult:
    """Successful chunk embeddings and identifiers skipped during validation."""

    embeddings: list[ChunkEmbedding]
    skipped_chunk_ids: list[str] = field(default_factory=list)


class AbstractEmbeddingProvider(ABC):
    """Provider contract for single and batched vector generation."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return a stable provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured model identifier."""

    @property
    @abstractmethod
    def dimension(self) -> int | None:
        """Return vector dimension once known, otherwise ``None``."""

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """Embed one non-empty text value."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a non-empty list of text values."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compatibility adapter returning JSON-friendly Python lists."""
        return self.embed_batch(texts).tolist()


class _SentenceTransformer(Protocol):
    max_seq_length: int

    def encode(self, sentences: str | list[str], **kwargs: Any) -> Any: ...


class SentenceTransformerProvider(AbstractEmbeddingProvider):
    """Lazy SentenceTransformer provider with automatic batch encoding."""

    def __init__(
        self,
        model_name: str | None = None,
        *,
        batch_size: int | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        settings = get_settings()
        configured_name = getattr(settings, "embedding_model", None)
        self._model_name = model_name or configured_name or DEFAULT_EMBEDDING_MODEL
        self._batch_size = max(1, int(batch_size or getattr(settings, "embedding_batch_size", 32)))
        self._normalize_embeddings = normalize_embeddings
        self._model: _SentenceTransformer | None = None
        self._dimension: int | None = None
        self._model_lock = RLock()
        logger.info("Configured sentence-transformer model={}", self._model_name)

    @property
    def provider_name(self) -> str:
        return "sentence_transformers"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def embed_text(self, text: str) -> np.ndarray:
        """Encode one text value as a one-dimensional float32 array."""
        self._validate_text(text)
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Encode texts in model-sized batches and return an ``(n, d)`` array."""
        self._validate_texts(texts)
        model = self._get_model()
        batches: list[np.ndarray] = []
        try:
            for start in range(0, len(texts), self._batch_size):
                batch = texts[start : start + self._batch_size]
                logger.debug("Encoding embedding batch start={} size={}", start, len(batch))
                vectors = model.encode(
                    batch,
                    batch_size=self._batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=self._normalize_embeddings,
                    show_progress_bar=False,
                )
                array = np.asarray(vectors, dtype=np.float32)
                if array.ndim == 1:
                    array = array.reshape(1, -1)
                if array.ndim != 2 or array.shape[0] != len(batch):
                    raise EmbeddingGenerationError(
                        "SentenceTransformer returned an invalid batch shape"
                    )
                batches.append(array)
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 - model backends expose varied errors.
            logger.exception("SentenceTransformer encoding failed")
            raise EmbeddingGenerationError("Failed to generate sentence embeddings") from exc

        result = np.concatenate(batches, axis=0).astype(np.float32, copy=False)
        self._record_dimension(result.shape[1])
        return result

    def _get_model(self) -> _SentenceTransformer:
        """Load the model once, safely under concurrent first-use calls."""
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    logger.info("Loading sentence-transformer model={}", self._model_name)
                    self._model = SentenceTransformer(self._model_name)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to load sentence-transformer model={}", self._model_name)
                    raise EmbeddingGenerationError(
                        f"Failed to load embedding model '{self._model_name}'"
                    ) from exc
        return self._model

    def _record_dimension(self, dimension: int) -> None:
        with self._model_lock:
            if self._dimension is not None and self._dimension != dimension:
                raise EmbeddingDimensionError(
                    f"Embedding dimension changed from {self._dimension} to {dimension}"
                )
            self._dimension = dimension

    @staticmethod
    def _validate_text(text: str) -> None:
        if not isinstance(text, str):
            raise EmbeddingInputError("Embedding text must be a string")
        if not text.strip():
            raise EmptyTextError("Embedding text must not be empty")

    @classmethod
    def _validate_texts(cls, texts: list[str]) -> None:
        if not isinstance(texts, list) or not texts:
            raise EmbeddingInputError("Embedding batch must be a non-empty list")
        for text in texts:
            cls._validate_text(text)


class EmbeddingService:
    """Public embedding facade with validation, batching, and async adapters."""

    def __init__(
        self,
        provider: AbstractEmbeddingProvider | None = None,
        *,
        expected_dimension: int | None = None,
    ) -> None:
        # Default dimension from settings; if not configured, derive from provider or default 768
        settings = get_settings()
        default_dim = getattr(settings, "embedding_dimension", 768)
        if provider is not None:
            self._provider = provider
        else:
            from app.core.gemini_embeddings import GeminiEmbeddingProvider
            self._provider = GeminiEmbeddingProvider(output_dimensionality=default_dim)
        self._expected_dimension = expected_dimension or getattr(provider, 'dimension', None) or default_dim
        self._dimension: int | None = self._expected_dimension
        logger.info("Embedding service ready provider={} model={}", self.provider_name, self.model_name)

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    @property
    def dimension(self) -> int | None:
        return self._dimension or self._provider.dimension

    def embed_text(self, text: str) -> np.ndarray:
        """Validate and embed one text value."""
        self._validate_text(text)
        vector = np.asarray(self._provider.embed_text(text), dtype=np.float32)
        self._validate_vectors(vector.reshape(1, -1), 1)
        return vector

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Validate and embed a batch, enforcing a stable vector dimension."""
        self._validate_texts(texts)
        vectors = np.asarray(self._provider.embed_batch(texts), dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        self._validate_vectors(vectors, len(texts))
        return vectors

    async def aembed_text(self, text: str) -> np.ndarray:
        """Run synchronous model inference off the event loop."""
        return await asyncio.to_thread(self.embed_text, text)

    async def aembed_batch(self, texts: list[str]) -> np.ndarray:
        """Run synchronous batch inference off the event loop."""
        return await asyncio.to_thread(self.embed_batch, texts)

    def embed_query(self, text: str) -> list[float]:
        """Return a query vector in the list form expected by vector stores."""
        return self.embed_text(text).tolist()

    def generate_embeddings(
        self,
        chunks: list[Any],
        repository_id: str | None = None,
        progress_callback: Any | None = None,
    ) -> EmbeddingBatchResult:
        """Embed repository chunks while preserving chunk metadata."""
        if not chunks:
            return EmbeddingBatchResult([])

        valid: list[tuple[Any, str]] = []
        skipped: list[str] = []
        for chunk in chunks:
            chunk_id = str(getattr(chunk, "chunk_id", "unknown"))
            text = getattr(chunk, "code", getattr(chunk, "source_code", ""))
            try:
                self._validate_text(text)
            except EmbeddingError as exc:
                logger.warning("Skipping chunk={} reason={}", chunk_id, exc)
                skipped.append(chunk_id)
            else:
                valid.append((chunk, text))

        if not valid:
            return EmbeddingBatchResult([], skipped)

        vectors = self.embed_batch([text for _, text in valid])
        if progress_callback:
            progress_callback(len(valid), len(valid))
        embeddings = [
            self._to_chunk_embedding(chunk, vectors[index], repository_id)
            for index, (chunk, _) in enumerate(valid)
        ]
        return EmbeddingBatchResult(embeddings, skipped)

    def _to_chunk_embedding(self, chunk: Any, vector: np.ndarray, repository_id: str | None) -> ChunkEmbedding:
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        # The vector store persists metadata, not the original CodeChunk.
        # Preserve the source text here so retrieval can reconstruct the
        # citation-ready code without reading the repository again.
        source_code = getattr(chunk, "code", getattr(chunk, "source_code", ""))
        if isinstance(source_code, str) and source_code:
            metadata.setdefault("code", source_code)
        # Line ranges are first-class fields on CodeChunk rather than entries
        # in its metadata mapping. Carry them into the persisted metadata so
        # vector retrieval can build valid source citations after deserialization.
        for line_key in ("start_line", "end_line"):
            line_value = getattr(chunk, line_key, None)
            if line_value is not None:
                metadata.setdefault(line_key, line_value)
        chunk_repository = repository_id or str(getattr(chunk, "repository_id", ""))
        file_path = getattr(chunk, "file_path", getattr(chunk, "relative_path", ""))
        language = getattr(chunk, "language", getattr(chunk, "programming_language", ""))
        return ChunkEmbedding(
            chunk_id=str(getattr(chunk, "chunk_id", "")),
            repository_id=str(chunk_repository),
            file_path=str(file_path),
            vector=np.asarray(vector, dtype=np.float32),
            model_name=self.model_name,
            provider_name=self.provider_name,
            symbol_name=getattr(chunk, "symbol_name", None),
            symbol_type=str(getattr(chunk, "symbol_type", "")) or None,
            language=str(language),
            metadata=metadata,
        )

    def _validate_vectors(self, vectors: np.ndarray, expected_rows: int) -> None:
        if vectors.ndim != 2 or vectors.shape[0] != expected_rows or vectors.shape[1] == 0:
            raise EmbeddingGenerationError("Embedding provider returned an invalid vector shape")
        dimension = int(vectors.shape[1])
        if self._dimension is None:
            self._dimension = dimension
        elif self._dimension != dimension:
            raise EmbeddingDimensionError(
                f"Expected embedding dimension {self._dimension}, received {dimension}"
            )

    @staticmethod
    def _validate_text(text: str) -> None:
        if not isinstance(text, str):
            raise EmbeddingInputError("Embedding text must be a string")
        if not text.strip():
            raise EmptyTextError("Embedding text must not be empty")

    @classmethod
    def _validate_texts(cls, texts: list[str]) -> None:
        if not isinstance(texts, list) or not texts:
            raise EmbeddingInputError("Embedding batch must be a non-empty list")
        for text in texts:
            cls._validate_text(text)


def estimate_token_count(text: str) -> int:
    """Estimate token count using a conservative character heuristic."""
    if not isinstance(text, str):
        raise EmbeddingInputError("Token estimation requires a string")
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


# Backward-compatible name for consumers written against the previous module.
EmbeddingProvider = AbstractEmbeddingProvider
