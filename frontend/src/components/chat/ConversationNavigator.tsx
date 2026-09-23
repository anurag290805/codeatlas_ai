// src/components/chat/ConversationNavigator.tsx

import { useMemo, useState, type FC, type KeyboardEvent } from "react";
import { motion } from "framer-motion";
import { Check, MessageSquarePlus, Pin, PinOff, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ID } from "@/types";
import type { ConversationGroup, ConversationListItem } from "@/types/chat-workspace";

export interface ConversationNavigatorProps {
  groups: readonly ConversationGroup[];
  activeConversationId?: ID;
  onSelectConversation?: (id: ID) => void;
  onNewConversation?: () => void;
  onPinConversation?: (id: ID, pinned: boolean) => void;
  onRenameConversation?: (id: ID, title: string) => void;
  className?: string;
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

const ConversationRow: FC<{
  conversation: ConversationListItem;
  active: boolean;
  onSelect: () => void;
  onPin?: (pinned: boolean) => void;
  onRename?: (title: string) => void;
}> = ({ conversation, active, onSelect, onPin, onRename }) => {
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(conversation.title);

  const commitRename = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== conversation.title) onRename?.(trimmed);
    setRenaming(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") commitRename();
    if (event.key === "Escape") {
      setDraft(conversation.title);
      setRenaming(false);
    }
  };

  if (renaming) {
    return (
      <div className="flex items-center gap-1 rounded-md bg-muted/40 px-2 py-1.5">
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground focus:outline-none"
        />
        <button type="button" onClick={commitRename} className="text-success hover:text-success/80">
          <Check className="h-3 w-3" />
        </button>
        <button type="button" onClick={() => setRenaming(false)} className="text-muted-foreground hover:text-foreground">
          <X className="h-3 w-3" />
        </button>
      </div>
    );
  }

  return (
    <motion.div
      whileHover={{ x: 2 }}
      className={cn(
        "group flex items-center gap-1 rounded-md px-2 py-1.5 text-xs transition-colors",
        active ? "bg-primary/10 text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
      )}
    >
      <button type="button" onClick={onSelect} onDoubleClick={() => setRenaming(true)} className="min-w-0 flex-1 text-left">
        <p className="truncate font-medium">{conversation.title}</p>
        <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{formatRelativeTime(conversation.updatedAt)}</p>
      </button>
      <button
        type="button"
        onClick={() => onPin?.(!conversation.pinned)}
        className={cn(
          "shrink-0 opacity-0 transition-opacity group-hover:opacity-100",
          conversation.pinned && "text-primary opacity-100",
        )}
        aria-label={conversation.pinned ? "Unpin conversation" : "Pin conversation"}
      >
        {conversation.pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
      </button>
    </motion.div>
  );
};

/**
 * Left-rail conversation history: grouped by repository, with search,
 * pin, and inline rename (double-click a title, or the row stays a plain
 * button for single-click select). Pinned conversations float to the top
 * of each group.
 */
export const ConversationNavigator: FC<ConversationNavigatorProps> = ({
  groups,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onPinConversation,
  onRenameConversation,
  className,
}) => {
  const [query, setQuery] = useState("");

  const filteredGroups = useMemo(() => {
    if (!query.trim()) return groups;
    const needle = query.toLowerCase();
    return groups
      .map((group) => ({
        ...group,
        conversations: group.conversations.filter((c) => c.title.toLowerCase().includes(needle)),
      }))
      .filter((group) => group.conversations.length > 0);
  }, [groups, query]);

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-2", className)}>
      <Button
        variant="outline"
        onClick={onNewConversation}
        className="justify-start gap-2 border-border/60 border-dashed text-muted-foreground hover:text-foreground"
      >
        <MessageSquarePlus className="h-4 w-4" />
        New conversation
      </Button>

      <div className="flex items-center gap-1.5 rounded-md border border-border/50 bg-muted/20 px-2 py-1.5">
        <Search className="h-3 w-3 shrink-0 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations\u2026"
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        {query && (
          <button type="button" onClick={() => setQuery("")} className="text-muted-foreground hover:text-foreground">
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 pr-2">
          {filteredGroups.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">No conversations found.</p>
          ) : (
            filteredGroups.map((group) => {
              const sorted = [...group.conversations].sort((a, b) => Number(b.pinned) - Number(a.pinned));
              return (
                <div key={group.repositoryId} className="space-y-1">
                  <p className="truncate px-1 text-[11px] font-medium text-muted-foreground">{group.repositoryName}</p>
                  <div className="space-y-0.5">
                    {sorted.map((conversation) => (
                      <ConversationRow
                        key={conversation.id}
                        conversation={conversation}
                        active={conversation.id === activeConversationId}
                        onSelect={() => onSelectConversation?.(conversation.id)}
                        onPin={(pinned) => onPinConversation?.(conversation.id, pinned)}
                        onRename={(title) => onRenameConversation?.(conversation.id, title)}
                      />
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
};

export default ConversationNavigator;
