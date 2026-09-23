// src/components/dashboard/RepositoryStatus.tsx
import {
  AlertCircle,
  CheckCircle2,
  CircleDot,
  Download,
  GitBranch,
  Layers,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type RepositoryStatusValue =
  | "idle"
  | "importing"
  | "cloning"
  | "indexing"
  | "embedding"
  | "ready"
  | "error"
  | "index_failed"
  | "failed_import"
  | "deleting";

interface RepositoryStatusProps {
  status: RepositoryStatusValue;
  className?: string;
}

const STATUS_CONFIG: Record<
  RepositoryStatusValue,
  { label: string; icon: LucideIcon; className: string }
> = {
  idle: {
    label: "Idle",
    icon: CircleDot,
    className: "border-transparent bg-muted text-muted-foreground",
  },
  index_failed: {
    label: "Index Failed",
    icon: AlertCircle,
    className:
      "border-transparent bg-danger/10 text-danger",
  },

  failed_import: {
    label: "Import Failed",
    icon: AlertCircle,
    className:
      "border-transparent bg-danger/10 text-danger",
  },

  deleting: {
    label: "Deleting",
    icon: AlertCircle,
    className:
      "border-transparent bg-warning/10 text-warning",
  },
  importing: {
    label: "Importing",
    icon: Download,
    className: "border-transparent bg-info/10 text-info",
  },
  cloning: {
    label: "Cloning",
    icon: GitBranch,
    className: "border-transparent bg-info/10 text-info",
  },
  indexing: {
    label: "Indexing",
    icon: Layers,
    className: "border-transparent bg-warning/10 text-warning",
  },
  embedding: {
    label: "Embedding",
    icon: Sparkles,
    className: "border-transparent bg-warning/10 text-warning",
  },
  ready: {
    label: "Ready",
    icon: CheckCircle2,
    className: "border-transparent bg-success/10 text-success",
  },
  error: {
    label: "Error",
    icon: AlertCircle,
    className: "border-transparent bg-danger/10 text-danger",
  },
};

/**
 * Displays backend processing status for a repository as a labeled
 * badge with an icon. Reusable anywhere repository status needs to be
 * surfaced (cards, tables, detail panes).
 *
 * `RepositoryStatusValue` is defined here as the presentation status union
 * and should move to `src/types` once shared domain types exist.
 */
export function RepositoryStatus({ status, className }: RepositoryStatusProps) {
  const config =
    STATUS_CONFIG[status] ??
    {
      label: status,
      icon: AlertCircle,
      className:
        "border-transparent bg-muted text-muted-foreground",
    };

  const { label, icon: Icon, className: statusClassName } = config;
  const isActive = ["importing", "cloning", "indexing", "embedding", "deleting"].includes(status);

  return (
    <Badge className={cn("gap-1.5 font-medium", statusClassName, isActive && "status-pulse", className)}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </Badge>
  );
}
