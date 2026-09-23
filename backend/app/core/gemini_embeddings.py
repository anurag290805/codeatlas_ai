"""Gemini embedding provider using current google-genai SDK."""
from __future__ import annotations

import os
from typing import Any

import numpy as np
from loguru import logger

from app.config import get_settings
from app.core.embeddings import AbstractEmbeddingProvider, EmbeddingError, EmbeddingGenerationError, EmbeddingInputError

# Verified current supported model (Google docs 2026-09-18)
DEFAULT_GEMINI_EMBED_MODEL = "gemini-embedding-2"
# Dimension is configurable via output_dimensionality; default/recommended 768.
GEMINI_EMBED_DIMENSION_DEFAULT = 768


class GeminiEmbeddingProvider(AbstractEmbeddingProvider):
    """Gemini API embedding provider using google-genai (current SDK)."""

    def __init__(
        self,
        model_name: str | None = None,
        *,
        api_key: str | None = None,
        output_dimensionality: int | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or getattr(settings, "embedding_model", DEFAULT_GEMINI_EMBED_MODEL) or DEFAULT_GEMINI_EMBED_MODEL
        self._api_key = api_key or (getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", ""))
        self._output_dim = output_dimensionality or getattr(settings, "embedding_dimension", GEMINI_EMBED_DIMENSION_DEFAULT) or GEMINI_EMBED_DIMENSION_DEFAULT
        self._dimension: int | None = self._output_dim
        if not self._api_key:
            logger.warning("GeminiEmbeddingProvider initialized without API key.")
        logger.info("GeminiEmbeddingProvider model={} dimension={} sdk=google-genai", self._model_name, self._dimension)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def embed_text(self, text: str) -> np.ndarray:
        self._validate_text(text)
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        self._validate_texts(texts)
        try:
            from google import genai
            from google.genai import types
        except Exception as exc:
            raise EmbeddingGenerationError("google-genai not installed; install 'google-genai' to use Gemini embeddings.") from exc
        if not self._api_key:
            raise EmbeddingGenerationError("Gemini API key not configured.")
        try:
            client = genai.Client(api_key=self._api_key)
            # Batch: pass list of strings to contents; config sets output_dimensionality
            response = client.models.embed_content(
                model=self._model_name,
                contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=self._output_dim),
            )
            # Response object has .embeddings list; each may have .values
            embeddings = []
            if hasattr(response, "embeddings") and response.embeddings is not None:
                embeddings = response.embeddings
            elif isinstance(response, dict):
                embeddings = response.get("embeddings", [])
            if not embeddings:
                raise EmbeddingGenerationError("Gemini embed_content returned no embeddings.")
            arrays = []
            for emb in embeddings:
                if hasattr(emb, "values"):
                    arrays.append(np.array(emb.values, dtype=np.float32))
                elif isinstance(emb, (list, tuple)):
                    arrays.append(np.array(emb, dtype=np.float32))
                elif isinstance(emb, dict) and "values" in emb:
                    arrays.append(np.array(emb["values"], dtype=np.float32))
                else:
                    # Fallback: treat emb as flat list
                    arrays.append(np.array(emb, dtype=np.float32))
            if not arrays:
                raise EmbeddingGenerationError("No embedding arrays extracted from Gemini response.")
            # Stack; if single text, arrays length = 1
            array = np.stack(arrays).astype(np.float32)
            if array.ndim == 1:
                array = array.reshape(1, -1)
            if array.ndim != 2 or array.shape[0] != len(texts):
                raise EmbeddingGenerationError(f"Gemini embedding batch shape invalid: expected ({len(texts)}, {self._output_dim}), got {array.shape}")
            actual_dim = int(array.shape[1])
            if actual_dim != self._output_dim:
                logger.warning("Gemini returned dimension %d, expected %d", actual_dim, self._output_dim)
            self._record_dimension(actual_dim)
            return array
        except EmbeddingError:
            raise
        except Exception as exc:
            logger.exception("Gemini embedding batch failed")
            raise EmbeddingGenerationError("Gemini embedding request failed") from exc

    def _record_dimension(self, dimension: int) -> None:
        if self._dimension is not None and self._dimension != dimension:
            raise EmbeddingGenerationError(
                f"Embedding dimension changed from {self._dimension} to {dimension}"
            )
        self._dimension = dimension

    @staticmethod
    def _validate_text(text: str) -> None:
        if not isinstance(text, str):
            raise EmbeddingInputError("Embedding text must be a string")
        if not text.strip():
            raise EmbeddingInputError("Embedding text must not be empty")

    @classmethod
    def _validate_texts(cls, texts: list[str]) -> None:
        if not isinstance(texts, list) or not texts:
            raise EmbeddingInputError("Embedding batch must be non-empty")
        for text in texts:
            cls._validate_text(text)
