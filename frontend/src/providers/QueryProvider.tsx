import { QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { queryClient } from "@/app/query-client";

/**
 * Integrates TanStack Query into the application by supplying the
 * shared `queryClient` instance to the component tree. Purely an
 * integration point — contains no application, routing, or theme logic.
 */
function QueryProvider({ children }: PropsWithChildren) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

export default QueryProvider;