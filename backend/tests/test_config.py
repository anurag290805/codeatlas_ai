from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import main
from app.core.config import Settings
from app.api import routes_query
from app.core.llm import (
    GeminiProvider,
    LLMProviderName,
    LLMRequest,
    LLMService,
    OmniRouteProvider,
    ProviderHealth,
)
from app.utils.logger import _create_file_handler


def test_backend_env_file_loads_csv_and_resolves_paths(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:4173\n"
        "CHROMA_DB_PATH=./data/chroma\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://localhost:4173",
    ]
    assert settings.chroma_persist_directory.is_absolute()


def test_shell_environment_overrides_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_MODEL=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "from-shell")
    assert Settings(_env_file=env_file).gemini_model == "from-shell"


def test_debug_accepts_deployment_labels(monkeypatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    assert Settings(_env_file=None, debug="release").debug is False
    assert Settings(_env_file=None, debug="production").debug is False
    assert Settings(_env_file=None, debug="debug").debug is True


def test_render_postgres_url_is_normalized() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgres://user:secret@example.internal:5432/codeatlas",
    )
    assert settings.DATABASE_URL == (
        "postgresql://user:secret@example.internal:5432/codeatlas"
    )


def test_sqlite_database_url_remains_local_development_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.DATABASE_URL.startswith("sqlite:///")
    assert settings.DATABASE_URL.endswith("/data/app.db")


def test_production_settings_load_with_canonical_workspace_secret(monkeypatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("WORKSPACE_SESSION_SECRET", "w" * 32)
    settings = Settings(
        _env_file=None,
        environment="production",
    )
    assert settings.workspace_session_secret == "w" * 32


def test_production_settings_requires_canonical_workspace_secret(monkeypatch) -> None:
    import pytest
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(ValueError, match="WORKSPACE_SESSION_SECRET must be configured"):
        Settings(_env_file=None, environment="production")


def test_production_settings_does_not_require_legacy_session_secret(monkeypatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    settings = Settings(
        _env_file=None,
        environment="production",
        WORKSPACE_SESSION_SECRET="c" * 32,
    )
    assert settings.workspace_session_secret == "c" * 32


def test_configured_cors_origin_allows_request_and_preflight(monkeypatch) -> None:
    settings = SimpleNamespace(
        cors_allowed_origins=["http://localhost:4173"],
        cors_allow_credentials=True,
        trusted_hosts=[],
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = FastAPI()
    app.get("/probe")(lambda: {"ok": True})
    main._register_middleware(app)

    with TestClient(app) as client:
        response = client.get("/probe", headers={"Origin": "http://localhost:4173"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:4173"
        preflight = client.options(
            "/probe",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:4173"

        rejected = client.get("/probe", headers={"Origin": "http://unconfigured.test"})
        assert "access-control-allow-origin" not in rejected.headers


class _GeminiClient:
    async def get(self, _url: str, **_kwargs):
        return SimpleNamespace(status_code=200)

    async def post(self, _url: str, **kwargs):
        self.payload = kwargs["json"]
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": "grounded answer"}]}],
                "usage": {"total_input_tokens": 4, "total_output_tokens": 2, "total_tokens": 6},
            },
        )


def test_gemini_generation_is_server_side_and_preserves_rag_context() -> None:
    settings = Settings(_env_file=None, gemini_api_key="test-key")
    client = _GeminiClient()
    provider = GeminiProvider(settings=settings, client=client)
    response = asyncio.run(provider.generate(LLMRequest(query="where?", context="File: src/main.py\nmain()")))
    assert response[0] == "grounded answer"
    assert "src/main.py" in client.payload["input"]
    assert "test-key" not in str(client.payload)


def test_gemini_remains_selectable() -> None:
    settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="test-key")
    service = LLMService(settings=settings)
    assert service.provider_name is LLMProviderName.GEMINI
    assert service.is_ready() is True


class _OmniRouteClient:
    async def post(self, _url: str, **kwargs):
        self.payload = kwargs["json"]
        return SimpleNamespace(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            text=(
                'data: {"choices":[{"delta":{"content":"grounded "}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"answer"}}],'
                '"usage":{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6}}\n\n'
                'data: [DONE]\n\n'
            ),
            json=lambda: {},
        )

    async def get(self, _url: str, **_kwargs):
        return SimpleNamespace(status_code=200)


def test_omniroute_parses_sse_and_uses_free_auto_model() -> None:
    settings = Settings(_env_file=None, omniroute_model="auto/best-free")
    client = _OmniRouteClient()
    provider = OmniRouteProvider(settings=settings, client=client)
    text, usage = asyncio.run(provider.generate(LLMRequest(query="where?")))
    assert text == "grounded answer"
    assert usage is not None and usage.total_tokens == 6
    assert client.payload["model"] == "auto/best-free"
    assert client.payload["stream"] is True


def test_gemini_health_is_healthy_when_retriever_is_ready() -> None:
    class HealthyGemini:
        provider_name = LLMProviderName.GEMINI
        model_name = "gemini-2.5-flash"

        async def check_health(self):
            return ProviderHealth(True, True, True, "healthy", "Gemini is available.")

    class ReadyRetriever:
        def is_ready(self):
            return True

    health = asyncio.run(routes_query.query_health(ReadyRetriever(), LLMService(provider=HealthyGemini(), settings=Settings(_env_file=None, gemini_api_key="test-key"))))
    assert health.status == "healthy"
    assert health.provider_healthy is True
    assert health.rag_status == "ready"


def test_missing_gemini_key_is_a_clear_provider_health_state() -> None:
    service = LLMService(settings=Settings(_env_file=None))
    health = asyncio.run(service.check_health())
    assert health.status == "configuration_missing"
    assert health.healthy is False
    assert health.configured is False


def test_logger_falls_back_when_log_file_cannot_be_created(tmp_path: Path) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("x", encoding="utf-8")
    assert _create_file_handler(parent_file / "app.log", 20) is None
