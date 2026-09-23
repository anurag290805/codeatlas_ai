// src/components/chat/AIComposer.tsx

import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FC,
  type KeyboardEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowUp,
  AtSign,
  Braces,
  Circle,
  File as FileIcon,
  Folder,
  GitBranch,
  GitCommitHorizontal,
  Loader2,
  Slash,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface SlashCommand {
  readonly command: string;
  readonly description: string;
}

export type MentionKind = "file" | "folder" | "function" | "class" | "commit" | "branch";

export interface MentionSuggestion {
  readonly id: string;
  readonly kind: MentionKind;
  readonly label: string;
  readonly detail?: string;
}

export interface AIComposerProps {
  onSubmit: (message: string) => void;
  isLoading?: boolean;
  disabled?: boolean;

  placeholder?: string;
  slashCommands?: SlashCommand[];
  mentionSuggestions?: MentionSuggestion[];
  onMentionQueryChange?: (query: string) => void;
  branchName?: string;
  modelName?: string;
  isIndexed?: boolean;
  contextWindow?: number;
  className?: string;
}

const DEFAULT_SLASH_COMMANDS: SlashCommand[] = [
  { command: "explain", description: "Explain how this works" },
  { command: "review", description: "Review for issues" },
  { command: "refactor", description: "Suggest a refactor" },
  { command: "find", description: "Find something in the repo" },
  { command: "bug", description: "Investigate a bug" },
  { command: "tests", description: "Generate tests" },
  { command: "document", description: "Write documentation" },
  { command: "search", description: "Search the codebase" },
];

const MENTION_ICONS: Record<MentionKind, FC<{ className?: string }>> = {
  file: FileIcon,
  folder: Folder,
  function: Braces,
  class: Braces,
  commit: GitCommitHorizontal,
  branch: GitBranch,
};

type MenuState =
  | { kind: "none" }
  | { kind: "slash"; triggerIndex: number; query: string }
  | { kind: "mention"; triggerIndex: number; query: string };

function detectMenu(text: string, caret: number): MenuState {
  const upToCaret = text.slice(0, caret);

  const slashMatch = upToCaret.match(/(?:^|\s)\/(\w*)$/);
  if (slashMatch) {
    return {
      kind: "slash",
      triggerIndex: caret - slashMatch[1].length - 1,
      query: slashMatch[1],
    };
  }

  const mentionMatch = upToCaret.match(/(?:^|\s)@([\w./-]*)$/);
  if (mentionMatch) {
    return {
      kind: "mention",
      triggerIndex: caret - mentionMatch[1].length - 1,
      query: mentionMatch[1],
    };
  }

  return { kind: "none" };
}

/**
 * The chat input as an AI command center: a growing textarea with slash
 * commands, @-mentions, a live repository-context strip, and keyboard
 * navigation through both suggestion menus. All state (text, submission,
 * suggestion lists) is controlled through props.
 */
