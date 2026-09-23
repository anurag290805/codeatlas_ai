"""Gemini-backed language-model service for CodeAtlas AI."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import httpx
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings, get_settings


class LLMProviderName(str, Enum):
    GEMINI = "gemini"


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class LLMServiceError(Exception):
    """Base exception for AI service failures."""


class LLMInvalidPromptError(LLMServiceError):
    pass


class LLMTimeoutError(LLMServiceError):
    pass


class LLMProviderOutageError(LLMServiceError):
    pass


class LLMModelNotFoundError(LLMServiceError):
    pass


class LLMMalformedResponseError(LLMServiceError):
    pass


class LLMContextOverflowError(LLMServiceError):
    pass


class LLMRateLimitError(LLMServiceError):
    pass


class LLMAuthenticationError(LLMServiceError):
    pass


@dataclass(frozen=True)
class ProviderHealth:
    configured: bool
    healthy: bool
    model_available: bool
    status: str
    message: str


class UsageMetadata(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)
    file_path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol_name: str | None = None

    @field_validator("end_line")
    @classmethod
    def validate_line_range(cls, value: int, info) -> int:
        start_line = info.data.get("start_line")
        if start_line is not None and value < start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return value


class LLMRequest(BaseModel):
    query: str = Field(min_length=1)
    context: str = ""
    citations: tuple[Citation, ...] = ()
    model: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, gt=0)
    response_format: ResponseFormat = ResponseFormat.MARKDOWN

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class LLMResponse(BaseModel):
    answer: str
    citations: tuple[Citation, ...] = ()
    provider: LLMProviderName = LLMProviderName.GEMINI
    model: str
    usage: UsageMetadata | None = None
    latency_seconds: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def token_usage(self) -> UsageMetadata | None:
        return self.usage

    @property
    def response_format(self) -> ResponseFormat:
        return ResponseFormat.JSON if self.answer.startswith("{") else ResponseFormat.MARKDOWN


class LLMStreamChunk(BaseModel):
    delta: str = ""
    is_final: bool = False
    provider: LLMProviderName = LLMProviderName.GEMINI
    model: str
    usage: UsageMetadata | None = None

    @property
    def token_usage(self) -> UsageMetadata | None:
        return self.usage


class _AsyncClient(Protocol):
    async def post(self, url: str, **kwargs: Any) -> httpx.Response: ...
    async def get(self, url: str, **kwargs: Any) -> httpx.Response: ...
    async def aclose(self) -> None: ...


class AbstractLLMProvider(ABC):
    provider_name: LLMProviderName

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def check_health(self) -> ProviderHealth: ...

    @abstractmethod
    async def generate(self, request: LLMRequest) -> tuple[str, UsageMetadata | None]: ...

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]: ...


class GeminiProvider(AbstractLLMProvider):
    """Server-side Gemini Interactions API provider."""

    provider_name = LLMProviderName.GEMINI
    _BASE_URL = "https://generativelanguage.googleapis.com"
    _SYSTEM_PROMPT = (
        "You are CodeAtlas AI, a repository code assistant. Use only the "
        "repository context delimited below as evidence. If it is insufficient, "
        "say so explicitly; never invent files, symbols, or behavior."
    )

    def __init__(self, settings: Settings | None = None, client: _AsyncClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=self._BASE_URL)
        logger.info("Initialized Gemini provider model={}", self.model_name)

    @property
    def model_name(self) -> str:
        return self._settings.gemini_model

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def check_health(self) -> ProviderHealth:
        if not self._settings.gemini_api_key:
            return ProviderHealth(False, False, False, "configuration_missing", "Gemini API key is not configured.")
        try:
            response = await self._client.get(f"/v1beta/models/{self.model_name}", headers={"x-goog-api-key": self._settings.gemini_api_key}, timeout=5.0)
            if response.status_code in {401, 403}:
                return ProviderHealth(True, False, False, "authentication_failure", "Gemini rejected the configured API key.")
            if response.status_code == 429:
                return ProviderHealth(True, False, False, "rate_limited", "Gemini is rate limiting health checks.")
            if response.status_code == 404:
                return ProviderHealth(True, False, False, "model_unavailable", "The configured Gemini model was not found.")
            if response.status_code >= 400:
                return ProviderHealth(True, False, False, "unavailable", "Gemini health check failed.")
            return ProviderHealth(True, True, True, "healthy", "Gemini and the configured model are available.")
        except httpx.TimeoutException:
            return ProviderHealth(True, False, False, "timeout", "Gemini health check timed out.")
        except httpx.RequestError:
            return ProviderHealth(True, False, False, "unavailable", "Gemini is unreachable.")

    async def generate(self, request: LLMRequest) -> tuple[str, UsageMetadata | None]:
        if not self._settings.gemini_api_key:
            raise LLMAuthenticationError("Gemini is not configured on the server.")
        body: dict[str, Any] = {
            "model": request.model or self.model_name,
            "input": f"{self._SYSTEM_PROMPT}\n\n{self._prompt(request)}",
            "generation_config": {"temperature": request.temperature, "max_output_tokens": min(request.max_tokens, self._settings.gemini_max_tokens)},
            "store": False,
        }
        try:
            response = await self._client.post("/v1beta/interactions", headers={"x-goog-api-key": self._settings.gemini_api_key}, json=body, timeout=self._settings.gemini_timeout_seconds)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Gemini generation timed out.") from exc
        except httpx.RequestError as exc:
            raise LLMProviderOutageError("Gemini could not be reached.") from exc
        if response.status_code in {401, 403}:
            raise LLMAuthenticationError("Gemini rejected the configured API key.")
        if response.status_code == 404:
            raise LLMModelNotFoundError("The configured Gemini model was not found.")
        if response.status_code == 429:
            raise LLMRateLimitError("Gemini rate limit or quota was exceeded.")
        if response.status_code >= 500:
            raise LLMProviderOutageError("Gemini returned a server error.")
        if response.status_code >= 400:
            raise LLMMalformedResponseError("Gemini rejected the request.")
        try:
            data = response.json()
            steps = data["steps"]
            parts = [part for step in steps if isinstance(step, dict) and step.get("type") == "model_output" for part in step.get("content", [])]
            text = "".join(str(part["text"]) for part in parts if isinstance(part, dict) and "text" in part)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMMalformedResponseError("Gemini returned an invalid response.") from exc
        if not text.strip():
            raise LLMMalformedResponseError("Gemini returned an empty response.")
        usage_data = data.get("usage", {})
        usage = UsageMetadata(prompt_tokens=int(usage_data.get("total_input_tokens", 0)), completion_tokens=int(usage_data.get("total_output_tokens", 0)), total_tokens=int(usage_data.get("total_tokens", 0))) if usage_data else None
        return text, usage

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        text, usage = await self.generate(request)
        yield LLMStreamChunk(delta=text, is_final=True, model=request.model or self.model_name, usage=usage)

    @staticmethod
    def _prompt(request: LLMRequest) -> str:
        context = request.context.strip() or "(No repository context was retrieved.)"
        return f"<repository_context>\n{context}\n</repository_context>\n\n<question>\n{request.query}\n</question>"


class LLMService:
    """Validate requests and orchestrate generation through Gemini."""

    def __init__(self, provider: AbstractLLMProvider | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._provider = provider or GeminiProvider(self._settings)
        self.provider_name = self._provider.provider_name
        self.model_name = self._provider.model_name

    def is_ready(self) -> bool:
        return bool(self.model_name) and bool(self._settings.gemini_api_key)

    async def check_health(self) -> ProviderHealth:
        if not self.is_ready():
            return ProviderHealth(False, False, False, "configuration_missing", "Gemini API key is not configured.")
        return await self._provider.check_health()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._validate_request(request)
        started = time.perf_counter()
        logger.info("LLM generation started provider={} model={}", self.provider_name.value, request.model or self.model_name)
        text, usage = await self._provider.generate(request)
        response = self._build_response(request, text, usage, time.perf_counter() - started)
        logger.info("LLM generation completed model={} latency_seconds={:.3f}", response.model, response.latency_seconds)
        return response

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        self._validate_request(request)
        async for chunk in self._provider.generate_stream(request):
            yield chunk

    async def generate_answer(self, retrieval_result: Any, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> LLMResponse:
        return await self.generate(self.request_from_retrieval(retrieval_result, response_format=response_format))

    async def generate_answer_stream(self, retrieval_result: Any) -> AsyncIterator[LLMStreamChunk]:
        async for chunk in self.generate_stream(self.request_from_retrieval(retrieval_result)):
            yield chunk

    @staticmethod
    def request_from_retrieval(retrieval_result: Any, *, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> LLMRequest:
        query = getattr(retrieval_result, "query", getattr(retrieval_result, "query_text", ""))
        if hasattr(query, "text"):
            query = query.text
        context_value = getattr(retrieval_result, "assembled_context", "")
        if hasattr(context_value, "chunks"):
            context_value = "\n\n".join(str(chunk.code) for chunk in context_value.chunks)
        citations = tuple(Citation.model_validate(citation, from_attributes=True) for citation in getattr(retrieval_result, "citations", ()))
        return LLMRequest(query=query, context=str(context_value), citations=citations, response_format=response_format)

    def _validate_request(self, request: LLMRequest) -> None:
        if not request.query.strip():
            raise LLMInvalidPromptError("LLM query must not be blank")
        estimated = (len(request.query) + len(request.context)) // 4
        if estimated + request.max_tokens > self._settings.retrieval_token_budget * 2:
            raise LLMContextOverflowError("LLM prompt exceeds the configured context budget")

    def _build_response(self, request: LLMRequest, text: str, usage: UsageMetadata | None, latency: float) -> LLMResponse:
        if request.response_format is ResponseFormat.JSON:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMMalformedResponseError("AI provider JSON response could not be decoded") from exc
            if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
                raise LLMMalformedResponseError("AI provider JSON response must contain an answer")
            text = parsed["answer"]
        if not text.strip():
            raise LLMMalformedResponseError("AI provider returned an empty answer")
        return LLMResponse(answer=text.strip(), citations=request.citations, provider=self.provider_name, model=request.model or self.model_name, usage=usage, latency_seconds=max(0.0, latency))
