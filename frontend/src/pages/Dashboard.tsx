import { useMemo, useState } from "react";
import {
  Boxes,
  CheckCircle2,
  CircleAlert,
  Database,
  FileCode2,
  Import,
  LayoutDashboard,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { ImportRepositoryDialog, type ImportRepositoryFormValues } from "@/components/dashboard/ImportRepositoryDialog";
import { RecentActivity, type ActivityItem } from "@/components/dashboard/RecentActivity";
import { RepositoryCard } from "@/components/dashboard/RepositoryCard";
import { StatsCard } from "@/components/dashboard/StatisticsCard";
import { WorkspaceReadiness, type ReadinessSegment } from "@/components/dashboard/WorkspaceReadiness";
import { useDeleteRepository, useImportRepository, useRepositories } from "@/hooks/useRepositories";
import { useNavigate } from "react-router-dom";
import type { RepositoryListItem } from "@/types/repository";
import type { RepositoryStatusValue } from "@/components/dashboard/RepositoryStatus";
import { cn } from "@/lib/utils";

const STATUS_MAP: Record<RepositoryListItem["status"], RepositoryStatusValue> = {
  pending: "importing",
  cloning: "cloning",
  parsing: "indexing",
  embedding: "embedding",
  indexing: "indexing",
  indexed: "ready",
  ready: "ready",
  index_failed: "error",
  failed_import: "error",
  failed: "error",
  deleting: "importing",
  discovering_files: "indexing",
  chunking: "indexing",
  storing: "embedding",
};

function repositoryName(repository: RepositoryListItem): string {
  const name = repository.repository_name.trim();
  if (!name.startsWith("https://github.com/")) return name;

  const path = name.replace("https://github.com/", "").replace(/\/$/, "");
  return path.endsWith(".git") ? path.slice(0, -4) : path;
}

function repositoryOwner(repository: RepositoryListItem): string {
  const name = repositoryName(repository);
  return name.includes("/") ? name.split("/")[0] : "GitHub";
}

function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return "Not indexed";

  const elapsedSeconds = Math.round((new Date(timestamp).getTime() - Date.now()) / 1000);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  for (const [unit, seconds] of units) {
    if (Math.abs(elapsedSeconds) >= seconds) {
      return formatter.format(Math.round(elapsedSeconds / seconds), unit);
    }
  }

  return formatter.format(elapsedSeconds, "second");
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("en").format(value);
}

function formatRepositorySize(repository: RepositoryListItem): string {
  return `${formatCount(repository.files_indexed)} files`;
}

function isRepositoryReady(repository: RepositoryListItem): boolean {
  return repository.status === "ready" || repository.status === "indexed";
}

function isRepositoryFailed(repository: RepositoryListItem): boolean {
  return ["failed", "index_failed", "failed_import"].includes(repository.status);
}

function toActivity(repository: RepositoryListItem): ActivityItem {
  const activityType: ActivityItem["type"] =
    isRepositoryReady(repository) ? "index_updated" : "repository_imported";

  return {
    id: String(repository.id),
    type: activityType,
    title: repositoryName(repository),
    description: isRepositoryReady(repository) ? "Repository indexed" : `Status: ${repository.status}`,
    timestamp: formatRelativeTime(repository.last_indexed_at),
  };
}

