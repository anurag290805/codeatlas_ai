"""Regression tests for vector metadata persistence."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.core.embeddings import ChunkEmbedding, EmbeddingService
from app.core.vector_store import (
    StoredVectorRecord,
    _chunk_embedding_to_record,
    _record_to_storage_metadata,
    _storage_metadata_to_record,
)


def test_source_code_survives_storage_metadata_round_trip() -> None:
    source_code = "def authenticate(user):\n    return user.is_valid()"
    record = StoredVectorRecord(
        chunk_id="chunk-1",
        repository_id="repo-1",
        file_path="src/auth.py",
        symbol_name="authenticate",
        symbol_type="function",
        language="python",
        start_line=1,
        end_line=2,
        metadata={"code": source_code, "team": "platform"},
    )

    persisted = _record_to_storage_metadata(record)
    restored = _storage_metadata_to_record(record.chunk_id, persisted)

    assert persisted["code"] == source_code
    assert restored.metadata["code"] == source_code
    assert restored.metadata["team"] == "platform"


def test_json_metadata_code_is_restored_for_backward_compatibility() -> None:
    persisted = {
        "repository_id": "repo-1",
        "chunk_id": "chunk-1",
        "file_path": "src/auth.py",
        "symbol_name": "authenticate",
        "symbol_type": "function",
        "language": "python",
        "start_line": 1,
        "end_line": 2,
        "metadata_json": '{"code": "def authenticate():\\n    pass"}',
    }

    restored = _storage_metadata_to_record("chunk-1", persisted)

    assert restored.metadata["code"] == "def authenticate():\n    pass"


def test_chunk_embedding_record_preserves_code_metadata() -> None:
    embedding = ChunkEmbedding(
        chunk_id="chunk-1",
        repository_id="repo-1",
        file_path="src/auth.py",
        vector=np.array([0.1, 0.2], dtype=np.float32),
        model_name="test-model",
        provider_name="test-provider",
        symbol_name="authenticate",
        symbol_type="function",
        language="python",
        metadata={"code": "def authenticate():\n    pass", "start_line": 1, "end_line": 2},
    )

    record = _chunk_embedding_to_record(embedding)

    assert record.metadata["code"] == "def authenticate():\n    pass"


def test_embedding_generation_preserves_chunk_line_ranges() -> None:
    class FakeProvider:
        provider_name = "test-provider"
        model_name = "test-model"
        dimension = 2

        def embed_batch(self, texts: list[str]) -> np.ndarray:
            return np.ones((len(texts), 2), dtype=np.float32)

        def embed_text(self, text: str) -> np.ndarray:
            return np.ones(2, dtype=np.float32)

    chunk = SimpleNamespace(
        chunk_id="chunk-1",
        repository_id=1,
        relative_path="src/auth.py",
        symbol_name="authenticate",
        symbol_type="function",
        programming_language="python",
        source_code="def authenticate():\n    pass",
        start_line=12,
        end_line=13,
        metadata={},
    )

    result = EmbeddingService(provider=FakeProvider()).generate_embeddings([chunk])

    assert result.embeddings[0].metadata["start_line"] == 12
    assert result.embeddings[0].metadata["end_line"] == 13
