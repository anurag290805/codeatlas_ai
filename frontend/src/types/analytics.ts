// src/types/analytics.ts

import type { ID, Timestamp } from "./common";

/** Share of a repository's files attributed to a single programming language. */
export interface LanguageDistributionItem {
  readonly language: string;
  readonly fileCount: number;
  readonly percentage: number;
}

/** Counts of AI-indexing chunks grouped by processing outcome. */
export interface ChunkStatistics {
  readonly totalChunks: number;
  readonly embeddedChunks: number;
  readonly pendingChunks: number | null;
  readonly failedChunks: number | null;
  readonly averageChunkSize?: number | null;
}

/** Byte-level breakdown of storage consumed by a repository's indexed data. */
export interface StorageBreakdown {
  readonly sourceFilesBytes: number | null;
  readonly embeddingsBytes: number | null;
  readonly metadataBytes: number | null;
  readonly graphDataBytes: number | null;
  readonly totalBytes: number | null;
}

/** Top-line repository analytics rendered by the summary metric cards. */
export interface RepositoryMetricsData {
  readonly totalRepositories: number;
  readonly totalFiles: number;
  readonly totalFolders: number | null;
  readonly totalSymbols: number | null;
  readonly linesOfCode: number | null;
  readonly languagesDetected: number;
  readonly aiChunks: number;
  readonly embeddings: number;
  readonly dependencyNodes: number | null;
  readonly repositorySizeBytes: number | null;
  readonly indexedRepositories: number;
  readonly pendingRepositories: number;
  readonly failedRepositories: number;
}

/** Number of commits recorded for a single point in time (typically a day). */
export interface CommitActivityDataPoint {
  readonly date: string;
  readonly commits: number;
}

/** Composed analytics payload for a repository's analytics dashboard. */
export interface AnalyticsSummary {
  readonly repositoryId: ID;
  readonly languageDistribution: readonly LanguageDistributionItem[];
  readonly chunkStatistics: ChunkStatistics;
  readonly storageBreakdown: StorageBreakdown;
  readonly metrics: RepositoryMetricsData;
  readonly commitActivity: readonly CommitActivityDataPoint[];
  readonly generatedAt?: Timestamp;
}
