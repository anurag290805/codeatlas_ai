const LANGUAGE_LABELS: Record<string, string> = {
  javascript: "JavaScript",
  typescript: "TypeScript",
  python: "Python",
  java: "Java",
  go: "Go",
  rust: "Rust",
  csharp: "C#",
  cpp: "C++",
  markdown: "Markdown",
};

export function formatLanguage(value: string | null | undefined): string {
  if (!value) return "Unknown language";
  const normalized = value.toLowerCase().split(".").pop() ?? value;
  return LANGUAGE_LABELS[normalized] ?? normalized.replace(/[-_]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatBytes(value: number | null | undefined): string {
  if (value == null || value < 0 || !Number.isFinite(value)) return "Not calculated";
  if (value === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatCount(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("en").format(value);
}
