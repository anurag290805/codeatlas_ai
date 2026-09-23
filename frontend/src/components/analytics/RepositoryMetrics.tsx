// src/components/analytics/RepositoryMetrics.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import {
  FileText,
  FolderTree,
  Code2,
  Languages,
  Boxes,
  Sparkles,
  Waypoints,
  HardDrive,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatBytes as formatSharedBytes } from "@/utils/format";
import type { RepositoryMetricsData } from "@/types/analytics";

export interface RepositoryMetricsProps {
  /** Summary analytics for the repository. */
  data: RepositoryMetricsData;
  isLoading?: boolean;
  className?: string;
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact" }).format(value);
}

function formatOptionalNumber(value: number | null): string {
  return value == null ? "—" : formatCompactNumber(value);
}

function formatOptionalBytes(bytes: number | null): string {
  return bytes == null ? "Not calculated" : formatSharedBytes(bytes);
}

interface MetricDefinition {
  key: string;
  label: string;
  icon: FC<{ className?: string }>;
  value: string;
  /** Accent tone for the leading icon. */
  tone: "primary" | "info" | "success" | "warning" | "danger";
  /** Secondary metrics render smaller and denser than the headline tier. */
  featured?: boolean;
}

/**
 * Aggregates a repository's top-line analytics into two visual tiers:
 * a few headline metrics carry the weight while the remainder sit in a
 * denser grid. This avoids the "wall of identical cards" failure mode
 * while keeping every metric visible.
 */
export const RepositoryMetrics: FC<RepositoryMetricsProps> = ({
  data,
  isLoading = false,
  className,
}) => {
  const metrics: MetricDefinition[] = [
    {
      key: "files",
      label: "Total files",
      icon: FileText,
      value: formatCompactNumber(data.totalFiles),
      tone: "info",
      featured: true,
    },
    {
      key: "languages",
      label: "Languages detected",
      icon: Languages,
      value: formatCompactNumber(data.languagesDetected),
      tone: "warning",
    },
    {
      key: "chunks",
      label: "AI chunks",
      icon: Boxes,
      value: formatCompactNumber(data.aiChunks),
      tone: "primary",
      featured: true,
    },
    {
      key: "size",
      label: "Repository size",
      icon: HardDrive,
      value: formatOptionalBytes(data.repositorySizeBytes),
      tone: "success",
    },
    {
      key: "repositories",
      label: "Repositories",
      icon: FolderTree,
      value: formatCompactNumber(data.totalRepositories),
      tone: "info",
    },
    {
      key: "folders",
      label: "Total folders",
      icon: FolderTree,
      value: formatOptionalNumber(data.totalFolders),
      tone: "info",
    },
    {
      key: "symbols",
      label: "Total symbols",
      icon: Code2,
      value: formatOptionalNumber(data.totalSymbols),
      tone: "primary",
    },
    {
      key: "embeddings",
      label: "Embeddings",
      icon: Sparkles,
      value: formatCompactNumber(data.embeddings),
      tone: "success",
    },
    {
      key: "nodes",
      label: "Dependencies",
      icon: Waypoints,
      value: formatOptionalNumber(data.dependencyNodes),
      tone: "primary",
      featured: true,
    },
    {
      key: "processing",
      label: "Indexed",
      icon: Sparkles,
      value: `${formatCompactNumber(data.indexedRepositories)}/${formatCompactNumber(data.totalRepositories)}`,
      tone: "success",
    },
    {
      key: "failed",
      label: "Failed processing",
      icon: Waypoints,
      value: formatCompactNumber(data.failedRepositories),
      tone: "danger",
    },
  ];

  const featured = metrics.filter((metric) => metric.featured);
  const secondary = metrics.filter((metric) => !metric.featured);

  if (isLoading) {
    return (
      <div className={cn("space-y-4", className)}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {featured.map((metric) => <MetricCardSkeleton key={metric.key} featured />)}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {secondary.map((metric) => <MetricCardSkeleton key={metric.key} />)}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {featured.map((metric, index) => (
          <MetricCard key={metric.key} metric={metric} index={index} />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {secondary.map((metric, index) => (
          <MetricCard key={metric.key} metric={metric} index={index + featured.length} compact />
        ))}
      </div>
    </div>
  );
};

const METRIC_TONE_STYLES: Record<
  MetricDefinition["tone"],
  { icon: string; chip: string }
> = {
  primary: { icon: "text-primary", chip: "bg-primary/10" },
  info: { icon: "text-info", chip: "bg-info/10" },
  success: { icon: "text-success", chip: "bg-success/10" },
  warning: { icon: "text-warning", chip: "bg-warning/10" },
  danger: { icon: "text-danger", chip: "bg-danger/10" },
};

const MetricCard: FC<{
  metric: MetricDefinition;
  index: number;
  compact?: boolean;
}> = ({ metric, index, compact = false }) => {
  const Icon = metric.icon;
  const toneStyle = METRIC_TONE_STYLES[metric.tone];
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, delay: index * 0.02 }}
      className={cn(!compact && "h-full")}
    >
      <Card
        className={cn(
          "h-full transition-colors hover:border-border",
          compact ? "border-border/50" : "border-border/70",
        )}
      >
        <CardContent className={cn(compact ? "p-3" : "flex items-start justify-between gap-3 p-4")}>
          {compact ? (
            <div className="flex items-center justify-between gap-2">
              <p className="truncate text-xs text-muted-foreground">{metric.label}</p>
              <p className="shrink-0 text-sm font-semibold tracking-tight tabular-nums">{metric.value}</p>
            </div>
          ) : (
            <>
              <div className="min-w-0">
                <p className="truncate text-xs text-muted-foreground">{metric.label}</p>
                <p className="mt-1 truncate text-2xl font-semibold tracking-tight tabular-nums">
                  {metric.value}
                </p>
              </div>
              <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", toneStyle.chip)}>
                <Icon className={cn("h-4 w-4", toneStyle.icon)} />
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
};

const MetricCardSkeleton: FC<{ featured?: boolean }> = ({ featured = false }) => (
  <Card className="border-border/60">
    <CardContent className={cn("space-y-2.5", featured ? "p-4" : "p-3")}>
      {featured ? (
        <>
          <div className="flex items-start justify-between gap-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-8 w-8 rounded-md" />
          </div>
          <Skeleton className="h-7 w-16" />
        </>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-4 w-10" />
        </div>
      )}
    </CardContent>
  </Card>
);

export default RepositoryMetrics;