import { motion, AnimatePresence } from "framer-motion";
import { FileCode2, FileWarning, Loader2, MousePointerClick } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { MonacoEditor } from "@/components/repository/MonacoEditor";
import type { RepositoryFile } from "@/types";

interface FileViewerProps {
  file: RepositoryFile | null;
  isLoading?: boolean;
  error?: unknown;
  className?: string;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted-foreground">
      <MousePointerClick className="h-8 w-8" />
      <p className="text-sm font-medium">No file selected</p>
      <p className="max-w-xs text-xs">
        Choose a file from the explorer to preview its contents here.
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" />
      <p className="text-sm">Loading file…</p>
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-destructive">
      <FileWarning className="h-8 w-8" />
      <p className="text-sm font-medium">Unable to load file</p>
      <p className="max-w-xs text-xs text-muted-foreground">
        The file contents could not be retrieved from the repository.
      </p>
    </div>
  );
}

function UnsupportedState({ name }: { name: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted-foreground">
      <FileWarning className="h-8 w-8" />
      <p className="text-sm font-medium">Preview not available</p>
      <p className="max-w-xs text-xs">
        {name} can&apos;t be previewed in the code viewer. Try opening it on GitHub instead.
      </p>
    </div>
  );
}

export function FileViewer({ file, isLoading = false, error, className }: FileViewerProps) {
  return (
    <div
      className={cn("flex h-full min-h-0 flex-col overflow-hidden", className)}
    >
      {file && !isLoading && (
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border/60 bg-muted/30 px-4 py-1.5">
          <div className="flex min-w-0 items-center gap-2">
            <FileCode2 className="h-4 w-4 shrink-0 text-muted-foreground/80" />
            <span className="truncate text-sm font-medium text-foreground">
              {file.name}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {file.language && (
              <Badge variant="secondary" className="h-5 gap-1 px-1.5 text-[10px] font-normal uppercase tracking-wide">
                {file.language}
              </Badge>
            )}
            <span className="text-xs tabular-nums text-muted-foreground">
              {formatBytes(file.sizeBytes)}
            </span>
          </div>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0"
            >
              <LoadingState />
            </motion.div>
          ) : error ? (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0"
            >
              <ErrorState />
            </motion.div>
          ) : !file ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0"
            >
              <EmptyState />
            </motion.div>
          ) : file.isBinary || file.content === undefined ? (
            <motion.div
              key="unsupported"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0"
            >
              <UnsupportedState name={file.name} />
            </motion.div>
          ) : (
            <motion.div
              key={file.path}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <MonacoEditor
                value={file.content}
                language={file.language}
                path={file.path}
                readOnly
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
