import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface LoadingProps {
  label?: string;
  className?: string;
}

/**
 * Small, quiet loading indicator used while data is being fetched.
 * Prefer this over ad-hoc spinners so every loading state reads the
 * same way.
 */
export function Loading({ label = "Loading…", className }: LoadingProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center justify-center gap-2 px-4 py-10 text-sm text-muted-foreground",
        className,
      )}
    >
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}