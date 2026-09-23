// src/components/dashboard/RecentActivity.tsx
import {
  FolderPlus,
  MessageSquare,
  Network,
  RefreshCw,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type ActivityType =
  | "repository_imported"
  | "repository_deleted"
  | "query_executed"
  | "graph_generated"
  | "index_updated";

export interface ActivityItem {
  id: string;
  type: ActivityType;
  title: string;
  description?: string;
  timestamp: string;
}

interface RecentActivityProps {
  activities: ActivityItem[];
  className?: string;
}

const ACTIVITY_ICONS: Record<ActivityType, LucideIcon> = {
  repository_imported: FolderPlus,
  repository_deleted: Trash2,
  query_executed: MessageSquare,
  graph_generated: Network,
  index_updated: RefreshCw,
};

/**
 * Chronological feed of recent repository activity. Follows the dashboard's
 * dense, left-pinned language: a flat panel with a hairline header and a
 * hairline-separated list. Icons are monochrome — no colour chips — so the
 * readout reads as quiet tooling rather than a decorated feed.
 */
export function RecentActivity({ activities, className }: RecentActivityProps) {
  return (
    <Card className={cn("border-0 bg-muted/20 shadow-none", className)}>
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <h3 className="t-heading">Recent activity</h3>
        {activities.length > 0 && (
          <span className="text-[11px] font-medium text-muted-foreground tabular-nums">
            {activities.length} events
          </span>
        )}
      </div>

      <CardContent className="p-4">
        {activities.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">No recent activity yet.</p>
        ) : (
          <ul className="divide-y divide-border/60">
            {activities.map((activity) => {
              const Icon = ACTIVITY_ICONS[activity.type];

              return (
                <li key={activity.id} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border/70 bg-muted/40 text-muted-foreground">
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{activity.title}</p>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {activity.timestamp}
                      </span>
                    </div>
                    {activity.description && (
                      <p className="truncate text-xs text-muted-foreground">{activity.description}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}