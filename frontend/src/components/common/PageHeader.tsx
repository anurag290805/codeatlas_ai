import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type PageHeaderAccent = "primary" | "neutral";

/** Monochrome chip — slate tones that don't compete with the page content. */
const ACCENT_CHIP_STYLES: Record<PageHeaderAccent, string> = {
  primary: "border-border/80 bg-muted/50 text-muted-foreground shadow-sm",
  neutral: "border-border/80 bg-muted/50 text-muted-foreground shadow-sm",
};

export interface PageHeaderProps {
  title: ReactNode;
  /** One-line supporting copy beneath the title. */
  description?: ReactNode;
  /** Optional small kicker above the title, e.g. "Repository intelligence". */
  eyebrow?: ReactNode;
  /** Optional leading icon rendered in a subtle square chip. */
  icon?: ReactNode;
  /** Accent tone for the leading icon chip. */
  accent?: PageHeaderAccent;
  /** Right-aligned primary actions (buttons, repository selectors, etc.). */
  actions?: ReactNode;
  className?: string;
}

/**
 * The single page-title treatment across CodeAtlas. Replaces the previous
 * per-page mix of gradient banners and ad-hoc headings with one flat,
 * structured toolbar header. Deliberately free of gradients and large
 * background panels — the emphasis is on a clear reading order:
 * eyebrow → title → description, with actions aligned to the end.
 */
export function PageHeader({
  title,
  description,
  eyebrow,
  icon,
  accent = "primary",
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-end sm:justify-between",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-3.5">
        {icon && (
          <div
            className={cn(
              "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
              ACCENT_CHIP_STYLES[accent],
            )}
          >
            {icon}
          </div>
        )}
        <div className="min-w-0 space-y-0.5">
          {eyebrow && (
            <p className="t-label flex items-center gap-1.5 normal-case">
              <span className="h-1 w-1 rounded-full bg-current" aria-hidden="true" />
              {eyebrow}
            </p>
          )}
          <h1 className="text-[1.5rem] font-semibold tracking-[-0.035em] text-foreground">
            {title}
          </h1>
          {description && (
            <p className="max-w-2xl text-sm text-muted-foreground">
              {description}
            </p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      )}
    </header>
  );
}
