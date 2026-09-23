import { z } from "zod";

const environmentSchema = z.object({
  VITE_API_BASE_URL: z.string().trim().default(""),
  VITE_API_PREFIX: z.string().trim().default("/api"),
});

const parsedEnvironment = environmentSchema.safeParse(import.meta.env);

if (!parsedEnvironment.success) {
  throw new Error("Invalid frontend environment configuration.");
}

function normalizePath(value: string): string {
  if (!value) return "";
  return `/${value.replace(/^\/+|\/+$/g, "")}`;
}

function normalizeApiBaseUrl(value: string, prefix: string): string {
  const normalized = value.replace(/\/$/, "");
  if (!prefix || !normalized.endsWith(prefix)) return normalized;
  return normalized.slice(0, -prefix.length).replace(/\/$/, "");
}

const apiPrefix = normalizePath(parsedEnvironment.data.VITE_API_PREFIX);

export const env = {
  // Accept either a backend origin or an origin that already includes the
  // API prefix. Keep system probes such as /health outside that prefix.
  apiBaseUrl: normalizeApiBaseUrl(parsedEnvironment.data.VITE_API_BASE_URL, apiPrefix),
  apiPrefix,
  mode: import.meta.env.MODE,
} as const;
