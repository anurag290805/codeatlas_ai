// src/components/chat/RepositoryMap.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Coins,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  Layers,
  Loader2,
  Network,
  Rocket,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RepositoryMapData } from "@/types/chat-workspace";

export interface RepositoryMapProps {
  data: RepositoryMapData;
  onOpenGraph?: () => void;
  className?: string;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function formatRelativeTime(iso?: string): string {
  if (!iso) return "\u2014";
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return "\u2014";
  const diffSeconds = Math.round((target - Date.now()) / 1000);
  const divisions: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, secondsInUnit] of divisions) {
    if (Math.abs(diffSeconds) >= secondsInUnit) {
      return formatter.format(Math.round(diffSeconds / secondsInUnit), unit);
    }
  }
  return formatter.format(diffSeconds, "second");
}

const HEALTH_COLOR: Record<string, string> = {
  excellent: "text-success",
  good: "text-success",
  fair: "text-warning",
  "needs attention": "text-danger",
};

/**
 * Graph preview: a small illustrative node cluster sized/colored off the
 * real node/edge/cluster counts — not the actual dependency graph (that
 * still lives on the Graph page), just a live-feeling glance that makes
 * the counts legible before someone clicks through.
 */
const GraphPreview: FC<{ nodeCount: number; edgeCount: number; clusterCount: number; onOpen?: () => void }> = ({
  nodeCount,
  edgeCount,
  clusterCount,
  onOpen,
}) => {
  const dots = Array.from({ length: Math.min(18, Math.max(6, clusterCount * 3)) }, (_, i) => i);
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!onOpen}
      className="group relative h-24 w-full overflow-hidden rounded-lg border border-border/50 bg-gradient-to-br from-primary/10 via-transparent to-chart-2/10 text-left"
    >
      <svg viewBox="0 0 200 100" className="absolute inset-0 h-full w-full opacity-70">
        {dots.map((i) => {
          const x = 15 + ((i * 37) % 170);
          const y = 12 + ((i * 53) % 76);
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={i % 5 === 0 ? 3 : 1.6}
              className={i % 3 === 0 ? "fill-chart-1/70" : "fill-chart-2/50"}
            />
          );
        })}
        {dots.slice(0, -1).map((i) => {
          const x1 = 15 + ((i * 37) % 170);
          const y1 = 12 + ((i * 53) % 76);
          const x2 = 15 + (((i + 1) * 37) % 170);
          const y2 = 12 + (((i + 1) * 53) % 76);
          return (
            <line key={`e${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="stroke-border/40" strokeWidth={0.5} />
          );
        })}
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-background/60 px-2.5 py-1.5 text-[10px] text-muted-foreground backdrop-blur-sm">
        <span>
          {nodeCount.toLocaleString()} nodes &middot; {edgeCount.toLocaleString()} edges
        </span>
        {onOpen && (
          <span className="flex items-center gap-1 text-primary opacity-0 transition-opacity group-hover:opacity-100">
            <Network className="h-3 w-3" /> Open graph
          </span>
        )}
      </div>
    </button>
  );
};

const StatTile: FC<{ icon: FC<{ className?: string }>; label: string; value: string; accent?: string }> = ({
  icon: Icon,
  label,
  value,
  accent,
}) => (
  <div className="rounded-lg border border-border/50 bg-muted/20 px-2.5 py-2">
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <Icon className="h-3 w-3" />
      {label}
    </div>
    <p className={cn("mt-0.5 truncate text-sm font-semibold text-foreground", accent)}>{value}</p>
  </div>
);

export const RepositoryMap: FC<RepositoryMapProps> = ({ data, onOpenGraph, className }) => {
  const { repository, languages = [], commitHash, branch, health, indexing, tokenUsage, embeddingCount, fileCount, entryPoints = [], largestModules = [], lastIndexedAt, graphPreview } = data;

  const topLanguages = [...languages].sort((a, b) => b.percentage - a.percentage).slice(0, 4);
  const initials = repository.name.slice(0, 2).toUpperCase();
  const isIndexing = indexing?.status === "indexing";

  return (
    <div className={cn("space-y-3", className)}>
      <Card className="border-border/60 bg-card/50 backdrop-blur-sm">
        <CardContent className="space-y-3.5 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-sm font-semibold text-primary">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-foreground">{repository.name}</p>
              <p className="truncate text-xs text-muted-foreground">{repository.owner}</p>
            </div>
            {health && (
              <span className={cn("shrink-0 text-xs font-semibold", HEALTH_COLOR[health.label] ?? "text-muted-foreground")}>
                {health.score}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
              <GitBranch className="h-3 w-3" />
              {branch ?? repository.defaultBranch}
            </Badge>
            {commitHash && (
              <Badge variant="outline" className="gap-1 font-mono font-normal text-muted-foreground">
                <GitCommitHorizontal className="h-3 w-3" />
                {commitHash.slice(0, 7)}
              </Badge>
            )}
            <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
              {formatBytes(repository.sizeBytes)}
            </Badge>
            {isIndexing ? (
              <Badge variant="outline" className="gap-1 border-transparent bg-warning/10 font-normal text-warning">
                <Loader2 className="h-3 w-3 animate-spin" />
                Indexing
              </Badge>
            ) : repository.status === "ready" ? (
              <Badge variant="outline" className="gap-1 border-transparent bg-success/10 font-normal text-success">
                <Sparkles className="h-3 w-3" />
                Ready
              </Badge>
            ) : null}
          </div>

          {isIndexing && typeof indexing?.percent === "number" && (
            <div className="space-y-1">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <motion.div
                  className="h-full rounded-full bg-primary"
                  animate={{ width: `${Math.round(indexing.percent * 100)}%` }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                />
              </div>
              <p className="text-[11px] text-muted-foreground">
                {indexing.filesProcessed?.toLocaleString() ?? 0} / {indexing.filesTotal?.toLocaleString() ?? "\u2014"} files
              </p>
            </div>
          )}

          {topLanguages.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
                {topLanguages.map((language, index) => (
                  <motion.span
                    key={language.language}
                    className={cn(
                      "h-full",
                      index === 0 && "bg-chart-1",
                      index === 1 && "bg-chart-2",
                      index === 2 && "bg-chart-5",
                      index === 3 && "bg-muted-foreground/50",
                    )}
                    animate={{ width: `${language.percentage}%` }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                {topLanguages.map((language) => (
                  <span key={language.language}>
                    {language.language} &middot; {language.percentage.toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          )}

          {graphPreview && (
            <GraphPreview
              nodeCount={graphPreview.nodeCount}
              edgeCount={graphPreview.edgeCount}
              clusterCount={graphPreview.clusterCount}
              onOpen={onOpenGraph}
            />
          )}

          <div className="grid grid-cols-2 gap-2 text-xs">
            <StatTile icon={FileCode2} label="Indexed files" value={fileCount?.toLocaleString() ?? "\u2014"} />
            <StatTile icon={Layers} label="Embeddings" value={embeddingCount?.toLocaleString() ?? "\u2014"} />
            {tokenUsage && (
              <StatTile
                icon={Coins}
                label="Token usage"
                value={`${tokenUsage.used.toLocaleString()} / ${tokenUsage.budget.toLocaleString()}`}
                accent={tokenUsage.used / tokenUsage.budget > 0.85 ? "text-warning" : undefined}
              />
            )}
            {health && (
              <StatTile
                icon={Activity}
                label="Health"
                value={`${health.score}/100`}
                accent={HEALTH_COLOR[health.label]}
              />
            )}
          </div>

          <p className="text-[11px] text-muted-foreground">Last indexed {formatRelativeTime(lastIndexedAt)}</p>
        </CardContent>
      </Card>

      {entryPoints.length > 0 && (
        <Card className="border-border/60 bg-card/40">
          <CardContent className="space-y-1.5 p-3.5">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Rocket className="h-3 w-3" /> Entry points
            </p>
            {entryPoints.map((entry) => (
              <p key={entry.path} className="truncate text-xs text-foreground/80">
                <span className="text-muted-foreground">{entry.label}</span>{" "}
                <span className="font-mono text-[11px]">{entry.path}</span>
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      {largestModules.length > 0 && (
        <Card className="border-border/60 bg-card/40">
          <CardContent className="space-y-1.5 p-3.5">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Layers className="h-3 w-3" /> Largest modules
            </p>
            {largestModules.map((module) => (
              <div key={module.path} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate font-mono text-[11px] text-foreground/80">{module.path}</span>
                <span className="shrink-0 text-muted-foreground">
                  {module.fileCount} files &middot; {formatBytes(module.sizeBytes)}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default RepositoryMap;
