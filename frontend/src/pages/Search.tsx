import { useMemo, useState, type KeyboardEvent } from "react";
import { FileCode2, FolderGit2, Search as SearchIcon } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { useRepositories } from "@/hooks/useRepositories";
import type { RepositoryListItem } from "@/types/repository";

type SearchScope = "repositories" | "files" | "symbols" | "semantic";

function repositoryName(repository: RepositoryListItem): string {
  return repository.repository_name
    .replace(/^https:\/\/github\.com\//, "")
    .replace(/\.git\/?$/, "");
}

function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"));
  return (
    <>
      {parts.map((part, index) =>
        part.toLowerCase() === query.toLowerCase() ? (
          <mark key={`${part}-${index}`} className="rounded bg-primary/20 px-0.5 text-foreground">
            {part}
          </mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        ),
      )}
    </>
  );
}

const SCOPES: SearchScope[] = ["repositories", "files", "symbols", "semantic"];

export function Search() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [scope, setScope] = useState<SearchScope>("repositories");
  const [activeIndex, setActiveIndex] = useState(0);
  const repositoriesQuery = useRepositories();
  const repositories = useMemo(() => repositoriesQuery.data?.items ?? [], [repositoriesQuery.data]);
  const results = useMemo(
    () =>
      scope === "repositories" && query.trim()
        ? repositories.filter((repository) => repositoryName(repository).toLowerCase().includes(query.trim().toLowerCase()))
        : [],
    [query, repositories, scope],
  );

  const handleQueryChange = (value: string) => {
    setQuery(value);
    setActiveIndex(0);
    if (value.trim()) setSearchParams({ q: value }, { replace: true });
    else setSearchParams({}, { replace: true });
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && results[activeIndex]) {
      navigate(`/repositories/${results[activeIndex].id}`);
    }
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <PageHeader
        eyebrow="Command search"
        title="Search"
        description="Find indexed repositories, files, and symbols across your workspace."
        icon={<SearchIcon className="h-5 w-5" />}
      />

      <Card className="border-border/70">
        <CardContent className="space-y-4 p-4 sm:p-5">
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              autoFocus
              type="search"
              value={query}
              onChange={(event) => handleQueryChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search repositories, files, or symbols…"
              className="h-10 pl-9"
              aria-label="Search CodeAtlas"
              aria-controls="search-results"
              aria-activedescendant={results[activeIndex] ? `search-result-${results[activeIndex].id}` : undefined}
            />
          </div>
          <div className="flex flex-wrap gap-1 rounded-md border border-border/60 bg-muted/20 p-1" role="group" aria-label="Search scope">
            {SCOPES.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setScope(value)}
                className={cn(
                  "rounded px-3 py-1.5 text-xs capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  scope === value
                    ? "border-primary/40 bg-primary/12 text-primary"
                    : "border-border/60 text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
                aria-pressed={scope === value}
              >
                {value}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card id="search-results" className="border-border/70">
        <CardContent className="p-0">
          {repositoriesQuery.isLoading ? (
            <div className="space-y-3 p-5">
              {[0, 1, 2].map((item) => <Skeleton key={item} className="h-16 w-full" />)}
            </div>
          ) : repositoriesQuery.isError ? (
            <div className="p-2">
              <ErrorState
                title="Unable to load searchable repositories"
                description="The search index could not be reached. Try again."
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void repositoriesQuery.refetch()}
                    className="gap-1.5"
                  >
                    <SearchIcon className="h-3.5 w-3.5" />
                    Retry
                  </Button>
                }
              />
            </div>
          ) : scope !== "repositories" ? (
            <EmptyState
              icon={SearchIcon}
              title={`${scope} search unavailable`}
              description="This backend does not currently expose a global scope search endpoint. Searching repositories is always available."
            />
          ) : !query.trim() ? (
            <div className="flex flex-col items-center px-6 py-12 text-center">
              <SearchIcon className="mb-3 h-5 w-5 text-muted-foreground/60" />
              <p className="text-sm font-medium text-foreground">Search your indexed codebase</p>
              <p className="mt-1 text-xs text-muted-foreground">Try a repository, file, or symbol name.</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {["auth", "useEffect", "package.json", "handleSubmit"].map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => handleQueryChange(example)}
                    className="rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ) : results.length === 0 ? (
            <EmptyState
              icon={FolderGit2}
              title="No repositories matched"
              description={`No imported repositories match “${query.trim()}”.`}
            />
          ) : (
            <div
              className="divide-y divide-border/60"
              role="listbox"
              aria-label="Search results"
              aria-live="polite"
            >
              {results.map((repository, index) => (
                <button
                  key={repository.id}
                  id={`search-result-${repository.id}`}
                  type="button"
                  role="option"
                  aria-selected={index === activeIndex}
                  onClick={() => navigate(`/repositories/${repository.id}`)}
                  className={`flex w-full items-center gap-3 p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${index === activeIndex ? "bg-muted/60" : "hover:bg-muted/40"}`}
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted/60 text-muted-foreground">
                    <FolderGit2 className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium"><Highlight text={repositoryName(repository)} query={query} /></span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <FileCode2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {repository.files_indexed.toLocaleString()} files
                      </span>
                      <Badge variant="outline" className="font-normal normal-case">{repository.status}</Badge>
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default Search;