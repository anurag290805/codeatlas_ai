// src/components/layout/PageContainer.tsx
import type { PropsWithChildren } from "react";
import { cn } from "@/lib/utils";

interface PageContainerProps extends PropsWithChildren {
  className?: string;
  /** Constrains and centers content to a max width. Defaults to true. */
  constrainWidth?: boolean;
  /** Allows the container to fill the available height for content such as workspaces and viewers. Defaults to false. */
  fullHeight?: boolean;
}

/**
 * Reusable page-level wrapper providing consistent spacing, responsive
 * width, and overflow handling across every page. Renders only its
 * `children`; page content is never hardcoded here.
 */
export function PageContainer({
  children,
  className,
  constrainWidth = true,
  fullHeight = false,
}: PageContainerProps) {
  return (
    <div
      className={cn(
        "min-h-0 w-full px-4 py-4 sm:px-6 lg:px-8",
        constrainWidth && "mx-auto max-w-[1440px]",
        fullHeight && "flex h-full flex-col",
        className,
      )}
    >
      {children}
    </div>
  );
}