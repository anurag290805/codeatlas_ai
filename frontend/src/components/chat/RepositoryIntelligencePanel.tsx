// src/components/chat/RepositoryIntelligencePanel.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import {
  BarChart3,
  ExternalLink,
  GitBranch,
  HardDrive,
  MessageSquarePlus,
  Network,
  Pin,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { ID, Repository, RepositoryLanguage, RepositoryStatistics, Timestamp } from "@/types";

export interface ConversationSummaryItem {
  readonly id: ID;
  readonly title: string;
  readonly updatedAt: Timestamp;
}

export interface RepositoryIntelligencePanelProps {
  repository: Repository;
  statistics?: RepositoryStatistics;
  languages?: readonly RepositoryLanguage[];
  lastIndexedAt?: Timestamp;
  conversations?: readonly ConversationSummaryItem[];
  activeConversationId?: ID;
  pinnedPrompts?: readonly string[];
  onNewConversation?: () => void;
  onSelectConversation?: (id: ID) => void;
  onSelectPinnedPrompt?: (prompt: string) => void;
  onReindex?: () => void;
  onOpenGraph?: () => void;
  onOpenAnalytics?: () => void;
  onOpenRepository?: () => void;
  className?: string;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function formatRelativeTime(iso?: string): string {
  if (!iso) return "\u2014";
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return "\u2014";
  const diffSeconds = Math.round((target - Date.now()) / 1000);
  const divisions: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, secondsInUnit] of divisions) {
    if (Math.abs(diffSeconds) >= secondsInUnit) {
      return formatter.format(Math.round(diffSeconds / secondsInUnit), unit);
    }
  }
  return formatter.format(diffSeconds, "second");
}

const QUICK_ACTIONS = (props: RepositoryIntelligencePanelProps) => [
  { key: "reindex", label: "Reindex", icon: RefreshCw, onClick: props.onReindex },
  { key: "graph", label: "Graph", icon: Network, onClick: props.onOpenGraph },
  { key: "analytics", label: "Analytics", icon: BarChart3, onClick: props.onOpenAnalytics },
  { key: "open", label: "Open", icon: ExternalLink, onClick: props.onOpenRepository },
];

/**
 * Left rail of the AI Chat workspace: a compact repository identity card,
 * key indexing stats, quick actions into the graph/analytics surfaces, and
 * conversation history. Purely presentational.
 */
export const RepositoryIntelligencePanel: FC<RepositoryIntelligencePanelProps> = (props) => {
  const {
    repository,
    statistics,
    languages = [],
    lastIndexedAt,
    conversations = [],
    activeConversationId,
    pinnedPrompts = [],
    onNewConversation,
    onSelectConversation,
    onSelectPinnedPrompt,
    className,
  } = props;

  const topLanguages = [...languages].sort((a, b) => b.percentage - a.percentage).slice(0, 4);
  const initials = repository.name.slice(0, 2).toUpperCase();

  return (
    <div className={cn("flex h-full flex-col gap-4 overflow-hidden", className)}>
      <Card className="border-border/60 bg-card/50 backdrop-blur-sm">
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-sm font-semibold text-primary">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">{repository.name}</p>
              <p className="truncate text-xs text-muted-foreground">{repository.owner}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
              <GitBranch className="h-3 w-3" />
              {repository.defaultBranch}
            </Badge>
            <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
              <HardDrive className="h-3 w-3" />
              {formatBytes(repository.sizeBytes)}
            </Badge>
            {repository.status === "ready" && (
              <Badge variant="outline" className="gap-1 border-transparent bg-success/10 font-normal text-success">
                <Sparkles className="h-3 w-3" />
                Ready
              </Badge>
            )}
          </div>

          {topLanguages.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
                {topLanguages.map((language, index) => (
                  <span
                    key={language.language}
                    className={cn(
                      "h-full",
                      index === 0 && "bg-chart-1",
                      index === 1 && "bg-chart-2",
                      index === 2 && "bg-chart-5",
                      index === 3 && "bg-muted-foreground/50",
                    )}
                    style={{ width: `${language.percentage}%` }}
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                {topLanguages.map((language) => (
                  <span key={language.language}>
                    {language.language} &middot; {language.percentage.toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg border border-border/50 bg-muted/20 px-2.5 py-2">
              <p className="text-muted-foreground">Indexed files</p>
              <p className="font-semibold text-foreground">
                {statistics?.fileCount?.toLocaleString() ?? "\u2014"}
              </p>
            </div>
            <div className="rounded-lg border border-border/50 bg-muted/20 px-2.5 py-2">
              <p className="text-muted-foreground">Embeddings</p>
              <p className="font-semibold text-foreground">
                {statistics?.embeddingCount?.toLocaleString() ?? "\u2014"}
              </p>
            </div>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Last indexed {formatRelativeTime(lastIndexedAt)}
          </p>

          <div className="grid grid-cols-4 gap-1.5">
            {QUICK_ACTIONS(props).map((action) => (
              <Button
                key={action.key}
                variant="outline"
                size="sm"
                onClick={action.onClick}
                disabled={!action.onClick}
                className="flex h-auto flex-col gap-1 border-border/60 py-2 text-[11px] font-normal text-muted-foreground hover:text-foreground"
              >
                <action.icon className="h-3.5 w-3.5" />
                {action.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Button
        variant="outline"
        onClick={onNewConversation}
        className="justify-start gap-2 border-border/60 border-dashed text-muted-foreground hover:text-foreground"
      >
        <MessageSquarePlus className="h-4 w-4" />
        New conversation
      </Button>

      <div className="flex min-h-0 flex-1 flex-col gap-4">
        {pinnedPrompts.length > 0 && (
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted-foreground">
              <Pin className="h-3 w-3" /> Pinned prompts
            </p>
            <div className="space-y-1">
              {pinnedPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onSelectPinnedPrompt?.(prompt)}
                  className="w-full truncate rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        <Separator className="bg-border/50" />

        <div className="flex min-h-0 flex-1 flex-col gap-1.5">
          <p className="px-1 text-xs font-medium text-muted-foreground">Recent conversations</p>
          <ScrollArea className="flex-1">
            <div className="space-y-1 pr-2">
              {conversations.length === 0 ? (
                <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                  No conversations yet.
                </p>
              ) : (
                conversations.map((conversation) => (
                  <motion.button
                    key={conversation.id}
                    type="button"
                    whileHover={{ x: 2 }}
                    onClick={() => onSelectConversation?.(conversation.id)}
                    className={cn(
                      "w-full rounded-md px-2 py-2 text-left text-xs transition-colors",
                      conversation.id === activeConversationId
                        ? "bg-primary/10 text-foreground"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                    )}
                  >
                    <p className="truncate font-medium">{conversation.title}</p>
                    <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                      {formatRelativeTime(conversation.updatedAt)}
                    </p>
                  </motion.button>
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
};

export default RepositoryIntelligencePanel;
