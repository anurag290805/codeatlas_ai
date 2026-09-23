import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Boxes,
  FoldHorizontal,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { FileExplorer } from "@/components/repository/FileExplorer";
import { RepositoryHeader } from "@/components/repository/RepositoryHeader";
import { RepositoryOverview } from "@/components/repository/RepositoryOverview";
import { RepositoryStats } from "@/components/repository/RepositoryStats";
import { Loading } from "@/components/common/Loading";
import { ErrorState } from "@/components/common/ErrorState";
import { SectionHeader } from "@/components/common/SectionHeader";
import { useRepository, useRepositoryFile, useRepositoryFileTree } from "@/hooks/useRepository";
import { useReindexRepository } from "@/hooks/useRepositories";
import type {
  Repository,
  RepositoryDetailResponse,
  RepositoryProcessingStatus,
} from "@/types/repository";
import { useGithubIntelligence } from "@/hooks/useIntelligence";

function repositoryName(data: RepositoryDetailResponse): string {
  const value = data.repository_name.trim();
  if (!value.startsWith("https://github.com/")) return value;
  return value.replace("https://github.com/", "").replace(/\.git\/?$/, "").replace(/\/$/, "");
}

function repositoryOwner(data: RepositoryDetailResponse): string {
  if (data.owner?.trim()) return data.owner;
  return repositoryName(data).split("/")[0] ?? "GitHub";
}

function processingStatus(status: RepositoryDetailResponse["status"]): RepositoryProcessingStatus {
  // Backend uses: ready, indexing, index_failed, failed_import, pending
  // Frontend uses: ready, pending, cloning, parsing, embedding, failed
  switch (status) {
    case "ready":
    case "indexed":
      return "ready";
    case "indexing":
    case "cloning":
    case "parsing":
    case "embedding":
      return "pending";
    case "discovering_files":
    case "chunking":
    case "storing":
      return "pending";
    case "index_failed":
    case "failed_import":
    case "failed":
      return "failed";
    default:
      return "pending";
  }
}

function stageStatus(stage: RepositoryDetailResponse["stage"]): RepositoryProcessingStatus {
  if (stage === "cloning" || stage === "embedding" || stage === "chunking" || stage === "discovering" || stage === "storing") return stage === "discovering" ? "discovering_files" : stage;
  return "pending";
}

function toRepository(data: RepositoryDetailResponse): Repository {
  const branches = data.branches ?? [];
  const statistics = data.statistics ?? {
    fileCount: data.files_indexed,
    directoryCount: data.directory_count ?? null,
    commitCount: data.commit_count ?? null,
    contributorCount: data.contributor_count ?? null,
    languageCount: data.language_count ?? null,
    branchCount: data.branch_count ?? (branches.length > 0 ? branches.length : null),
    chunkCount: data.chunks_generated,
    embeddingCount: data.embeddings_generated,
  };

  return {
    id: String(data.id),
    name: repositoryName(data),
    fullName: repositoryName(data),
    description: data.description ?? undefined,
    owner: repositoryOwner(data),
    url: data.url,
    htmlUrl: data.url,
    isPrivate: data.visibility === "private",
    defaultBranch: data.default_branch,
    branches,
    status: data.stage && data.status !== "ready" && data.status !== "indexed" && data.status !== "failed" && data.status !== "index_failed" && data.status !== "failed_import"
      ? stageStatus(data.stage)
      : processingStatus(data.status),
    stage: data.stage,
    progress_percent: data.progress_percent,
    processed_files: data.processed_files,
    processed_chunks: data.processed_chunks,
    processed_embeddings: data.processed_embeddings,
    estimated_seconds_remaining: data.estimated_seconds_remaining,
    primaryLanguage: data.primary_language ?? undefined,
    sizeBytes: data.metrics?.sizeBytes ?? 0,
    statistics,
    metrics: data.metrics,
    createdAt: data.created_at ?? undefined,
    updatedAt: data.last_indexed_at ?? data.created_at ?? "",
    lastIndexedAt: data.last_indexed_at ?? undefined,
  };
}

