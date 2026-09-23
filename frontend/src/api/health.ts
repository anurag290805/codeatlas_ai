// src/api/health.ts
import type { AxiosResponse } from "axios";
import { apiClient } from "@/api/client";
import type {
  BackendHealthResponse,
  QueryHealthResponse,
  VersionResponse,
} from "@/types/health";

/**
 * Every probe rides the prefixed API client. Serverless gateways (e.g. the
 * Vercel monorepo) forward only `{apiPrefix}/*` to the backend, so a
 * root-level `/health` probe never arrives; routing it through `apiClient`
 * keeps it on the same proven path as the feature routers.
 */
export const HealthApi = {
  getLiveness(): Promise<AxiosResponse<BackendHealthResponse>> {
    return apiClient.get<BackendHealthResponse>("/health");
  },
  getQueryHealth(): Promise<AxiosResponse<QueryHealthResponse>> {
    return apiClient.get<QueryHealthResponse>("/query/health");
  },
  getVersion(): Promise<AxiosResponse<VersionResponse>> {
    return apiClient.get<VersionResponse>("/version");
  },
};
