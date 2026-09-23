import { useMemo, useState } from "react";
import { FolderGit2, Import, RefreshCw, Search as SearchIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { ImportRepositoryDialog, type ImportRepositoryFormValues } from "@/components/dashboard/ImportRepositoryDialog";
import { RepositoryCard } from "@/components/dashboard/RepositoryCard";
import type { RepositoryStatusValue } from "@/components/dashboard/RepositoryStatus";
import { useImportRepository, useRepositories } from "@/hooks/useRepositories";
import type { RepositoryListItem } from "@/types/repository";

function nameOf(repository: RepositoryListItem): string {
  return repository.repository_name.replace(/^https:\/\/github\.com\//, "").replace(/\.git\/?$/, "");
}

function statusOf(repository: RepositoryListItem): RepositoryStatusValue {
  if (repository.status === "ready" || repository.status === "indexed") return "ready";
  if (repository.status === "failed" || repository.status === "index_failed" || repository.status === "failed_import") return "error";
  if (repository.stage === "embedding") return "embedding";
  if (repository.stage === "cloning") return "cloning";
  return "indexing";
}

const SKELETON_KEYS = ["repo-skeleton-a", "repo-skeleton-b", "repo-skeleton-c"];

export function Repositories() {
  const navigate = useNavigate();
  const repositoriesQuery = useRepositories();
  const importRepository = useImportRepository();
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const repositories = useMemo(() => repositoriesQuery.data?.items ?? [], [repositoriesQuery.data]);
  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return repositories;
    return repositories.filter((repository) => nameOf(repository).toLowerCase().includes(query));
  }, [repositories, filter]);

  const handleImport = async ({ repositoryUrl }: ImportRepositoryFormValues) => {
    await importRepository.mutateAsync({ url: repositoryUrl });
    setIsDialogOpen(false);
  };

  const isLoading = repositoriesQuery.isLoading;
  const hasError = repositoriesQuery.isError && repositories.length === 0;
  const isEmpty = !isLoading && !hasError && repositories.length === 0;
  const noMatches = !isLoading && !hasError && !isEmpty && filtered.length === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Repositories"
        description="Manage imported codebases and their indexing status."
        actions={
          <>
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
            <Button size="sm" onClick={() => setIsDialogOpen(true)} className="gap-1.5">
              <Import className="h-3.5 w-3.5" />
              Import repository
            </Button>
          </>
        }
      />

      {hasError ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Unable to load repositories"
              description="The repository list could not be fetched."
              action={
                <Button variant="outline" size="sm" onClick={() => void repositoriesQuery.refetch()} className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : isEmpty ? (
        <EmptyState
          icon={FolderGit2}
          title="No repositories yet"
          description="Import a GitHub repository to start building your code intelligence workspace."
          action={
            <Button onClick={() => setIsDialogOpen(true)} className="gap-1.5">
              <Import className="h-4 w-4" />
              Import repository
            </Button>
          }
        />
      ) : (
        <>
          <div className="relative max-w-sm">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter by repository name…"
              className="pl-8"
              aria-label="Filter repositories"
            />
          </div>

          {isLoading ? (
            <div className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border/70 bg-card">
              {SKELETON_KEYS.map((key) => (
                <div key={key} className="flex items-center gap-3 px-3 py-3">
                  <Skeleton className="h-7 w-7 shrink-0 rounded-md" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                  <Skeleton className="hidden h-6 w-20 rounded-full md:block" />
                </div>
              ))}
            </div>
          ) : noMatches ? (
            <EmptyState
              icon={FolderGit2}
              title="No matching repositories"
              description={`No imported repositories match “${filter.trim()}”.`}
            />
          ) : (
            <div className="overflow-hidden rounded-lg border border-border/70 bg-card">
              {filtered.map((repository, index) => (
                <div key={repository.id} className={cn(index > 0 && "border-t border-border/60")}>
                  <RepositoryCard
                    variant="row"
                    name={nameOf(repository)}
                    owner={nameOf(repository).split("/")[0] ?? "GitHub"}
                    visibility="public"
                    defaultBranch={repository.default_branch}
                    size={`${repository.files_indexed.toLocaleString()} files`}
                    lastUpdated={repository.last_indexed_at ? new Date(repository.last_indexed_at).toLocaleDateString() : "Not indexed"}
                    status={statusOf(repository)}
                    progressPercent={repository.progress_percent}
                    stage={repository.stage}
                    processedFiles={repository.processed_files}
                    totalFiles={repository.files_indexed}
                    processedChunks={repository.processed_chunks}
                    totalChunks={repository.chunks_generated}
                    processedEmbeddings={repository.processed_embeddings}
                    totalEmbeddings={repository.embeddings_generated}
                    onOpen={() => navigate(`/repositories/${repository.id}`)}
                    onRefresh={() => void repositoriesQuery.refetch()}
                  />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <ImportRepositoryDialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        onSubmit={handleImport}
        isLoading={importRepository.isPending}
      />
    </div>
  );
}

export default Repositories;