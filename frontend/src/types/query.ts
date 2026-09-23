// src/types/query.ts

import type { ID, Timestamp } from "./common";

/** Author role for a message within a conversation. */
export type ChatRole = "user" | "assistant" | "system";

/** A grounded reference to a specific location in the source code backing an AI answer. */
export interface Citation {
  readonly id: ID;
  readonly filePath: string;
  readonly startLine: number;
  readonly endLine: number;
  readonly snippet?: string;
  readonly symbolName?: string;
  readonly codePreview?: string;
  readonly relevanceScore?: number;
}

/** A single message rendered in the chat window. */
export interface ChatMessage {
  readonly id: ID;
  readonly role: ChatRole;
  readonly content: string;
  readonly citations?: readonly Citation[];
  readonly createdAt: Timestamp;
  readonly isStreaming?: boolean;
  readonly status?: "pending" | "streaming" | "complete" | "error";
}

/** Payload accepted by the FastAPI repository query endpoint. */
export interface QueryRequest {
  readonly repository_id: number;
  readonly query: string;
  readonly top_k?: number;
}

/** Citation shape returned by the FastAPI query endpoint. */
export interface QueryCitation {
  readonly file_path: string;
  readonly start_line: number;
  readonly end_line: number;
  readonly symbol_name?: string | null;
  readonly code_preview?: string | null;
  readonly relevance_score?: number | null;
}

/** Complete (non-streamed) response returned by the query endpoint. */
export interface QueryResponse {
  readonly repository_id: number | string;
  readonly query: string;
  readonly answer: string;
  readonly citations: readonly QueryCitation[];
  readonly provider: string;
  readonly model: string;
  readonly latency_seconds: number;
  readonly token_usage?: Readonly<Record<string, number>> | null;
}

export interface AgentTaskRequest {
  readonly repository_id: number;
  readonly task: string;
  readonly top_k?: number;
  readonly acceptance_criteria?: readonly string[];
  readonly image_data_url?: string;
  readonly route?: string;
  readonly mode?: "analyze" | "modify";
}

export interface AgentSkillResult {
  readonly skill: string;
  readonly status: string;
  readonly summary: string;
  readonly output: Readonly<Record<string, unknown>>;
  readonly errors: readonly string[];
  readonly duration_seconds: number;
}

export interface AgentTaskResponse {
  readonly task: string;
  readonly selected_skills: readonly string[];
  readonly status: string;
  readonly final_result: string;
  readonly skill_results: readonly AgentSkillResult[];
  readonly duration_seconds: number;
  readonly errors: readonly string[];
  readonly modification?: {
    readonly status?: string;
    readonly files_changed?: readonly string[];
    readonly operations?: readonly Readonly<Record<string, unknown>>[];
    readonly validation?: Readonly<Record<string, unknown>> | null;
    readonly attempts?: number;
    readonly summary?: string;
    readonly errors?: readonly string[];
    readonly playwright?: Readonly<Record<string, unknown>> | null;
  } | null;
  readonly mode?: "analyze" | "modify";
}

/** A single incremental chunk of a streamed AI answer. */
export interface StreamingChunk {
  readonly delta: string;
  readonly isFinal: boolean;
  readonly citations?: readonly Citation[];
}

/** A persisted message belonging to a stored conversation. */
export interface ConversationMessage extends Omit<ChatMessage, "isStreaming"> {
  readonly conversationId: ID;
  readonly sequence: number;
}

/** A stored, multi-turn conversation scoped to a single repository. */
export interface Conversation {
  readonly id: ID;
  readonly repositoryId: ID;
  readonly title?: string;
  readonly messages: readonly ConversationMessage[];
  readonly createdAt: Timestamp;
  readonly updatedAt: Timestamp;
}
