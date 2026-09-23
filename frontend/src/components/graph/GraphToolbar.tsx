// src/components/graph/GraphToolbar.tsx

import type { FC, ReactNode } from "react";
import {
  Maximize2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Map as MapIcon,
  SlidersHorizontal,
  Grid3x3,
  Expand,
  RefreshCw,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface GraphToolbarProps {
  /** Fit the entire graph within the viewport. */
  onFitView: () => void;
  /** Zoom the canvas in by one step. */
  onZoomIn: () => void;
  /** Zoom the canvas out by one step. */
  onZoomOut: () => void;
  /** Reset pan and zoom to the initial viewport. */
  onResetView: () => void;
  /** Toggle the minimap overlay. */
  onToggleMiniMap: () => void;
  /** Toggle the zoom/pan controls overlay. */
  onToggleControls: () => void;
  /** Toggle the background grid. */
  onToggleGrid: () => void;
  /** Toggle fullscreen presentation of the graph. */
  onFullscreen?: () => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  /** Whether the minimap is currently visible. */
  showMiniMap: boolean;
  /** Whether the controls overlay is currently visible. */
  showControls: boolean;
  /** Whether the background grid is currently visible. */
  showGrid: boolean;
  /** Whether the graph is currently in fullscreen mode. */
  isFullscreen?: boolean;
  className?: string;
}

interface ToggleAction {
  key: string;
  label: string;
  icon: FC<{ className?: string }>;
  active: boolean;
  onToggle: () => void;
}

/**
 * Reusable, presentation-only toolbar for the dependency graph canvas.
 *
 * This component never touches React Flow's imperative API directly -
 * every action is surfaced through callback props so the toolbar can be
 * reused against any graph instance (or storybook fixture) without
 * depending on a live `ReactFlowInstance`.
 */
export const GraphToolbar: FC<GraphToolbarProps> = ({
  onFitView,
  onZoomIn,
  onZoomOut,
  onResetView,
  onToggleMiniMap,
  onToggleControls,
  onToggleGrid,
  onFullscreen,
  showMiniMap,
  showControls,
  showGrid,
  isFullscreen = false,
  onRefresh,
  isRefreshing = false,
  searchQuery,
  onSearchChange,
  className,
}) => {
  const toggles: ToggleAction[] = [
    {
      key: "minimap",
      label: showMiniMap ? "Hide minimap" : "Show minimap",
      icon: MapIcon,
      active: showMiniMap,
      onToggle: onToggleMiniMap,
    },
    {
      key: "controls",
      label: showControls ? "Hide controls" : "Show controls",
      icon: SlidersHorizontal,
      active: showControls,
      onToggle: onToggleControls,
    },
    {
      key: "grid",
      label: showGrid ? "Hide background grid" : "Show background grid",
      icon: Grid3x3,
      active: showGrid,
      onToggle: onToggleGrid,
    },
  ];

  return (
    <TooltipProvider delay={200}>
      <div
        className={cn(
          "flex items-center gap-1 rounded-lg border border-border/60 bg-card/95 p-1 shadow-sm backdrop-blur-sm",
          className,
        )}
        role="toolbar"
        aria-label="Graph view controls"
      >
        <div className="hidden items-center gap-1.5 px-1 sm:flex">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search nodes"
            aria-label="Search graph nodes"
            className="h-8 w-36 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
          />
        </div>
        <Separator orientation="vertical" className="mx-1 hidden h-5 sm:block" />
        <ToolbarButton label="Zoom in" onClick={onZoomIn}>
          <ZoomIn className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Zoom out" onClick={onZoomOut}>
          <ZoomOut className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Fit view" onClick={onFitView}>
          <Maximize2 className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Reset view" onClick={onResetView}>
          <RotateCcw className="h-4 w-4" />
        </ToolbarButton>

        <Separator orientation="vertical" className="mx-1 h-5" />

        {toggles.map(({ key, label, icon: Icon, active, onToggle }) => (
          <ToolbarButton
            key={key}
            label={label}
            onClick={onToggle}
            active={active}
          >
            <Icon className="h-4 w-4" />
          </ToolbarButton>
        ))}

        <Separator orientation="vertical" className="mx-1 h-5" />

        <ToolbarButton
          label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          onClick={onFullscreen}
          disabled={!onFullscreen}
          active={isFullscreen}
        >
          <Expand className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Refresh graph" onClick={onRefresh} disabled={!onRefresh || isRefreshing}>
          <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
        </ToolbarButton>
      </div>
    </TooltipProvider>
  );
};

interface ToolbarButtonProps {
  label: string;
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
  children: ReactNode;
}

const ToolbarButton: FC<ToolbarButtonProps> = ({
  label,
  onClick,
  active = false,
  disabled = false,
  children,
}) => (
  <Tooltip>
    <TooltipTrigger
      render={
        <Button
          type="button"
          variant={active ? "secondary" : "ghost"}
          size="icon"
          className={cn(
            "h-8 w-8 text-muted-foreground transition-colors",
            active && "text-foreground",
          )}
          onClick={onClick}
          disabled={disabled}
          aria-pressed={active}
          aria-label={label}
        />
      }
    >
      {children}
    </TooltipTrigger>
    <TooltipContent side="bottom">{label}</TooltipContent>
  </Tooltip>
);

export default GraphToolbar;
