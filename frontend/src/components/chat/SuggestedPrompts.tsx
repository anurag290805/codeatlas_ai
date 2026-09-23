// src/components/chat/SuggestedPrompts.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";

import { cn } from "@/lib/utils";

export interface SuggestedPromptsProps {
  prompts: string[];
  onSelect: (prompt: string) => void;
  className?: string;
}

/**
 * Row of animated follow-up suggestion chips shown after an assistant
 * answer (and reused for example prompts in the empty state).
 */
export const SuggestedPrompts: FC<SuggestedPromptsProps> = ({
  prompts,
  onSelect,
  className,
}) => {
  if (prompts.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {prompts.map((prompt, index) => (
        <motion.button
          key={prompt}
          type="button"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: index * 0.04 }}
          onClick={() => onSelect(prompt)}
          className={cn(
            "group inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-card/40 px-3 py-1.5 text-xs text-foreground/80 backdrop-blur-sm transition-colors",
            "hover:border-primary/30 hover:bg-primary/10 hover:text-foreground",
          )}
        >
          {prompt}
          <ArrowUpRight className="h-3 w-3 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-primary" />
        </motion.button>
      ))}
    </div>
  );
};

export default SuggestedPrompts;
