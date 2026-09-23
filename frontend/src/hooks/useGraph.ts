// src/hooks/useGraph.ts
import { useQuery } from "@tanstack/react-query";
import { GraphApi } from "@/api/graph";
import type { GraphApiResponse } from "@/types/graph";

/**
 * Retrieves the dependency graph for a repository. Automatically
 * disabled when no `repositoryId` is provided.
 */
export function useGraph(repositoryId: string | undefined) {
  return useQuery<GraphApiResponse>({
    queryKey: ["graph", repositoryId],
    queryFn: () =>
      GraphApi.getDependencyGraph(repositoryId as string).then((response) => response.data),
    enabled: Boolean(repositoryId),
  });
}
