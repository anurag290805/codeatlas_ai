import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AlertCircle, Bot, Loader2, MessageSquare, Server, Sparkles } from "lucide-react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { RepositorySelector } from "@/components/common/RepositorySelector";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRepositories } from "@/hooks/useRepositories";
import { useAgentTask, useRepositoryQuery } from "@/hooks/useQuery";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/utils/errors";
import type { ChatMessage, Citation, QueryResponse } from "@/types";
import type { RepositoryListItem } from "@/types/repository";

function messageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function formatError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 502 || /gemini|provider/i.test(error.message)) {
      return "The AI provider could not complete this request. Check provider availability and try again.";
    }
    return error.message;
  }
  if (error instanceof Error && /indexed repository|select an indexed/i.test(error.message)) {
    return error.message;
  }
  return "CodeAtlas could not complete this repository request. Try again.";
}

function repositoryLabel(repository: RepositoryListItem): string {
  const name = repository.repository_name.trim();
  return name.replace(/^https:\/\/github\.com\//, "").replace(/\.git\/?$/, "");
}

function toCitation(citation: QueryResponse["citations"][number], index: number): Citation {
  return {
    id: `${citation.file_path}-${citation.start_line}-${index}`,
    filePath: citation.file_path,
    startLine: citation.start_line,
    endLine: citation.end_line,
    symbolName: citation.symbol_name ?? undefined,
    codePreview: citation.code_preview ?? undefined,
    relevanceScore: citation.relevance_score ?? undefined,
  };
}

function toAssistantMessage(response: QueryResponse): ChatMessage {
  return {
    id: messageId("assistant"),
    role: "assistant",
    content: response.answer,
    citations: response.citations.map(toCitation),
    createdAt: new Date().toISOString(),
    status: "complete",
  };
}

export function Chat() {
  const navigate = useNavigate();
  const { repositoryId: routeRepositoryId } = useParams<{ repositoryId: string }>();
  const [searchParams] = useSearchParams();
  const [selectedRepositoryId, setSelectedRepositoryId] = useState(
    routeRepositoryId ?? searchParams.get("repositoryId") ?? "",
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const repositoriesQuery = useRepositories();
  const queryMutation = useRepositoryQuery();
  const agentMutation = useAgentTask();
  const [agentMode, setAgentMode] = useState<"chat" | "analyze" | "modify">("chat");

  const repositories = useMemo(() => repositoriesQuery.data?.items ?? [], [repositoriesQuery.data]);
  const selectedRepository = useMemo(
    () => repositories.find((repository) => String(repository.id) === selectedRepositoryId),
    [repositories, selectedRepositoryId],
  );

  useEffect(() => {
    if (selectedRepositoryId || repositories.length === 0) return;
    const readyRepository = repositories.find(
      (repository) => repository.status === "ready" || repository.status === "indexed",
    );
    const nextRepository = readyRepository ?? repositories[0];
    setSelectedRepositoryId(String(nextRepository.id));
    navigate(`/chat/${nextRepository.id}`, { replace: true });
  }, [navigate, repositories, selectedRepositoryId]);

  const handleRepositoryChange = (repositoryId: string) => {
    setSelectedRepositoryId(repositoryId);
    setMessages([]);
    if (repositoryId) {
      navigate(`/chat/${repositoryId}`);
    }
  };

  const handleSubmit = async (text: string) => {
    const numericRepositoryId = Number(selectedRepositoryId);
    if (!Number.isInteger(numericRepositoryId) || numericRepositoryId <= 0) {
      setMessages((current) => [
        ...current,
        {
          id: messageId("error"),
          role: "assistant",
          content: "Select an indexed repository before sending a question.",
          createdAt: new Date().toISOString(),
          status: "error",
        },
      ]);
      return;
    }

    setMessages((current) => [
      ...current,
      {
        id: messageId("user"),
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
        status: "complete",
      },
    ]);

    try {
      if (agentMode !== "chat") {
        const response = await agentMutation.mutateAsync({ repository_id: numericRepositoryId, task: text, top_k: 3, mode: agentMode });
        const skillSummary = response.skill_results.map((item) => `- ${item.skill}: ${item.status}`).join("\n");
        const warnings = response.errors.length ? `\n\nWarnings:\n${response.errors.map((error) => `- ${error}`).join("\n")}` : "";
        const modification = response.modification;
        const changedFiles = modification?.files_changed?.length ? `\n\nFiles changed:\n${modification.files_changed.map((file) => `- ${file}`).join("\n")}` : "";
        const validation = modification?.validation && typeof modification.validation.status === "string" ? `\nValidation: ${modification.validation.status}` : "";
        const playwright = modification?.playwright && typeof modification.playwright.verified === "boolean" ? `\nPlaywright: ${modification.playwright.verified ? "passed" : "failed"}` : "";
        const content = `Skills used:\n${skillSummary || "- repository query fallback"}\n\n${response.final_result}${changedFiles}${validation}${playwright}${warnings}`;
        setMessages((current) => [...current, { id: messageId("assistant"), role: "assistant", content, createdAt: new Date().toISOString(), status: response.status === "completed" ? "complete" : "error" }]);
      } else {
        const response = await queryMutation.mutateAsync({ repository_id: numericRepositoryId, query: text, top_k: 3 });
        setMessages((current) => [...current, toAssistantMessage(response)]);
      }
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: messageId("error"),
          role: "assistant",
          content: formatError(error),
          createdAt: new Date().toISOString(),
          status: "error",
        },
      ]);
    }
  };

  const handleOpenCitation = (citation: Citation) => {
    if (!selectedRepositoryId) return;
    navigate(
      `/repositories/${selectedRepositoryId}?file=${encodeURIComponent(citation.filePath)}`,
    );
  };

  const queryError = repositoriesQuery.error;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-7rem)] w-full max-w-6xl flex-col gap-5">
      <PageHeader
        eyebrow="Repository intelligence"
        title="AI Chat"
        description="Ask grounded questions about an indexed repository, route analysis to specialists, or request a validated code change."
        icon={<Bot className="h-4 w-4" />}
        actions={
          <>
            <div
              className="flex items-center rounded-lg border border-border/70 bg-muted/40 p-0.5"
              role="group"
              aria-label="Agent mode"
            >
              {(["chat", "analyze", "modify"] as const).map((mode) => (
                <Button
                  key={mode}
                  type="button"
                  variant={agentMode === mode ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setAgentMode(mode)}
                  aria-pressed={agentMode === mode}
                >
                  {mode === "modify" && <Sparkles className="h-3.5 w-3.5" />}
                  {mode[0].toUpperCase() + mode.slice(1)}
                </Button>
              ))}
            </div>
            <RepositorySelector
              repositories={repositories}
              value={selectedRepositoryId}
              onChange={handleRepositoryChange}
              isLoading={repositoriesQuery.isLoading}
            />
          </>
        }
      />

      {repositoriesQuery.isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading repositories…
        </div>
      )}

      {queryError && (
        <Card className="border-destructive/30">
          <CardContent className="flex items-center gap-2 p-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            Unable to load repositories. Try refreshing the page.
          </CardContent>
        </Card>
      )}

      {!repositoriesQuery.isLoading && !queryError && repositories.length === 0 && (
        <Card>
          <CardContent className="flex min-h-40 flex-col items-center justify-center gap-2 text-center">
            <Server className="h-7 w-7 text-muted-foreground" />
            <p className="font-medium">No repositories are available</p>
            <p className="text-sm text-muted-foreground">
              Import a repository before starting a conversation.
            </p>
          </CardContent>
        </Card>
      )}

      {selectedRepository && (
        <Card className="flex min-h-0 flex-1 flex-col overflow-hidden border-border/70 shadow-sm">
          <CardHeader className="border-b bg-muted/15 py-3.5">
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquare className="h-4 w-4 text-primary" />
                {repositoryLabel(selectedRepository)}
              </CardTitle>
          </CardHeader>
          {agentMode !== "chat" && (
            <div className="border-b border-border/60 bg-muted/20 px-4 py-2 text-xs text-muted-foreground">
              {agentMode === "modify" ? "Modify mode can modify files in this repository, validate the patch, and roll it back if validation fails." : "Analyze mode routes tasks to specialists without modifying repository files."}
            </div>
          )}
          <ChatWindow
            messages={messages}
            isLoading={queryMutation.isPending || agentMutation.isPending}
            disabled={queryMutation.isPending || agentMutation.isPending}
            onSubmit={handleSubmit}
            onSelectPrompt={(prompt) => void handleSubmit(prompt)}
            emptyStateRepositoryName={repositoryLabel(selectedRepository)}
            onOpenCitation={handleOpenCitation}
            className="min-h-[32rem] flex-1 border-0 bg-transparent shadow-none"
          />
        </Card>
      )}
    </div>
  );
}

export default Chat;
