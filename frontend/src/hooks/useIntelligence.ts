import { useQuery } from "@tanstack/react-query";
import { IntelligenceApi } from "@/api/intelligence";

export function useGithubIntelligence(repositoryId: string | undefined) {
  return useQuery({
    queryKey: ["github-intelligence", repositoryId],
    queryFn: () => IntelligenceApi.getGithub(repositoryId as string).then((response) => response.data),
    enabled: Boolean(repositoryId),
    staleTime: 10 * 60 * 1000,
  });
}

export function useDependencies(repositoryId: string | undefined) {
  return useQuery({
    queryKey: ["dependencies", repositoryId],
    queryFn: () => IntelligenceApi.getDependencies(repositoryId as string).then((response) => response.data),
    enabled: Boolean(repositoryId),
    staleTime: 10 * 60 * 1000,
  });
}

export function useSecurity(repositoryId: string | undefined) {
  return useQuery({
    queryKey: ["security", repositoryId],
    queryFn: () => IntelligenceApi.getSecurity(repositoryId as string).then((response) => response.data),
    enabled: Boolean(repositoryId),
    staleTime: 10 * 60 * 1000,
  });
}
