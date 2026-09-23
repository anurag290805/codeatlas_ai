import {
  isValidElement,
  useEffect,
  useState,
  type ComponentPropsWithoutRef,
  type ReactElement,
  type ReactNode,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

const HIGHLIGHT_STYLE_ELEMENT_ID = "codeatlas-markdown-hljs-theme";

/**
 * Minimal, dark-mode-aware syntax highlighting palette for the token
 * classes rehype-highlight attaches to fenced code blocks. Injected once
 * into <head> on first mount rather than per-instance, since many
 * MarkdownRenderer instances can be mounted at once inside a chat thread.
 */
const HIGHLIGHT_THEME_CSS = `
.catlas-markdown .hljs { color: inherit; background: transparent; }
.catlas-markdown .hljs-keyword,
.catlas-markdown .hljs-selector-tag,
.catlas-markdown .hljs-literal,
.catlas-markdown .hljs-section { color: #c678dd; }
.catlas-markdown .hljs-string,
.catlas-markdown .hljs-addition { color: #98c379; }
.catlas-markdown .hljs-number,
.catlas-markdown .hljs-attr { color: #d19a66; }
.catlas-markdown .hljs-title,
.catlas-markdown .hljs-title.function_,
.catlas-markdown .hljs-title.class_ { color: #61afef; }
.catlas-markdown .hljs-comment,
.catlas-markdown .hljs-quote { color: #7f848e; font-style: italic; }
.catlas-markdown .hljs-built_in,
.catlas-markdown .hljs-type { color: #e5c07b; }
.catlas-markdown .hljs-deletion { color: #e06c75; }
.catlas-markdown .hljs-tag,
.catlas-markdown .hljs-name { color: #e06c75; }
.catlas-markdown .hljs-attribute { color: #d19a66; }
.catlas-markdown .hljs-symbol,
.catlas-markdown .hljs-bullet { color: #56b6c2; }
`;

function useHighlightThemeInjection() {
  useEffect(() => {
    if (document.getElementById(HIGHLIGHT_STYLE_ELEMENT_ID)) return;
    const styleElement = document.createElement("style");
    styleElement.id = HIGHLIGHT_STYLE_ELEMENT_ID;
    styleElement.textContent = HIGHLIGHT_THEME_CSS;
    document.head.appendChild(styleElement);
  }, []);
}

function extractPlainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractPlainText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return extractPlainText(node.props.children);
  }
  return "";
}

function CodeBlock({ children, ...props }: ComponentPropsWithoutRef<"pre">) {
  const [isCopied, setIsCopied] = useState(false);
  const codeElement = isValidElement<{ className?: string; children?: ReactNode }>(children)
    ? (children as ReactElement<{ className?: string; children?: ReactNode }>)
    : null;

  const languageMatch = /language-(\w+)/.exec(codeElement?.props.className ?? "");
  const language = languageMatch?.[1] ?? "text";
  const codeText = extractPlainText(codeElement?.props.children);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeText);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 1500);
    } catch {
      // Clipboard permission may be denied; the button simply stays idle.
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border/60">
      <div className="flex items-center justify-between bg-muted/60 px-3 py-1.5">
        <span className="font-mono text-[11px] text-muted-foreground">{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {isCopied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {isCopied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre
        {...props}
        className="overflow-x-auto bg-background/60 p-3 text-[13px] leading-relaxed"
      >
        {children}
      </pre>
    </div>
  );
}

function InlineCode({ className, children, ...props }: ComponentPropsWithoutRef<"code">) {
  const isFencedBlock = Boolean(className);

  if (!isFencedBlock) {
    return (
      <code
        {...props}
        className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground"
      >
        {children}
      </code>
    );
  }

  return (
    <code {...props} className={cn(className, "font-mono")}>
      {children}
    </code>
  );
}

const markdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-5 text-lg font-semibold tracking-tight text-foreground first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2.5 mt-5 text-base font-semibold tracking-tight text-foreground first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-4 text-sm font-semibold text-foreground first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-2 mt-4 text-sm font-medium text-foreground first:mt-0">
      {children}
    </h4>
  ),
  p: ({ children }) => (
    <p className="mb-3 text-sm leading-relaxed text-foreground last:mb-0">{children}</p>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="font-medium text-primary underline underline-offset-2 hover:text-primary/80"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 ml-4 list-disc space-y-1 text-sm text-foreground marker:text-muted-foreground last:mb-0">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 ml-4 list-decimal space-y-1 text-sm text-foreground marker:text-muted-foreground last:mb-0">
      {children}
    </ol>
  ),
  li: ({ children, className }) => (
    <li className={cn("leading-relaxed", className)}>{children}</li>
  ),
  input: (props) => (
    <input
      {...props}
      disabled
      className="mr-1.5 h-3.5 w-3.5 rounded border-border align-middle accent-primary"
    />
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-border pl-3 text-sm italic text-muted-foreground last:mb-0">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto rounded-md border border-border/60 last:mb-0">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/50">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-border/60 px-3 py-1.5 text-xs font-semibold text-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-border/40 px-3 py-1.5 align-top text-sm text-foreground">
      {children}
    </td>
  ),
  hr: () => <hr className="my-4 border-border/60" />,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  pre: CodeBlock,
  code: InlineCode,
};

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  useHighlightThemeInjection();

  return (
    <div className={cn("catlas-markdown min-w-0", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}