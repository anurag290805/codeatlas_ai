import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { ErrorState } from "@/components/common/ErrorState";
import { useSecurity } from "@/hooks/useIntelligence";

const SEVERITIES: Array<{
  key: string;
  label: string;
  badge: "destructive" | "warning" | "secondary" | "outline";
  dot: string;
  bar: string;
}> = [
  { key: "Critical", label: "Critical", badge: "destructive", dot: "bg-danger", bar: "bg-danger" },
  { key: "High", label: "High", badge: "warning", dot: "bg-warning", bar: "bg-warning" },
  { key: "Moderate", label: "Moderate", badge: "warning", dot: "bg-warning", bar: "bg-warning" },
  { key: "Low", label: "Low", badge: "outline", dot: "bg-info", bar: "bg-info" },
  { key: "Unknown", label: "Unknown", badge: "outline", dot: "bg-muted-foreground", bar: "bg-muted-foreground" },
];

export default function Security() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const query = useSecurity(repositoryId);
  const data = query.data;

  const totalVulnerabilities = data?.vulnerabilities?.length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Security"
        eyebrow="Repository intelligence"
        description="Known vulnerabilities matched by OSV against the versions discovered in dependencies."
        icon={<ShieldCheck className="h-5 w-5" />}
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
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      ) : query.isError || !data?.available ? (
        <Card>
          <CardContent className="p-0">
            <ErrorState
              title="Security intelligence could not be refreshed"
              description="Core repository analysis remains available. Refresh the scan and try again."
              action={
                <Button variant="outline" size="sm" onClick={() => void query.refetch()} className="gap-1.5">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-foreground">Vulnerabilities by severity</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">
                    {totalVulnerabilities} across {data.dependencies_scanned} dependencies checked by OSV
                  </p>
                </div>
              </div>

              <div className="mt-4 flex h-2 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label="Vulnerabilities by severity">
                {SEVERITIES.map((severity) => {
                  const count = data.severity_counts[severity.key] ?? 0;
                  if (count <= 0) return null;
                  return (
                    <div
                      key={severity.key}
                      className={severity.bar}
                      style={{ width: `${(count / Math.max(totalVulnerabilities, 1)) * 100}%` }}
                    />
                  );
                })}
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-5">
                {SEVERITIES.map((severity) => {
                  const count = data.severity_counts[severity.key] ?? 0;
                  return (
                    <div
                      key={severity.key}
                      className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-xs"
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${severity.dot}`} aria-hidden="true" />
                      <span className="text-muted-foreground">{severity.label}</span>
                      <span className="ml-auto font-semibold tabular-nums">{count}</span>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4 p-0">
              {data.vulnerabilities.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
                  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-success/10 text-success">
                    <ShieldCheck className="h-5 w-5" />
                  </span>
                  <p className="text-sm font-medium text-foreground">No known vulnerabilities</p>
                  <p className="max-w-sm text-sm text-muted-foreground">
                    {data.dependencies_scanned} dependencies were checked by OSV and none matched known advisories.
                  </p>
                </div>
              ) : (
                <>
                  <div className="border-b px-5 py-3">
                    <p className="text-sm font-medium text-foreground">
                      {totalVulnerabilities} vulnerable {totalVulnerabilities === 1 ? "dependency" : "dependencies"}
                    </p>
                  </div>
                  <div className="space-y-3 px-5 pb-5">
                    {data.vulnerabilities.map((vulnerability) => {
                      const severity = SEVERITIES.find(
                        (item) => item.key === vulnerability.severity,
                      ) ?? SEVERITIES[SEVERITIES.length - 1];
                      return (
                        <div key={`${vulnerability.package}-${vulnerability.id}`} className="rounded-lg border border-border/60 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="truncate font-medium">{vulnerability.package}</p>
                                <span className="font-mono text-xs text-muted-foreground">
                                  {vulnerability.installed_version}
                                </span>
                              </div>
                              <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                                {vulnerability.id}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`h-2 w-2 rounded-full ${severity.dot}`} aria-hidden="true" />
                              <Badge variant={severity.badge}>{vulnerability.severity}</Badge>
                            </div>
                          </div>

                          {vulnerability.summary && (
                            <p className="mt-3 text-sm text-muted-foreground">{vulnerability.summary}</p>
                          )}

                          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                            {vulnerability.fixed_versions.length > 0 && (
                              <p className="text-xs text-success">
                                Fixed in {vulnerability.fixed_versions.join(", ")}
                              </p>
                            )}
                            {vulnerability.references.length > 0 && (
                              <a
                                href={vulnerability.references[0]}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                              >
                                View advisory <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}