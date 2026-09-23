import { motion } from "framer-motion";
import {
  Files,
  FolderTree,
  GitCommitHorizontal,
  Users,
  Languages,
  GitBranch,
  Boxes,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RepositoryStatistics } from "@/types";

interface RepositoryStatsProps {
  stats: RepositoryStatistics;
  className?: string;
}

type StatTone = "primary" | "info" | "success" | "warning";

interface StatDefinition {
  key: keyof RepositoryStatistics;
  label: string;
  icon: LucideIcon;
  tone: StatTone;
  featured?: boolean;
}

const STAT_DEFINITIONS: StatDefinition[] = [
  { key: "fileCount", label: "Files", icon: Files, tone: "info", featured: true },
  { key: "directoryCount", label: "Directories", icon: FolderTree, tone: "info" },
  { key: "commitCount", label: "Commits", icon: GitCommitHorizontal, tone: "primary" },
  { key: "contributorCount", label: "Contributors", icon: Users, tone: "info" },
  { key: "languageCount", label: "Languages", icon: Languages, tone: "warning" },
  { key: "branchCount", label: "Branches", icon: GitBranch, tone: "info" },
  { key: "chunkCount", label: "AI Chunks", icon: Boxes, tone: "primary", featured: true },
  { key: "embeddingCount", label: "Embeddings", icon: Sparkles, tone: "success", featured: true },
];

const STAT_TONE_STYLES: Record<StatTone, string> = {
  primary: "text-primary",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
};

interface StatCardProps {
  label: string;
  value: number | null;
  icon: LucideIcon;
  tone: StatTone;
  delay: number;
  featured?: boolean;
}

function StatCard({ label, value, icon: Icon, tone, delay, featured = false }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut", delay }}
    >
      <Card className={cn(
        "group transition-colors hover:border-border hover:bg-muted/40",
        featured ? "border-border/70 p-4" : "border-border/50 p-3",
      )}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">
            {label}
          </span>
          <Icon className={cn("h-3.5 w-3.5 transition-colors", STAT_TONE_STYLES[tone])} />
        </div>
        <p className={cn(
          "mt-1.5 font-semibold tracking-tight text-foreground tabular-nums",
          featured ? "text-2xl" : "text-base",
        )}>
          {value == null ? "—" : value.toLocaleString()}
        </p>
      </Card>
    </motion.div>
  );
}

export function RepositoryStats({ stats, className }: RepositoryStatsProps) {
  const featured = STAT_DEFINITIONS.filter((definition) => definition.featured);
  const secondary = STAT_DEFINITIONS.filter((definition) => !definition.featured);
  return (
    <div className={cn("space-y-3", className)}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {featured.map((definition, index) => (
          <StatCard
            key={definition.key}
            label={definition.label}
            value={stats[definition.key]}
            icon={definition.icon}
            tone={definition.tone}
            delay={index * 0.03}
            featured
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {secondary.map((definition, index) => (
          <StatCard
            key={definition.key}
            label={definition.label}
            value={stats[definition.key]}
            icon={definition.icon}
            tone={definition.tone}
            delay={(index + featured.length) * 0.03}
          />
        ))}
      </div>
    </div>
  );
}
