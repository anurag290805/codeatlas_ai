// src/components/repository/FileExplorer.tsx
import { useState } from "react";
import { FileQuestion, FolderOpen } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { FileTree } from "@/components/repository/FileTree";
import { FileViewer } from "@/components/repository/FileViewer";
import { cn } from "@/lib/utils";
import type { FileContent, FileTreeNode } from "@/types";

interface FileExplorerProps {
  /** Hierarchical file structure for the repository. */
  fileTree: FileTreeNode[];
  /** Currently selected file path. */
  selectedPath?: string;
  /** File content returned by the repository file hook. */
  selectedFile: FileContent | null;
  /** True while the selected file is being fetched. */
  isFileLoading?: boolean;
  /** Error raised while loading the selected file. */
  fileError?: unknown;
  /** Notified whenever the selected file changes. */
  onFileSelect: (path: string) => void;
  className?: string;
}

/**
 * Composes the repository browsing experience — a file tree on the
 * left and a file viewer on the right — in a resizable, IDE-style
 * layout on desktop and a stacked layout on mobile.
 */
export function FileExplorer({
  fileTree,
  selectedPath,
  selectedFile,
  isFileLoading = false,
  fileError,
  onFileSelect,
  className,
}: FileExplorerProps) {
  const [internalSelectedPath, setInternalSelectedPath] = useState<string | undefined>(selectedPath);
  const activePath = selectedPath ?? internalSelectedPath;

  const handleSelectFile = (path: string) => {
    setInternalSelectedPath(path);
    onFileSelect(path);
  };

  const emptyState = (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted/60 border border-border/60">
        <FileQuestion className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">No file selected</p>
        <p className="text-xs text-muted-foreground">
          Choose a file from the tree to view its contents.
        </p>
      </div>
    </div>
  );

  return (
    <div className={cn("w-full min-w-0", className)}>
      {/* Desktop — resizable panels */}
      <div className="hidden h-full min-h-[28rem] w-full min-w-0 overflow-hidden rounded-lg border border-border/60 bg-card md:flex">
        <ResizablePanelGroup orientation="horizontal" className="h-full w-full min-w-0">
          <ResizablePanel
            defaultSize={320}
            minSize={280}
            maxSize={360}
            className="min-w-[17.5rem] shrink-0"
          >
            <div className="flex h-full w-full min-w-0 flex-col border-r border-border/60 bg-muted/20">
              <div className="flex h-10 shrink-0 items-center gap-1.5 border-b border-border/50 px-3">
                <FolderOpen className="h-3.5 w-3.5 text-muted-foreground/70 shrink-0" aria-hidden="true" />
                <span className="text-xs font-medium text-muted-foreground">Explorer</span>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
                <FileTree
                  nodes={fileTree}
                  selectedPath={activePath}
                  onSelectFile={handleSelectFile}
                  className="w-full min-w-0"
                />
              </div>
            </div>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel minSize={320} className="min-w-0 flex-1">
            <div className="h-full min-w-0 overflow-hidden bg-background">
              {activePath ? (
                <FileViewer
                  file={selectedFile}
                  isLoading={isFileLoading}
                  error={fileError}
                />
              ) : emptyState}
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* Mobile — stacked layout */}
      <div className="flex flex-col gap-3 md:hidden">
        <div className="max-h-72 overflow-y-auto rounded-lg border border-border/60 bg-muted/20">
          <div className="flex h-10 items-center gap-1.5 border-b border-border/50 px-3">
            <FolderOpen className="h-3.5 w-3.5 text-muted-foreground/70 shrink-0" />
            <span className="text-xs font-medium text-muted-foreground">Explorer</span>
          </div>
          <FileTree nodes={fileTree} selectedPath={activePath} onSelectFile={handleSelectFile} />
        </div>
        <div className="min-h-[18rem] overflow-hidden rounded-lg border border-border/60 bg-background">
          {activePath ? (
            <FileViewer file={selectedFile} isLoading={isFileLoading} error={fileError} />
          ) : emptyState}
        </div>
      </div>
    </div>
  );
}
