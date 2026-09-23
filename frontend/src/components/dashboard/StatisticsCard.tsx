// src/components/dashboard/StatisticsCard.tsx
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatTrendDirection = "positive" | "negative" | "neutral";

export interface StatTrend {
  value: string;
  direction: StatTrendDirection;
}

/** Accent tone for the leading icon glyph — monochrome slate. */
export type StatTone = "primary" | "neutral";

const TONE_STYLES: Record<StatTone, { icon: string }> = {
  primary: { icon: "text-primary" },
  neutral: { icon: "text-muted-foreground" },
};

interface StatsCardProps {
  icon: LucideIcon;
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: StatTrend;
  tone?: StatTone;
  className?: string;
}

/**
 * A single statistic rendered as a boxless, left-pinned metric block —
 * label above, large tabular value with an inline muted unit beside it.
 * Belongs inside a hairline-divided strip (see the Dashboard); it never
 * draws its own card box. Left-aligned by construction so the dashboard
 * reads as anchored, dense tooling rather than centered marketing cards.
 */
export function StatsCard({
  icon: Icon,
  title,
  value,
  subtitle,
  trend,
  tone = "neutral",
  className,
}: StatsCardProps) {
  const toneStyle = TONE_STYLES[tone];

  return (
    <div className={cn("flex min-w-0 flex-col justify-center gap-1 py-1", className)}>
      <div className="flex items-center gap-1.5">
        <Icon className={cn("h-3.5 w-3.5 shrink-0", toneStyle.icon)} aria-hidden="true" />
        <span className="t-label">{title}</span>
      </div>

      <div className="flex min-w-0 items-baseline gap-2">
        <span className="t-metric">{value}</span>
        {subtitle && <span className="t-metric-unit truncate">{subtitle}</span>}
      </div>

      {trend && (
        <span className="text-[11px] font-medium text-success">{trend.value}</span>
      )}
    </div>
  );
}