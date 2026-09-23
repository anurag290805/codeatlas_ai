import { motion } from "framer-motion";
import { AlertCircle, Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { CitationCard } from "@/components/chat/CitationCard";
import type { ChatMessage, Citation } from "@/types";

interface MessageBubbleProps {
  message: ChatMessage;
  onOpenCitation?: (citation: Citation) => void;
  className?: string;
}

function formatTimestamp(isoDate: string): string {
  return new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(isoDate));
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 1, 2].map((index) => (
        <motion.span
          key={index}
          className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60"
          animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
          transition={{
            duration: 1,
            repeat: Infinity,
            delay: index * 0.15,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}

export function MessageBubble({ message, onOpenCitation, className }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isPending = message.status === "pending" && message.content.length === 0;
  const isStreaming = message.status === "streaming";
  const isError = message.status === "error";

  return (
    <div
      className={cn("flex items-start gap-3", isUser && "flex-row-reverse", className)}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
          isUser
            ? "border-border/60 bg-muted text-foreground"
            : "border-primary/20 bg-primary/10 text-primary",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div className={cn("flex min-w-0 max-w-[85%] flex-col gap-1.5", isUser && "items-end")}>
        <div
          className={cn(
            "min-w-0 rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground"
              : isError
                ? "border border-destructive/30 bg-destructive/5 text-destructive"
                : "border border-border/60 bg-card text-card-foreground",
          )}
        >
          {isPending ? (
            <TypingIndicator />
          ) : isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : isError ? (
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="whitespace-pre-wrap break-words">{message.content}</p>
            </div>
          ) : (
            <div className="min-w-0">
              <MarkdownRenderer content={message.content} />
              {isStreaming && (
                <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-current align-middle" />
              )}
            </div>
          )}
        </div>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="w-full space-y-1.5">
            <div className="flex items-center gap-1.5 px-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              <span className="h-px w-3 bg-border" />
              Sources
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.citations.map((citation) => (
                <CitationCard
                  key={citation.id}
                  citation={citation}
                  onOpen={onOpenCitation}
                />
              ))}
            </div>
          </div>
        )}

        <span className="px-1 text-[11px] text-muted-foreground">
          {formatTimestamp(message.createdAt)}
        </span>
      </div>
    </div>
  );
}
