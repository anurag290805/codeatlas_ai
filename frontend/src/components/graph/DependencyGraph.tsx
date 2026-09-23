// src/components/graph/DependencyGraph.tsx

import { useCallback, useEffect, useMemo, useState, type FC } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type NodeTypes,
  type EdgeTypes,
  type NodeProps,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion, AnimatePresence } from "framer-motion";
import { Waypoints, FolderTree } from "lucide-react";

import { GraphToolbar } from "@/components/graph/GraphToolbar";
import { NodeDetails } from "@/components/graph/NodeDetails";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useDependencyGraph } from "@/hooks/useDependencyGraph";
import type { GraphNode, GraphEdge, GraphNodeData } from "@/types/graph";

export interface DependencyGraphProps {
  /** Identifier of the repository whose dependency graph should be rendered. */
  repositoryId: string;
  /**
   * Optional layout function, allowing future layout engines (Dagre, ELK,
   * etc.) to be plugged in without changing this component's public API.
   * When omitted, nodes are rendered using the positions returned by the
   * API / hook layer.
   */
  applyLayout?: (nodes: GraphNode[], edges: GraphEdge[]) => GraphNode[];
  /**
   * Optional predicate to filter which nodes are rendered, enabling future
   * search/filter UI to be layered on top of this component.
   */
  nodeFilter?: (node: GraphNode) => boolean;
  searchQuery?: string;
  onSearchQueryChange?: (value: string) => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  className?: string;
}

/**
 * Custom node renderer for file/module nodes on the canvas. Registered
 * through `nodeTypes` below so additional node variants (class, interface,
 * external package, etc.) can be added later without touching the graph
 * shell itself.
 */
