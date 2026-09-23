// src/components/graph/NodeDetails.tsx

import type { FC } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCode2,
  ArrowDownToLine,
  ArrowUpFromLine,
  Network,
  Clock,
  Waypoints,
  X,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types/graph";

export interface NodeDetailsProps {
  /** The currently selected graph node, or `null` when nothing is selected. */
  node: GraphNode | null;
  /** Show a skeleton state while the graph is still loading. */
  isLoading?: boolean;
  /** Called when the panel's close control is pressed. */
  onClose?: () => void;
  className?: string;
  error?: string;
}

/**
 * Displays metadata for the node currently selected on the dependency graph
 * canvas. This component is purely presentational - it receives node data
 * through props and never performs data fetching of its own.
 */
export const NodeDetails: FC<NodeDetailsProps> = ({
  node,
  isLoading = false,
  onClose,
  className,
  error,
}) => {
  return (
    <Card
      className={cn(
        "flex h-full w-full flex-col overflow-hidden border-border/60 bg-card/95 shadow-sm backdrop-blur-sm",
        className,
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border/60 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <FileCode2 className="h-4 w-4 text-muted-foreground" />
          Node details
        </div>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground"
            onClick={onClose}
            aria-label="Close node details"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-4 p-4"
            >
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-5/6" />
              <Separator />
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-3 w-1/2" />
            </motion.div>
          ) : error ? (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center"
            >
              <p className="text-sm font-medium text-destructive">Unable to load node details</p>
              <p className="text-xs text-muted-foreground">{error}</p>
            </motion.div>
          ) : !node ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center"
            >
              <Waypoints className="h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm font-medium text-foreground">
                No node selected
              </p>
              <p className="text-xs text-muted-foreground">
                Select a node on the graph to inspect its metadata and
                relationships.
              </p>
            </motion.div>
          ) : (
            <motion.div
              key={node.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex h-full flex-col"
            >
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  <div className="space-y-1">
                    <p className="break-all text-sm font-semibold text-foreground">
                      {node.data.label}
                    </p>
                    <p className="break-all text-xs text-muted-foreground">
                      {node.data.filePath}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <Detail label="Symbol type" value={node.data.symbolType ?? "—"} />
                    <Detail label="Lines" value={formatLines(node.data.startLine, node.data.endLine)} />
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary" className="capitalize">
                      {node.data.nodeType}
                    </Badge>
                    <Badge variant="outline">{node.data.language}</Badge>
                  </div>

                  <Separator />

                  <div className="grid grid-cols-2 gap-3">
                    <Stat
                      icon={ArrowDownToLine}
                      label="Imports"
                      value={node.data.importsCount}
                    />
                    <Stat
                      icon={ArrowUpFromLine}
                      label="Exports"
                      value={node.data.exportsCount}
                    />
                  </div>

                  <Separator />

                  <RelationList
                    icon={Network}
                    title="Dependencies"
                    items={node.data.dependencies}
                    emptyLabel="No outgoing dependencies"
                  />

                  <RelationList
                    icon={Network}
                    title="Dependents"
                    items={node.data.dependents}
                    emptyLabel="No dependents"
                  />

                  <Separator />

                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="h-3.5 w-3.5" />
                    Last modified {node.data.lastModified}
                  </div>

                  {Object.keys(node.data.metadata).length > 0 && (
                    <div className="space-y-2">
                      <Separator />
                      <p className="text-xs font-medium text-foreground">Metadata</p>
                      <dl className="space-y-1.5">
                        {Object.entries(node.data.metadata).map(([key, value]) => (
                          <div key={key} className="flex justify-between gap-3 text-xs">
                            <dt className="text-muted-foreground">{key}</dt>
                            <dd className="max-w-[60%] break-words text-right text-foreground">
                              {String(value)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
};

interface StatProps {
  icon: FC<{ className?: string }>;
  label: string;
  value: number;
}

const Stat: FC<StatProps> = ({ icon: Icon, label, value }) => (
  <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-2.5 py-2">
    <Icon className="h-3.5 w-3.5 text-muted-foreground" />
    <div className="leading-tight">
      <p className="text-sm font-semibold text-foreground">{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  </div>
);

function formatLines(startLine: number | null, endLine: number | null): string {
  if (startLine == null) return "—";
  return endLine == null || endLine === startLine ? `L${startLine}` : `L${startLine}–${endLine}`;
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/60 bg-muted/30 px-2.5 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words font-medium text-foreground">{value}</p>
    </div>
  );
}

interface RelationListProps {
  icon: FC<{ className?: string }>;
  title: string;
  items: readonly string[];
  emptyLabel: string;
}

const RelationList: FC<RelationListProps> = ({
  icon: Icon,
  title,
  items,
  emptyLabel,
}) => (
  <div className="space-y-2">
    <div className="flex items-center gap-2 text-xs font-medium text-foreground">
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      {title}
      <span className="text-muted-foreground">({items.length})</span>
    </div>
    {items.length === 0 ? (
      <p className="text-xs text-muted-foreground">{emptyLabel}</p>
    ) : (
      <ul className="space-y-1">
        {items.map((item) => (
          <li
            key={item}
            className="truncate rounded-md bg-muted/40 px-2 py-1 text-xs text-muted-foreground"
            title={item}
          >
            {item}
          </li>
        ))}
      </ul>
    )}
  </div>
);

export default NodeDetails;
