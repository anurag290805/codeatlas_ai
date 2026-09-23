import { useQuery } from "@tanstack/react-query";
import { AnalyticsApi } from "@/api/analytics";
import { useRepositories } from "@/hooks/useRepositories";
import type { AnalyticsSummary } from "@/types/analytics";

const EMPTY_ANALYTICS: AnalyticsSummary = {
  repositoryId: "all",
  languageDistribution: [],
  chunkStatistics: {
    totalChunks: 0,
    embeddedChunks: 0,
    pendingChunks: 0,
    failedChunks: 0,
    averageChunkSize: 0,
  },
  storageBreakdown: {
    sourceFilesBytes: 0,
    embeddingsBytes: 0,
    metadataBytes: 0,
    graphDataBytes: 0,
    totalBytes: 0,
  },
  metrics: {
    totalRepositories: 0,
    totalFiles: 0,
    totalFolders: 0,
    totalSymbols: 0,
    linesOfCode: 0,
    languagesDetected: 0,
    aiChunks: 0,
    embeddings: 0,
    dependencyNodes: 0,
    repositorySizeBytes: 0,
    indexedRepositories: 0,
    pendingRepositories: 0,
    failedRepositories: 0,
  },
  commitActivity: [],
};

export function useAnalytics(repositoryId?: string) {
  const repositoriesQuery = useRepositories();
  const analyticsQuery = useQuery({
    queryKey: ["analytics", repositoryId ?? "all"],
    queryFn: () => AnalyticsApi.getAnalytics(repositoryId).then((response) => response.data),
  });

  return {
    data: analyticsQuery.data ?? EMPTY_ANALYTICS,
    repositories: repositoriesQuery.data?.items ?? [],
    isLoading: repositoriesQuery.isLoading || analyticsQuery.isLoading,
    isError: repositoriesQuery.isError || analyticsQuery.isError,
    error: repositoriesQuery.error ?? analyticsQuery.error,
    isFetching: repositoriesQuery.isFetching || analyticsQuery.isFetching,
    refetch: async () => {
      await Promise.all([repositoriesQuery.refetch(), analyticsQuery.refetch()]);
    },
  };
}
