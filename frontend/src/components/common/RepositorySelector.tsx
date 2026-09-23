import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown, FolderGit2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RepositoryListItem } from "@/types/repository";

interface RepositorySelectorProps {
  repositories: readonly RepositoryListItem[];
  value: string;
  onChange: (repositoryId: string) => void;
  placeholder?: string;
  allLabel?: string;
  disabled?: boolean;
  isLoading?: boolean;
  error?: string;
  className?: string;
}

function repositoryLabel(repository: RepositoryListItem): string {
  return repository.repository_name.replace(/^https:\/\/github\.com\//, "").replace(/\.git\/?$/, "");
}

function statusLabel(status: RepositoryListItem["status"]): string {
  if (status === "ready" || status === "indexed") return "Ready";
  if (status === "index_failed" || status === "failed_import" || status === "failed") return "Failed";
  return "Indexing";
}

export function RepositorySelector({ repositories, value, onChange, placeholder = "Select a repository", allLabel, disabled = false, isLoading = false, error, className }: RepositorySelectorProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const selected = repositories.find((repository) => String(repository.id) === value);
  const options = allLabel ? [{ id: "", label: allLabel }, ...repositories.map((repository) => ({ id: String(repository.id), label: repositoryLabel(repository) }))] : repositories.map((repository) => ({ id: String(repository.id), label: repositoryLabel(repository) }));
  const selectedIndex = Math.max(0, options.findIndex((option) => option.id === value));

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  const choose = (repositoryId: string) => {
    onChange(repositoryId);
    setOpen(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled || isLoading) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open && options[activeIndex]) choose(options[activeIndex].id);
      else { setActiveIndex(selectedIndex); setOpen(true); }
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex(selectedIndex);
      setOpen(true);
      setActiveIndex((current) => (current + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length);
    }
  };

  return <div ref={rootRef} className={cn("relative w-full max-w-80", className)}>
    <button type="button" aria-haspopup="listbox" aria-expanded={open} aria-controls={listId} aria-label={allLabel ? "Filter by repository" : "Select repository"} disabled={disabled || isLoading} onClick={() => { setActiveIndex(selectedIndex); setOpen((current) => !current); }} onKeyDown={handleKeyDown} className="flex h-10 w-full items-center gap-2 rounded-xl border border-border/70 bg-card px-3 text-left text-sm shadow-sm transition-all hover:border-primary/50 hover:bg-primary/5 focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">{isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderGit2 className="h-3.5 w-3.5" />}</span>
      <span className="min-w-0 flex-1 truncate">{selected ? repositoryLabel(selected) : allLabel ?? placeholder}</span>
      <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
    </button>
    {open && <div id={listId} role="listbox" aria-label={allLabel ? "Repositories" : "Select repository"} className="absolute right-0 z-50 mt-2 max-h-80 w-full min-w-64 overflow-auto rounded-xl border border-border/80 bg-popover p-1.5 text-popover-foreground shadow-xl ring-1 ring-black/5 dark:ring-white/10">
      {error ? <p className="px-3 py-4 text-xs text-destructive">{error}</p> : options.length === 0 ? <p className="px-3 py-4 text-xs text-muted-foreground">No repositories available.</p> : options.map((option, index) => {
        const repository = repositories.find((item) => String(item.id) === option.id);
        return <button key={option.id || "all"} type="button" role="option" aria-selected={option.id === value} onMouseEnter={() => setActiveIndex(index)} onClick={() => choose(option.id)} className={cn("flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors", index === activeIndex && "bg-primary/10", option.id === value && "text-primary")}>
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground"><FolderGit2 className="h-3.5 w-3.5" /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{option.label}</span>{repository && <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><span className={cn("h-1.5 w-1.5 rounded-full", statusLabel(repository.status) === "Ready" ? "bg-success" : statusLabel(repository.status) === "Failed" ? "bg-danger" : "bg-warning")} />{statusLabel(repository.status)}</span>}</span>{option.id === value && <Check className="h-4 w-4 shrink-0" />}
        </button>;
      })}
    </div>}
  </div>;
}
