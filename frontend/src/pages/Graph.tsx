import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Network, Server } from "lucide-react";
import { DependencyGraph } from "@/components/graph/DependencyGraph";
import { RepositorySelector } from "@/components/common/RepositorySelector";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { useRepositories } from "@/hooks/useRepositories";
import { useGraph } from "@/hooks/useGraph";
import type { RepositoryListItem } from "@/types/repository";

function repositoryLabel(repository: RepositoryListItem): string {
  return repository.repository_name
    .replace(/^https:\/\/github\.com\//, "")
    .replace(/\.git\/?$/, "");
}

export function Graph() {
  const navigate = useNavigate();
  const { repositoryId: routeRepositoryId } = useParams<{ repositoryId: string }>();
  const [selectedRepositoryId, setSelectedRepositoryId] = useState(routeRepositoryId ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const repositoriesQuery = useRepositories();
  const graphQuery = useGraph(selectedRepositoryId || undefined);
  const repositories = useMemo(() => repositoriesQuery.data?.items ?? [], [repositoriesQuery.data]);
  const selectedRepository = repositories.find(
    (repository) => String(repository.id) === selectedRepositoryId,
  );

  const handleRepositoryChange = (repositoryId: string) => {
    setSelectedRepositoryId(repositoryId);
    setSearchQuery("");
    if (repositoryId) navigate(`/graph/${repositoryId}`);
  };

  return (
    <div className="flex min-h-[calc(100vh-7rem)] flex-col gap-5">
      <PageHeader
        eyebrow="System map"
        title="Dependency Graph"
        description="Explore relationships across files, symbols, and modules — click a node to inspect it, drag to pan, and scroll to zoom."
        icon={<Network className="h-5 w-5" />}
        actions={
          <RepositorySelector
            repositories={repositories}
            value={selectedRepositoryId}
            onChange={handleRepositoryChange}
            isLoading={repositoriesQuery.isLoading}
          />
        }
      />

      {repositoriesQuery.isLoading && (
        <Loading label="Loading repositories…" className="justify-start py-6" />
      )}

      {repositoriesQuery.isError && (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Unable to load repositories"
              description="Import and index a repository before exploring its graph."
            />
          </CardContent>
        </Card>
      )}

      {!repositoriesQuery.isLoading && !repositoriesQuery.isError && repositories.length === 0 && (
        <EmptyState
          icon={Server}
          title="No repositories available"
          description="Import and index a repository, then select it above to explore its dependency graph."
        />
      )}

      {selectedRepository && (
        <section className="min-h-0 flex-1 space-y-3">
          <div className="flex items-baseline justify-between gap-3 border-b border-border/60 pb-3">
            <div className="flex items-baseline gap-3">
              <h2 className="font-mono text-sm font-semibold tracking-tight">
                {repositoryLabel(selectedRepository)}
              </h2>
              {graphQuery.data && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {graphQuery.data.nodes.length} nodes · {graphQuery.data.edges.length} relationships
                </span>
              )}
            </div>
          </div>
          <div className="overflow-hidden rounded-lg border border-border/70 bg-muted/10 shadow-sm">
            <DependencyGraph
            repositoryId={selectedRepositoryId}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            onRefresh={() => void graphQuery.refetch()}
            isRefreshing={graphQuery.isFetching}
              className="h-[calc(100vh-16rem)] min-h-[34rem]"
            />
          </div>
        </section>
      )}
    </div>
  );
}

export default Graph;