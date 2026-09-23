// src/components/analytics/StorageChart.tsx

import { useMemo, type FC } from "react";
import { motion } from "framer-motion";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { HardDrive } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { StorageBreakdown } from "@/types/analytics";

export interface StorageChartProps {
  /** Storage breakdown, in bytes, for the repository. */
  data: StorageBreakdown;
  isLoading?: boolean;
  error?: string;
  className?: string;
}

interface StorageDatum {
  key: string;
  name: string;
  bytes: number;
  color: string;
}

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
];

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[exponent]}`;
}

interface TooltipPayloadItem {
  payload: StorageDatum;
}

const StorageTooltip: FC<{
  active?: boolean;
  payload?: TooltipPayloadItem[];
  total: number;
}> = ({ active, payload, total }) => {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  const percentage = total > 0 ? (item.bytes / total) * 100 : 0;

  return (
    <div className="rounded-md border border-border/60 bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-popover-foreground">{item.name}</p>
      <p className="text-muted-foreground">
        {formatBytes(item.bytes)} &middot; {percentage.toFixed(1)}%
      </p>
    </div>
  );
};

/**
 * Renders repository storage usage (source, embeddings, metadata, graph
 * data) as a donut chart with the total displayed at its center.
 */
export const StorageChart: FC<StorageChartProps> = ({
  data,
  isLoading = false,
  error,
  className,
}) => {
  const chartData = useMemo<StorageDatum[]>(() => {
    const entries: Array<Omit<StorageDatum, "color"> | null> = [
      data.sourceFilesBytes == null ? null : { key: "source", name: "Source files", bytes: data.sourceFilesBytes },
      data.embeddingsBytes == null ? null : { key: "embeddings", name: "Embeddings", bytes: data.embeddingsBytes },
      data.metadataBytes == null ? null : { key: "metadata", name: "Metadata", bytes: data.metadataBytes },
      data.graphDataBytes == null ? null : { key: "graph", name: "Graph data", bytes: data.graphDataBytes },
    ];
    return entries.filter((entry): entry is Omit<StorageDatum, "color"> => entry !== null).map((entry, index) => ({
      ...entry,
      color: CHART_COLORS[index % CHART_COLORS.length],
    }));
  }, [data]);

  const total = data.totalBytes;
  const isEmpty = total == null || total === 0;

  return (
    <Card className={cn("border-border/60", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-foreground">
          Storage usage
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <StorageChartSkeleton />
        ) : error ? (
          <ChartErrorState message={error} />
        ) : isEmpty ? (
          <StorageChartEmptyState />
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className="relative h-64 w-full"
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="bytes"
                  nameKey="name"
                  innerRadius="60%"
                  outerRadius="80%"
                  paddingAngle={2}
                  stroke="var(--card)"
                  strokeWidth={2}
                >
                  {chartData.map((entry) => (
                    <Cell key={entry.key} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={<StorageTooltip total={total ?? 0} />} />
                <Legend
                  verticalAlign="bottom"
                  height={36}
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => (
                    <span className="text-xs text-muted-foreground">{value}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center pb-9">
              <p className="text-lg font-semibold text-foreground">
                {formatBytes(total ?? 0)}
              </p>
              <p className="text-[11px] text-muted-foreground">total storage</p>
            </div>
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
};

const StorageChartSkeleton: FC = () => (
  <div className="flex h-64 flex-col items-center justify-center gap-4">
    <Skeleton className="h-40 w-40 rounded-full" />
    <div className="flex gap-2">
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-3 w-16" />
    </div>
  </div>
);

const StorageChartEmptyState: FC = () => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <HardDrive className="h-8 w-8 text-muted-foreground/50" />
    <p className="text-sm font-medium text-foreground">No storage data</p>
    <p className="max-w-[220px] text-xs text-muted-foreground">
      Storage usage will appear once the repository has been processed.
    </p>
  </div>
);

const ChartErrorState: FC<{ message: string }> = ({ message }) => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <p className="text-sm font-medium text-destructive">Unable to load storage data</p>
    <p className="max-w-[240px] text-xs text-muted-foreground">{message}</p>
  </div>
);

export default StorageChart;
