"""
Application entry point for CodeAtlas AI.

This module is responsible exclusively for application assembly: building
the FastAPI instance via an application factory, registering routers,
middleware, exception handlers, and lifecycle events, and exposing
lightweight health endpoints. It contains no business logic -- all
domain behavior lives in the existing service and router modules.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.routes_graph import router as graph_router
from app.api.routes_analytics import router as analytics_router
from app.api.routes_query import router as query_router
from app.api.routes_agent import router as agent_router
from app.api.routes_repo import router as repo_router
from app.api.routes_intelligence import router as intelligence_router
from app.config import get_settings
from app.core.workspace import (
    WORKSPACE_COOKIE,
    initialize_request_workspace,
    set_workspace_cookie,
)
from app.core.indexing_queue import recover_indexing_jobs
from app.db.database import close_db, init_db
from app.utils.logger import get_logger

logger = get_logger(__name__)

API_VERSION = "1.0.0"


# =========================================================================
# Lifecycle management
# =========================================================================


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage application startup and shutdown.

    Startup validates configuration and initializes the database
    connection. Shutdown releases database resources. Heavier services
    (embedding, vector store, LLM providers) initialize lazily on first
    use and are intentionally not eagerly constructed here, keeping
    startup fast and side-effect-light.
    """
    settings = get_settings()
    logger.info("Application startup initiated environment=%s", settings.environment)

    try:
        init_db()
        recover_indexing_jobs()
        logger.info("Database initialized")
    except Exception:
        logger.exception("Database initialization failed")
        raise

    logger.info(
        "Application startup completed version=%s environment=%s",
        API_VERSION,
        settings.environment,
    )

    yield

    logger.info("Application shutdown initiated")
    try:
        close_db()
        logger.info("Database connections closed")
    except Exception:
        logger.exception("Error while closing database connections")

    logger.info("Application shutdown completed")


# =========================================================================
# Middleware registration
# =========================================================================


