// src/pages/NotFound.tsx
import { Compass, FileQuestion } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

/**
 * Rendered when no route matches the current path. Provides clear ways
 * back into the application, aligned with the CodeAtlas visual language
 * (quiet surface, primary action, secondary escape hatch).
 */
export function NotFound() {
  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col items-center justify-center gap-5 px-6 text-center">
      <span
        className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border/60 bg-muted/40 text-muted-foreground"
        aria-hidden="true"
      >
        <Compass className="h-6 w-6" strokeWidth={1.75} />
      </span>
      <div className="space-y-1.5">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Page not found
        </p>
        <h1 className="text-6xl font-semibold tracking-tight text-foreground">404</h1>
        <p className="mx-auto max-w-sm text-sm text-muted-foreground">
          We couldn't find the page you're looking for. It may have been moved or no longer
          exists.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button nativeButton={false} render={<Link to="/" />} className="gap-1.5">
          <Compass className="h-4 w-4" aria-hidden="true" />
          Return to Dashboard
        </Button>
        <Button nativeButton={false} variant="outline" render={<Link to="/repositories" />} className="gap-1.5">
          <FileQuestion className="h-4 w-4" aria-hidden="true" />
          Browse Repositories
        </Button>
      </div>
    </div>
  );
}

export default NotFound;