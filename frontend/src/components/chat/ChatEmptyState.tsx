// src/components/chat/ChatEmptyState.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import {
  BookOpen,
  Bug,
  FileSearch,
  Network,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

export interface ExamplePrompt {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly prompt: string;
}

export interface ChatEmptyStateProps {
  repositoryName: string;
  examplePrompts?: readonly ExamplePrompt[];
  onSelectPrompt: (prompt: string) => void;
  className?: string;
}

const DEFAULT_PROMPTS: ExamplePrompt[] = [
  { icon: BookOpen, title: "Explain this project's architecture", prompt: "Explain this project's architecture." },
  { icon: Network, title: "Find the main entry points", prompt: "Find the main entry points." },
  { icon: Bug, title: "How does authentication work?", prompt: "How does authentication work?" },
  { icon: FileSearch, title: "Trace dependencies for a file", prompt: "Trace dependencies for a file." },
  { icon: FileSearch, title: "Where is this function used?", prompt: "Where is this function used?" },
];

/**
 * The first-run state for a conversation: a quiet AI mark, a short prompt,
 * and a grid of example questions scoped to the active repository.
 */
export const ChatEmptyState: FC<ChatEmptyStateProps> = ({
  repositoryName,
  examplePrompts = DEFAULT_PROMPTS,
  onSelectPrompt,
  className,
}) => {
  return (
    <div className={cn("flex h-full flex-col items-center justify-center px-6 py-8 text-center", className)}>
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/8"
      >
        <Sparkles className="h-4 w-4 text-primary" />
      </motion.div>

      <motion.h2
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.05 }}
        className="text-base font-semibold tracking-tight text-foreground"
      >
        Understand your codebase.
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="mt-1.5 max-w-md text-sm text-muted-foreground"
      >
        Ask about architecture, dependencies, files, symbols, bugs, or implementation details in {repositoryName}.
      </motion.p>

      <div className="mt-6 flex w-full max-w-2xl flex-wrap justify-center gap-2">
        {examplePrompts.map((item, index) => (
          <motion.button
            key={item.title}
            type="button"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: 0.12 + index * 0.04 }}
            onClick={() => onSelectPrompt(item.prompt)}
            className={cn(
              "group flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-3 py-2 text-left transition-colors",
              "hover:border-primary/40 hover:bg-primary/5",
            )}
          >
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-muted/50 text-muted-foreground transition-colors group-hover:text-primary">
              <item.icon className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-foreground">{item.title}</p>
            </div>
          </motion.button>
        ))}
      </div>
    </div>
  );
};

export default ChatEmptyState;
