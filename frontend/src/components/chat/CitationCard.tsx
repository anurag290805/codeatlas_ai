// src/components/chat/CitationCard.tsx

import { useState, type FC } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, FileCode2, Folder, Hash } from "lucide-react";

import { cn } from "@/lib/utils";
import { CodeBlock } from "@/components/chat/CodeBlock";
import type { Citation } from "@/types";
import type { EnrichedCitation } from "@/types/chat-workspace";

export interface CitationCardProps {
  citation: Citation | EnrichedCitation;
  onOpen?: (citation: Citation) => void;
  className?: string;
}

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function dirname(path: string): string | null {
  const parts = path.split("/");
  parts.pop();
  return parts.length > 0 ? parts.join("/") : null;
}

function isEnriched(c: Citation | EnrichedCitation): c is EnrichedCitation {
  return "confidence" in c || "symbol" in c || "language" in c;
}

/**
 * Full detail card for a single grounding citation. Renders whatever
 * metadata is actually present (confidence/symbol/language are optional —
 * see the EnrichedCitation note in types/chat-workspace.ts) and expands
 * in place to show the real snippet, rather than only linking out.
 */
export const CitationCard: FC<CitationCardProps> = ({ citation, onOpen, className }) => {
  const [expanded, setExpanded] = useState(false);
  const enriched = isEnriched(citation) ? citation : undefined;
  const folder = enriched?.folder ?? dirname(citation.filePath);
  const lineLabel =
    citation.startLine === citation.endLine
      ? `Line ${citation.startLine}`
      : `Lines ${citation.startLine}\u2013${citation.endLine}`;

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-border/60 bg-muted/20 transition-colors",
        "hover:border-primary/30",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 px-3.5 py-3 text-left"
      >
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FileCode2 className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="truncate text-sm font-medium text-foreground">{basename(citation.filePath)}</span>
            {enriched?.language && (
              <span className="rounded bg-muted/50 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                {enriched.language}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-muted-foreground">
            {folder && (
              <span className="inline-flex items-center gap-1 truncate">
                <Folder className="h-3 w-3 shrink-0" /> {folder}
              </span>
            )}
            <span>{lineLabel}</span>
            {enriched?.symbol && (
              <span className="inline-flex items-center gap-1">
                <Hash className="h-3 w-3" /> {enriched.symbol}
              </span>
            )}
          </div>
          {typeof enriched?.confidence === "number" && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <div className="h-1 w-16 overflow-hidden rounded-full bg-muted/50">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${Math.round(enriched.confidence * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-muted-foreground">
                {Math.round(enriched.confidence * 100)}% match
              </span>
            </div>
          )}
        </div>
        <ChevronDown
          className={cn(
            "mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.18 }}
            className="border-t border-border/40 px-3.5 py-3"
          >
            {enriched?.preview ? (
              <CodeBlock
                code={enriched.preview}
                language={enriched.language}
                filename={basename(citation.filePath)}
                highlightLines={Array.from(
                  { length: Math.max(1, citation.endLine - citation.startLine + 1) },
                  (_, i) => citation.startLine + i,
                )}
                collapseAfter={40}
              />
            ) : (
              <p className="text-xs text-muted-foreground">
                No preview available for this citation yet \u2014 open the file to view it in context.
              </p>
            )}
            <button
              type="button"
              onClick={() => onOpen?.(citation)}
              className="mt-2 text-xs font-medium text-primary hover:text-primary/80"
            >
              Open in workspace \u2192
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default CitationCard;
