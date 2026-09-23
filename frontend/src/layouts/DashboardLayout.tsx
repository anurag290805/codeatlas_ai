// src/layouts/DashboardLayout.tsx
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Navbar } from "@/components/layout/Navbar";
import { PageContainer } from "@/components/layout/PageContainer";
import { Sidebar } from "@/components/layout/Sidebar";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/repositories": "Repositories",
  "/chat": "AI Chat",
  "/graph": "Dependency Graph",
  "/analytics": "Analytics",
  "/settings": "Settings",
  "/search": "Search",
};

/**
 * Application shell composing the sidebar, top navigation, and routed
 * page content. Owns only shell-level state (the mobile sidebar
 * drawer) — page content and data fetching belong to individual routes.
 */
export function DashboardLayout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { pathname } = useLocation();

  const title =
    PAGE_TITLES[pathname] ??
    (pathname.includes("/dependencies")
      ? "Dependencies"
      : pathname.includes("/security")
        ? "Security Audit"
        : pathname.startsWith("/repositories/")
          ? "Repository Explorer"
          : pathname.startsWith("/chat")
            ? "AI Chat"
            : pathname.startsWith("/graph")
              ? "Dependency Graph"
              : pathname.startsWith("/analytics")
                ? "Analytics"
                : "CodeAtlas AI");

  return (
    <div className="flex min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:border focus:border-border focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:text-foreground focus:shadow-md"
      >
        Skip to content
      </a>

      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />

      <div className="flex h-screen min-h-0 flex-1 flex-col">
        <Navbar title={title} onMenuClick={() => setIsSidebarOpen(true)} />

        <main id="main-content" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto outline-none">
          <PageContainer fullHeight>
            <Outlet />
          </PageContainer>
        </main>
      </div>
    </div>
  );
}
