// src/components/chat/AnswerCard.tsx

import { useMemo, useState, type FC, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Boxes,
  ChevronDown,
  FileCode2,
  FolderTree,
  Lightbulb,
  ListTree,
  MessageCircleQuestion,
  Network,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { CitationCard } from "@/components/chat/CitationCard";
import { CodeBlock } from "@/components/chat/CodeBlock";
import type { Citation } from "@/types";
import type { AnswerSection, AnswerSectionKind } from "@/types/chat-workspace";

export interface AnswerCardProps {
  content: string;
  citations?: readonly Citation[];
  /**
   * Pre-structured sections, if your backend already segments the answer
   * (ideal — see reconciliation note below). When omitted, this falls back
   * to splitting `content` on markdown headings that match known section
   * names, which is a real parse of what the model actually wrote, not a
   * canned layout.
   */
  sections?: readonly AnswerSection[];
  onCitationOpen?: (citation: Citation) => void;
  onFollowUpSelect?: (prompt: string) => void;
  className?: string;
}

const SECTION_META: Record<AnswerSectionKind, { title: string; icon: FC<{ className?: string }> }> = {
  summary: { title: "Repository Summary", icon: FileCode2 },
  architecture: { title: "Architecture", icon: Network },
  relevant_files: { title: "Relevant Files", icon: FolderTree },
  dependencies: { title: "Dependencies", icon: Workflow },
  classes: { title: "Classes", icon: Boxes },
  functions: { title: "Functions", icon: ListTree },
  issues: { title: "Potential Issues", icon: AlertTriangle },
  improvements: { title: "Suggested Improvements", icon: Lightbulb },
  referenced_code: { title: "Referenced Code", icon: FileCode2 },
  next_questions: { title: "Next Questions", icon: MessageCircleQuestion },
};

const HEADING_TO_KIND: Array<[RegExp, AnswerSectionKind]> = [
  [/^(repository )?summary$/i, "summary"],
  [/^architecture( overview)?$/i, "architecture"],
  [/^relevant files$/i, "relevant_files"],
  [/^dependencies$/i, "dependencies"],
  [/^classes$/i, "classes"],
  [/^functions$/i, "functions"],
  [/^(potential )?issues$/i, "issues"],
  [/^suggested improvements$/i, "improvements"],
  [/^referenced code$/i, "referenced_code"],
  [/^next questions$/i, "next_questions"],
];

/** Splits raw markdown into sections on `##`/`###` headings that match known section names. */
function deriveSections(content: string): AnswerSection[] {
  const lines = content.split("\n");
  const headingRe = /^#{2,3}\s+(.+)$/;

  const chunks: { title: string | null; body: string[] }[] = [{ title: null, body: [] }];
  for (const line of lines) {
    const match = line.match(headingRe);
    if (match) {
      chunks.push({ title: match[1].trim(), body: [] });
    } else {
      chunks[chunks.length - 1].body.push(line);
    }
  }

  const sections: AnswerSection[] = [];
  for (const chunk of chunks) {
    const body = chunk.body.join("\n").trim();
    if (!body) continue;
    const kind =
      (chunk.title && HEADING_TO_KIND.find(([re]) => re.test(chunk.title!))?.[1]) ?? (chunk.title ? null : "summary");
    if (kind) {
      sections.push({ kind, title: SECTION_META[kind].title, content: body, defaultCollapsed: false });
    } else if (chunk.title) {
      // Unrecognized heading — keep it visible under summary rather than dropping content.
      sections.push({
        kind: "summary",
        title: chunk.title,
        content: body,
        defaultCollapsed: false,
      });
    }
  }
  return sections.length > 0 ? sections : [{ kind: "summary", title: "Repository Summary", content }];
}

/** Minimal, dependency-free markdown: paragraphs, bullet/numbered lists, bold, inline code, and fenced code blocks (rendered as CodeBlock). */
function renderMarkdownLite(text: string): ReactNode[] {
  const blocks = text.split(/```(\w*)\n([\s\S]*?)```/g);
  const nodes: ReactNode[] = [];

  for (let i = 0; i < blocks.length; i += 3) {
    const prose = blocks[i];
    const lang = blocks[i + 1];
    const code = blocks[i + 2];

    if (prose?.trim()) {
      const paragraphs = prose.trim().split(/\n{2,}/);
      paragraphs.forEach((para, pIndex) => {
        const lines = para.split("\n").filter(Boolean);
        const isList = lines.every((l) => /^\s*[-*]\s+/.test(l) || /^\s*\d+\.\s+/.test(l));
        if (isList) {
          nodes.push(
            <ul key={`${i}-${pIndex}`} className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-foreground/85">
              {lines.map((line, lIndex) => (
                <li key={lIndex}>{inlineFormat(line.replace(/^\s*[-*]\s+|\s*\d+\.\s+/, ""))}</li>
              ))}
            </ul>,
          );
        } else {
          nodes.push(
            <p key={`${i}-${pIndex}`} className="text-sm leading-relaxed text-foreground/85">
              {inlineFormat(para)}
            </p>,
          );
        }
      });
    }

    if (code !== undefined) {
      nodes.push(<CodeBlock key={`code-${i}`} code={code} language={lang || undefined} />);
    }
  }
  return nodes;
}

function inlineFormat(line: string): ReactNode {
  const parts = line.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={index} className="rounded bg-muted/50 px-1 py-0.5 font-mono text-[0.85em] text-primary">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

const SectionCard: FC<{ section: AnswerSection; onCitationOpen?: (c: Citation) => void; onFollowUpSelect?: (p: string) => void }> = ({
  section,
  onCitationOpen,
  onFollowUpSelect,
}) => {
  const [open, setOpen] = useState(!section.defaultCollapsed);
  const meta = SECTION_META[section.kind];
  const Icon = meta.icon;

  return (
    <div className="overflow-hidden rounded-xl border border-border/50 bg-background/30">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-muted/20"
      >
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
        <span className="flex-1 text-xs font-semibold uppercase tracking-wide text-foreground/80">
          {section.title}
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            <div className="space-y-2.5 border-t border-border/40 px-3.5 py-3">
              {section.content && renderMarkdownLite(section.content)}

              {section.kind === "next_questions" && section.nextQuestions && section.nextQuestions.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {section.nextQuestions.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => onFollowUpSelect?.(q)}
                      className="rounded-full border border-border/60 bg-card/40 px-3 py-1.5 text-xs text-foreground/80 hover:border-primary/30 hover:bg-primary/10"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {section.citations && section.citations.length > 0 && (
                <div className="space-y-2">
                  {section.citations.map((citation, index) => (
                    <CitationCard key={`${citation.filePath}-${index}`} citation={citation} onOpen={onCitationOpen} />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

/**
 * Structured answer surface. Prefers a `sections` prop from the backend;
 * otherwise derives sections from real markdown headings in `content`
 * (see `deriveSections`) so answers stop being one long blob even before
 * routes_query.py returns structured output. Global `citations` (the
 * existing per-message citation list) are attached to a synthesized
 * "Referenced Code" section when no section already carries citations.
 */
export const AnswerCard: FC<AnswerCardProps> = ({
  content,
  citations = [],
  sections,
  onCitationOpen,
  onFollowUpSelect,
  className,
}) => {
  const resolvedSections = useMemo(() => {
    const base = sections && sections.length > 0 ? [...sections] : deriveSections(content);
    const anySectionHasCitations = base.some((s) => s.citations && s.citations.length > 0);
    if (!anySectionHasCitations && citations.length > 0) {
      base.push({ kind: "referenced_code", title: SECTION_META.referenced_code.title, citations });
    }
    return base;
  }, [sections, content, citations]);

  if (resolvedSections.length === 1 && resolvedSections[0].kind === "summary" && resolvedSections[0].content === content) {
    // No real structure detected and it's short — skip the section chrome for a plain, quick answer.
    const isShort = content.length < 280 && !content.includes("```");
    if (isShort) {
      return <div className={cn("space-y-2", className)}>{renderMarkdownLite(content)}</div>;
    }
  }

  return (
    <div className={cn("space-y-2.5", className)}>
      {resolvedSections.map((section, index) => (
        <SectionCard
          key={`${section.kind}-${index}`}
          section={section}
          onCitationOpen={onCitationOpen}
          onFollowUpSelect={onFollowUpSelect}
        />
      ))}
    </div>
  );
};

export default AnswerCard;
