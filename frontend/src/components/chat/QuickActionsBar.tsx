// src/components/chat/QuickActionsBar.tsx

import type { FC } from "react";
import { motion } from "framer-motion";
import {
  BookOpen,
  Bug,
  FileWarning,
  Hammer,
  Network,
  ShieldCheck,
  Skull,
  TestTubeDiagonal,
  Workflow,
  Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { QuickAction, QuickActionKey } from "@/types/chat-workspace";

export interface QuickActionsBarProps {
  onSelectAction: (action: QuickAction) => void;
  actions?: readonly QuickAction[];
  className?: string;
}

const ICONS: Record<QuickActionKey, FC<{ className?: string }>> = {
  explain_repository: BookOpen,
  generate_documentation: FileWarning,
  review_architecture: Network,
  find_bugs: Bug,
  find_dead_code: Skull,
  explain_api: Workflow,
  review_security: ShieldCheck,
  generate_tests: TestTubeDiagonal,
  refactor_module: Wrench,
  convert_to_diagram: Hammer,
};

const DEFAULT_ACTIONS: QuickAction[] = [
  { key: "explain_repository", label: "Explain Repository", prompt: "Explain what this repository does and how it's organized." },
  { key: "generate_documentation", label: "Generate Documentation", prompt: "Generate documentation for the main entry point." },
  { key: "review_architecture", label: "Review Architecture", prompt: "Review the overall architecture and call out any concerns." },
  { key: "find_bugs", label: "Find Bugs", prompt: "Look for likely bugs or unhandled edge cases." },
  { key: "find_dead_code", label: "Find Dead Code", prompt: "Find code that appears unused or dead." },
  { key: "explain_api", label: "Explain API", prompt: "Explain the public API surface of this repository." },
  { key: "review_security", label: "Review Security", prompt: "Review this repository for common security issues." },
  { key: "generate_tests", label: "Generate Tests", prompt: "Suggest tests for the least-covered parts of this codebase." },
  { key: "refactor_module", label: "Refactor Module", prompt: "Suggest a refactor for the most complex module." },
  { key: "convert_to_diagram", label: "Convert to Diagram", prompt: "Show me a diagram of how the main modules relate to each other." },
];

/**
 * Horizontally-scrolling row of one-click quick-action prompts, sitting
 * directly above the composer. Selecting one hands the resolved prompt
 * text back to the caller (typically `onComposerChange` + `onSubmit`, or
 * just `onComposerChange` if you want the person to confirm before send).
 */
export const QuickActionsBar: FC<QuickActionsBarProps> = ({ onSelectAction, actions = DEFAULT_ACTIONS, className }) => {
  return (
    <div className={cn("flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden", className)}>
      {actions.map((action, index) => {
        const Icon = ICONS[action.key];
        return (
          <motion.button
            key={action.key}
            type="button"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15, delay: index * 0.02 }}
            onClick={() => onSelectAction(action)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border/60 bg-card/40 px-3 py-1.5 text-xs text-foreground/80 backdrop-blur-sm transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-foreground"
          >
            <Icon className="h-3.5 w-3.5 text-primary" />
            {action.label}
          </motion.button>
        );
      })}
    </div>
  );
};

export default QuickActionsBar;
