import type { AxiosResponse } from "axios";
import { apiClient } from "@/api/client";
import type { DependenciesResponse, GithubIntelligence, SecurityResponse } from "@/types/intelligence";

export const IntelligenceApi = {
  getGithub(repositoryId: string): Promise<AxiosResponse<GithubIntelligence>> {
    return apiClient.get(`/repositories/${repositoryId}/github`);
  },
  getDependencies(repositoryId: string): Promise<AxiosResponse<DependenciesResponse>> {
    return apiClient.get(`/repositories/${repositoryId}/dependencies`);
  },
  getSecurity(repositoryId: string): Promise<AxiosResponse<SecurityResponse>> {
    return apiClient.get(`/repositories/${repositoryId}/security`);
  },
};
