import { QueryClient } from "@tanstack/react-query";

/**
 * Singleton QueryClient for the CodeAtlas AI application.
 *
 * Centralizes server-state defaults for communicating with the FastAPI
 * backend (repositories, query, graph, and health endpoints). Import
 * this instance wherever a QueryClient is required; do not instantiate
 * additional clients elsewhere in the app.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      refetchOnMount: false,
    },
    mutations: {
      retry: 0,
    },
  },
});