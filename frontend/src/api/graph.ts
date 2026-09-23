// src/api/graph.ts
import type { AxiosResponse } from "axios";
import { apiClient } from "@/api/client";
import type { GraphApiResponse } from "@/types/graph";

/**
 * Thin service layer over the repository-scoped graph endpoint.
 */
export const GraphApi = {
  getDependencyGraph(repositoryId: string): Promise<AxiosResponse<GraphApiResponse>> {
    return apiClient.get<GraphApiResponse>(`/repositories/${repositoryId}/graph`);
  },
};
