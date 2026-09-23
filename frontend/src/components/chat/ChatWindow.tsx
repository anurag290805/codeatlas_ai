import { useEffect, useRef, useState, type UIEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, MessagesSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { AIComposer } from "@/components/chat/AIComposer";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import type { ChatMessage, Citation } from "@/types";

interface ChatWindowProps {
  messages: ChatMessage[];
  /** True while waiting on a response that has not started streaming yet. */
  isLoading?: boolean;
  disabled?: boolean;
  onSubmit: (message: string) => void;
  onOpenCitation?: (citation: Citation) => void;
  emptyStateTitle?: string;
  emptyStateDescription?: string;
  emptyStateRepositoryName?: string;
  onSelectPrompt?: (prompt: string) => void;
  className?: string;
}

const NEAR_BOTTOM_THRESHOLD_PX = 96;

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border/60 bg-muted/40">
        <MessagesSquare className="h-5 w-5 text-muted-foreground" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="max-w-sm text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

export function ChatWindow({
  messages,
  isLoading = false,
  disabled = false,
  onSubmit,
  onOpenCitation,
  emptyStateTitle = "Ask anything about this repository",
  emptyStateDescription = "CodeAtlas AI reads the indexed source to answer with grounded, cited explanations.",
  emptyStateRepositoryName = "this repository",
  onSelectPrompt,
  className,
}: ChatWindowProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [isPinnedToBottom, setIsPinnedToBottom] = useState(true);

  useEffect(() => {
    if (!isPinnedToBottom) return;
    const container = scrollContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading, isPinnedToBottom]);

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const distanceFromBottom =
      target.scrollHeight - target.scrollTop - target.clientHeight;
    setIsPinnedToBottom(distanceFromBottom <= NEAR_BOTTOM_THRESHOLD_PX);
  };

  const scrollToBottom = () => {
    const container = scrollContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    setIsPinnedToBottom(true);
  };

  const isAwaitingFirstToken =
    isLoading && messages[messages.length - 1]?.role === "user";

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto px-4 py-4 sm:px-6"
        >
          {messages.length === 0 ? (
            onSelectPrompt ? (
              <ChatEmptyState repositoryName={emptyStateRepositoryName} onSelectPrompt={onSelectPrompt} />
            ) : (
              <EmptyState title={emptyStateTitle} description={emptyStateDescription} />
            )
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-5">
              <AnimatePresence initial={false}>
                {messages.map((message) => (
                  <motion.div
                    key={message.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                  >
                    <MessageBubble message={message} onOpenCitation={onOpenCitation} />
                  </motion.div>
                ))}
              </AnimatePresence>

              {isAwaitingFirstToken && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                >
                  <MessageBubble
                    message={{
                      id: "__pending__",
                      role: "assistant",
                      content: "",
                      createdAt: new Date().toISOString(),
                      status: "pending",
                    }}
                  />
                </motion.div>
              )}
            </div>
          )}
        </div>

        <AnimatePresence>
          {!isPinnedToBottom && messages.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="absolute bottom-3 left-1/2 -translate-x-1/2"
            >
              <Button
                size="sm"
                variant="secondary"
                onClick={scrollToBottom}
                className="gap-1.5 shadow-md"
              >
                <ArrowDown className="h-3.5 w-3.5" />
                New messages
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="shrink-0 border-t border-border/60 bg-background/80 px-4 py-3 backdrop-blur-sm sm:px-6">
        <div className="mx-auto max-w-3xl">
          <AIComposer
          onSubmit={onSubmit}
          isLoading={isLoading}
          disabled={disabled}
        />
        </div>
      </div>
    </div>
  );
}
export default ChatWindow;
