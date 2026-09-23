// src/types/common.ts

/** Opaque identifier for domain entities. Backend IDs are treated as strings. */
export type ID = string;

/** ISO-8601 timestamp string as returned by the backend. */
export type Timestamp = string;

/** A value that may be `null`, as commonly returned by the backend for optional fields. */
export type Nullable<T> = T | null;

/** A value that may be `undefined`, typically used for client-side optional state. */
export type Optional<T> = T | undefined;

/** Sort direction used by list and table views. */
export type SortDirection = "asc" | "desc";

/** Standard pagination metadata returned alongside paginated list responses. */
export interface Pagination {
  readonly page: number;
  readonly pageSize: number;
  readonly totalItems: number;
  readonly totalPages: number;
}

/** Normalized error shape surfaced by the API client on failed requests. */
export interface ApiError {
  readonly message: string;
  readonly code?: string;
  readonly statusCode?: number;
  readonly details?: Readonly<Record<string, unknown>>;
}

/** Generic envelope for backend responses that wrap a payload. */
export interface ApiResponse<T> {
  readonly data: T;
  readonly success: boolean;
  readonly error?: ApiError;
}

/** Discrete lifecycle states for asynchronous operations driven outside of TanStack Query. */
export type LoadingState = "idle" | "loading" | "success" | "error";

/** Supported application theme modes. */
export type ThemeMode = "light" | "dark" | "system";