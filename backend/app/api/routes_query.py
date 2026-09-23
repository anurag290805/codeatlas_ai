"""
REST API routes for Retrieval-Augmented Generation (RAG) querying in
CodeAtlas AI.

This router exposes endpoints that let clients ask natural-language
questions about indexed repositories. It is intentionally thin: all
retrieval logic lives in RetrieverService and all answer generation
logic lives in LLMService. This module only validates requests,
orchestrates calls between those two services, maps exceptions to HTTP
responses, and shapes strongly typed responses.

Synchronous service calls are offloaded to a thread pool via
run_in_threadpool so route handlers never block the event loop, keeping
the server responsive under concurrent query load.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.llm import (
    LLMAuthenticationError,
    LLMContextOverflowError,
    LLMInvalidPromptError,
    LLMModelNotFoundError,
    LLMMalformedResponseError,
    LLMProviderOutageError,
    LLMRateLimitError,
    LLMService,
    LLMServiceError,
    LLMTimeoutError,
    ResponseFormat,
)
from app.core.retriever import (
    RepositoryNotIndexedError,
    RetrievalError,
    RetrievalQuery,
    RetrieverService,
)
from app.db import crud
from app.db.database import get_db
from app.core.auth import get_workspace_id
from app.core.workspace import ensure_workspace
from app.models import schemas
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["query"], dependencies=[Depends(ensure_workspace)])


# =========================================================================
# Service dependency providers
# =========================================================================


@lru_cache
def get_retriever_service() -> RetrieverService:
    """Provide a shared RetrieverService instance."""
    return RetrieverService()


@lru_cache
def get_llm_service() -> LLMService:
    """Provide a shared LLMService instance."""
    return LLMService()


# =========================================================================
# Endpoints
# =========================================================================


@router.post(
    "/query",
    response_model=schemas.QueryResponse,
    summary="Ask a question about a repository",
    description=(
        "Retrieves relevant code context for the given repository and "
        "generates a grounded, citation-preserving answer."
    ),
)
async def query_repository(
    payload: schemas.QueryRequest,
    db: Session = Depends(get_db),
    retriever: RetrieverService = Depends(get_retriever_service),
    llm_service: LLMService = Depends(get_llm_service),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.QueryResponse:
    """Answer a natural-language question about a repository using RAG."""
    return await _answer_query(
        repository_id=payload.repository_id,
        query=payload.query,
        top_k=payload.top_k,
        db=db,
        retriever=retriever,
        llm_service=llm_service,
        workspace_id=workspace_id,
    )


@router.post(
    "/repositories/{repository_id}/query",
    response_model=schemas.QueryResponse,
    summary="Ask a question about a specific repository",
    description=(
        "Repository-scoped variant of /query. Retrieves relevant code "
        "context for the repository identified in the path and generates "
        "a grounded, citation-preserving answer."
    ),
)
async def query_specific_repository(
    repository_id: str,
    payload: schemas.RepositoryScopedQueryRequest,
    db: Session = Depends(get_db),
    retriever: RetrieverService = Depends(get_retriever_service),
    llm_service: LLMService = Depends(get_llm_service),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.QueryResponse:
    """Answer a natural-language question scoped to a single repository."""
    return await _answer_query(
        repository_id=repository_id,
        query=payload.query,
        top_k=payload.top_k,
        db=db,
        retriever=retriever,
        llm_service=llm_service,
        workspace_id=workspace_id,
    )


@router.post(
    "/query/stream",
    summary="Ask a question with a streamed answer",
    description=(
        "Retrieves relevant code context and streams the generated "
        "answer back to the client as Server-Sent Events (SSE)."
    ),
    response_class=StreamingResponse,
)
async def query_repository_stream(
    payload: schemas.QueryRequest,
    db: Session = Depends(get_db),
    retriever: RetrieverService = Depends(get_retriever_service),
    llm_service: LLMService = Depends(get_llm_service),
    workspace_id: str = Depends(get_workspace_id),
) -> StreamingResponse:
    """Answer a natural-language question about a repository, streaming the response."""
    _ensure_repository_ready(db, payload.repository_id, workspace_id)

    logger.info("Query received repository_id=%s streaming=true", payload.repository_id)

    retrieval_result = await _retrieve(
        retriever, payload.repository_id, payload.query, payload.top_k, workspace_id
    )

    logger.info(
        "Retrieval completed repository_id=%s chunks=%d streaming=true",
        payload.repository_id,
        retrieval_result.retrieved_chunk_count,
    )

    return StreamingResponse(
        _stream_answer_events(llm_service, retrieval_result, payload.repository_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/query/health",
    response_model=schemas.QueryHealthResponse,
    summary="Query subsystem health check",
    description="Reports whether the retrieval and answer-generation subsystems are configured and reachable.",
)
async def query_health(
    retriever: RetrieverService = Depends(get_retriever_service),
    llm_service: LLMService = Depends(get_llm_service),
) -> schemas.QueryHealthResponse:
    """Return independent RAG and Gemini provider status."""
    provider = await llm_service.check_health()
    retriever_ready = retriever.is_ready()
    health_status = "healthy" if retriever_ready and provider.healthy else "degraded"
    if not retriever_ready:
        health_status, message = "unhealthy", "Repository retrieval is not configured."
    else:
        message = provider.message
    return schemas.QueryHealthResponse(
        status=health_status,
        retriever_ready=retriever_ready,
        rag_status="ready" if retriever_ready else "unavailable",
        provider_status=provider.status,
        provider_configured=provider.configured,
        provider_healthy=provider.healthy,
        llm_provider=llm_service.provider_name.value,
        llm_model=llm_service.model_name,
        model_available=provider.model_available,
        message=message,
    )


# =========================================================================
# Orchestration helpers
# =========================================================================


async def _answer_query(
    *,
    repository_id: str,
    query: str,
    top_k: Optional[int],
    db: Session,
    retriever: RetrieverService,
    llm_service: LLMService,
    workspace_id: str | None = None,
) -> schemas.QueryResponse:
    """
    Execute the full non-streaming query pipeline: validate repository
    readiness, retrieve context, generate a grounded answer, and shape
    the response.
    """
    _ensure_repository_ready(db, repository_id, workspace_id)

    logger.info("Query received repository_id=%s streaming=false", repository_id)

    retrieval_result = await _retrieve(retriever, repository_id, query, top_k, workspace_id)

    logger.info(
        "Retrieval completed repository_id=%s chunks=%d",
        repository_id,
        retrieval_result.retrieved_chunk_count,
    )

    answer = await _generate_answer(llm_service, retrieval_result)

    logger.info(
        "Answer generated repository_id=%s provider=%s model=%s latency=%.3fs",
        repository_id,
        answer.provider.value,
        answer.model,
        answer.latency_seconds,
    )

    return schemas.QueryResponse(
        repository_id=repository_id,
        query=query,
        answer=answer.answer,
        citations=[
            schemas.CitationSchema(
                file_path=citation.file_path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                symbol_name=citation.symbol_name,
            )
            for citation in answer.citations
            if citation.start_line is not None
            and citation.end_line is not None
            and citation.start_line >= 1
            and citation.end_line >= citation.start_line
        ],
        provider=answer.provider.value,
        model=answer.model,
        latency_seconds=answer.latency_seconds,
        token_usage=(
            schemas.TokenUsageSchema(
                prompt_tokens=answer.token_usage.prompt_tokens,
                completion_tokens=answer.token_usage.completion_tokens,
                total_tokens=answer.token_usage.total_tokens,
            )
            if answer.token_usage is not None
            else None
        ),
    )


async def _retrieve(
    retriever: RetrieverService,
    repository_id: str,
    query: str,
    top_k: Optional[int],
    workspace_id: str | None = None,
):
    """Run retrieval on a worker thread and translate failures into HTTPExceptions."""
    try:
        retrieval_query = RetrievalQuery(
            text=query,
            repository_id=str(repository_id),
            top_k=top_k,
            workspace_id=workspace_id,
        )
        return await run_in_threadpool(retriever.retrieve, retrieval_query)
    except RepositoryNotIndexedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not yet indexed: {repository_id}",
        ) from exc
    except RetrievalError as exc:
        logger.error("Retrieval failed repository_id=%s error=%s", repository_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve repository context. Please retry.",
        ) from exc


async def _generate_answer(llm_service: LLMService, retrieval_result):
    """Run answer generation on a worker thread and translate failures into HTTPExceptions."""
    try:
        return await llm_service.generate_answer(retrieval_result, ResponseFormat.MARKDOWN)
    except LLMInvalidPromptError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMContextOverflowError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The AI provider is rate limiting requests. Please retry shortly.",
        ) from exc
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Answer generation timed out. Please retry.",
        ) from exc
    except LLMModelNotFoundError as exc:
        logger.error("Configured Gemini model is unavailable error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except LLMProviderOutageError as exc:
        logger.error("Gemini provider is unavailable error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except LLMMalformedResponseError as exc:
        logger.error("Answer generation failed error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider is temporarily unavailable. Please retry.",
        ) from exc
    except LLMAuthenticationError as exc:
        logger.error("LLM authentication failed error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Answer generation is misconfigured. Please contact support.",
        ) from exc
    except LLMServiceError as exc:
        logger.error("Unexpected LLM service error error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate an answer. Please retry.",
        ) from exc


async def _stream_answer_events(
    llm_service: LLMService,
    retrieval_result,
    repository_id: str,
) -> AsyncIterator[str]:
    """
    Stream LLM answer chunks as Server-Sent Events.

    Each event carries a JSON payload with the incremental text delta.
    Errors that occur after streaming has begun are emitted as a final
    ``event: error`` frame, since the HTTP status code can no longer be
    changed once the response has started.
    """
    try:
        async for chunk in llm_service.generate_answer_stream(retrieval_result):
            event_payload = {
                "delta": chunk.delta,
                "is_final": chunk.is_final,
                "provider": chunk.provider.value,
                "model": chunk.model,
            }
            if chunk.token_usage is not None:
                event_payload["token_usage"] = {
                    "prompt_tokens": chunk.token_usage.prompt_tokens,
                    "completion_tokens": chunk.token_usage.completion_tokens,
                    "total_tokens": chunk.token_usage.total_tokens,
                }
            yield f"data: {json.dumps(event_payload)}\n\n"

        logger.info("Streaming completed repository_id=%s", repository_id)

    except LLMServiceError as exc:
        logger.error("Streaming failed repository_id=%s error=%s", repository_id, exc)
        error_payload = {"message": "Answer generation failed. Please retry."}
        yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"


def _ensure_repository_ready(db: Session, repository_id: str, workspace_id: str | None = None) -> None:
    """
    Validate that a repository exists and has completed indexing before
    a query is attempted.

    Raises:
        HTTPException: 404 if the repository does not exist, 409 if it
            exists but has not finished indexing.
    """
    repository = crud.get_repository(db, repository_id=repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repository_id}",
        )
    if repository.status not in {
        schemas.RepositoryStatus.READY,
        schemas.RepositoryStatus.INDEXED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready for querying (status: {repository.status}).",
        )
