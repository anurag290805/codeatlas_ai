import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BarChart3, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/common/PageHeader";
import { ErrorState } from "@/components/common/ErrorState";
import { ChunkChart } from "@/components/analytics/ChunkChart";
import { CommitActivityChart } from "@/components/analytics/CommitActivityChart";
import { LanguageChart } from "@/components/analytics/LanguageChart";
import { RepositoryMetrics } from "@/components/analytics/RepositoryMetrics";
import { StorageChart } from "@/components/analytics/StorageUsage";
import { useAnalytics } from "@/hooks/useAnalytics";
import { RepositorySelector } from "@/components/common/RepositorySelector";

export function Analytics() {
  const navigate = useNavigate();
  const { repositoryId: routeRepositoryId } = useParams<{ repositoryId: string }>();
  const [selectedRepositoryId, setSelectedRepositoryId] = useState(routeRepositoryId ?? "");
  const analytics = useAnalytics(selectedRepositoryId || undefined);
  const errorMessage = "CodeAtlas couldn't load analytics for this repository. Try again.";

  const handleRepositoryChange = (value: string) => {
    setSelectedRepositoryId(value);
    navigate(value ? `/analytics/${value}` : "/analytics");
  };

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <PageHeader
        eyebrow="Workspace telemetry"
        title="Analytics"
        description="Understand repository scale, indexing progress, and code structure."
        icon={<BarChart3 className="h-5 w-5" />}
        actions={
          <>
            <RepositorySelector
              repositories={analytics.repositories}
              value={selectedRepositoryId}
              onChange={handleRepositoryChange}
              allLabel="All repositories"
              isLoading={analytics.isLoading}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => void analytics.refetch()}
              disabled={analytics.isFetching}
              aria-label="Refresh analytics"
            >
              {analytics.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
            </Button>
          </>
        }
      />

      {analytics.isError && (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Analytics data could not be loaded"
              description={errorMessage}
              action={
                <Button variant="outline" size="sm" onClick={() => void analytics.refetch()} className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
              }
            />
          </CardContent>
        </Card>
      )}

      <section aria-label="Repository metrics">
        <RepositoryMetrics data={analytics.data.metrics} isLoading={analytics.isLoading} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <LanguageChart
          data={[...analytics.data.languageDistribution]}
          isLoading={analytics.isLoading}
          error={analytics.isError ? errorMessage : undefined}
        />
        <StorageChart
          data={analytics.data.storageBreakdown}
          isLoading={analytics.isLoading}
          error={analytics.isError ? errorMessage : undefined}
        />
        <ChunkChart
          data={analytics.data.chunkStatistics}
          isLoading={analytics.isLoading}
          error={analytics.isError ? errorMessage : undefined}
        />
        <CommitActivityChart
          data={[...analytics.data.commitActivity]}
          isLoading={analytics.isLoading}
          error={analytics.isError ? errorMessage : undefined}
        />
      </div>
    </div>
  );
}

export default Analytics;