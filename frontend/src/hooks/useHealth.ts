// src/hooks/useHealth.ts
import { useQuery } from "@tanstack/react-query";
import { HealthApi } from "@/api/health";
import type { BackendHealthResponse } from "@/types/health";
import { ApiRequestError } from "@/utils/errors";

/** Retrieves the lightweight FastAPI liveness probe from GET /health. */
export function useHealth() {
  return useQuery<BackendHealthResponse>({
    queryKey: ["health", "liveness"],
    queryFn: () => HealthApi.getLiveness().then((response) => response.data),
    staleTime: 15_000,
    retry: (failureCount, error) => failureCount < 3 && (error instanceof ApiRequestError ? (error.status === undefined || error.status >= 500) : true),
    retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 8_000),
  });
}

export function useQueryHealth() {
  return useQuery({
    queryKey: ["health", "query"],
    queryFn: () => HealthApi.getQueryHealth().then((response) => response.data),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useVersion() {
  return useQuery({
    queryKey: ["health", "version"],
    queryFn: () => HealthApi.getVersion().then((response) => response.data),
  });
}
