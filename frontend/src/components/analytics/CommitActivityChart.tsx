// src/components/analytics/CommitActivityChart.tsx

import { useMemo, type FC } from "react";
import { motion } from "framer-motion";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { GitCommitHorizontal } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { CommitActivityDataPoint } from "@/types/analytics";

export interface CommitActivityChartProps {
  /** Commit activity for the repository, ordered chronologically. */
  data: CommitActivityDataPoint[];
  isLoading?: boolean;
  error?: string;
  className?: string;
}

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
});

interface TooltipPayloadItem {
  value: number;
  payload: CommitActivityDataPoint;
}

const CommitActivityTooltip: FC<{
  active?: boolean;
  payload?: TooltipPayloadItem[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  const date = new Date(item.date);

  return (
    <div className="rounded-md border border-border/60 bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-popover-foreground">
        {Number.isNaN(date.getTime()) ? item.date : dateFormatter.format(date)}
      </p>
      <p className="text-muted-foreground">
        {item.commits.toLocaleString()} {item.commits === 1 ? "commit" : "commits"}
      </p>
    </div>
  );
};

/**
 * Renders repository commit activity over time as a line chart. Purely
 * presentational - data arrives through props and no requests are made.
 */
export const CommitActivityChart: FC<CommitActivityChartProps> = ({
  data,
  isLoading = false,
  error,
  className,
}) => {
  const chartData = useMemo(
    () =>
      [...data].sort(
        (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
      ),
    [data],
  );

  const isEmpty = chartData.length === 0;

  return (
    <Card className={cn("border-border/60", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-foreground">
          Commit activity
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <CommitActivityChartSkeleton />
        ) : error ? (
          <ChartErrorState message={error} />
        ) : isEmpty ? (
          <CommitActivityChartEmptyState />
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className="h-64 w-full"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="var(--border)"
                  opacity={0.5}
                />
                <XAxis
                  dataKey="date"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  tickFormatter={(value: string) => {
                    const date = new Date(value);
                    return Number.isNaN(date.getTime())
                      ? value
                      : dateFormatter.format(date);
                  }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={36}
                  allowDecimals={false}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                />
                <Tooltip
                  content={<CommitActivityTooltip />}
                  cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
                />
                <Legend
                  verticalAlign="top"
                  height={28}
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => (
                    <span className="text-xs text-muted-foreground">{value}</span>
                  )}
                />
                <Line
                  type="monotone"
                  dataKey="commits"
                  name="Commits"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
};

const CommitActivityChartSkeleton: FC = () => (
  <div className="flex h-64 flex-col justify-end gap-3 px-2 pb-6">
    <Skeleton className="h-px w-full" />
    <div className="flex h-40 items-end gap-2">
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-28 w-full" />
    </div>
    <Skeleton className="h-3 w-full" />
  </div>
);

const CommitActivityChartEmptyState: FC = () => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <GitCommitHorizontal className="h-8 w-8 text-muted-foreground/50" />
    <p className="text-sm font-medium text-foreground">No commit activity</p>
    <p className="max-w-[220px] text-xs text-muted-foreground">
      Commit history hasn&apos;t been indexed for this repository yet.
    </p>
  </div>
);

const ChartErrorState: FC<{ message: string }> = ({ message }) => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <p className="text-sm font-medium text-destructive">Unable to load commit data</p>
    <p className="max-w-[240px] text-xs text-muted-foreground">{message}</p>
  </div>
);

export default CommitActivityChart;
