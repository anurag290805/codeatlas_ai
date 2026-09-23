// src/components/chat/SourceChip.tsx

import type { FC } from "react";
import { FileCode2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Citation } from "@/types";

export interface SourceChipProps {
  citation: Citation;
  onClick?: (citation: Citation) => void;
  className?: string;
}

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

/**
 * A compact, clickable pill representing a single grounding citation —
 * the file, line range, and (when available) the symbol it came from.
 * Clicking is expected to open the referenced file in the workspace.
 */
export const SourceChip: FC<SourceChipProps> = ({ citation, onClick, className }) => {
  const lineLabel =
    citation.startLine === citation.endLine
      ? `L${citation.startLine}`
      : `L${citation.startLine}\u2013${citation.endLine}`;

  return (
    <button
      type="button"
      onClick={() => onClick?.(citation)}
      className={cn(
        "group inline-flex max-w-full items-center gap-1.5 rounded-full border border-border/60 bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground transition-colors",
        "hover:border-primary/30 hover:bg-primary/10 hover:text-foreground",
        className,
      )}
      title={citation.filePath}
    >
      <FileCode2 className="h-3 w-3 shrink-0 text-primary/80" />
      <span className="truncate font-medium text-foreground/90">
        {basename(citation.filePath)}
      </span>
      <span className="shrink-0 text-muted-foreground/70">{lineLabel}</span>
    </button>
  );
};

export default SourceChip;
