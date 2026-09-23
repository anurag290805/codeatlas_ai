"""
Semantic retrieval engine for CodeAtlas AI.

This module is the bridge between a user's natural language question and
the code context an LLM needs to answer it. It embeds the query, performs
similarity search through ``VectorStoreService``, filters and reranks the
resulting candidates, and assembles a token-budgeted, citation-ready context
object for downstream LLM consumption.

The retriever never calls ChromaDB directly (it depends only on
``VectorStoreService``), never generates embeddings itself (it depends only
on ``EmbeddingService``), and never calls an LLM. Its sole responsibility is
producing the highest-quality grounded context available for a query.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.config import get_settings
from app.core.embeddings import EmbeddingError, EmbeddingService, estimate_token_count
from app.core.vector_store import (
    CollectionNotFoundError,
    SearchFilters,
    StoredVectorRecord,
    VectorSearchResult,
    VectorStoreError,
    VectorStoreService,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Metadata key under which the original chunk source text is expected to be
# stored. Vector storage is responsible for persisting this value at index
# time so that retrieval never needs to reparse a repository.
_CODE_METADATA_KEY = "code"

# Multiplier applied to the caller-requested top_k when querying the vector
# store, giving downstream filtering and reranking stages headroom to
# discard invalid, duplicate, or low-relevance candidates without
# under-filling the final result set.
_CANDIDATE_POOL_MULTIPLIER = 3

# Hard ceiling on how many candidates are pulled from the vector store per
# query, regardless of the requested top_k, to bound worst-case latency.
_MAX_CANDIDATE_POOL_SIZE = 200


class RetrievalError(Exception):
    """Base exception for all retrieval failures."""


class EmptyQueryError(RetrievalError):
    """Raised when a retrieval query has no usable text or repository id."""


class RepositoryNotIndexedError(RetrievalError):
    """Raised when the target repository has no vector collection yet."""


class QueryEmbeddingError(RetrievalError):
    """Raised when the query text cannot be embedded."""


class SimilaritySearchFailedError(RetrievalError):
    """Raised when the underlying vector similarity search fails."""


@dataclass(frozen=True)
class RetrievalFilters:
    """Optional constraints narrowing which chunks are eligible for retrieval."""

    language: str | None = None
    symbol_type: str | None = None
    file_path: str | None = None
    metadata_equals: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalQuery:
    """A single natural language retrieval request scoped to one repository."""

    text: str
    repository_id: str
    top_k: int | None = None
    similarity_threshold: float | None = None
    token_budget: int | None = None
    filters: RetrievalFilters | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class CitationReference:
    """Precise source-location citation for a single retrieved chunk."""

    repository_id: str
    file_path: str
    symbol_name: str | None
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True)
class RetrievedChunk:
    """A single piece of retrieved code context, ready for LLM consumption."""

    code: str
    relevance_score: float
    citation: CitationReference
    language: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AssembledContext:
    """Token-budgeted, ordered collection of retrieved chunks for a query."""

    query_text: str
    chunks: list[RetrievedChunk]
    estimated_token_count: int
    token_budget: int
    truncated: bool

    @property
    def citations(self) -> list[CitationReference]:
        """Convenience accessor returning citations for every included chunk."""
        return [chunk.citation for chunk in self.chunks]


@dataclass(frozen=True)
class RetrievalResult:
    """The complete outcome of a retrieval request."""

    query: RetrievalQuery
    context: AssembledContext
    candidates_found: int
    candidates_after_filtering: int

    @property
    def retrieved_chunk_count(self) -> int:
        """Compatibility count for the query orchestration layer."""
        return len(self.context.chunks)

    @property
    def assembled_context(self) -> str:
        """Return retrieved code as a prompt-ready context string."""
        sections = []

        for chunk in self.context.chunks:
            sections.append(
                f"File: {chunk.citation.file_path}\n\n"
                f"{chunk.code[:800]}"
            )

        return "\n\n" + ("\n\n" + "-" * 80 + "\n\n").join(sections)

    @property
    def citations(self) -> list[CitationReference]:
        """Expose included citations for LLM prompt construction."""
        return self.context.citations


@dataclass
class _ScoredChunk:
    """Internal working representation of a candidate during pipeline stages."""

    record: StoredVectorRecord
    code: str
    similarity_score: float
    rank_score: float


class Reranker(ABC):
    """
    Abstract reranking stage applied to candidate chunks after retrieval.

    Concrete implementations receive the original query text and a list of
    similarity-ranked candidates and return a re-ordered list. This is the
    extension point for cross-encoder rerankers, LLM-based reranking, or
    BM25 hybrid retrieval; none of those require changes to
    ``SearchPipeline`` or ``RetrieverService``, only a new ``Reranker``.
    """

    @abstractmethod
    def rerank(
        self, query_text: str, candidates: list[_ScoredChunk]
    ) -> list[_ScoredChunk]:
        """Return ``candidates`` re-ordered from most to least relevant."""


class LexicalOverlapReranker(Reranker):
    """
    Lightweight default reranker combining vector similarity with lexical cues.

    This blends the vector similarity score with a small bonus for query
    terms appearing in a candidate's symbol name or file path, which helps
    surface exact-name matches (e.g. a query mentioning a function by name)
    above vector-similar but less directly relevant chunks. It is
    intentionally cheap: no external model calls are made.
    """

    _LEXICAL_BONUS_WEIGHT = 0.05

    def rerank(
        self, query_text: str, candidates: list[_ScoredChunk]
    ) -> list[_ScoredChunk]:
        query_terms = self._tokenize(query_text)
        if not query_terms:
            return sorted(candidates, key=lambda c: c.similarity_score, reverse=True)

        for candidate in candidates:
            candidate.rank_score = candidate.similarity_score + self._lexical_bonus(
                query_terms, candidate.record
            )

        return sorted(candidates, key=lambda c: c.rank_score, reverse=True)

    def _lexical_bonus(
        self, query_terms: set[str], record: StoredVectorRecord
    ) -> float:
        haystack_terms = self._tokenize(record.symbol_name or "")
        haystack_terms |= self._tokenize(record.file_path)
        overlap = len(query_terms & haystack_terms)
        return overlap * self._LEXICAL_BONUS_WEIGHT

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        separators = ("_", "-", "/", ".", "::", "(", ")")
        normalized = text.lower()
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        return {token for token in normalized.split() if len(token) > 1}


class SearchPipeline:
    """
    Executes the search, filter, deduplicate, and rerank stages of retrieval.

    This isolates every stage that operates on raw candidates before context
    assembly, keeping ``RetrieverService`` focused on orchestration and
    ``ContextAssembler`` focused on token budgeting and output shaping.
    """

    def __init__(
        self,
        vector_store_service: VectorStoreService,
        reranker: Reranker,
    ) -> None:
        self._vector_store_service = vector_store_service
        self._reranker = reranker

    def execute(
        self, query: RetrievalQuery, query_vector: list[float]
    ) -> tuple[list[_ScoredChunk], int]:
        """
        Run the full candidate pipeline and return the final ranked chunks.

        Returns:
            A tuple of ``(ranked_chunks, raw_candidate_count)`` where
            ``raw_candidate_count`` reflects the number of results returned
            by the vector store before any filtering was applied.
        """
        candidate_pool_size = self._resolve_candidate_pool_size(query)
        search_filters = self._build_search_filters(query.filters)

        raw_results = self._search(query, query_vector, candidate_pool_size, search_filters)
        valid_chunks = self._extract_valid_chunks(raw_results)
        deduplicated = self._deduplicate(valid_chunks)
        filtered = self._apply_post_search_filters(deduplicated, query.filters)
        thresholded = self._apply_similarity_threshold(filtered, query.similarity_threshold)
        reranked = self._reranker.rerank(query.text, thresholded)

        final_top_k = self._resolve_top_k(query)
        return reranked[:final_top_k], len(raw_results)

    def _search(
        self,
        query: RetrievalQuery,
        query_vector: list[float],
        candidate_pool_size: int,
        search_filters: SearchFilters | None,
    ) -> list[VectorSearchResult]:
        try:
            return self._vector_store_service.search(
                repository_id=query.repository_id,
                query_vector=query_vector,
                top_k=candidate_pool_size,
                filters=search_filters,
                workspace_id=query.workspace_id,
            )
        except CollectionNotFoundError as exc:
            raise RepositoryNotIndexedError(
                f"Repository '{query.repository_id}' has not been indexed."
            ) from exc
        except VectorStoreError as exc:
            raise SimilaritySearchFailedError(
                f"Similarity search failed for repository '{query.repository_id}'."
            ) from exc

    @staticmethod
    def _extract_valid_chunks(results: list[VectorSearchResult]) -> list[_ScoredChunk]:
        """
        Convert search results into scored chunks, discarding malformed ones.

        A result is malformed if its metadata does not contain the original
        source code text, which should always be present when a vector was
        indexed correctly. Malformed results are skipped and logged rather
        than surfaced as a hard failure, since one bad record should not
        fail an entire retrieval request.
        """
        valid_chunks: list[_ScoredChunk] = []

        for result in results:
            code = result.record.metadata.get(_CODE_METADATA_KEY)
            if not code or not str(code).strip():
                logger.warning(
                    "Skipping chunk '%s': missing source code in stored metadata.",
                    result.record.chunk_id,
                )
                continue

            valid_chunks.append(
                _ScoredChunk(
                    record=result.record,
                    code=str(code),
                    similarity_score=result.similarity_score,
                    rank_score=result.similarity_score,
                )
            )

        return valid_chunks

    @staticmethod
    def _deduplicate(chunks: list[_ScoredChunk]) -> list[_ScoredChunk]:
        """Remove duplicate chunk identifiers, keeping the highest-scoring copy."""
        best_by_chunk_id: dict[str, _ScoredChunk] = {}

        for chunk in chunks:
            chunk_id = chunk.record.chunk_id
            existing = best_by_chunk_id.get(chunk_id)
            if existing is None or chunk.similarity_score > existing.similarity_score:
                best_by_chunk_id[chunk_id] = chunk

        return list(best_by_chunk_id.values())

    @staticmethod
    def _apply_post_search_filters(
        chunks: list[_ScoredChunk], filters: RetrievalFilters | None
    ) -> list[_ScoredChunk]:
        """
        Apply constraints not natively supported by the vector store's search.

        File-path filtering is applied here (rather than pushed into
        ``SearchFilters``) since exact-path matching is a client-side concern
        that keeps the vector store's search interface backend-agnostic.
        """
        if filters is None or not filters.file_path:
            return chunks
        return [chunk for chunk in chunks if chunk.record.file_path == filters.file_path]

    @staticmethod
    def _apply_similarity_threshold(
        chunks: list[_ScoredChunk], threshold: float | None
    ) -> list[_ScoredChunk]:
        if threshold is None:
            return chunks
        return [chunk for chunk in chunks if chunk.similarity_score >= threshold]

    @staticmethod
    def _build_search_filters(filters: RetrievalFilters | None) -> SearchFilters | None:
        if filters is None:
            return None
        return SearchFilters(
            language=filters.language,
            symbol_type=filters.symbol_type,
            metadata_equals=dict(filters.metadata_equals),
        )

    @staticmethod
    def _resolve_candidate_pool_size(query: RetrievalQuery) -> int:
        requested_top_k = SearchPipeline._resolve_top_k(query)
        pool_size = requested_top_k * _CANDIDATE_POOL_MULTIPLIER
        return min(pool_size, _MAX_CANDIDATE_POOL_SIZE)

    @staticmethod
    def _resolve_top_k(query: RetrievalQuery) -> int:
        if query.top_k is not None and query.top_k > 0:
            return query.top_k
        return get_settings().retrieval_top_k


class ContextAssembler:
    """
    Assembles ranked chunks into a token-budgeted, citation-ready context.

    This stage owns ordering, truncation, and translation from internal
    working types into the public ``RetrievedChunk`` / ``AssembledContext``
    types consumed by the rest of the application.
    """

    def assemble(
        self,
        query_text: str,
        ranked_chunks: list[_ScoredChunk],
        token_budget: int,
    ) -> AssembledContext:
        """
        Build an ``AssembledContext`` that fits within ``token_budget``.

        Chunks are included in rank order (highest relevance first) until
        adding another chunk would exceed the budget. Truncation never
        splits a chunk's code; a chunk either fits whole or is omitted,
        preserving citation integrity for every included chunk.
        """
        included: list[RetrievedChunk] = []
        consumed_tokens = 0
        truncated = False

        for scored_chunk in ranked_chunks:
            chunk_tokens = estimate_token_count(scored_chunk.code)

            if consumed_tokens + chunk_tokens > token_budget:
                truncated = True
                continue

            included.append(self._to_retrieved_chunk(scored_chunk))
            consumed_tokens += chunk_tokens

        return AssembledContext(
            query_text=query_text,
            chunks=included,
            estimated_token_count=consumed_tokens,
            token_budget=token_budget,
            truncated=truncated,
        )

    @staticmethod
    def _to_retrieved_chunk(scored_chunk: _ScoredChunk) -> RetrievedChunk:
        record = scored_chunk.record
        citation = CitationReference(
            repository_id=record.repository_id,
            file_path=record.file_path,
            symbol_name=record.symbol_name,
            start_line=record.start_line,
            end_line=record.end_line,
        )
        extra_metadata = {
            key: str(value)
            for key, value in record.metadata.items()
            if key != _CODE_METADATA_KEY
        }
        return RetrievedChunk(
            code=scored_chunk.code,
            relevance_score=scored_chunk.similarity_score,
            citation=citation,
            language=record.language,
            metadata=extra_metadata,
        )


class RetrieverService:
    """
    Public interface for semantic code retrieval.

    This is the only retrieval-related type the rest of the backend should
    depend on. It orchestrates query embedding, candidate search and
    filtering, reranking, and token-budgeted context assembly, while relying
    exclusively on ``EmbeddingService`` and ``VectorStoreService`` for their
    respective concerns.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store_service: VectorStoreService | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        """
        Args:
            embedding_service: Service used to embed query text. Constructed
                from application configuration when omitted.
            vector_store_service: Service used to perform similarity search.
                Constructed from application configuration when omitted.
            reranker: Reranking strategy applied to search candidates.
                Defaults to ``LexicalOverlapReranker`` when omitted.
        """
        self._embedding_service = embedding_service or EmbeddingService()
        self._vector_store_service = vector_store_service or VectorStoreService()
        self._reranker = reranker or LexicalOverlapReranker()
        self._search_pipeline = SearchPipeline(self._vector_store_service, self._reranker)
        self._context_assembler = ContextAssembler()

    def is_ready(self) -> bool:
        """Return whether retrieval dependencies have been constructed."""
        return self._embedding_service is not None and self._vector_store_service is not None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """
        Execute the full retrieval pipeline for a single query.

        Args:
            query: The natural language question and retrieval parameters.

        Returns:
            A ``RetrievalResult`` containing an assembled, citation-ready
            context for LLM consumption.

        Raises:
            EmptyQueryError: If the query text or repository id is missing.
            QueryEmbeddingError: If the query text cannot be embedded.
            RepositoryNotIndexedError: If the target repository has no
                vector collection.
            SimilaritySearchFailedError: If the underlying vector search
                fails.
        """
        self._validate_query(query)

        logger.info(
            "Retrieval started for repository '%s' (query length=%d chars).",
            query.repository_id,
            len(query.text),
        )

        query_vector = self._embed_query(query.text)
        ranked_chunks, candidates_found = self._search_pipeline.execute(query, query_vector)

        token_budget = self._resolve_token_budget(query)
        context = self._context_assembler.assemble(query.text, ranked_chunks, token_budget)

        logger.info(
            "Retrieval completed for repository '%s': %d candidate(s) found, "
            "%d chunk(s) included in context (%d/%d estimated tokens, "
            "truncated=%s).",
            query.repository_id,
            candidates_found,
            len(context.chunks),
            context.estimated_token_count,
            token_budget,
            context.truncated,
        )

        return RetrievalResult(
            query=query,
            context=context,
            candidates_found=candidates_found,
            candidates_after_filtering=len(ranked_chunks),
        )

    def _embed_query(self, text: str) -> list[float]:
        try:
            return self._embedding_service.embed_query(text)
        except EmbeddingError as exc:
            raise QueryEmbeddingError(
                "Failed to generate an embedding for the retrieval query."
            ) from exc

    @staticmethod
    def _validate_query(query: RetrievalQuery) -> None:
        if not query.text or not query.text.strip():
            raise EmptyQueryError("Retrieval query text must not be empty.")
        if not query.repository_id or not query.repository_id.strip():
            raise EmptyQueryError("Retrieval query must specify a repository id.")

    @staticmethod
    def _resolve_token_budget(query: RetrievalQuery) -> int:
        if query.token_budget is not None and query.token_budget > 0:
            return query.token_budget
        return get_settings().retrieval_token_budget
