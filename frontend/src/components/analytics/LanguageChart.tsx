// src/components/analytics/LanguageChart.tsx

import { useMemo, type FC } from "react";
import { motion } from "framer-motion";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Braces } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatLanguage } from "@/utils/format";
import type { LanguageDistributionItem } from "@/types/analytics";

export interface LanguageChartProps {
  /** Language breakdown for the repository. */
  data: LanguageDistributionItem[];
  isLoading?: boolean;
  error?: string;
  className?: string;
}

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

interface TooltipPayloadItem {
  payload: LanguageDistributionItem;
}

const LanguageTooltip: FC<{ active?: boolean; payload?: TooltipPayloadItem[] }> = ({
  active,
  payload,
}) => {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;

  return (
    <div className="rounded-md border border-border/60 bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-popover-foreground">{item.language}</p>
      <p className="text-muted-foreground">
        {item.percentage.toFixed(1)}% &middot; {item.fileCount.toLocaleString()}{" "}
        {item.fileCount === 1 ? "file" : "files"}
      </p>
    </div>
  );
};

/**
 * Renders the programming-language distribution of a repository as a pie
 * chart. Purely presentational - all data arrives through props.
 */
export const LanguageChart: FC<LanguageChartProps> = ({
  data,
  isLoading = false,
  error,
  className,
}) => {
  const chartData = useMemo(
    () => [...data].map((item) => ({ ...item, language: formatLanguage(item.language) })).sort((a, b) => b.percentage - a.percentage),
    [data],
  );

  return (
    <Card className={cn("border-border/60", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-foreground">
          Language distribution
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LanguageChartSkeleton />
        ) : error ? (
          <ChartErrorState message={error} />
        ) : chartData.length === 0 ? (
          <LanguageChartEmptyState />
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className={cn("w-full", chartData.length === 1 ? "h-32" : "h-64")}
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="percentage"
                  nameKey="language"
                  cx="50%"
                  cy="50%"
                  innerRadius={chartData.length === 1 ? "52%" : 0}
                  outerRadius={chartData.length === 1 ? "78%" : "80%"}
                  startAngle={90}
                  endAngle={-270}
                  paddingAngle={1}
                  stroke="var(--card)"
                  strokeWidth={2}
                >
                  {chartData.map((entry, index) => (
                    <Cell
                      key={entry.language}
                      fill={CHART_COLORS[index % CHART_COLORS.length]}
                    />
                  ))}
                </Pie>
                {chartData.length === 1 && (
                  <text x="50%" y="45%" textAnchor="middle" dominantBaseline="middle" className="fill-foreground text-sm font-semibold">
                    100%
                  </text>
                )}
                <Tooltip content={<LanguageTooltip />} />
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
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
};

const LanguageChartSkeleton: FC = () => (
  <div className="flex h-64 flex-col items-center justify-center gap-4">
    <Skeleton className="h-40 w-40 rounded-full" />
    <div className="flex gap-2">
      <Skeleton className="h-3 w-14" />
      <Skeleton className="h-3 w-14" />
      <Skeleton className="h-3 w-14" />
    </div>
  </div>
);

const LanguageChartEmptyState: FC = () => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <Braces className="h-8 w-8 text-muted-foreground/50" />
    <p className="text-sm font-medium text-foreground">No language data</p>
    <p className="max-w-[220px] text-xs text-muted-foreground">
      Language detection hasn&apos;t completed for this repository yet.
    </p>
  </div>
);

const ChartErrorState: FC<{ message: string }> = ({ message }) => (
  <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
    <p className="text-sm font-medium text-destructive">Unable to load language data</p>
    <p className="max-w-[240px] text-xs text-muted-foreground">{message}</p>
  </div>
);

export default LanguageChart;
