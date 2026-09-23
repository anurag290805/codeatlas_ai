// src/types/health.ts

/** Status values emitted by the backend liveness and query probes. */
export type HealthStatus = "healthy" | "degraded" | "unhealthy";

/** Exact response from GET /health. */
export interface BackendHealthResponse {
  readonly status: "healthy";
}

/** Exact response from GET /api/query/health. */
export interface QueryHealthResponse {
  readonly status: HealthStatus;
  readonly retriever_ready: boolean;
  readonly rag_status: "ready" | "degraded" | "unavailable";
  readonly provider_status: string;
  readonly provider_configured: boolean;
  readonly provider_healthy: boolean;
  readonly model_available: boolean;
  readonly llm_provider: string;
  readonly llm_model: string;
  readonly message: string;
}

/** Exact response from GET /version. */
export interface VersionResponse {
  readonly version: string;
  readonly environment: string;
}

export type HealthResponse = QueryHealthResponse;
