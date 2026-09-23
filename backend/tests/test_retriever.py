"""Enterprise behavioral tests for the CodeAtlas retrieval pipeline."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import retriever as retriever_module
from app.core.embeddings import EmbeddingError, estimate_token_count
from app.core.retriever import (
    AssembledContext,
    CitationReference,
    ContextAssembler,
    EmptyQueryError,
    LexicalOverlapReranker,
    QueryEmbeddingError,
    RepositoryNotIndexedError,
    RetrievedChunk,
    RetrievalFilters,
    RetrievalQuery,
    RetrievalResult,
    SearchPipeline,
    SimilaritySearchFailedError,
    _ScoredChunk,
)
from app.core.vector_store import (
    CollectionNotFoundError,
    SearchFilters,
    StoredVectorRecord,
    VectorSearchResult,
    VectorStoreError,
)
from app.core.llm import LLMService


class IdentityReranker:
    def rerank(self, _query_text: str, candidates: list[_ScoredChunk]) -> list[_ScoredChunk]:
        return candidates


def test_retrieval_context_reaches_llm_request_with_citation_path() -> None:
    retrieval = RetrievalResult(
        query=RetrievalQuery("summarize the repository", "repo-1"),
        context=AssembledContext(
            query_text="summarize the repository",
            chunks=[
                RetrievedChunk(
                    code="def main():\n    pass",
                    relevance_score=0.9,
                    citation=CitationReference("repo-1", "src/main.py", "main", 1, 2),
                    language="python",
                )
            ],
            estimated_token_count=6,
            token_budget=1200,
            truncated=False,
        ),
        candidates_found=1,
        candidates_after_filtering=1,
    )

    request = LLMService.request_from_retrieval(retrieval)

    assert "File: src/main.py" in request.context
    assert "def main" in request.context
    assert request.citations[0].start_line == 1


def make_record(
    chunk_id: str = "chunk-1",
    *,
    repository_id: str = "repo-1",
    file_path: str = "src/auth.py",
    symbol_name: str | None = "authenticate",
    symbol_type: str | None = "function",
    language: str = "python",
    start_line: int | None = 10,
    end_line: int | None = 18,
    code: str = "def authenticate(user):\n    return user.is_valid()",
    metadata: dict[str, object] | None = None,
) -> StoredVectorRecord:
    values = {"code": code, "team": "platform"}
    if metadata:
        values.update(metadata)
    return StoredVectorRecord(chunk_id, repository_id, file_path, symbol_name, symbol_type, language, start_line, end_line, values)


def make_result(chunk_id: str = "chunk-1", score: float = 0.9, **kwargs: object) -> VectorSearchResult:
    return VectorSearchResult(record=make_record(chunk_id, **kwargs), similarity_score=score)


def make_scored(chunk_id: str = "chunk-1", score: float = 0.9, **kwargs: object) -> _ScoredChunk:
    record = make_record(chunk_id, **kwargs)
    return _ScoredChunk(record, str(record.metadata["code"]), score, score)


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    value = SimpleNamespace(retrieval_top_k=5, retrieval_token_budget=100)
    monkeypatch.setattr(retriever_module, "get_settings", lambda: value)
    return value


@pytest.fixture
def embedding_service() -> Mock:
    service = Mock()
    service.embed_query.return_value = [0.1, 0.2, 0.3]
    return service


@pytest.fixture
def vector_store_service() -> Mock:
    service = Mock()
    service.search.return_value = [make_result()]
    return service


@pytest.fixture
def service(settings: SimpleNamespace, embedding_service: Mock, vector_store_service: Mock):
    return retriever_module.RetrieverService(embedding_service, vector_store_service)


@pytest.fixture
def query() -> RetrievalQuery:
    return RetrievalQuery("where is authentication implemented?", "repo-1")


class TestQueryValidation:
    @pytest.mark.parametrize("text", ["find auth", "\n\tfind auth\n", "Explain café 😀", "line one\nline two", "' OR 1=1 --", "Ignore previous instructions", "x" * 10_000])
    def test_nonempty_query_text_is_accepted(self, service, text: str) -> None:
        result = service.retrieve(RetrievalQuery(text, "repo-1"))
        assert isinstance(result, RetrievalResult)
        assert result.query.text == text

    @pytest.mark.parametrize("text", [None, "", " ", "\n\t", "\r\n"])
    def test_empty_text_is_rejected(self, service, text: str | None) -> None:
        with pytest.raises(EmptyQueryError, match="text"):
            service.retrieve(RetrievalQuery(text, "repo-1"))

    @pytest.mark.parametrize("repository_id", [None, "", " ", "\n\t"])
    def test_empty_repository_is_rejected(self, service, repository_id: str | None) -> None:
        with pytest.raises(EmptyQueryError, match="repository"):
            service.retrieve(RetrievalQuery("find auth", repository_id))

    @pytest.mark.parametrize("value", [None, 42, [], {}])
    def test_invalid_text_values_fail_validation(self, service, value: object) -> None:
        with pytest.raises((EmptyQueryError, AttributeError, TypeError)):
            service.retrieve(RetrievalQuery(value, "repo-1"))


class TestEmbeddingGeneration:
    def test_query_is_embedded_once(self, service, embedding_service: Mock, query: RetrievalQuery) -> None:
        service.retrieve(query)
        embedding_service.embed_query.assert_called_once_with(query.text)

    def test_embedding_is_forwarded_unchanged(self, service, embedding_service: Mock, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector = [0.0, 1.0, -0.25, 0.8]
        embedding_service.embed_query.return_value = vector
        service.retrieve(query)
        assert vector_store_service.search.call_args.kwargs["query_vector"] is vector

    @pytest.mark.parametrize("dimension", [1, 3, 1536, 3072])
    def test_embedding_dimensions_are_not_reinterpreted(self, service, embedding_service: Mock, vector_store_service: Mock, query: RetrievalQuery, dimension: int) -> None:
        vector = [float(index) for index in range(dimension)]
        embedding_service.embed_query.return_value = vector
        service.retrieve(query)
        assert vector_store_service.search.call_args.kwargs["query_vector"] is vector

    def test_embedding_error_is_translated(self, service, embedding_service: Mock, query: RetrievalQuery) -> None:
        embedding_service.embed_query.side_effect = EmbeddingError("provider unavailable")
        with pytest.raises(QueryEmbeddingError, match="embedding") as caught:
            service.retrieve(query)
        assert isinstance(caught.value.__cause__, EmbeddingError)

    @pytest.mark.parametrize("error", [TimeoutError("timeout"), ConnectionError("offline")])
    def test_unexpected_embedding_errors_propagate(self, service, embedding_service: Mock, query: RetrievalQuery, error: Exception) -> None:
        embedding_service.embed_query.side_effect = error
        with pytest.raises(type(error), match=str(error)):
            service.retrieve(query)


class TestSimilaritySearch:
    def test_search_is_repository_scoped(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        service.retrieve(query)
        assert vector_store_service.search.call_args.kwargs["repository_id"] == "repo-1"

    @pytest.mark.parametrize("top_k, expected_pool", [(1, 3), (2, 6), (5, 15), (67, 200), (1000, 200)])
    def test_candidate_pool_has_headroom_and_ceiling(self, service, vector_store_service: Mock, query: RetrievalQuery, top_k: int, expected_pool: int) -> None:
        service.retrieve(replace(query, top_k=top_k))
        assert vector_store_service.search.call_args.kwargs["top_k"] == expected_pool

    def test_empty_store_returns_empty_context(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = []
        result = service.retrieve(query)
        assert result.candidates_found == 0
        assert result.candidates_after_filtering == 0
        assert result.context.chunks == []
        assert result.context.truncated is False

    def test_search_scores_are_preserved(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("high", 0.9), make_result("low", 0.2)]
        result = service.retrieve(query)
        assert [chunk.relevance_score for chunk in result.context.chunks] == [0.9, 0.2]

    def test_missing_collection_is_translated(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.side_effect = CollectionNotFoundError("missing")
        with pytest.raises(RepositoryNotIndexedError, match="repo-1") as caught:
            service.retrieve(query)
        assert isinstance(caught.value.__cause__, CollectionNotFoundError)

    def test_vector_store_error_is_translated(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.side_effect = VectorStoreError("database failed")
        with pytest.raises(SimilaritySearchFailedError, match="Similarity search") as caught:
            service.retrieve(query)
        assert isinstance(caught.value.__cause__, VectorStoreError)

    def test_unexpected_search_error_propagates(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.side_effect = RuntimeError("unexpected")
        with pytest.raises(RuntimeError, match="unexpected"):
            service.retrieve(query)


class TestMetadataFiltering:
    @pytest.mark.parametrize("filters", [RetrievalFilters(language="python"), RetrievalFilters(symbol_type="class"), RetrievalFilters(metadata_equals={"team": "platform"}), RetrievalFilters(language="typescript", symbol_type="interface", metadata_equals={"team": "platform"})])
    def test_store_filters_are_translated(self, service, vector_store_service: Mock, query: RetrievalQuery, filters: RetrievalFilters) -> None:
        service.retrieve(replace(query, filters=filters))
        actual = vector_store_service.search.call_args.kwargs["filters"]
        assert actual == SearchFilters(filters.language, filters.symbol_type, filters.metadata_equals)
        assert actual.metadata_equals is not filters.metadata_equals

    def test_no_filters_passes_none(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        service.retrieve(query)
        assert vector_store_service.search.call_args.kwargs["filters"] is None

    def test_path_filter_is_applied_after_search(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("a", file_path="src/a.py"), make_result("b", file_path="src/b.py")]
        result = service.retrieve(replace(query, filters=RetrievalFilters(file_path="src/b.py")))
        assert [chunk.citation.file_path for chunk in result.context.chunks] == ["src/b.py"]

    @pytest.mark.parametrize("path", ["src/é.py", "src/😀.py", "C:\\repo\\main.py", "/opt/repo/main.py"])
    def test_platform_and_unicode_paths_match_exactly(self, service, vector_store_service: Mock, query: RetrievalQuery, path: str) -> None:
        vector_store_service.search.return_value = [make_result("path", file_path=path)]
        result = service.retrieve(replace(query, filters=RetrievalFilters(file_path=path)))
        assert result.context.chunks[0].citation.file_path == path

    def test_empty_path_does_not_filter(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("a"), make_result("b", file_path="other.py")]
        assert service.retrieve(replace(query, filters=RetrievalFilters(file_path=""))).candidates_after_filtering == 2


class TestMalformedResultsAndDeduplication:
    def test_missing_code_is_discarded(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("bad", code="   "), make_result("good")]
        result = service.retrieve(query)
        assert result.candidates_found == 2
        assert result.candidates_after_filtering == 1

    @pytest.mark.parametrize("metadata", [{"code": None}, {"code": ""}, {"code": "\n\t"}])
    def test_invalid_code_metadata_is_skipped(self, service, vector_store_service: Mock, query: RetrievalQuery, metadata: dict[str, object]) -> None:
        vector_store_service.search.return_value = [make_result("bad", metadata=metadata)]
        assert service.retrieve(query).context.chunks == []

    def test_duplicate_keeps_highest_score(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("same", 0.4), make_result("same", 0.95)]
        result = service.retrieve(query)
        assert result.candidates_after_filtering == 1
        assert result.context.chunks[0].relevance_score == 0.95

    def test_duplicate_order_uses_first_key_position(self) -> None:
        chunks = [make_scored("a", 0.7), make_scored("b", 0.8), make_scored("a", 0.9)]
        deduplicated = SearchPipeline._deduplicate(chunks)
        assert [chunk.record.chunk_id for chunk in deduplicated] == ["a", "b"]
        assert [chunk.similarity_score for chunk in deduplicated] == [0.9, 0.8]

    def test_unique_chunks_are_preserved(self) -> None:
        chunks = [make_scored("a"), make_scored("b"), make_scored("c")]
        assert SearchPipeline._deduplicate(chunks) == chunks


class TestSimilarityThresholds:
    @pytest.mark.parametrize("threshold, expected_count", [(None, 2), (0.8, 2), (0.9, 1), (0.95, 0)])
    def test_threshold_is_inclusive(self, service, vector_store_service: Mock, query: RetrievalQuery, threshold: float | None, expected_count: int) -> None:
        vector_store_service.search.return_value = [make_result("a", 0.9), make_result("b", 0.8)]
        result = service.retrieve(replace(query, similarity_threshold=threshold))
        assert result.candidates_after_filtering == expected_count

    @pytest.mark.parametrize("threshold", [-1.0, 0.0, 1.0, 2.0])
    def test_extreme_thresholds_are_deterministic(self, service, vector_store_service: Mock, query: RetrievalQuery, threshold: float) -> None:
        vector_store_service.search.return_value = [make_result("a", 0.9)]
        result = service.retrieve(replace(query, similarity_threshold=threshold))
        assert result.candidates_after_filtering == (1 if threshold <= 0.9 else 0)


class TestReranking:
    def test_default_reranker_rewards_exact_symbol_match(self, service, vector_store_service: Mock) -> None:
        vector_store_service.search.return_value = [make_result("generic", 0.90, symbol_name="handler", file_path="src/handler.py"), make_result("exact", 0.88, symbol_name="authenticate", file_path="src/auth.py")]
        result = service.retrieve(RetrievalQuery("authenticate", "repo-1"))
        assert result.context.chunks[0].citation.symbol_name == "authenticate"

    def test_custom_reranker_is_used(self, embedding_service: Mock, vector_store_service: Mock, query: RetrievalQuery) -> None:
        reranker = Mock()
        reranker.rerank.side_effect = lambda _text, candidates: list(reversed(candidates))
        service = retriever_module.RetrieverService(embedding_service, vector_store_service, reranker)
        vector_store_service.search.return_value = [make_result("a", 0.9), make_result("b", 0.8)]
        result = service.retrieve(query)
        reranker.rerank.assert_called_once()
        assert result.context.chunks[0].relevance_score == 0.8

    def test_identity_reranker_preserves_order(self) -> None:
        candidates = [make_scored("a", 0.9), make_scored("b", 0.8)]
        assert IdentityReranker().rerank("query", candidates) == candidates

    @pytest.mark.parametrize("text", ["", "x", "A_B", "path/to/file.py", "Class::method()"])
    def test_tokenizer_returns_normalized_terms(self, text: str) -> None:
        tokens = LexicalOverlapReranker._tokenize(text)
        assert all(len(token) > 1 for token in tokens)
        assert tokens == {token.lower() for token in tokens}

    def test_empty_query_terms_use_similarity_only(self) -> None:
        candidates = [make_scored("low", 0.2), make_scored("high", 0.9)]
        ranked = LexicalOverlapReranker().rerank("a", candidates)
        assert [chunk.similarity_score for chunk in ranked] == [0.9, 0.2]


class TestContextAssembly:
    def test_context_contains_ordered_chunks_and_citations(self) -> None:
        chunks = [make_scored("a", 0.9), make_scored("b", 0.8, file_path="src/b.py", start_line=20, end_line=25)]
        context = ContextAssembler().assemble("find auth", chunks, 1000)
        assert isinstance(context, AssembledContext)
        assert [chunk.relevance_score for chunk in context.chunks] == [0.9, 0.8]
        assert context.citations == [chunk.citation for chunk in context.chunks]

    def test_extra_metadata_is_stringified_and_code_is_excluded(self) -> None:
        scored = make_scored("x", metadata={"owner": "security", "priority": 2})
        chunk = ContextAssembler().assemble("q", [scored], 100).chunks[0]
        assert chunk.metadata == {"team": "platform", "owner": "security", "priority": "2"}
        assert "code" not in chunk.metadata

    def test_empty_context_is_explicit(self) -> None:
        assert ContextAssembler().assemble("nothing", [], 10) == AssembledContext("nothing", [], 0, 10, False)

    @pytest.mark.parametrize("budget", [0, 1, 2, 10, 10_000])
    def test_budget_is_recorded_and_enforced(self, budget: int) -> None:
        context = ContextAssembler().assemble("q", [make_scored(code="abcdefghij")], budget)
        assert context.token_budget == budget
        assert context.estimated_token_count <= budget

    def test_overflow_omits_chunk_without_splitting_code(self) -> None:
        first = make_scored("first", code="12345678")
        second = make_scored("second", code="abcdefgh")
        context = ContextAssembler().assemble("q", [first, second], estimate_token_count(first.code))
        assert [chunk.code for chunk in context.chunks] == [first.code]
        assert context.truncated is True

    def test_later_small_chunk_can_fit_after_large_chunk(self) -> None:
        context = ContextAssembler().assemble("q", [make_scored("large", code="x" * 40), make_scored("small", code="1234")], 1)
        assert [chunk.code for chunk in context.chunks] == ["1234"]
        assert context.truncated is True

    @pytest.mark.parametrize("line_values", [(None, None), (1, None), (None, 4), (0, 0)])
    def test_citations_preserve_optional_lines(self, line_values: tuple[int | None, int | None]) -> None:
        citation = ContextAssembler().assemble("q", [make_scored(start_line=line_values[0], end_line=line_values[1])], 100).citations[0]
        assert (citation.start_line, citation.end_line) == line_values


class TestModelsAndPipeline:
    def test_retrieved_chunk_model_contains_expected_fields(self) -> None:
        citation = CitationReference("repo", "main.py", "run", 1, 3)
        chunk = RetrievedChunk("code", 0.8, citation, "python", {"owner": "team"})
        assert (chunk.code, chunk.relevance_score, chunk.citation, chunk.language) == ("code", 0.8, citation, "python")

    def test_citation_supports_missing_symbol_and_lines(self) -> None:
        citation = CitationReference("repo", "README.md", None, None, None)
        assert citation.symbol_name is None and citation.start_line is None and citation.end_line is None

    def test_retrieval_result_counts_match_pipeline(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("a"), make_result("b", code="other")]
        result = service.retrieve(query)
        assert result.query == query
        assert result.candidates_found == 2
        assert result.candidates_after_filtering == 2
        assert result.context.estimated_token_count == sum(estimate_token_count(chunk.code) for chunk in result.context.chunks)

    def test_context_citations_property_is_derived(self) -> None:
        citation = CitationReference("r", "f", "s", 1, 2)
        chunk = RetrievedChunk("code", 1.0, citation, "python")
        assert AssembledContext("q", [chunk], 1, 1, False).citations == [citation]

    def test_pipeline_returns_raw_count_and_top_k(self, vector_store_service: Mock) -> None:
        vector_store_service.search.return_value = [make_result("a"), make_result("b"), make_result("c")]
        ranked, found = SearchPipeline(vector_store_service, IdentityReranker()).execute(RetrievalQuery("q", "r", top_k=2), [1.0])
        assert found == 3
        assert len(ranked) == 2

    def test_pipeline_applies_path_then_threshold_then_top_k(self, vector_store_service: Mock) -> None:
        vector_store_service.search.return_value = [make_result("wrong", 0.99, file_path="wrong.py"), make_result("right", 0.5, file_path="right.py")]
        query = RetrievalQuery("q", "r", top_k=1, similarity_threshold=0.5, filters=RetrievalFilters(file_path="right.py"))
        ranked, found = SearchPipeline(vector_store_service, IdentityReranker()).execute(query, [1.0])
        assert found == 2
        assert [chunk.record.chunk_id for chunk in ranked] == ["right"]

    def test_pipeline_discards_invalid_results(self) -> None:
        store = Mock()
        store.search.return_value = [make_result("bad", code=""), make_result("good")]
        ranked, found = SearchPipeline(store, IdentityReranker()).execute(RetrievalQuery("q", "r"), [1.0])
        assert found == 2
        assert [chunk.record.chunk_id for chunk in ranked] == ["good"]

    @pytest.mark.parametrize("requested, expected", [(None, 5), (0, 5), (-1, 5), (1, 1), (10, 10)])
    def test_top_k_resolution(self, settings: SimpleNamespace, requested: int | None, expected: int) -> None:
        assert SearchPipeline._resolve_top_k(RetrievalQuery("q", "r", top_k=requested)) == expected

    @pytest.mark.parametrize("requested, expected", [(None, 100), (0, 100), (-3, 100), (1, 1), (250, 250)])
    def test_token_budget_resolution(self, settings: SimpleNamespace, requested: int | None, expected: int) -> None:
        assert retriever_module.RetrieverService._resolve_token_budget(RetrievalQuery("q", "r", token_budget=requested)) == expected

    def test_search_filter_metadata_is_copied(self) -> None:
        original = RetrievalFilters(metadata_equals={"team": "platform"})
        translated = SearchPipeline._build_search_filters(original)
        assert translated == SearchFilters(metadata_equals={"team": "platform"})
        assert translated is not None and translated.metadata_equals is not original.metadata_equals


class TestRegressionAndScale:
    def test_duplicate_retrieval_does_not_inflate_count(self, service, vector_store_service: Mock, query: RetrievalQuery) -> None:
        vector_store_service.search.return_value = [make_result("same", 0.5), make_result("same", 0.4), make_result("other", 0.3)]
        result = service.retrieve(query)
        assert result.candidates_found == 3 and result.candidates_after_filtering == 2

    def test_repository_id_is_retained_in_citation(self, service, vector_store_service: Mock) -> None:
        vector_store_service.search.return_value = [make_result("a", repository_id="repo-special")]
        assert service.retrieve(RetrievalQuery("q", "repo-special")).context.citations[0].repository_id == "repo-special"

    def test_threshold_uses_similarity_not_rank_score(self) -> None:
        candidate = make_scored("a", 0.5)
        candidate.rank_score = 10.0
        assert SearchPipeline._apply_similarity_threshold([candidate], 0.6) == []

    def test_metadata_values_are_stringified(self) -> None:
        scored = make_scored(metadata={"count": 4, "enabled": True, "none": None})
        metadata = ContextAssembler().assemble("q", [scored], 100).chunks[0].metadata
        assert metadata["count"] == "4" and metadata["enabled"] == "True" and metadata["none"] == "None"

    def test_retrieval_handles_hundreds_of_candidates(self, service, vector_store_service: Mock) -> None:
        vector_store_service.search.return_value = [make_result(str(index), score=1 / (index + 1)) for index in range(300)]
        result = service.retrieve(RetrievalQuery("find code", "repo", top_k=100, token_budget=10_000))
        assert result.candidates_found == 300
        assert result.candidates_after_filtering == 100
        assert len(result.context.chunks) == 100

    def test_large_metadata_is_preserved(self) -> None:
        extra = {f"key-{index}": "value" * 20 for index in range(100)}
        chunk = ContextAssembler().assemble("q", [make_scored(metadata=extra)], 1000).chunks[0]
        assert len(chunk.metadata) == 101
        assert chunk.code.startswith("def authenticate")

    @pytest.mark.parametrize("language", ["python", "javascript", "typescript", "go", "rust", ""])
    def test_language_metadata_is_returned_verbatim(self, language: str) -> None:
        chunk = ContextAssembler().assemble("q", [make_scored(language=language)], 100).chunks[0]
        assert chunk.language == language
