// src/components/chat/AIThinkingTimeline.tsx

import type { FC } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FileSearch, GitBranch, Loader2, Search, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RetrievalStage } from "@/types/chat-workspace";

export type { RetrievalStage } from "@/types/chat-workspace";
export interface RetrievalStats {
  readonly filesSearched?: number;
  readonly chunksRetrieved?: number;
  readonly contextTokens?: number;
}

export interface AIThinkingTimelineProps {
  stage: RetrievalStage;
  stats?: RetrievalStats;
  className?: string;
}

const STAGES: { key: RetrievalStage; label: string; icon: FC<{ className?: string }> }[] = [
  { key: "searching", label: "Searching repository\u2026", icon: Search },
  { key: "finding_files", label: "Finding relevant files\u2026", icon: FileSearch },
  { key: "analyzing_dependencies", label: "Analyzing dependencies\u2026", icon: GitBranch },
  { key: "building_context", label: "Building context\u2026", icon: Sparkles },
  { key: "generating", label: "Generating response\u2026", icon: Sparkles },
];

const STAGE_ORDER = STAGES.map((s) => s.key);

/**
 * Shows the real retrieval pipeline as it happens. `stage` is driven by
 * whatever the streaming hook currently reports (e.g. SSE `stage` events
 * from routes_query.py) — this component never invents timing of its own.
 * Rows before the current stage are marked done, the current one animates,
 * later ones sit dim and pending. When retrieval finishes, the caller swaps
 * this out for the completed-stats strip (rendered here when `stats` is
 * present and stage is "generating", so the two can cross-fade).
 */
export const AIThinkingTimeline: FC<AIThinkingTimelineProps> = ({ stage, stats, className }) => {
  const currentIndex = STAGE_ORDER.indexOf(stage);
  const showStats = stage === "generating" && stats && Object.keys(stats).length > 0;

  return (
    <div className={cn("min-w-[15rem]", className)}>
      <div className="space-y-2">
        {STAGES.map((row, index) => {
          const isDone = index < currentIndex || (index === currentIndex && showStats);
          const isActive = index === currentIndex && !showStats;
          const isPending = index > currentIndex;
          const Icon = row.icon;

          return (
            <motion.div
              key={row.key}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: isPending ? 0.4 : 1, x: 0 }}
              transition={{ duration: 0.2 }}
              className="flex items-center gap-2.5 text-xs"
            >
              <span
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
                  isDone && "text-success",
                  isActive && "text-primary",
                  isPending && "text-muted-foreground",
                )}
              >
                {isDone ? (
                  <Check className="h-3.5 w-3.5" />
                ) : isActive ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Icon className="h-3 w-3" />
                )}
              </span>
              <span className={cn(isDone && "text-muted-foreground line-through decoration-muted-foreground/40", isActive && "font-medium text-foreground", isPending && "text-muted-foreground")}>
                {row.label}
              </span>
            </motion.div>
          );
        })}
      </div>

      <AnimatePresence>
        {showStats && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-border/40 pt-2.5 text-[11px] text-success/90"
          >
            {typeof stats?.filesSearched === "number" && (
              <span className="inline-flex items-center gap-1">
                <Check className="h-3 w-3" /> {stats.filesSearched} files searched
              </span>
            )}
            {typeof stats?.chunksRetrieved === "number" && (
              <span className="inline-flex items-center gap-1">
                <Check className="h-3 w-3" /> {stats.chunksRetrieved} chunks retrieved
              </span>
            )}
            {typeof stats?.contextTokens === "number" && (
              <span className="inline-flex items-center gap-1">
                <Check className="h-3 w-3" /> Context {stats.contextTokens.toLocaleString()} tokens
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default AIThinkingTimeline;