const FileNode: FC<NodeProps<GraphNode>> = ({ data, selected }) => {
  const nodeData = data as GraphNodeData;

  return (
    <div
      className={cn(
        "min-w-[160px] rounded-lg border bg-card px-3 py-2 shadow-sm transition-all",
        selected
          ? "border-primary/60 shadow-md ring-1 ring-primary/30"
          : "border-border/60 hover:border-border hover:shadow-md",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground/50" />
      <div className="flex items-center gap-2">
        <FolderTree className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <p className="truncate text-xs font-medium text-foreground">
          {nodeData.label}
        </p>
      </div>
      <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
        {nodeData.nodeType}
      </p>
      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground/50" />
    </div>
  );
};

// Module-level constants: React Flow requires stable object identity for
// `nodeTypes` / `edgeTypes`, so these are declared outside the component and
// designed to accept further variants as the visualization grows.
const nodeTypes: NodeTypes = {
  code: FileNode,
};

const edgeTypes: EdgeTypes = {};

const DependencyGraphCanvas: FC<DependencyGraphProps> = ({
  repositoryId,
  applyLayout,
  nodeFilter,
  searchQuery = "",
  onSearchQueryChange,
  onRefresh,
  isRefreshing = false,
  className,
}) => {
  const { nodes: sourceNodes, edges: sourceEdges, isLoading, isError, isEmpty } =
    useDependencyGraph(repositoryId);

  const { fitView, zoomIn, zoomOut, setViewport, setCenter } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNode>([]);
  const [, setEdges, onEdgesChange] = useEdgesState<GraphEdge>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const filteredNodes = useMemo((): GraphNode[] => {
    const normalizedSearch = searchQuery.trim().toLowerCase();
    return sourceNodes.filter((node) => {
      const matchesSearch =
        !normalizedSearch ||
        node.data.label.toLowerCase().includes(normalizedSearch) ||
        node.data.filePath.toLowerCase().includes(normalizedSearch);
      return matchesSearch && (!nodeFilter || nodeFilter(node));
    });
  }, [sourceNodes, nodeFilter, searchQuery]);

  const visibleNodeIds = useMemo(
    () => new Set(filteredNodes.map((node) => node.id)),
    [filteredNodes],
  );

  const visibleEdges = useMemo(
    () => sourceEdges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)),
    [sourceEdges, visibleNodeIds],
  );

  const layoutedNodes = useMemo(
    () =>
      applyLayout
        ? applyLayout(filteredNodes, visibleEdges)
        : filteredNodes.map((node, index) => ({
            ...node,
            position: { x: (index % 6) * 240, y: Math.floor(index / 6) * 140 },
          })),
    [applyLayout, filteredNodes, visibleEdges],
  );

  useEffect(() => {
    setNodes(layoutedNodes);
    setEdges(visibleEdges);
  }, [layoutedNodes, visibleEdges, setNodes, setEdges]);

  useEffect(() => {
    if (!isLoading && layoutedNodes.length > 0) {
      const raf = requestAnimationFrame(() => fitView({ padding: 0.2, duration: 300 }));
      return () => cancelAnimationFrame(raf);
    }
  }, [isLoading, layoutedNodes.length, fitView]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedNode(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleNodeClick: NodeMouseHandler<GraphNode> = useCallback((_event, node) => {
    setSelectedNode(node);
  }, []);

  const handleNodeDoubleClick: NodeMouseHandler<GraphNode> = useCallback(
    (_event, node) => {
      setSelectedNode(node);
      setCenter(node.position.x + 80, node.position.y + 40, { zoom: 1.25, duration: 350 });
    },
    [setCenter],
  );

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const handleFitView = useCallback(() => {
    fitView({ padding: 0.2, duration: 300 });
  }, [fitView]);

  const handleResetView = useCallback(() => {
    setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 300 });
  }, [setViewport]);

  const handleFullscreen = useCallback(() => {
    setIsFullscreen((previous) => !previous);
  }, []);

  const connectedNodeIds = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const ids = new Set<string>([selectedNode.id]);
    for (const edge of visibleEdges) {
      if (edge.source === selectedNode.id) ids.add(edge.target);
      if (edge.target === selectedNode.id) ids.add(edge.source);
    }
    return ids;
  }, [selectedNode, visibleEdges]);

  const renderedEdges = useMemo(
    () =>
      visibleEdges.map((edge) => {
        const active =
          !selectedNode || edge.source === selectedNode.id || edge.target === selectedNode.id;
        return {
          ...edge,
          style: {
            ...edge.style,
            opacity: active ? 1 : 0.18,
            stroke: active ? "var(--primary)" : "var(--muted-foreground)",
          },
          animated: Boolean(selectedNode && active),
        };
      }),
    [visibleEdges, selectedNode],
  );

  const renderedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        style: {
          ...node.style,
          opacity: selectedNode && !connectedNodeIds.has(node.id) ? 0.35 : 1,
        },
      })),
    [nodes, selectedNode, connectedNodeIds],
  );

  if (isLoading) {
    return <GraphLoadingState className={className} />;
  }

  if (isError) {
    return <GraphErrorState className={className} />;
  }

  if (isEmpty || nodes.length === 0) {
    return <GraphEmptyState className={className} />;
  }

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden rounded-lg border border-border/60 bg-background",
        isFullscreen && "fixed inset-0 z-50 rounded-none",
        className,
      )}
    >
      <ReactFlow<GraphNode, GraphEdge>
        nodes={renderedNodes}
        edges={renderedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        proOptions={{ hideAttribution: true }}
        minZoom={0.1}
        maxZoom={2}
        fitView
        className="bg-background"
      >
        {showGrid && (
          <Background
            variant={BackgroundVariant.Dots}
            gap={22}
            size={1.25}
            color="var(--border)"
            className="opacity-80"
          />
        )}
        {showControls && (
          <Controls
            showInteractive={false}
            className="!border !border-border/60 !bg-card/95 !shadow-sm [&_button]:!border-border/60 [&_button]:!bg-card [&_button]:!text-foreground"
          />
        )}
        {showMiniMap && (
          <MiniMap
            pannable
            zoomable
            className="!border !border-border/60 !bg-card/95 !shadow-sm"
            maskColor="rgba(0,0,0,0.08)"
          />
        )}
      </ReactFlow>

      <div className="pointer-events-none absolute inset-x-0 top-3 z-10 flex justify-center px-3">
        <div className="pointer-events-auto">
          <GraphToolbar
            onFitView={handleFitView}
            onZoomIn={() => zoomIn({ duration: 200 })}
            onZoomOut={() => zoomOut({ duration: 200 })}
            onResetView={handleResetView}
            onToggleMiniMap={() => setShowMiniMap((v) => !v)}
            onToggleControls={() => setShowControls((v) => !v)}
            onToggleGrid={() => setShowGrid((v) => !v)}
            onFullscreen={handleFullscreen}
            onRefresh={onRefresh}
            isRefreshing={isRefreshing}
            searchQuery={searchQuery}
            onSearchChange={onSearchQueryChange ?? (() => undefined)}
            showMiniMap={showMiniMap}
            showControls={showControls}
            showGrid={showGrid}
            isFullscreen={isFullscreen}
          />
        </div>
      </div>

      <AnimatePresence>
        {selectedNode && (
          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 16 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="absolute right-3 top-3 z-10 h-[calc(100%-1.5rem)] w-80 max-w-[85vw]"
          >
            <NodeDetails
              node={selectedNode}
              onClose={() => setSelectedNode(null)}
              className="h-full"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

/**
 * Public entry point for the repository dependency graph. Wraps the canvas
 * in `ReactFlowProvider` so imperative viewport controls (`useReactFlow`)
 * are available internally without requiring consumers to set up the
 * provider themselves.
 */
export const DependencyGraph: FC<DependencyGraphProps> = (props) => (
  <ReactFlowProvider>
    <DependencyGraphCanvas {...props} />
  </ReactFlowProvider>
);

const GraphLoadingState: FC<{ className?: string }> = ({ className }) => (
  <div
    className={cn(
      "flex h-full w-full flex-col gap-3 rounded-lg border border-border/60 bg-background p-4",
      className,
    )}
  >
    <div className="flex items-center justify-between">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-8 w-24" />
    </div>
    <div className="grid flex-1 grid-cols-3 gap-4 p-6">
      <Skeleton className="h-24 w-full self-center" />
      <Skeleton className="h-32 w-full self-center" />
      <Skeleton className="h-20 w-full self-center" />
    </div>
  </div>
);

const GraphEmptyState: FC<{ className?: string }> = ({ className }) => (
  <div
    className={cn(
      "flex h-full w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 bg-background p-8 text-center",
      className,
    )}
  >
    <Waypoints className="h-10 w-10 text-muted-foreground/50" />
    <p className="text-sm font-medium text-foreground">
      No dependency data yet
    </p>
    <p className="max-w-sm text-xs text-muted-foreground">
      This repository hasn&apos;t produced a dependency graph, or hasn&apos;t
      finished analysis yet.
    </p>
  </div>
);

const GraphErrorState: FC<{ className?: string }> = ({ className }) => (
  <div
    className={cn(
      "flex h-full w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-destructive/40 bg-background p-8 text-center",
      className,
    )}
  >
    <Waypoints className="h-10 w-10 text-destructive/60" />
    <p className="text-sm font-medium text-foreground">
      Couldn&apos;t load the dependency graph
    </p>
    <p className="max-w-sm text-xs text-muted-foreground">
      Something went wrong while fetching graph data for this repository.
    </p>
  </div>
);

export default DependencyGraph;
