import type { Citation, ID, RepositoryLanguage } from "@/types";

export type RetrievalStage =
  | "searching"
  | "finding_files"
  | "analyzing_dependencies"
  | "building_context"
  | "generating";

export type QuickActionKey =
  | "explain_repository"
  | "generate_documentation"
  | "review_architecture"
  | "find_bugs"
  | "find_dead_code"
  | "explain_api"
  | "review_security"
  | "generate_tests"
  | "refactor_module"
  | "convert_to_diagram";

export interface QuickAction {
  readonly key: QuickActionKey;
  readonly label: string;
  readonly prompt: string;
}

export interface EnrichedCitation extends Citation {
  readonly folder?: string;
  readonly symbol?: string;
  readonly language?: string;
  readonly confidence?: number;
  readonly preview?: string;
}

export type AnswerSectionKind =
  | "summary"
  | "architecture"
  | "relevant_files"
  | "dependencies"
  | "classes"
  | "functions"
  | "issues"
  | "improvements"
  | "referenced_code"
  | "next_questions";

export interface AnswerSection {
  readonly kind: AnswerSectionKind;
  readonly title: string;
  readonly content?: string;
  readonly citations?: readonly Citation[];
  readonly nextQuestions?: readonly string[];
  readonly defaultCollapsed?: boolean;
}

export interface ConversationListItem {
  readonly id: ID;
  readonly title: string;
  readonly updatedAt: string;
  readonly pinned: boolean;
}

export interface ConversationGroup {
  readonly repositoryId: ID;
  readonly repositoryName: string;
  readonly conversations: readonly ConversationListItem[];
}

export interface RepositoryMapData {
  readonly repository: {
    readonly name: string;
    readonly owner: string;
    readonly defaultBranch: string;
    readonly sizeBytes: number;
    readonly status: string;
  };
  readonly languages?: readonly RepositoryLanguage[];
  readonly commitHash?: string;
  readonly branch?: string;
  readonly health?: { readonly score: number; readonly label: string };
  readonly indexing?: {
    readonly status: string;
    readonly percent?: number;
    readonly filesProcessed?: number;
    readonly filesTotal?: number;
  };
  readonly tokenUsage?: { readonly used: number; readonly budget: number };
  readonly embeddingCount?: number;
  readonly fileCount?: number;
  readonly entryPoints?: readonly { readonly label: string; readonly path: string }[];
  readonly largestModules?: readonly { readonly path: string; readonly fileCount: number; readonly sizeBytes: number }[];
  readonly lastIndexedAt?: string;
  readonly graphPreview?: { readonly nodeCount: number; readonly edgeCount: number; readonly clusterCount: number };
}
