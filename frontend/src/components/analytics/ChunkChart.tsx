// src/components/analytics/ChunkChart.tsx

import { useMemo, type FC } from "react";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Boxes } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChunkStatistics } from "@/types/analytics";

export interface ChunkChartProps {
  /** Indexing statistics for the repository's chunked content. */
  data: ChunkStatistics;
  isLoading?: boolean;
  error?: string;
  className?: string;
}

interface ChunkDatum {
  key: "total" | "embedded" | "pending" | "failed";
  name: string;
  value: number;
  color: string;
}

interface TooltipPayloadItem {
  payload: ChunkDatum;
}

const ChunkTooltip: FC<{ active?: boolean; payload?: TooltipPayloadItem[] }> = ({
  active,
  payload,
}) => {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;

  return (
    <div className="rounded-md border border-border/60 bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-popover-foreground">{item.name}</p>
      <p className="text-muted-foreground">{item.value.toLocaleString()} chunks</p>
    </div>
  );
};

/**
 * Renders AI indexing statistics (total / embedded / pending / failed
 * chunks) as a bar chart. Purely presentational.
 */
export const ChunkChart: FC<ChunkChartProps> = ({
  data,
  isLoading = false,
  error,
  className,
}) => {
  const chartData = useMemo<ChunkDatum[]>(
    () => [
      {
        key: "total",
        name: "Total",
        value: data.totalChunks,
        color: "var(--chart-1)",
      },
      {
        key: "embedded",
        name: "Embedded",
        value: data.embeddedChunks,
        color: "var(--chart-2)",
      },
      data.pendingChunks == null ? null : {
        key: "pending",
        name: "Pending",
        value: data.pendingChunks,
        color: "var(--chart-4)",
      },
      data.failedChunks == null ? null : {
        key: "failed",
        name: "Failed",
        value: data.failedChunks,
        color: "var(--destructive)",
      },
    ].filter((entry): entry is ChunkDatum => entry !== null),
    [data],
  );

  const isEmpty = data.totalChunks === 0;

  return (
    <Card className={cn("border-border/60", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-foreground">
          Indexing status
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <ChunkChartSkeleton />
        ) : error ? (
          <ChartErrorState message={error} />
        ) : isEmpty ? (
          <ChunkChartEmptyState />
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className="h-64 w-full"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="var(--border)"
                  opacity={0.5}
                />
                <XAxis
                  dataKey="name"
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={40}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  allowDecimals={false}
                />
                <Tooltip content={<ChunkTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.3 }} />
                <Legend
                  verticalAlign="top"
                  height={28}
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => (
                    <span className="text-xs text-muted-foreground">{value}</span>
                  )}
                />
                <Bar dataKey="value" name="Chunks" radius={[4, 4, 0, 0]} maxBarSize={56}>
                  {chartData.map((entry) => (
                    <Cell key={entry.key} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
};

const ChunkChartSkeleton: FC = () => (
  <div className="flex h-64 items-end justify-center gap-6 px-4 pb-4">
    <Skeleton className="h-32 w-10" />
    <Skeleton className="h-44 w-10" />
    <Skeleton className="h-20 w-10" />
    <Skeleton className="h-10 w-10" />
  </div>
);

const ChunkChartEmptyState: FC = () => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <Boxes className="h-8 w-8 text-muted-foreground/50" />
    <p className="text-sm font-medium text-foreground">No chunks indexed yet</p>
    <p className="max-w-[220px] text-xs text-muted-foreground">
      Indexing statistics will appear once analysis has started.
    </p>
  </div>
);

const ChartErrorState: FC<{ message: string }> = ({ message }) => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <p className="text-sm font-medium text-destructive">Unable to load chunk data</p>
    <p className="max-w-[240px] text-xs text-muted-foreground">{message}</p>
  </div>
);

export default ChunkChart;
