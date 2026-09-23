// src/app/providers.tsx
import { RouterProvider } from "react-router-dom";
import { QueryProvider, ThemeProvider } from "@/providers";
import { router } from "@/app/router";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { ImportProvider } from "@/components/common/ImportProvider";

/**
 * Composes the application's global providers in the required order:
 * server state (QueryProvider), theme (ThemeProvider), routing
 * (RouterProvider), and the shell-level import dialog (ImportProvider).
 */
export function AppProviders() {
  return (
    <ErrorBoundary>
      <QueryProvider>
        <ThemeProvider>
          <ImportProvider>
            <RouterProvider router={router} />
          </ImportProvider>
        </ThemeProvider>
      </QueryProvider>
    </ErrorBoundary>
  );
}
