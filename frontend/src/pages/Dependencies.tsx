import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Boxes, PackageCheck, RefreshCw, Search as SearchIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { useDependencies } from "@/hooks/useIntelligence";

function statusVariant(status: string): "destructive" | "secondary" | "outline" {
  if (status === "vulnerable") return "destructive";
  if (status === "outdated") return "secondary";
  return "outline";
}

export default function Dependencies() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const query = useDependencies(repositoryId);
  const data = query.data;
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!data?.dependencies) return [];
    const needle = filter.trim().toLowerCase();
    if (!needle) return data.dependencies;
    return data.dependencies.filter((dependency) =>
      dependency.name.toLowerCase().includes(needle) ||
      dependency.ecosystem.toLowerCase().includes(needle),
    );
  }, [data, filter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dependencies"
        eyebrow="Repository intelligence"
        description="Versions discovered from manifests (package.json, requirements.txt, pyproject.toml) in this repository."
        icon={<Boxes className="h-5 w-5" />}
        actions={
          <>
            <Button nativeButton={false} variant="ghost" size="sm" render={<Link to={`/repositories/${repositoryId}`} />} className="gap-1.5">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to repository
            </Button>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching} className="gap-1.5">
              <RefreshCw className={query.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              Refresh
            </Button>
          </>
        }
      />

      {query.isLoading ? (
        <Card>
          <CardContent className="space-y-3 p-6">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      ) : query.isError || !data?.available ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              icon={PackageCheck}
              title="Dependency data is unavailable"
              description={data?.message ?? "The repository may not be indexed yet. Refresh the repository index and try again."}
              action={
                <Button variant="outline" size="sm" onClick={() => void query.refetch()} className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : data.dependencies.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No supported manifests found"
          description="Add package.json, requirements.txt, or pyproject.toml to expose dependency intelligence."
        />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative max-w-sm">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter by package or ecosystem…"
                className="pl-8"
                aria-label="Filter dependencies"
              />
            </div>
            <span className="text-xs text-muted-foreground">
              {filtered.length} of {data.dependencies.length} dependencies
            </span>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              icon={SearchIcon}
              title="No matching dependencies"
              description={`No dependencies match “${filter.trim()}”.`}
            />
          ) : (
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[42rem] text-left text-sm">
                  <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 font-medium">Package</th>
                      <th className="px-4 py-3 font-medium">Ecosystem</th>
                      <th className="px-4 py-3 font-medium">Installed</th>
                      <th className="px-4 py-3 font-medium">Latest</th>
                      <th className="px-4 py-3 text-right font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filtered.map((dependency) => (
                      <tr key={`${dependency.ecosystem}-${dependency.name}`} className="transition-colors hover:bg-muted/30">
                        <td className="py-3 pl-4 pr-4">
                          <div className="flex items-center gap-2.5">
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                              <PackageCheck className="h-3.5 w-3.5" />
                            </span>
                            <span className="min-w-0">
                              <span className="block truncate font-medium">{dependency.name}</span>
                              <span className="block truncate text-xs text-muted-foreground">
                                {dependency.source_file}
                              </span>
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline" className="font-normal">{dependency.ecosystem}</Badge>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">
                          {dependency.installed_version ?? "Not pinned"}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">
                          {dependency.latest_version ?? "Unavailable"}
                        </td>
                        <td className="py-3 pl-4 pr-4 text-right">
                          <Badge variant={statusVariant(dependency.status)} className="normal-case">
                            {dependency.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}