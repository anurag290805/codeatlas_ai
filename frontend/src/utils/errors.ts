import axios from "axios";

export class ApiRequestError extends Error {
  readonly status?: number;
  readonly details?: unknown;

  constructor(message: string, status?: number, details?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.details = details;
  }
}

export function normalizeApiError(error: unknown): ApiRequestError {
  if (error instanceof ApiRequestError) return error;
  if (!axios.isAxiosError(error)) {
    return new ApiRequestError(error instanceof Error ? error.message : "Unexpected request failure.");
  }

  const responseData = error.response?.data as { detail?: unknown; message?: unknown } | undefined;
  const detail = responseData?.detail ?? responseData?.message;
  const message = typeof detail === "string" ? detail : error.message || "The backend request failed.";
  return new ApiRequestError(message, error.response?.status, detail);
}
