// src/components/dashboard/RepositoryCard.tsx
import {
  ExternalLink,
  FolderGit2,
  Globe,
  Lock,
  MoreVertical,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { RepositoryStatus, type RepositoryStatusValue } from "@/components/dashboard/RepositoryStatus";
import { formatLanguage } from "@/utils/format";
import { cn } from "@/lib/utils";

export type RepositoryVisibility = "public" | "private";

interface RepositoryCardProps {
  name: string;
  owner: string;
  visibility: RepositoryVisibility;
  defaultBranch: string;
  language?: string;
  size: string;
  lastUpdated: string;
  status: RepositoryStatusValue;
  isLoading?: boolean;
  /** "card" renders a flat, left-anchored tile; "row" renders a dense hairline list row. */
  variant?: "card" | "row";
  onOpen?: () => void;
  onRefresh?: () => void;
  onDelete?: () => void;
  className?: string;
  progressPercent?: number;
  stage?: string;
  processedFiles?: number;
  totalFiles?: number;
  processedChunks?: number;
  totalChunks?: number;
  processedEmbeddings?: number;
  totalEmbeddings?: number;
}

/**
 * Presents a single imported repository — its metadata and current
 * processing status — with quick actions to open, refresh, or delete it.
 * Purely presentational; all data and handlers are supplied via props.
 *
 * Two layouts share the same data:
 *  - `card`: a flat, left-anchored tile with a quiet hairline border. No
 *    lift and no drop shadow — hover only deepens the border and surface,
 *    so the grid reads as tooling rather than a row of floating boxes.
 *  - `row`: a dense, hairline-separated list row for the Dashboard, where
 *    the whole line is the affordance (GitHub / Vercel listing style).
 */
export function RepositoryCard({
  name,
  owner,
  visibility,
  defaultBranch,
  language,
  size,
  lastUpdated,
  status,
  isLoading = false,
  variant = "card",
  onOpen,
  onRefresh,
  onDelete,
  className,
  progressPercent = 0,
  stage,
  processedFiles,
  totalFiles,
  processedChunks,
  totalChunks,
  processedEmbeddings,
  totalEmbeddings,
}: RepositoryCardProps) {
  const isReady = status === "ready";
  const VisibilityIcon = visibility === "private" ? Lock : Globe;
  const percent = Math.round(Math.min(100, Math.max(0, progressPercent)));

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="space-y-2">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </CardContent>
      </Card>
    );
  }

  const actions = (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            className={cn("shrink-0", variant === "row" ? "h-7 w-7" : "h-7 w-7")}
            aria-label="Repository actions"
          />
        }
      >
        <MoreVertical className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onOpen} className="gap-2">
          <ExternalLink className="h-4 w-4" />
          Open Repository
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onRefresh} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive gap-2">
          <Trash2 className="h-4 w-4" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  /* ---- Dense hairline list row (GitHub / Vercel listing) ---- */
  if (variant === "row") {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen?.();
          }
        }}
        className={cn(
          "group flex w-full cursor-pointer items-center gap-3 rounded-md px-2.5 py-2.5 text-left outline-none transition-colors",
          "hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/60",
          className,
        )}
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border/70 bg-muted/40 text-muted-foreground transition-colors group-hover:border-primary/30 group-hover:text-primary">
          <FolderGit2 className="h-3.5 w-3.5" aria-hidden="true" />
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-medium text-foreground">{name}</span>
            {!isReady && (
              <span className="shrink-0 text-[11px] font-medium capitalize text-warning">
                {stage ? stage.replace("_", " ") : "Indexing"} · {percent}%
              </span>
            )}
          </span>
          <span className="block truncate text-[11px] text-muted-foreground">
            {owner} · {size} · updated {lastUpdated}
          </span>
        </span>

        {/* meta — quiet on wide screens, hidden on cramped ones */}
        <span className="hidden shrink-0 items-center gap-3 md:flex">
          {language && (
            <Badge variant="outline" className="font-normal text-[11px]">
              {formatLanguage(language)}
            </Badge>
          )}
          <Badge variant="outline" className="hidden font-normal text-[11px] lg:inline-flex">
            <VisibilityIcon className="h-3 w-3" />
            {visibility === "private" ? "Private" : "Public"}
          </Badge>
          <span className="hidden font-mono text-[11px] font-medium text-muted-foreground xl:block">{defaultBranch}</span>
        </span>

        <RepositoryStatus status={status} className="shrink-0" />
        <span onClick={(event) => event.stopPropagation()}>{actions}</span>
      </div>
    );
  }

  /* ---- Flat, left-anchored card tile ---- */
  return (
    <Card
      className={cn(
        "flex h-full flex-col overflow-hidden transition-colors hover:border-border/100 hover:bg-card",
        className,
      )}
    >
      <CardHeader className="flex flex-col items-start justify-between gap-3 space-y-0 pb-1">
        <div className="flex w-full items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <h3 className="truncate text-sm font-semibold leading-tight text-foreground">{name}</h3>
            </div>
            <p className="truncate text-xs text-muted-foreground font-medium">{owner}</p>
          </div>
          {actions}
        </div>
        <RepositoryStatus status={status} />
      </CardHeader>

      <CardContent className="flex-1 pt-3">
        {!isReady && (
          <div className="space-y-2" aria-label={`${percent}% indexed`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground capitalize">
                {stage ? stage.replace("_", " ") : "Indexing"}
              </span>
              <span className="text-xs font-semibold text-foreground tabular-nums">{percent}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500"
                style={{ width: `${percent}%` }}
                role="progressbar"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground font-medium">
              {processedFiles != null && (
                <span>
                  <span className="text-foreground font-semibold">{processedFiles}</span>/{totalFiles ?? 0} files
                </span>
              )}
              {processedChunks != null && (
                <span>
                  <span className="text-foreground font-semibold">{processedChunks}</span>/{totalChunks ?? 0} chunks
                </span>
              )}
              {processedEmbeddings != null && (
                <span>
                  <span className="text-foreground font-semibold">{processedEmbeddings}</span>/{totalEmbeddings ?? 0} vectors
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>

      <div className="flex items-center gap-2 border-t border-border/60 pt-3 text-xs font-medium text-muted-foreground">
        <Badge variant="outline" className="font-normal text-[11px]">
          <VisibilityIcon className="h-3 w-3" />
          {visibility === "private" ? "Private" : "Public"}
        </Badge>
        {language && (
          <Badge variant="outline" className="font-normal text-[11px]">
            <span className="mr-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
            {formatLanguage(language)}
          </Badge>
        )}
        <span className="ml-auto shrink-0">{size}</span>
      </div>
    </Card>
  );
}