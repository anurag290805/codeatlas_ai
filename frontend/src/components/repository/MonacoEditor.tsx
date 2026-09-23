import { useState, type ReactNode } from "react";
import Editor, { type OnChange } from "@monaco-editor/react";
import { Loader2 } from "lucide-react";
import { useTheme } from "@/providers";
import { cn } from "@/lib/utils";

interface MonacoEditorProps {
  value: string;
  /** Explicit Monaco language id. When omitted, `path` drives detection. */
  language?: string;
  /** File path/name passed to Monaco for automatic language detection and
   * per-file model state (undo history, scroll position, selections). */
  path?: string;
  readOnly?: boolean;
  loading?: ReactNode;
  minimap?: boolean;
  wordWrap?: boolean;
  onChange?: (value: string | undefined) => void;
  className?: string;
  height?: string;
}

function DefaultLoadingIndicator() {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" />
      <span className="text-sm">Loading editor…</span>
    </div>
  );
}

export function MonacoEditor({
  value,
  language,
  path,
  readOnly = false,
  loading,
  minimap = false,
  wordWrap = true,
  onChange,
  className,
  height = "100%",
}: MonacoEditorProps) {
  const { resolvedTheme } = useTheme();
  const [isMounted, setIsMounted] = useState(false);

  const handleChange: OnChange = (nextValue) => {
    onChange?.(nextValue);
  };

  return (
    <div className={cn("h-full w-full overflow-hidden", className)}>
      <Editor
        height={height}
        value={value}
        language={language}
        path={path}
        theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
        loading={loading ?? <DefaultLoadingIndicator />}
        onChange={handleChange}
        onMount={() => setIsMounted(true)}
        options={{
          readOnly,
          minimap: { enabled: minimap },
          wordWrap: wordWrap ? "on" : "off",
          automaticLayout: true,
          fontSize: 14,
          fontLigatures: true,
          lineNumbers: "on",
          renderLineHighlight: readOnly ? "none" : "line",
          scrollBeyondLastLine: false,
          smoothScrolling: true,
          cursorBlinking: "smooth",
          padding: { top: 14, bottom: 14 },
          tabSize: 2,
          folding: true,
          contextmenu: !readOnly,
          domReadOnly: readOnly,
          renderWhitespace: "selection",
          scrollbar: {
            useShadows: false,
            verticalHasArrows: false,
            horizontalHasArrows: false,
          },
        }}
        className={cn(!isMounted && "opacity-0", "transition-opacity duration-150")}
      />
    </div>
  );
}
