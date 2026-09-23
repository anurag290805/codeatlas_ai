import {
  BarChart3,
  FolderGit2,
  LayoutDashboard,
  MessageSquare,
  Network,
  Plus,
  Search,
  Settings,
  X,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useGlobalImport } from "@/components/common/useGlobalImport";
import { useVersion } from "@/hooks/useHealth";

interface NavItem {
  label: string;
  to: string;
  icon: typeof LayoutDashboard;
  /** When true, the item is active for any child route (e.g. chat/:id). */
  activeForPrefix?: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard },
      { label: "Repositories", to: "/repositories", icon: FolderGit2, activeForPrefix: "/repositories" },
      { label: "Search", to: "/search", icon: Search },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { label: "AI Chat", to: "/chat", icon: MessageSquare, activeForPrefix: "/chat" },
      { label: "Dependency Graph", to: "/graph", icon: Network, activeForPrefix: "/graph" },
      { label: "Analytics", to: "/analytics", icon: BarChart3, activeForPrefix: "/analytics" },
    ],
  },
  {
    label: "System",
    items: [{ label: "Settings", to: "/settings", icon: Settings }],
  },
];

/**
 * Monochrome active indicator — a quiet surface + a thin left accent
 * rail, the way Linear and GitHub nav treat selection. No filled pill
 * and no border: the rail and the stronger foreground carry the state.
 */
const ACTIVE_CLASS = "bg-sidebar-accent/65 text-sidebar-foreground";
const INACTIVE_CLASS = "text-sidebar-foreground/60 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground active:translate-y-px";

interface SidebarProps {
  /** Whether the mobile drawer is open. Ignored on desktop, where the sidebar is always visible. */
  isOpen?: boolean;
  /** Invoked when the mobile drawer should close. */
  onClose?: () => void;
}

/**
 * Primary application navigation. Renders as a fixed column on desktop
 * and a collapsible drawer on mobile. Navigation is grouped by
 * functional area so the product structure is legible at a glance, with
 * a primary import action and a quiet workspace footer.
 */
export function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const { openImport } = useGlobalImport();
  const version = useVersion();
  const backendVersion = version.data?.version
    ? `v${version.data.version}`
    : version.isLoading
      ? "v—"
      : "offline";

  const handleNav = () => onClose?.();

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[14.5rem] flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-200 ease-in-out",
          "md:sticky md:top-0 md:h-screen md:translate-x-0",
          isOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Primary navigation"
      >
        {/* Logo header — minimal, clean */}
        <div className="flex h-12 items-center justify-between border-b border-sidebar-border px-3.5">
          <a href="/" className="flex items-center gap-2.5 outline-none focus-visible:rounded focus-visible:ring-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
              <img
                src="/codeatlas-logo.png"
                alt="CodeAtlas"
                className="h-8 w-8 object-contain"
              />
            </span>
            <span className="text-[13px] font-semibold tracking-tight text-sidebar-foreground">
              CodeAtlas <span className="text-primary">AI</span>
            </span>
          </a>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={onClose}
            aria-label="Close navigation"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Import action — prominent but restrained */}
        <div className="border-b border-sidebar-border p-2.5">
          <Button
            onClick={() => {
              openImport();
              onClose?.();
            }}
            className="w-full gap-1.5 shadow-sm shadow-primary/15"
          >
            <Plus className="h-4 w-4" />
            Import repository
          </Button>
        </div>

        {/* Navigation groups — tight, scannable */}
        <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-5">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="space-y-1.5">
              <p className="t-label px-2.5">
                {group.label}
              </p>
              <div className="space-y-1">
                {group.items.map(({ label, to, icon: Icon, activeForPrefix }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={handleNav}
                    className="relative block"
                  >
                    {({ isActive }) => {
                      const active =
                        isActive ||
                        (activeForPrefix !== undefined &&
                          window.location.pathname.startsWith(activeForPrefix));
                      return (
                        <span
                          className={cn(
                            "relative flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-all duration-150 cursor-pointer",
                            active ? ACTIVE_CLASS : INACTIVE_CLASS,
                          )}
                        >
                          {active && (
                            <span
                              className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                              aria-hidden="true"
                            />
                          )}
                          <Icon
                            className={cn(
                              "h-4 w-4 shrink-0 transition-colors",
                              active ? "text-primary" : "text-sidebar-foreground/40",
                            )}
                            aria-hidden="true"
                          />
                          <span>{label}</span>
                        </span>
                      );
                    }}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Status footer — subdued, informational */}
        <div className="border-t border-sidebar-border p-2.5">
          <div className="flex items-center gap-2.5 rounded-lg border border-sidebar-border bg-sidebar-accent/40 px-3 py-2 text-xs">
            <span
              className={cn(
                "h-2 w-2 shrink-0 rounded-full ring-2 ring-offset-1 ring-offset-sidebar",
                version.isSuccess
                  ? "bg-success ring-success/30"
                  : "bg-muted-foreground ring-muted-foreground/20",
              )}
              aria-hidden="true"
            />
            <span className="flex-1 text-sidebar-foreground/75">
              {version.data?.environment === "production" ? "Production" : version.data?.environment === "staging" ? "Staging" : "Local"}
            </span>
            <span className="font-mono text-[11px] font-medium text-sidebar-foreground/60">{backendVersion}</span>
          </div>
        </div>
      </aside>
    </>
  );
}
