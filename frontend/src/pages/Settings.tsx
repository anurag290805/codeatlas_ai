import { useEffect, useState, type ReactNode } from "react";
import { Activity, Brain, Code2, Palette, Settings2 } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PageHeader } from "@/components/common/PageHeader";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { useHealth, useQueryHealth, useVersion } from "@/hooks/useHealth";

const STORAGE_KEYS = {
  streaming: "codeatlas.settings.streaming",
  citations: "codeatlas.settings.citations",
  compact: "codeatlas.settings.compact",
} as const;

function storedBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback;
  return window.localStorage.getItem(key) == null
    ? fallback
    : window.localStorage.getItem(key) === "true";
}

function SettingToggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-3 transition-opacity hover:opacity-90" >
      <span>
        <span className="block text-sm font-medium">{label}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4 shrink-0 accent-primary"
      />
    </label>
  );
}

function KeyValueRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

export function Settings() {
  const { theme } = useTheme();
  const health = useHealth();
  const queryHealth = useQueryHealth();
  const version = useVersion();
  const [streaming, setStreaming] = useState(() => storedBoolean(STORAGE_KEYS.streaming, true));
  const [citations, setCitations] = useState(() => storedBoolean(STORAGE_KEYS.citations, true));
  const [compact, setCompact] = useState(() => storedBoolean(STORAGE_KEYS.compact, false));

  useEffect(() => { window.localStorage.setItem(STORAGE_KEYS.streaming, String(streaming)); }, [streaming]);
  useEffect(() => { window.localStorage.setItem(STORAGE_KEYS.citations, String(citations)); }, [citations]);
  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.compact, String(compact));
    document.documentElement.dataset.density = compact ? "compact" : "comfortable";
  }, [compact]);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "Same origin";
  // Prefer the last-known-good probe result over `isError`: a failed
  // background refetch flips the query to an error state while retaining
  // the previous successful data, which would otherwise mislabel a live
  // backend as "unavailable".
  const backendStatus = health.data ? "online" : health.isLoading ? "checking" : "unavailable";
  const queryStatus = queryHealth.isLoading ? "checking" : queryHealth.isError ? "unavailable" : queryHealth.data?.status ?? "unavailable";
  const themeLabel = theme ? theme.charAt(0).toUpperCase() + theme.slice(1) : "System";

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8">
      <PageHeader
        eyebrow="Workspace controls"
        title="Settings"
        description="Manage workspace preferences and runtime diagnostics."
        icon={<Settings2 className="h-5 w-5" />}
      />

      <div className="grid items-stretch gap-4 lg:grid-cols-2">
        <Card className="h-full border-border/70">
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 border-b border-border/60 pb-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/12">
              <Palette className="h-4 w-4" />
            </span>
            <div>
              <CardTitle className="text-base">Appearance</CardTitle>
              <CardDescription>Control theme and information density.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="divide-y divide-border/60 p-4 pt-1">
            <div className="flex items-center justify-between py-3 first:pt-0">
              <div>
                <p className="text-sm font-medium">Theme</p>
                <p className="mt-0.5 text-xs text-muted-foreground">Current: {themeLabel}</p>
              </div>
              <ThemeToggle />
            </div>
            <SettingToggle
              label="Compact mode"
              description="Reduce spacing in dense repository views."
              checked={compact}
              onChange={setCompact}
            />
          </CardContent>
        </Card>

        <Card className="h-full border-border/70">
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 border-b border-border/60 pb-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/12">
              <Brain className="h-4 w-4" />
            </span>
            <div>
              <CardTitle className="text-base">AI preferences</CardTitle>
              <CardDescription>How grounded answers are presented.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="divide-y divide-border/60 p-4 pt-1">
            <SettingToggle
              label="Streaming responses"
              description="Persist the preference for progressive responses when supported."
              checked={streaming}
              onChange={setStreaming}
            />
            <SettingToggle
              label="Show citations"
              description="Keep source references visible in AI answers."
              checked={citations}
              onChange={setCitations}
            />
            <div className="py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium">AI query status</p>
                <span className="text-xs font-medium capitalize text-primary">{queryStatus}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {queryHealth.data?.llm_provider ?? "Provider unavailable"} · {queryHealth.data?.llm_model ?? "configured by the backend"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {queryHealth.data?.message ?? "Health details unavailable."}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="h-full border-border/70">
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 border-b border-border/60 pb-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/12">
              <Activity className="h-4 w-4" />
            </span>
            <div>
              <CardTitle className="text-base">Runtime diagnostics</CardTitle>
              <CardDescription>Connection, AI readiness, and environment.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border border-border/70 p-3">
                <p className="text-xs text-muted-foreground">Backend status</p>
                <p className="mt-1 text-sm font-medium capitalize">{backendStatus}</p>
                <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{apiBaseUrl}</p>
              </div>
              <div className="rounded-md border border-border/70 p-3">
                <p className="text-xs text-muted-foreground">AI status</p>
                <p className="mt-1 text-sm font-medium capitalize">{queryStatus}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">{queryHealth.data?.message ?? "Checking query subsystem…"}</p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => { void health.refetch(); void queryHealth.refetch(); void version.refetch(); }}
              disabled={health.isFetching || queryHealth.isFetching || version.isFetching}
            >
              Refresh diagnostics
            </Button>
          </CardContent>
        </Card>

        <Card className="h-full">
          <CardHeader className="flex flex-row items-center gap-3 space-y-0">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/12">
              <Code2 className="h-4 w-4" />
            </span>
            <div>
              <CardTitle className="text-base">Developer</CardTitle>
              <CardDescription>Build and environment information.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="divide-y divide-border/60 p-4 pt-1">
            <KeyValueRow label="Application" value="CodeAtlas AI" />
            <KeyValueRow label="Frontend environment" value={import.meta.env.MODE} />
            <KeyValueRow label="Backend version" value={version.data?.version ?? "Unavailable"} />
            <KeyValueRow label="Backend environment" value={version.data?.environment ?? "Unavailable"} />
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Settings2 className="h-3.5 w-3.5" />
        Preferences are stored locally in this browser.
      </div>
    </div>
  );
}

export default Settings;