export const AIComposer: FC<AIComposerProps> = ({
  onSubmit,
  isLoading = false,
  disabled = false,
  placeholder = "Ask anything about this repository\u2026",
  slashCommands = DEFAULT_SLASH_COMMANDS,
  mentionSuggestions = [],
  onMentionQueryChange,
  branchName,
  modelName,
  isIndexed,
  contextWindow,
  className,
}) => {
  const [value, setValue] = useState("");
  const [menu, setMenu] = useState<MenuState>({ kind: "none" });
  const [activeIndex, setActiveIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const filteredCommands = useMemo(() => {
    if (menu.kind !== "slash") return [];
    return slashCommands.filter((item) =>
      item.command.toLowerCase().startsWith(menu.query.toLowerCase()),
    );
  }, [menu, slashCommands]);

  const menuItems: Array<{ id: string; label: string; sublabel?: string; icon: FC<{ className?: string }> }> =
    menu.kind === "slash"
      ? filteredCommands.map((item) => ({
          id: item.command,
          label: `/${item.command}`,
          sublabel: item.description,
          icon: Slash,
        }))
      : menu.kind === "mention"
        ? mentionSuggestions.map((item) => ({
            id: item.id,
            label: item.label,
            sublabel: item.detail,
            icon: MENTION_ICONS[item.kind],
          }))
        : [];

  const closeMenu = useCallback(() => {
    setMenu({ kind: "none" });
    setActiveIndex(0);
  }, []);

  const applySelection = useCallback(
    (label: string) => {
      if (menu.kind === "none") return;
      const caret = textareaRef.current?.selectionStart ?? value.length;
      const insertion = menu.kind === "slash" ? `${label} ` : `${label} `;
      const next = value.slice(0, menu.triggerIndex) + insertion + value.slice(caret);
      setValue(next);
      closeMenu();
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [menu, value, setValue, closeMenu],
  );

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = event.target;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
    const nextValue = event.target.value;
    setValue(nextValue);
    const nextMenu = detectMenu(nextValue, event.target.selectionStart ?? nextValue.length);
    setMenu(nextMenu);
    setActiveIndex(0);
    if (nextMenu.kind === "mention") {
      onMentionQueryChange?.(nextMenu.query);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (menu.kind !== "none" && menuItems.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => (index + 1) % menuItems.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => (index - 1 + menuItems.length) % menuItems.length);
        return;
      }
      if (event.key === "Tab" || event.key === "Enter") {
        event.preventDefault();
        applySelection(menuItems[activeIndex].label);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu();
        return;
      }
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (value.trim() && !isLoading && !disabled) {
        onSubmit(value.trim());
        setValue("");
      }
    }
  };
  return (
    <div className={cn("relative", className)}>
      <AnimatePresence>
        {menu.kind !== "none" && menuItems.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.12 }}
            className="absolute bottom-full left-0 z-20 mb-2 w-full max-w-sm overflow-hidden rounded-xl border border-border/60 bg-popover/95 shadow-xl backdrop-blur-md"
            role="listbox"
          >
            <div className="max-h-64 overflow-y-auto p-1">
              {menuItems.map((item, index) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="option"
                    aria-selected={index === activeIndex}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => applySelection(item.label)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                      index === activeIndex
                        ? "bg-primary/10 text-foreground"
                        : "text-muted-foreground hover:bg-muted/60",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
                    {item.sublabel && (
                      <span className="shrink-0 truncate text-xs text-muted-foreground">
                        {item.sublabel}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div
        className={cn(
          "rounded-xl border border-border/70 bg-card transition-colors",
          "focus-within:border-primary/50",
        )}
      >
        <div className="flex items-center gap-1.5 border-b border-border/40 px-3 py-1.5">
          {branchName && (
            <Badge variant="outline" className="gap-1 border-border/60 font-normal text-muted-foreground">
              <GitBranch className="h-3 w-3" />
              {branchName}
            </Badge>
          )}
          {typeof isIndexed === "boolean" && (
            <Badge
              variant="outline"
              className={cn(
                "gap-1 border-border/60 font-normal",
                isIndexed ? "text-success" : "text-muted-foreground",
              )}
            >
              <Circle className={cn("h-2 w-2 fill-current", isIndexed ? "text-success" : "text-muted-foreground")} />
              {isIndexed ? "Indexed" : "Indexing"}
            </Badge>
          )}
          {modelName && (
            <Badge variant="outline" className="gap-1 border-border/60 font-normal text-muted-foreground">
              <Sparkles className="h-3 w-3" />
              {modelName}
            </Badge>
          )}
          {typeof contextWindow === "number" && (
            <span className="ml-auto text-[11px] text-muted-foreground">
              {contextWindow.toLocaleString()} token context
            </span>
          )}
        </div>

        <div className="flex items-end gap-2 px-3 py-2.5">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            style={{ height: "auto" }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            className={cn(
              "max-h-48 min-h-[2.25rem] w-full resize-none bg-transparent text-sm leading-relaxed text-foreground",
              "placeholder:text-muted-foreground focus:outline-none",
            )}
          />
          <Button
            type="button"
            size="icon"
            disabled={!value.trim() || isLoading || disabled}
            onClick={() => {
              if (!value.trim()) return;
              onSubmit(value.trim());
              setValue("");
            }}
            className="h-8 w-8 shrink-0 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
            aria-label="Send message"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowUp className="h-4 w-4" />
            )}
          </Button>
        </div>

        <div className="flex items-center gap-3 border-t border-border/40 px-3.5 py-1.5 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Slash className="h-3 w-3" /> commands
          </span>
          <span className="inline-flex items-center gap-1">
            <AtSign className="h-3 w-3" /> mention files, symbols, commits
          </span>
          <span className="ml-auto">Enter to send &middot; Shift+Enter for a new line</span>
        </div>
      </div>
    </div>
  );
};

export default AIComposer;