def _register_middleware(app: FastAPI) -> None:
    """Register all application middleware, in outermost-to-innermost order."""
    settings = get_settings()

    logger.info("CORS origins loaded: %s", settings.cors_allowed_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.middleware("http")(_request_context_middleware)

    logger.info("Middleware initialized")


async def _request_context_middleware(request: Request, call_next):
    """
    Attach a correlation id and timing to every request, and log
    completion at a level appropriate for production traffic volume.

    This is a placeholder integration point for future authentication
    middleware: a request-scoped correlation id is already threaded
    through logging and response headers, so an auth layer can later
    attach principal information to ``request.state`` without any
    change to this function's structure.
    """
    correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    workspace_id, workspace_created = initialize_request_workspace(request)
    start_time = time.monotonic()

    response = await call_next(request)

    if workspace_created:
        set_workspace_cookie(response, workspace_id, request)

    duration_ms = (time.monotonic() - start_time) * 1000
    response.headers["X-Request-ID"] = correlation_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

    logger.info(
        "request completed method=%s path=%s status=%d duration_ms=%.2f correlation_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        correlation_id,
    )
    return response


# =========================================================================
# Exception handlers
# =========================================================================


def _error_response(request: Request, status_code: int, message: str, detail: object = None) -> JSONResponse:
    """Build a consistent JSON error envelope for all exception handlers."""
    correlation_id = getattr(request.state, "correlation_id", None)
    payload = {
        "error": message,
        "detail": detail,
        "status_code": status_code,
        "correlation_id": correlation_id,
    }
    response = JSONResponse(status_code=status_code, content=payload)
    _apply_cors_headers(request, response)
    return response


def _apply_cors_headers(request: Request, response: JSONResponse) -> None:
    """Mirror the CORSMiddleware's allow-origin logic on error responses.

    Starlette raises unhandled exceptions through the CORS middleware, so a
    response produced by the generic ``Exception`` handler (and the FastAPI
    validation handler) bypasses the middleware and ships without CORS
    headers. A browser then blocks the cross-origin error body and surfaces
    it as a generic "Network Error", hiding the real HTTP status. Adding the
    same allow-origin/credentials headers here keeps error responses readable
    to the frontend for permitted origins.
    """
    settings = get_settings()
    origin = request.headers.get("origin")
    if not origin or origin not in settings.cors_allowed_origins:
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers.setdefault("Vary", "Origin")
    if settings.cors_allow_credentials:
        response.headers["Access-Control-Allow-Credentials"] = "true"


def _register_exception_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers producing consistent API responses."""

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Request validation failed path=%s errors=%s", request.url.path, exc.errors())
        return _error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Request validation failed.",
            detail=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        return _error_response(request, exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        logger.exception(
            "Unhandled exception path=%s correlation_id=%s", request.url.path, correlation_id
        )
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An unexpected error occurred.",
        )

    logger.info("Exception handlers registered")


# =========================================================================
# Routers
# =========================================================================


def _register_routers(app: FastAPI) -> None:
    """Register all API routers under the configured API prefix."""
    settings = get_settings()
    api_prefix = settings.api_prefix

    app.include_router(repo_router, prefix=api_prefix)
    app.include_router(query_router, prefix=api_prefix)
    app.include_router(agent_router, prefix=api_prefix)
    app.include_router(graph_router, prefix=api_prefix)
    app.include_router(analytics_router, prefix=api_prefix)
    app.include_router(intelligence_router, prefix=api_prefix)

    logger.info("Routers registered prefix=%s", api_prefix)


# =========================================================================
# Health endpoints
# =========================================================================


def _version_payload() -> dict[str, str]:
    """Build the application version payload shared by both health routes."""
    settings = get_settings()
    return {"version": API_VERSION, "environment": settings.environment}


def _register_health_endpoints(app: FastAPI) -> None:
    """
    Register lightweight health and metadata endpoints.

    These endpoints deliberately avoid touching the database, vector
    store, or LLM providers so they remain fast and reliable even when
    a downstream dependency is degraded.

    The root-level routes are mirrored under ``api_prefix`` because some
    serverless gateways (e.g. the Vercel monorepo) only forward
    ``{api_prefix}/*`` to this service -- a root-level ``/health`` probe
    would otherwise land on the frontend instead of the backend.
    """
    api_prefix = get_settings().api_prefix

    @app.get("/", tags=["system"], summary="Service banner")
    async def root() -> dict[str, str]:
        """Return a minimal service identification payload."""
        return {"service": "CodeAtlas AI", "status": "running"}

    @app.get("/health", tags=["system"], summary="Liveness check")
    async def health() -> dict[str, str]:
        """Return a lightweight liveness signal for load balancers and orchestrators."""
        return {"status": "healthy"}

    @app.get("/version", tags=["system"], summary="Application version")
    async def version() -> dict[str, str]:
        """Return the running application version and environment."""
        return _version_payload()

    if api_prefix:
        @app.get(f"{api_prefix}/health", tags=["system"], summary="Liveness check (prefixed)")
        async def health_prefixed() -> dict[str, str]:
            """Prefixed alias of GET /health for prefix-only gateways."""
            return {"status": "healthy"}

        @app.get(f"{api_prefix}/version", tags=["system"], summary="Application version (prefixed)")
        async def version_prefixed() -> dict[str, str]:
            """Prefixed alias of GET /version for prefix-only gateways."""
            return _version_payload()


# =========================================================================
# Application factory
# =========================================================================


def create_app() -> FastAPI:
    """
    Construct and fully configure the CodeAtlas AI FastAPI application.

    This is the single composition point for the application: routers,
    middleware, exception handlers, lifecycle events, and OpenAPI
    metadata are all assembled here from existing, already-implemented
    modules.
    """
    settings = get_settings()
    logger.info("Configuration loaded environment=%s", settings.environment)

    app = FastAPI(
        title="CodeAtlas AI",
        description=(
            "AI-powered code intelligence platform for exploring GitHub "
            "repositories through Retrieval-Augmented Generation and "
            "interactive dependency graphs."
        ),
        version=API_VERSION,
        contact={"name": "CodeAtlas AI", "url": "https://github.com"},
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "repositories", "description": "Repository lifecycle management."},
            {"name": "query", "description": "Retrieval-Augmented Generation querying."},
            {"name": "agent", "description": "Routed, skill-aware repository tasks."},
            {"name": "graph", "description": "Repository dependency graph access."},
            {"name": "system", "description": "Service health and metadata."},
        ],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_routers(app)
    _register_health_endpoints(app)

    return app


app = create_app()
