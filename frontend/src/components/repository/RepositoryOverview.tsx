import { motion } from "framer-motion";
import {
  CalendarDays,
  GitBranch,
  HardDrive,
  Languages,
  Sparkles,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Repository } from "@/types";

interface RepositoryOverviewProps {
  repository: Repository;
  className?: string;
}

function formatDate(value?: string): string {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function RepositoryOverview({ repository, className }: RepositoryOverviewProps) {
  const languages = repository.statistics?.languageCount;
  const branches = repository.branches ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut", delay: 0.05 }}
      className={className}
    >
      <Card className="border-border/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Repository Overview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <p className="text-sm leading-relaxed text-muted-foreground">
            {repository.description?.trim() || "No description provided."}
          </p>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <CalendarDays className="h-3.5 w-3.5" />
                Last indexed
              </p>
              <p className="mt-1.5 text-sm font-semibold">{formatDate(repository.lastIndexedAt)}</p>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Languages className="h-3.5 w-3.5" />
                Languages
              </p>
              <p className="mt-1.5 text-sm font-semibold">{languages ?? "—"}</p>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <GitBranch className="h-3.5 w-3.5" />
                Branches
              </p>
              <p className="mt-1.5 text-sm font-semibold">
                {branches.length > 0 ? branches.length : repository.statistics?.branchCount ?? "—"}
              </p>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <HardDrive className="h-3.5 w-3.5" />
                Repository size
              </p>
              <p className="mt-1.5 text-sm font-semibold">
                {repository.sizeBytes > 0 ? `${repository.sizeBytes.toLocaleString()} bytes` : "—"}
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Sparkles className="h-3.5 w-3.5" />
                Repository metrics
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {repository.metrics ? (
                  <>
                    <Badge variant="outline">{repository.metrics.stars.toLocaleString()} stars</Badge>
                    <Badge variant="outline">{repository.metrics.forks.toLocaleString()} forks</Badge>
                    <Badge variant="outline">{repository.metrics.openIssues.toLocaleString()} open issues</Badge>
                  </>
                ) : (
                  <span className="text-sm text-muted-foreground">Metrics unavailable</span>
                )}
              </div>
            </div>
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Users className="h-3.5 w-3.5" />
                Branch information
              </h3>
              {branches.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {branches.slice(0, 6).map((branch) => (
                    <Badge key={branch.name} variant={branch.isDefault ? "default" : "outline"}>
                      {branch.name}
                    </Badge>
                  ))}
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">Branch details unavailable</span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
