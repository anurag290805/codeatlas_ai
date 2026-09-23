// src/components/chat/ContextSidebar.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import { Coins, FileCode2, Layers, Sparkles } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { Repository, RepositoryStatistics } from "@/types";

export interface ContextSidebarProps {
  repository: Repository;
  statistics?: RepositoryStatistics;
  modelName?: string;
  contextWindow?: number;
  className?: string;
}

const StatTile: FC<{ icon: FC<{ className?: string }>; label: string; value: string }> = ({
  icon: Icon,
  label,
  value,
}) => (
  <div className="rounded-lg border border-border/50 bg-muted/20 px-2.5 py-2">
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <Icon className="h-3 w-3" />
      {label}
    </div>
    <p className="mt-0.5 text-sm font-semibold text-foreground">{value}</p>
  </div>
);

/**
 * Right rail of the AI Chat workspace: the active model/session and a
 * quick repository snapshot. Per-answer citations and retrieval detail now
 * live inline in each answer's `AnswerCard`, so this panel stays focused
 * on session-level context rather than duplicating that per message.
 */
export const ContextSidebar: FC<ContextSidebarProps> = ({
  repository,
  statistics,
  modelName,
  contextWindow,
  className,
}) => {
  return (
    <div className={cn("flex h-full flex-col overflow-hidden", className)}>
      <div className="px-1 pb-3">
        <p className="text-xs font-medium text-muted-foreground">Session</p>
      </div>

      <ScrollArea className="flex-1">
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15 }}
          className="space-y-4 pr-2"
        >
          <Card className="border-border/60 bg-card/40">
            <CardContent className="space-y-3 p-3.5">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Sparkles className="h-4 w-4 text-primary" />
                {modelName ?? "Assistant"}
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {repository.description?.trim() ||
                  `Ask a question about ${repository.name} to get grounded answers with citations.`}
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-2">
            <StatTile
              icon={FileCode2}
              label="Files"
              value={statistics?.fileCount?.toLocaleString() ?? "\u2014"}
            />
            <StatTile
              icon={Layers}
              label="Chunks"
              value={statistics?.chunkCount?.toLocaleString() ?? "\u2014"}
            />
            <StatTile
              icon={Sparkles}
              label="Embeddings"
              value={statistics?.embeddingCount?.toLocaleString() ?? "\u2014"}
            />
            <StatTile
              icon={Coins}
              label="Context window"
              value={contextWindow ? `${contextWindow.toLocaleString()} tok` : "\u2014"}
            />
          </div>

          <p className="px-1 text-[11px] text-muted-foreground">
            Every answer's sources, confidence, and referenced files now appear inline with the answer itself.
          </p>
        </motion.div>
      </ScrollArea>
    </div>
  );
};

export default ContextSidebar;