export function Repository() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [searchParams] = useSearchParams();
  const repositoryQuery = useRepository(repositoryId);
  const treeQuery = useRepositoryFileTree(repositoryId);
  const [selection, setSelection] = useState<{ repositoryId: string; path?: string }>({
    repositoryId: repositoryId ?? "",
    path: searchParams.get("file") ?? undefined,
  });
  const selectedPath = selection.repositoryId === repositoryId ? selection.path : undefined;
  const fileQuery = useRepositoryFile(repositoryId, selectedPath);
  const githubQuery = useGithubIntelligence(repositoryId);
  const reindexRepository = useReindexRepository();

  const repository = useMemo(
    () => (repositoryQuery.data ? toRepository(repositoryQuery.data) : undefined),
    [repositoryQuery.data],
  );
  const fileTree = treeQuery.data ?? repositoryQuery.data?.files ?? [];

  if (repositoryQuery.isLoading) {
    return <Loading label="Loading repository workspace…" className="min-h-[32rem]" />;
  }

  if (repositoryQuery.isError || !repository) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Unable to load this repository"
              description="The repository may not exist or is unavailable right now."
              action={
                <Button variant="outline" size="sm" onClick={() => void repositoryQuery.refetch()} className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
              }
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Breadcrumb repositoryName={repository.name} filePath={selectedPath} />

      <div className="flex items-center justify-between gap-3">
        <Button nativeButton={false} variant="ghost" size="sm" render={<Link to="/repositories" />} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" />
          Repositories
        </Button>
      </div>

      <RepositoryHeader
        repository={repository}
        onRefresh={() => void repositoryQuery.refetch()}
        isRefreshing={repositoryQuery.isFetching}
        onRetry={repository.status === "failed" ? () => void reindexRepository.mutateAsync(repositoryId ?? "") : undefined}
      />
      {repositoryQuery.data?.error_message && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-4 text-sm text-destructive">
            {repositoryQuery.data.error_message}
          </CardContent>
        </Card>
      )}

      <section aria-label="Repository intelligence" className="space-y-3">
        <SectionHeader
          title="Explore"
          description="Jump to related intelligence for this repository."
        />
        <div className="grid gap-3 sm:grid-cols-3">
          <Card className="border-border/60 transition-colors hover:border-border">
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted/60 text-muted-foreground">
                  <Star className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">GitHub stars</p>
                  <p className="truncate text-sm font-semibold">
                    {githubQuery.data?.available ? githubQuery.data.stars.toLocaleString() : "Unavailable"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border/60 transition-colors hover:border-border">
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted/60 text-muted-foreground">
                  <Boxes className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Dependencies</p>
                  <Link className="text-sm font-semibold text-primary hover:underline" to={`/repositories/${repositoryId}/dependencies`}>
                    Inspect packages
                  </Link>
                </div>
              </div>
              <GitBranch className="h-4 w-4 shrink-0 text-muted-foreground/60" aria-hidden="true" />
            </CardContent>
          </Card>
          <Card className="border-border/60 transition-colors hover:border-border">
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted/60 text-muted-foreground">
                  <ShieldCheck className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Security</p>
                  <Link className="text-sm font-semibold text-primary hover:underline" to={`/repositories/${repositoryId}/security`}>
                    Scan with OSV
                  </Link>
                </div>
              </div>
              <FoldHorizontal className="h-4 w-4 shrink-0 text-muted-foreground/60" aria-hidden="true" />
            </CardContent>
          </Card>
        </div>
      </section>

      <RepositoryOverview repository={repository} />
      <RepositoryStats stats={repository.statistics!} />

      <section aria-label="Files" className="space-y-3">
        <SectionHeader
          title="Files"
          description="Browse the indexed repository and inspect source files in read-only mode."
        />
        <FileExplorer
          fileTree={[...fileTree]}
          selectedPath={selectedPath}
          selectedFile={fileQuery.data ?? null}
          isFileLoading={fileQuery.isLoading}
          fileError={fileQuery.error}
          onFileSelect={(path) => setSelection({ repositoryId: repositoryId ?? "", path })}
          className="h-[min(42rem,calc(100vh-24rem))] min-h-[28rem]"
        />
      </section>
    </div>
  );
}

export default Repository;