import { CheckCircle2, CircleAlert, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

export interface ReadinessSegment {
  label: string;
  count: number;
  /** Tailwind text/bg colour for the segment. */
  color: string;
  icon: typeof CheckCircle2;
}

interface WorkspaceReadinessProps {
  total: number;
  segments: ReadinessSegment[];
  className?: string;
}

/**
 * Primary dashboard summary showing how many of the workspace's
 * repositories are ready, processing, or failed — the single most useful
 * "what is happening" signal. Follows the dashboard's dense, left-pinned
 * language: a flat panel with a hairline header, a proportionate status
 * bar, and a hairline-divided segment readout instead of floated chips.
 */
export function WorkspaceReadiness({
  total,
  segments,
  className,
}: WorkspaceReadinessProps) {
  const ready = segments.find((segment) => segment.label === "Ready")?.count ?? 0;
  const widthFor = (count: number) => (total > 0 ? `${(count / total) * 100}%` : "0%");
  const visible = segments.filter((segment) => segment.count > 0);

  return (
    <Card className={cn("border-0 bg-muted/20 shadow-none", className)}>
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <h3 className="t-heading">Repository readiness</h3>
        {total > 0 ? (
          <span className="text-[11px] font-medium text-success tabular-nums">{ready} ready</span>
        ) : (
          <Loader2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        )}
      </div>

      <CardContent className="space-y-3 p-4">
        <div className="flex items-baseline gap-2">
          <span className="t-metric">{total}</span>
          <span className="text-[13px] font-medium text-muted-foreground">
            repositories
          </span>
        </div>

        <div
          className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted"
          role="img"
          aria-label={`${ready} of ${total} repositories ready`}
        >
          {total > 0 &&
            segments
              .filter((segment) => segment.count > 0)
              .map((segment) => (
                <div
                  key={segment.label}
                  className={cn("h-full", segment.color)}
                  style={{ width: widthFor(segment.count) }}
                  aria-hidden="true"
                />
              ))}
        </div>

        {visible.length > 0 ? (
          <div className="grid grid-cols-3 divide-x divide-border/70 rounded-md border border-border/70">
            {visible.map((segment) => {
              const Icon = segment.icon;
              return (
                <div key={segment.label} className="flex min-w-0 flex-col gap-1 px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <Icon className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                    <span className="t-label truncate">{segment.label}</span>
                  </span>
                  <span className="text-sm font-semibold tabular-nums">{segment.count}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="flex items-center gap-2 text-xs text-warning">
            <CircleAlert className="h-3.5 w-3.5" />
            No repositories — import one to begin indexing.
          </p>
        )}
      </CardContent>
    </Card>
  );
}