// src/api/repositories.ts
import type { AxiosResponse } from "axios";
import { apiClient } from "@/api/client";
import type {
  RepositoryCreateRequest,
  RepositoryCreateResponse,
  RepositoryDetailResponse,
  RepositoryListResponse,
} from "@/types/repository";

/**
 * Thin service layer over the `/repositories` backend endpoints.
 * Returns raw Axios responses; hooks are responsible for unwrapping
 * data, caching, and error handling.
 *
 */
export const RepositoryApi = {
  getRepositories(): Promise<AxiosResponse<RepositoryListResponse>> {
    return apiClient.get<RepositoryListResponse>("/repositories");
  },

  createRepository(
    payload: RepositoryCreateRequest,
  ): Promise<AxiosResponse<RepositoryCreateResponse>> {
    return apiClient.post<RepositoryCreateResponse>("/repositories", payload);
  },

  getRepository(repositoryId: string): Promise<AxiosResponse<RepositoryDetailResponse>> {
    return apiClient.get<RepositoryDetailResponse>(`/repositories/${repositoryId}`);
  },

  getRepositoryStatus(repositoryId: string): Promise<AxiosResponse<RepositoryDetailResponse>> {
    return apiClient.get<RepositoryDetailResponse>(`/repositories/${repositoryId}/status`);
  },

  getRepositoryFileTree(
    repositoryId: string,
  ): Promise<AxiosResponse<{ files: Array<{ id: number; relative_path: string; language: string | null; file_size_bytes: number; checksum_sha256: string; chunks_generated: number }> }>> {
    return apiClient.get(`/repositories/${repositoryId}/files`);
  },

  getRepositoryFile(
    repositoryId: string,
    filePath: string,
  ): Promise<AxiosResponse<{ path: string; content: string; language: string | null; size_bytes: number }>> {
    return apiClient.get(`/repositories/${repositoryId}/files/content`, {
      params: { path: filePath },
    });
  },

  deleteRepository<TResponse = unknown>(repositoryId: string): Promise<AxiosResponse<TResponse>> {
    return apiClient.delete<TResponse>(`/repositories/${repositoryId}`);
  },

  reindexRepository(repositoryId: string): Promise<AxiosResponse<RepositoryDetailResponse>> {
    return apiClient.post<RepositoryDetailResponse>(`/repositories/${repositoryId}/reindex`);
  },
};
