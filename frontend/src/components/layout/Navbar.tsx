// src/components/layout/Navbar.tsx
import { Menu, Search as SearchIcon, Command } from "lucide-react";
import { useState, useEffect, useRef, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

interface NavbarProps {
  title: string;
  /** Invoked when the mobile menu button is pressed to open the sidebar drawer. */
  onMenuClick?: () => void;
}

/**
 * Sticky top navigation bar. Shows the current page title, a global
 * search field with keyboard shortcut support (Cmd+K / /), and theme toggle.
 */
export function Navbar({ title, onMenuClick }: NavbarProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedQuery = query.trim();
    navigate(trimmedQuery ? `/search?q=${encodeURIComponent(trimmedQuery)}` : "/search");
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === "/" && document.activeElement !== inputRef.current && !["INPUT", "TEXTAREA"].includes((document.activeElement as HTMLElement)?.tagName)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-border/70 bg-background/85 px-3.5 backdrop-blur-xl supports-[backdrop-filter]:bg-background/75 sm:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="flex min-w-0 items-center gap-2">
        <span className="sr-only" aria-hidden="true">{title}</span>
        <span className="truncate text-sm font-semibold tracking-tight text-foreground sm:text-[15px]">{title}</span>
      </div>

      <form onSubmit={submitSearch} className="relative ml-4 hidden max-w-lg flex-1 sm:block">
        <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70" />
        <Input
          ref={inputRef}
          type="search"
          placeholder="Search repositories, files, symbols..."
          className="h-8 rounded-md border-border/80 bg-muted/35 pl-8 pr-12 text-xs hover:bg-muted/60 focus-visible:border-primary/50 focus-visible:bg-background transition-all"
          aria-label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-0.5 rounded border border-border/60 bg-muted/60 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground select-none">
          <Command className="h-2.5 w-2.5" />K
        </kbd>
      </form>

      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
      </div>
    </header>
  );
}