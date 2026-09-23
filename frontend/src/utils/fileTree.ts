// src/utils/fileTree.ts

import type { FileTreeNode, RepositoryFile } from "@/types";

/**
 * Build a hierarchical file tree from a flat list of file metadata.
 * The backend returns a flat list of indexed files; the frontend FileTree
 * component expects a recursive tree structure.
 */
export function buildFileTree(files: Array<{ relative_path: string; language?: string | null; file_size_bytes?: number }>): FileTreeNode[] {
  const root: FileTreeNode[] = [];
  const nodeMap = new Map<string, FileTreeNode>();

  // Sort paths to ensure consistent ordering (directories before files, then alphabetically)
  const sortedFiles = [...files].sort((a, b) => {
    const pathA = a.relative_path;
    const pathB = b.relative_path;
    const aIsDir = !pathA.includes(".") || pathA.endsWith("/");
    const bIsDir = !pathB.includes(".") || pathB.endsWith("/");

    if (aIsDir && !bIsDir) return -1;
    if (!aIsDir && bIsDir) return 1;
    return pathA.localeCompare(pathB);
  });

  for (const file of sortedFiles) {
    const path = file.relative_path;
    const segments = path.split("/").filter(Boolean);

    // Build each segment of the path
    let currentPath = "";
    let currentLevel = root;

    for (let i = 0; i < segments.length; i++) {
      const segment = segments[i];
      const isFile = i === segments.length - 1 && !path.endsWith("/");
      currentPath = currentPath ? `${currentPath}/${segment}` : segment;

      let node = nodeMap.get(currentPath);

      if (!node) {
        node = {
          id: undefined,
          name: segment,
          path: currentPath,
          type: isFile ? "file" : "directory",
          language: isFile ? (file.language ?? undefined) : undefined,
          sizeBytes: isFile ? (file.file_size_bytes ?? 0) : undefined,
          children: isFile ? undefined : [],
        };
        nodeMap.set(currentPath, node);
        currentLevel.push(node);
      }

      if (!isFile && node.children) {
        currentLevel = node.children;
      }
    }
  }

  return root;
}

/**
 * Convert backend file content response to frontend RepositoryFile format.
 */
export function toRepositoryFile(data: {
  path: string;
  content: string;
  language?: string | null;
  size_bytes: number;
}): RepositoryFile {
  const name = data.path.split("/").pop() ?? data.path;
  return {
    path: data.path,
    name,
    language: data.language ?? undefined,
    sizeBytes: data.size_bytes,
    content: data.content,
  };
}
