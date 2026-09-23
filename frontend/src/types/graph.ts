import type { Edge, Node } from "@xyflow/react";

import type { ID, Timestamp } from "./common";

/** Node categories emitted by the graph API. */
export type GraphNodeType =
  | "repository"
  | "directory"
  | "file"
  | "class"
  | "function"
  | "method"
  | "module"
  | "interface"
  | "import"
  | "external_module"
  | "external_symbol";

/** Relationship categories emitted by the graph API. */
export type DependencyType = string;

export interface GraphApiNode {
  readonly id: string;
  readonly repository_id: string;
  readonly type: GraphNodeType | string;
  readonly name: string;
  readonly file_path: string | null;
  readonly symbol_type: string | null;
  readonly language: string | null;
  readonly start_line: number | null;
  readonly end_line: number | null;
  readonly parent_node_id: string | null;
  readonly metadata: Readonly<Record<string, unknown>>;
}

export interface GraphApiEdge {
  readonly source: string;
  readonly target: string;
  readonly relationship: string;
  readonly weight: number;
  readonly metadata: Readonly<Record<string, unknown>>;
}

export interface GraphApiResponse {
  readonly repository_id: string;
  readonly nodes: readonly GraphApiNode[];
  readonly edges: readonly GraphApiEdge[];
}

export interface GraphNodeData extends Record<string, unknown> {
  readonly label: string;
  readonly filePath: string;
  readonly nodeType: GraphNodeType | string;
  readonly language: string;
  readonly importsCount: number;
  readonly exportsCount: number;
  readonly dependencies: readonly string[];
  readonly dependents: readonly string[];
  readonly lastModified: string;
  readonly symbolType: string | null;
  readonly startLine: number | null;
  readonly endLine: number | null;
  readonly metadata: Readonly<Record<string, unknown>>;
}

/** React Flow uses one stable renderer for all API node categories. */
export type GraphNode = Node<GraphNodeData, "code">;
export type GraphEdge = Edge<Record<string, unknown>, string>;

export interface GraphStatistics {
  readonly total_nodes: number;
  readonly total_edges: number;
  readonly density: number;
  readonly isolated_node_count: number;
  readonly connected_component_count: number;
  readonly relationship_counts: Readonly<Record<string, number>>;
}

export interface DependencyGraph {
  readonly repositoryId: ID;
  readonly nodes: readonly GraphNode[];
  readonly edges: readonly GraphEdge[];
  readonly statistics?: GraphStatistics;
  readonly generatedAt?: Timestamp;
}
