import { useState } from "react";
import { motion } from "framer-motion";
import {
  ExternalLink,
  GitBranch,
  Globe,
  Lock,
  MoreVertical,
  RefreshCw,
  Trash2,
  Code2,
  HardDrive,
  Clock,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { Repository, RepositoryProcessingStatus } from "@/types";

interface RepositoryHeaderProps {
  repository: Repository;
  onRefresh: () => void;
  onDelete?: () => void;
  onRetry?: () => void;
  isRefreshing?: boolean;
  isDeleting?: boolean;
  className?: string;
}

interface StatusConfig {
  label: string;
  icon: LucideIcon;
  badgeClassName: string;
  spin?: boolean;
}

const STATUS_CONFIG: Record<RepositoryProcessingStatus, StatusConfig> = {
  pending: {
    label: "Importing",
    icon: Clock,
    badgeClassName: "bg-muted text-muted-foreground border-transparent",
  },
  cloning: {
    label: "Indexing",
    icon: Loader2,
    badgeClassName: "bg-info/10 text-info border-transparent",
    spin: true,
  },
  parsing: {
    label: "Indexing",
    icon: Loader2,
    badgeClassName: "bg-info/10 text-info border-transparent",
    spin: true,
  },
  discovering_files: {
    label: "Indexing",
    icon: Loader2,
    badgeClassName: "bg-info/10 text-info border-transparent",
    spin: true,
  },
  chunking: {
    label: "Indexing",
    icon: Loader2,
    badgeClassName: "bg-info/10 text-info border-transparent",
    spin: true,
  },
  storing: {
    label: "Indexing",
    icon: Loader2,
    badgeClassName: "bg-info/10 text-info border-transparent",
    spin: true,
  },
  embedding: {
    label: "Indexing",
    icon: Loader2,
    badgeClassName: "bg-info/10 text-info border-transparent",
    spin: true,
  },
  ready: {
    label: "Ready",
    icon: CheckCircle2,
    badgeClassName: "bg-success/10 text-success border-transparent",
  },
  failed: {
    label: "Failed",
    icon: AlertTriangle,
    badgeClassName: "bg-destructive/10 text-destructive border-transparent",
  },
};

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function formatRelativeTime(isoDate?: string): string {
  if (!isoDate) return "Not indexed";
  const target = new Date(isoDate).getTime();
  if (Number.isNaN(target)) return "Not indexed";
  const diffSeconds = Math.round((target - Date.now()) / 1000);
  const divisions: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
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

function formatEta(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "Calculating time remaining…";
  if (seconds < 60) return `About ${Math.max(1, seconds)}s remaining`;
  return `About ${Math.ceil(seconds / 60)}m remaining`;
}

function progressLabel(repository: Repository): string {
  if (repository.status === "ready") return "Indexing complete";
  if (repository.status === "failed") return "Indexing failed. Retry to try again.";
  const labels: Record<string, string> = {
    queued: "Waiting to start…", cloning: "Cloning repository…", discovering: "Discovering files…",
    chunking: "Building code chunks…", embedding: "Generating embeddings…", storing: "Storing vectors…",
  };
  return labels[repository.stage ?? "queued"] ?? "Preparing index…";
}

export function RepositoryHeader({
  repository,
  onRefresh,
  onDelete,
  onRetry,
  isRefreshing = false,
  isDeleting = false,
  className,
}: RepositoryHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const status = STATUS_CONFIG[repository.status];
  const StatusIcon = status.icon;
  const VisibilityIcon = repository.isPrivate ? Lock : Globe;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={className}
    >
      <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-xl font-semibold tracking-tight text-foreground">
                {repository.name}
              </h1>
              <span className="text-sm text-muted-foreground">
                {repository.owner}
              </span>
            </div>

            {repository.description && (
              <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
                {repository.description}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-1.5">
              <Badge
                variant="outline"
                className={cn("gap-1 font-normal", status.badgeClassName)}
              >
                <StatusIcon
                  className={cn("h-3 w-3", status.spin && "animate-spin")}
                />
                {status.label}
              </Badge>
              <Badge variant="outline" className="gap-1 font-normal">
                <VisibilityIcon className="h-3 w-3" />
                {repository.isPrivate ? "Private" : "Public"}
              </Badge>
              <Badge variant="outline" className="gap-1 font-normal">
                <GitBranch className="h-3 w-3" />
                {repository.defaultBranch}
              </Badge>
              {repository.primaryLanguage && (
                <Badge variant="outline" className="gap-1 font-normal">
                  <Code2 className="h-3 w-3" />
                  {repository.primaryLanguage}
                </Badge>
              )}
              <Badge variant="outline" className="gap-1 font-normal">
                <HardDrive className="h-3 w-3" />
                {formatBytes(repository.sizeBytes)}
              </Badge>
            </div>

            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              Last indexed {formatRelativeTime(repository.lastIndexedAt ?? repository.updatedAt)}
            </p>

            {repository.status !== "ready" && (
              <div className="w-full max-w-xl space-y-2 pt-1" aria-live="polite">
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="font-medium text-foreground">{progressLabel(repository)}</span>
                  <span className="tabular-nums text-muted-foreground">{Math.round(Math.min(100, Math.max(0, repository.progress_percent ?? 0)))}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted ring-1 ring-border/50" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={repository.progress_percent ?? 0}>
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-primary to-primary/80 transition-[width] duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, repository.progress_percent ?? 0))}%` }}
                  />
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {repository.processed_files != null && <span>{repository.processed_files}/{repository.statistics?.fileCount ?? 0} files</span>}
                  {repository.processed_chunks != null && <span>{repository.processed_chunks}/{repository.statistics?.chunkCount ?? 0} chunks</span>}
                  {repository.processed_embeddings != null && <span>{repository.processed_embeddings}/{repository.statistics?.embeddingCount ?? 0} vectors</span>}
                  <span>{repository.status === "failed" ? "" : formatEta(repository.estimated_seconds_remaining)}</span>
                </div>
              </div>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              disabled={isRefreshing || isDeleting}
              className="gap-1.5"
            >
              <RefreshCw
                className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")}
              />
              Refresh
            </Button>

            <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9"
                    aria-label="Repository actions"
                  />
                }
              >
                <MoreVertical className="h-4 w-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem
                  render={
                    <a
                      href={repository.htmlUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="flex cursor-pointer items-center gap-2"
                    />
                  }
                >
                    <ExternalLink className="h-4 w-4" />
                    Open on GitHub
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {onRetry && repository.status === "failed" && (
                  <DropdownMenuItem
                    onSelect={(event) => {
                      event.preventDefault();
                      setMenuOpen(false);
                      onRetry();
                    }}
                    className="flex cursor-pointer items-center gap-2"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Retry indexing
                  </DropdownMenuItem>
                )}
                {onDelete && (
                  <DropdownMenuItem
                    disabled={isDeleting}
                    onSelect={(event) => {
                      event.preventDefault();
                      setMenuOpen(false);
                      onDelete();
                    }}
                    className="flex cursor-pointer items-center gap-2 text-destructive focus:bg-destructive/10 focus:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete Repository
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
