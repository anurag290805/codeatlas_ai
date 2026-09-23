// src/types/repository.ts

import type { ID, Timestamp } from "./common";

/** Access level reported by the source host (e.g. GitHub) for a repository. */
export type RepositoryVisibility = "public" | "private" | "internal";

/** Lifecycle status of a repository within CodeAtlas, independent of indexing progress. */
export type RepositoryStatus = "active" | "archived" | "disabled";

/**
 * Progress of the ingestion pipeline for a repository, as surfaced in the
 * workspace header's status badge.
 */
export type RepositoryProcessingStatus =
  | "pending"
  | "cloning"
  | "parsing"
  | "embedding"
  | "discovering_files"
  | "chunking"
  | "storing"
  | "ready"
  | "failed";

export type IndexingStage = "queued" | "cloning" | "discovering" | "chunking" | "embedding" | "storing" | "completed" | "failed";

/** Owning user or organization for a repository, as reported by the source host. */
export interface RepositoryOwner {
  readonly id: ID;
  readonly login: string;
  readonly avatarUrl?: string;
  readonly type: "user" | "organization";
}

/** A single branch reference for a repository. */
export interface RepositoryBranch {
  readonly name: string;
  readonly isDefault: boolean;
  readonly lastCommitSha?: string;
  readonly lastCommitAt?: Timestamp;
}

/** Per-language breakdown of a repository's source files. */
export interface RepositoryLanguage {
  readonly language: string;
  readonly fileCount: number;
  readonly percentage: number;
}

/**
 * Structural counts for a repository, rendered by `RepositoryStats` as a
 * row of metric cards. Every field is a required `number` and nothing
 * else: the component looks values up dynamically via
 * `stats[key as keyof RepositoryStatistics]`, so any optional or
 * non-numeric field here would widen that lookup's type and break the
 * card's `value: number` prop.
 */
export interface RepositoryStatistics {
  readonly fileCount: number | null;
  readonly directoryCount: number | null;
  readonly commitCount: number | null;
  readonly contributorCount: number | null;
  readonly languageCount: number | null;
  readonly branchCount: number | null;
  readonly chunkCount: number | null;
  readonly embeddingCount: number | null;
}

/** Source-host engagement metrics (distinct from CodeAtlas-derived analytics). */
export interface RepositoryMetrics {
  readonly stars: number;
  readonly forks: number;
  readonly watchers: number;
  readonly openIssues: number;
  readonly sizeBytes: number;
}

/**
 * A single file's metadata and, once loaded, its contents — consumed by
 * the file explorer's viewer and passed through to the Monaco editor.
 * `path` is the natural identity for a file (it's used as the map key in
 * `FileExplorer`'s `fileContents` and as the React key in the viewer), so
 * `id` is not assumed to always be present.
 */
export interface RepositoryFile {
  readonly id?: ID;
  readonly path: string;
  readonly name: string;
  readonly extension?: string;
  readonly language?: string;
  readonly sizeBytes: number;
  readonly lineCount?: number;
  readonly lastModified?: Timestamp;
  /** True for non-text assets (images, binaries) that cannot be previewed as code. */
  readonly isBinary?: boolean;
  /** File contents, once fetched. Absent for binary files or before content loads. */
  readonly content?: string;
}

/**
 * Pre-loaded file payload as stored in the file explorer's `fileContents`
 * map. Identical in shape to `RepositoryFile` so a lookup from that map can
 * be passed anywhere a `RepositoryFile` is expected without conversion.
 */
export type FileContent = RepositoryFile;

/**
 * Recursive node used to render the repository file explorer tree.
 * `children` is intentionally a mutable array (not `readonly`): `FileTree`
 * recurses into it via a helper typed as `(nodes: FileTreeNode[]) => ...`,
 * so a readonly array here would not be assignable at that call site.
 * `children` being `undefined` (as opposed to an empty array) signals a
 * directory whose contents have not been lazily loaded yet.
 */
export interface FileTreeNode {
  readonly id?: ID;
  readonly name: string;
  readonly path: string;
  readonly type: "file" | "directory";
  readonly language?: string;
  readonly sizeBytes?: number;
  /** True while a directory's children are being lazily fetched. */
  readonly isLoading?: boolean;
  children?: FileTreeNode[];
}