export function Dashboard() {
  const navigate = useNavigate();
  const repositoriesQuery = useRepositories();
  const importRepository = useImportRepository();
  const deleteRepository = useDeleteRepository();
  const [isImportDialogOpen, setIsImportDialogOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const repositories = useMemo(
    () => repositoriesQuery.data?.items ?? [],
    [repositoriesQuery.data?.items],
  );
  const totalFiles = repositories.reduce((sum, repository) => sum + repository.files_indexed, 0);
  const totalChunks = repositories.reduce(
    (sum, repository) => sum + repository.chunks_generated,
    0,
  );
  const totalEmbeddings = repositories.reduce(
    (sum, repository) => sum + repository.embeddings_generated,
    0,
  );
  const indexedRepositories = repositories.filter(isRepositoryReady).length;
  const failedRepositories = repositories.filter(isRepositoryFailed).length;
  const processingRepositories = repositories.length - indexedRepositories - failedRepositories;

  const activities = useMemo(
    () => repositories.slice(0, 5).map(toActivity),
    [repositories],
  );

  const readinessSegments: ReadinessSegment[] = useMemo(
    () => [
      { label: "Ready", count: indexedRepositories, color: "bg-success", icon: CheckCircle2 },
      { label: "Processing", count: processingRepositories, color: "bg-warning", icon: Loader2 },
      { label: "Failed", count: failedRepositories, color: "bg-danger", icon: CircleAlert },
    ],
    [indexedRepositories, processingRepositories, failedRepositories],
  );

  const handleImport = async ({ repositoryUrl }: ImportRepositoryFormValues) => {
    setFeedback(null);

    try {
      await importRepository.mutateAsync({ url: repositoryUrl });
      setIsImportDialogOpen(false);
      setFeedback("Repository import started successfully.");
    } catch {
      setFeedback("CodeAtlas couldn't start this repository import. Try again.");
    }
  };

  const handleDelete = async (repository: RepositoryListItem) => {
    if (!window.confirm(`Delete ${repositoryName(repository)} and all indexed data?`)) return;
    setFeedback(null);
    try {
      await deleteRepository.mutateAsync(String(repository.id));
      setFeedback("Repository deleted successfully.");
    } catch {
      setFeedback("CodeAtlas couldn't delete this repository. Try again.");
    }
  };

  const isLoading = repositoriesQuery.isLoading;
  const hasError = repositoriesQuery.isError && repositories.length === 0;
  const isEmpty = !isLoading && !hasError && repositories.length === 0;

  return (
    <div className="flex min-h-full flex-col gap-5 lg:min-h-[calc(100dvh-12rem)] lg:justify-between">
      <PageHeader
        eyebrow="Workspace overview"
        className="[&_h1]:text-[1.4rem] sm:[&_h1]:text-[1.45rem]"
        title="Your code intelligence workspace"
        description={
          repositories.length > 0
            ? `${formatCount(repositories.length)} repositories in view · ${formatCount(indexedRepositories)} ready for questions`
            : "Import a repository to start building a searchable map of your code."
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void repositoriesQuery.refetch()}
            disabled={repositoriesQuery.isFetching}
            className="gap-1.5"
          >
            <RefreshCw className={repositoriesQuery.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            Refresh
          </Button>
        }
      />

      {feedback && (
        <Card className="border-border/60 bg-muted/30">
          <CardContent className="py-3 px-4 text-sm text-foreground font-medium">{feedback}</CardContent>
        </Card>
      )}

      {hasError ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Unable to load repositories"
              description="Refresh and try again."
              action={
                <Button variant="outline" size="sm" onClick={() => void repositoriesQuery.refetch()} className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Repository readiness + recent activity — tight two-column on desktop */}
          <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
            {isLoading ? (
              <Card>
                <CardHeader className="space-y-2">
                  <Skeleton className="h-5 w-1/3" />
                  <Skeleton className="h-4 w-1/2" />
                </CardHeader>
                <CardContent className="space-y-2">
                  <Skeleton className="h-8 w-1/4" />
                  <Skeleton className="h-2 w-full" />
                  <Skeleton className="h-10 w-full" />
                </CardContent>
              </Card>
            ) : (
              <WorkspaceReadiness total={repositories.length} segments={readinessSegments} />
            )}
            <RecentActivity
              activities={isLoading ? [] : activities}
              className={isLoading ? "opacity-0" : undefined}
            />
          </div>

          {/* Indexed data — one left-aligned, hairline-divided metric strip.
              No floating boxes: columns are separated by hairlines so the
              whole readout reads as a single anchored data row. */}
          <section aria-label="Indexed data" className="border-t border-border/70 pt-4">
            <div className="mb-2 flex items-end justify-between gap-4">
              <div>
                <p className="t-label">Knowledge base</p>
                <h2 className="t-heading mt-1">Indexed data</h2>
              </div>
              <span className="hidden text-xs text-muted-foreground sm:block">Across this workspace</span>
            </div>
            <div className="divide-y divide-border/70 overflow-hidden rounded-lg border border-border/70 bg-card sm:grid sm:grid-cols-3 sm:divide-y-0 sm:divide-x">
              <div className="px-4 py-3 sm:flex sm:flex-col sm:justify-center">
                <StatsCard
                  icon={FileCode2}
                  title="Indexed files"
                  value={isLoading ? "—" : formatCount(totalFiles)}
                  subtitle="Across all repositories"
                  tone="neutral"
                />
              </div>
              <div className="px-4 py-3 sm:flex sm:flex-col sm:justify-center">
                <StatsCard
                  icon={Boxes}
                  title="Code chunks"
                  value={isLoading ? "—" : formatCount(totalChunks)}
                  subtitle="Ready for retrieval"
                  tone="neutral"
                />
              </div>
              <div className="px-4 py-3 sm:flex sm:flex-col sm:justify-center">
                <StatsCard
                  icon={Database}
                  title="Embeddings"
                  value={isLoading ? "—" : formatCount(totalEmbeddings)}
                  subtitle="Stored vectors"
                  tone="neutral"
                />
              </div>
            </div>
          </section>

          {/* Repositories — dense, hairline-separated list.
              Left-anchored rows read like GitHub / Vercel listings, not a
              grid of floating boxes. */}
          <section aria-label="Repositories" className="border-t border-border/70 pt-4">
            <div className="mb-2 flex items-center justify-between gap-4">
              <h2 className="t-heading">Repositories</h2>
              {!isEmpty && repositories.length > 0 && (
                <span className="text-xs font-medium text-muted-foreground tabular-nums">
                  {formatCount(repositories.length)} total
                </span>
              )}
            </div>

            {isLoading ? (
              <div className="space-y-1">
                {["repository-skeleton-1", "repository-skeleton-2", "repository-skeleton-3"].map((key) => (
                  <div key={key} className="flex items-center gap-3 px-2 py-3">
                    <Skeleton className="h-7 w-7 shrink-0 rounded-md" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-1/3" />
                      <Skeleton className="h-3 w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : isEmpty ? (
              <EmptyState
                icon={LayoutDashboard}
                className="mx-auto flex min-h-56 w-full max-w-2xl border-border/50 bg-card/30 py-8"
                title="No repositories yet"
                description="Import a GitHub repository to start building your code intelligence workspace."
                action={
                  <Button onClick={() => setIsImportDialogOpen(true)} className="gap-1.5">
                    <Import className="h-4 w-4" />
                    Import repository
                  </Button>
                }
              />
            ) : (
              <div className="overflow-hidden rounded-lg border border-border/70 bg-card">
                {repositories.map((repository, index) => (
                  <div
                    key={repository.id}
                    className={cn(
                      "border-border/60",
                      index > 0 && "border-t",
                    )}
                  >
                    <RepositoryCard
                      key={repository.id}
                      variant="row"
                      name={repositoryName(repository)}
                      owner={repositoryOwner(repository)}
                      visibility="public"
                      defaultBranch={repository.default_branch}
                      size={formatRepositorySize(repository)}
                      lastUpdated={formatRelativeTime(repository.last_indexed_at)}
                      status={STATUS_MAP[repository.status]}
                      isLoading={false}
                      stage={repository.stage}
                      progressPercent={repository.progress_percent}
                      processedFiles={repository.processed_files}
                      totalFiles={repository.files_indexed}
                      processedChunks={repository.processed_chunks}
                      totalChunks={repository.chunks_generated}
                      processedEmbeddings={repository.processed_embeddings}
                      totalEmbeddings={repository.embeddings_generated}
                      onOpen={() => navigate(`/repositories/${repository.id}`)}
                      onRefresh={() => void repositoriesQuery.refetch()}
                      onDelete={() => void handleDelete(repository)}
                    />
                  </div>
                ))}
              </div>
            )}
          </section>

        </>
      )}

      <ImportRepositoryDialog
        open={isImportDialogOpen}
        onOpenChange={setIsImportDialogOpen}
        onSubmit={handleImport}
        isLoading={importRepository.isPending}
      />
    </div>
  );
}

export default Dashboard;