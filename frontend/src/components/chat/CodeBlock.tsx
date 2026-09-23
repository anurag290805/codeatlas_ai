// src/components/chat/CodeBlock.tsx

import { useMemo, useRef, useState, type FC, type KeyboardEvent } from "react";
import { motion } from "framer-motion";
import { Check, ChevronDown, ChevronUp, Copy, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface CodeBlockProps {
  code: string;
  language?: string;
  filename?: string;
  /** 1-indexed line numbers to visually highlight, e.g. the exact lines a citation points to. */
  highlightLines?: readonly number[];
  /** Collapse automatically past this many lines (still expandable). Default 18, matches prior behavior. */
  collapseAfter?: number;
  className?: string;
}

/**
 * Note on syntax highlighting: this is monospace + line numbers only, same
 * as before — no tokenizer wired in yet. Wiring in Shiki is still the clean
 * follow-up flagged in the original delivery; didn't want to sneak in a new
 * dependency assumption as part of this pass.
 */
export const CodeBlock: FC<CodeBlockProps> = ({
  code,
  language,
  filename,
  highlightLines = [],
  collapseAfter = 18,
  className,
}) => {
  const lines = useMemo(() => code.replace(/\n$/, "").split("\n"), [code]);
  const [expanded, setExpanded] = useState(lines.length <= collapseAfter);
  const [copied, setCopied] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [jumpTarget, setJumpTarget] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const highlightSet = useMemo(() => new Set(highlightLines), [highlightLines]);

  const matchLines = useMemo(() => {
    if (!query.trim()) return new Set<number>();
    const needle = query.toLowerCase();
    const matched = new Set<number>();
    lines.forEach((line, index) => {
      if (line.toLowerCase().includes(needle)) matched.add(index + 1);
    });
    return matched;
  }, [query, lines]);

  const visibleLines = expanded ? lines : lines.slice(0, collapseAfter);
  const hiddenCount = lines.length - visibleLines.length;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const scrollToLine = (lineNumber: number) => {
    setExpanded(true);
    setJumpTarget(lineNumber);
    requestAnimationFrame(() => {
      const el = containerRef.current?.querySelector<HTMLElement>(`[data-line="${lineNumber}"]`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => setJumpTarget(null), 1200);
    });
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && matchLines.size > 0) {
      scrollToLine([...matchLines][0]);
    }
    if (event.key === "Escape") {
      setSearchOpen(false);
      setQuery("");
    }
  };

  return (
    <div className={cn("overflow-hidden rounded-xl border border-border/60 bg-[#0a0d15]", className)}>
      {/* Sticky toolbar */}
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border/50 bg-[#0e121b]/95 px-3 py-1.5 backdrop-blur-sm">
        {filename && <span className="truncate text-xs font-medium text-foreground/80">{filename}</span>}
        {language && (
          <span className="shrink-0 rounded-md bg-muted/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {language}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={() => setSearchOpen((v) => !v)}
            aria-label="Search in code"
          >
            <Search className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={handleCopy}
            aria-label="Copy code"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </span>
      </div>

      {searchOpen && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="flex items-center gap-2 border-b border-border/40 bg-[#0f1015]/80 px-3 py-1.5"
        >
          <Search className="h-3 w-3 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search this file\u2026"
            className="min-w-0 flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {query ? `${matchLines.size} match${matchLines.size === 1 ? "" : "es"}` : ""}
          </span>
          <button
            type="button"
            onClick={() => {
              setSearchOpen(false);
              setQuery("");
            }}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </motion.div>
      )}

      {/* Code */}
      <div ref={containerRef} className="max-h-[28rem] overflow-auto">
        <table className="w-full border-collapse font-mono text-[12.5px] leading-relaxed">
          <tbody>
            {visibleLines.map((line, index) => {
              const lineNumber = index + 1;
              const isHighlighted = highlightSet.has(lineNumber);
              const isMatch = matchLines.has(lineNumber);
              const isJumpTarget = jumpTarget === lineNumber;
              return (
                <tr
                  key={lineNumber}
                  data-line={lineNumber}
                  className={cn(
                    "transition-colors",
                    isHighlighted && "bg-primary/10",
                    isMatch && "bg-warning/10",
                    isJumpTarget && "bg-info/20",
                  )}
                >
                  <td className="select-none whitespace-nowrap px-3 py-0 text-right text-muted-foreground/50">
                    {lineNumber}
                  </td>
                  <td
                    className={cn(
                      "w-full whitespace-pre px-3 py-0 text-foreground/90",
                      isHighlighted && "border-l-2 border-primary",
                    )}
                  >
                    {line.length > 0 ? line : "\u00A0"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {hiddenCount > 0 && !expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex w-full items-center justify-center gap-1 border-t border-border/40 py-1.5 text-[11px] text-muted-foreground hover:bg-muted/20 hover:text-foreground"
        >
          <ChevronDown className="h-3 w-3" /> Show {hiddenCount} more lines
        </button>
      )}
      {expanded && lines.length > collapseAfter && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="flex w-full items-center justify-center gap-1 border-t border-border/40 py-1.5 text-[11px] text-muted-foreground hover:bg-muted/20 hover:text-foreground"
        >
          <ChevronUp className="h-3 w-3" /> Collapse
        </button>
      )}
    </div>
  );
};

export default CodeBlock;
