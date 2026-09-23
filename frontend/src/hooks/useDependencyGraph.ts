import { useCallback, useEffect, useMemo } from "react";
import { useEdgesState, useNodesState } from "@xyflow/react";
import { useGraph } from "@/hooks/useGraph";
import type { GraphEdge, GraphNode, GraphNodeData } from "@/types/graph";

function numericMetadata(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function buildGraphNodes(
  graph: NonNullable<ReturnType<typeof useGraph>["data"]>,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const labels = new Map(graph.nodes.map((node) => [node.id, node.name]));

  for (const edge of graph.edges) {
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge.target]);
    incoming.set(edge.target, [...(incoming.get(edge.target) ?? []), edge.source]);
  }

  const nodes = graph.nodes.map((node, index): GraphNode => {
    const nodeType = node.type;
    const data: GraphNodeData = {
      label: node.name,
      filePath: node.file_path ?? "",
      nodeType,
      language: node.language ?? "unknown",
      importsCount: numericMetadata(node.metadata.imports_count),
      exportsCount: numericMetadata(node.metadata.exports_count),
      dependencies: (outgoing.get(node.id) ?? []).map((id) => labels.get(id) ?? id),
      dependents: (incoming.get(node.id) ?? []).map((id) => labels.get(id) ?? id),
      lastModified: typeof node.metadata.last_modified === "string" ? node.metadata.last_modified : "",
      symbolType: node.symbol_type,
      startLine: node.start_line,
      endLine: node.end_line,
      metadata: node.metadata,
    };

    return {
      id: node.id,
      type: "code",
      data,
      position: { x: (index % 6) * 240, y: Math.floor(index / 6) * 140 },
    };
  });

  const edges = graph.edges.map(
    (edge, index): GraphEdge => ({
      id: `${edge.source}-${edge.relationship}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      type: "smoothstep",
      label: edge.relationship,
      data: {
        relationship: edge.relationship,
        weight: edge.weight,
        ...edge.metadata,
      },
      animated: false,
      style: {
        strokeWidth: Math.max(1, Math.min(4, edge.weight)),
      },
    }),
  );

  return { nodes, edges };
}

export function useDependencyGraph(repositoryId: string | undefined) {
  const graphQuery = useGraph(repositoryId);
  const graph = graphQuery.data;
  const converted = useMemo(() => (graph ? buildGraphNodes(graph) : { nodes: [], edges: [] }), [graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphEdge>([]);

  useEffect(() => {
    setNodes(converted.nodes);
    setEdges(converted.edges);
  }, [converted, setNodes, setEdges]);

  const onConnect = useCallback(
    () => {
      // The graph is read-only; connections are intentionally not persisted.
    },
    [],
  );

  return {
    nodes,
    edges,
    setNodes,
    setEdges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    refetch: graphQuery.refetch,
    isLoading: graphQuery.isLoading,
    isFetching: graphQuery.isFetching,
    isError: graphQuery.isError,
    error: graphQuery.error,
    isEmpty: !graphQuery.isLoading && nodes.length === 0,
  };
}
