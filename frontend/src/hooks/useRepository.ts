// src/hooks/useRepository.ts
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { RepositoryApi } from "@/api/repositories";
import { buildFileTree, toRepositoryFile } from "@/utils/fileTree";
import type { FileTreeNode } from "@/types";

/**
 * Fetches a single repository by id. Automatically disabled when no
 * `repositoryId` is provided.
 */
export function useRepository(repositoryId: string | undefined) {
  return useQuery({
    queryKey: ["repository", repositoryId],
    queryFn: () =>
      RepositoryApi.getRepository(repositoryId as string).then((response) => response.data),
    enabled: Boolean(repositoryId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !["ready", "indexed", "failed", "index_failed", "failed_import"].includes(status)
        ? 1500
        : false;
    },
  });
}

/** Loads the repository file list and builds a hierarchical tree. */
export function useRepositoryFileTree(repositoryId: string | undefined) {
  const query = useQuery({
    queryKey: ["repository-files", repositoryId],
    queryFn: () =>
      RepositoryApi.getRepositoryFileTree(repositoryId as string).then(
        (response) => response.data,
      ),
    enabled: Boolean(repositoryId),
  });

  // Transform flat file list into hierarchical tree structure
  const fileTree: FileTreeNode[] = useMemo(() => {
    const files = query.data?.files ?? [];
    if (files.length === 0) return [];
    return buildFileTree(files.map(f => ({
      relative_path: f.relative_path,
      language: f.language,
      file_size_bytes: f.file_size_bytes,
    })));
  }, [query.data]);

  return {
    ...query,
    data: fileTree,
    rawFiles: query.data?.files,
  };
}

/** Loads file contents only after a file has been selected. */
export function useRepositoryFile(
  repositoryId: string | undefined,
  filePath: string | undefined,
) {
  const query = useQuery({
    queryKey: ["repository-file", repositoryId, filePath],
    queryFn: () =>
      RepositoryApi.getRepositoryFile(repositoryId as string, filePath as string).then(
        (response) => response.data,
      ),
    enabled: Boolean(repositoryId && filePath),
  });

  // Transform backend response to frontend RepositoryFile format
  const file = useMemo(() => {
    if (!query.data) return null;
    return toRepositoryFile(query.data);
  }, [query.data]);

  return {
    ...query,
    data: file,
  };
}
