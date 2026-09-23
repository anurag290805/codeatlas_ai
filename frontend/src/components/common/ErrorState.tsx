import { AlertTriangle, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ErrorStateProps {
  icon?: LucideIcon;
  title?: ReactNode;
  /** Explanation of what went wrong. */
  description?: ReactNode;
  /** A recovery action, e.g. "Try again". */
  action?: ReactNode;
  className?: string;
}

/**
 * Standard error state. Visually distinct from both cards and empty
 * states without being alarming: a soft destructive tint, an explanatory
 * message, and an optional recovery action.
 */
export function ErrorState({
  icon: Icon = AlertTriangle,
  title = "Something went wrong",
  description,
  action,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-6 py-10 text-center",
        className,
      )}
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
        <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}