/**
 * Full repository detail, as returned by the repository detail endpoint and
 * rendered by the workspace header. `owner` and `isPrivate` are flat
 * primitives rather than a nested object/enum, matching how the header
 * renders them directly.
 */
export interface Repository {
  readonly id: ID;
  readonly name: string;
  readonly fullName?: string;
  readonly description?: string;
  /** Login of the owning user or organization. */
  readonly owner: string;
  readonly url?: string;
  readonly htmlUrl: string;
  readonly isPrivate: boolean;
  readonly defaultBranch: string;
  readonly branches?: readonly RepositoryBranch[];
  readonly status: RepositoryProcessingStatus;
  readonly stage?: IndexingStage;
  readonly progress_percent?: number;
  readonly processed_files?: number;
  readonly processed_chunks?: number;
  readonly processed_embeddings?: number;
  readonly estimated_seconds_remaining?: number | null;
  readonly primaryLanguage?: string;
  readonly sizeBytes: number;
  readonly statistics?: RepositoryStatistics;
  readonly metrics?: RepositoryMetrics;
  readonly createdAt?: Timestamp;
  readonly updatedAt: Timestamp;
  readonly lastIndexedAt?: Timestamp;
}

/** Detail payload returned by the repository workspace endpoint. */
export interface RepositoryDetailResponse extends RepositoryListItem {
  readonly description?: string | null;
  readonly owner?: string | null;
  readonly visibility?: RepositoryVisibility;
  readonly primary_language?: string | null;
  readonly created_at?: string | null;
  readonly directory_count?: number | null;
  readonly commit_count?: number | null;
  readonly contributor_count?: number | null;
  readonly language_count?: number | null;
  readonly branch_count?: number | null;
  readonly branches?: readonly RepositoryBranch[];
  readonly statistics?: RepositoryStatistics;
  readonly metrics?: RepositoryMetrics;
  readonly files?: readonly FileTreeNode[];
  readonly indexing_started_at?: string | null;
  readonly error_message?: string | null;
  readonly stage?: IndexingStage;
  readonly progress_percent?: number;
  readonly processed_files?: number;
  readonly processed_chunks?: number;
  readonly processed_embeddings?: number;
  readonly estimated_seconds_remaining?: number | null;
  readonly completed_at?: string | null;
}

/** Condensed repository projection used in list and card views (e.g. the dashboard). */
export interface RepositorySummary {
  readonly id: ID;
  readonly name: string;
  readonly fullName?: string;
  readonly description?: string;
  readonly owner: string;
  readonly primaryLanguage?: string;
  readonly isPrivate: boolean;
  readonly status: RepositoryProcessingStatus;
  readonly fileCount?: number;
  readonly sizeBytes?: number;
  readonly updatedAt: Timestamp;
}

/** Repository projection returned by the backend repository list endpoint. */
export interface RepositoryListItem {
  readonly id: number;
  readonly repository_name: string;
  readonly url: string;
  readonly default_branch: string;
  readonly status: "pending" | "cloning" | "parsing" | "embedding" | "discovering_files" | "chunking" | "storing" | "ready" | "indexed" | "indexing" | "index_failed" | "failed_import" | "failed" | "deleting";
  readonly files_indexed: number;
  readonly chunks_generated: number;
  readonly embeddings_generated: number;
  readonly last_indexed_at: string | null;
  readonly stage?: IndexingStage;
  readonly progress_percent?: number;
  readonly processed_files?: number;
  readonly processed_chunks?: number;
  readonly processed_embeddings?: number;
  readonly estimated_seconds_remaining?: number | null;
}

/** Paginated repository response returned by the backend. */
export interface RepositoryListResponse {
  readonly items: readonly RepositoryListItem[];
  readonly total: number;
  readonly skip: number;
  readonly limit: number;
}

/** Payload accepted by the backend repository import endpoint. */
export interface RepositoryCreateRequest {
  readonly url: string;
  readonly branch?: string;
}

/** Repository response returned after an import is scheduled. */
export type RepositoryCreateResponse = RepositoryListItem;
