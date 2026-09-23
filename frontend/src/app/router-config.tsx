import { createElement, lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";
import { DashboardLayout as dashboardLayout } from "@/layouts/DashboardLayout";
import { NotFound as notFound } from "@/pages/NotFound";

const dashboard = lazy(() => import("@/pages/Dashboard"));
const repositories = lazy(() => import("@/pages/Repositories"));
const search = lazy(() => import("@/pages/Search"));
const repository = lazy(() => import("@/pages/Repository").then((module) => ({ default: module.Repository })));
const chat = lazy(() => import("@/pages/Chat"));
const graph = lazy(() => import("@/pages/Graph"));
const analytics = lazy(() => import("@/pages/Analytics"));
const settings = lazy(() => import("@/pages/Settings"));
const dependencies = lazy(() => import("@/pages/Dependencies"));
const security = lazy(() => import("@/pages/Security"));

function withSuspense(element: ReactNode) {
  return <Suspense fallback={<div className="flex min-h-[20rem] items-center justify-center text-sm text-muted-foreground" role="status">Loading workspace…</div>}>{element}</Suspense>;
}

export const router = createBrowserRouter([{ path: "/", element: createElement(dashboardLayout), errorElement: createElement(notFound), children: [
  { index: true, element: withSuspense(createElement(dashboard)) },
  { path: "repositories", element: withSuspense(createElement(repositories)) },
  { path: "repositories/:repositoryId", element: withSuspense(createElement(repository)) },
  { path: "repositories/:repositoryId/dependencies", element: withSuspense(createElement(dependencies)) },
  { path: "repositories/:repositoryId/security", element: withSuspense(createElement(security)) },
  { path: "search", element: withSuspense(createElement(search)) },
  { path: "chat", element: withSuspense(createElement(chat)) },
  { path: "chat/:repositoryId", element: withSuspense(createElement(chat)) },
  { path: "graph", element: withSuspense(createElement(graph)) },
  { path: "graph/:repositoryId", element: withSuspense(createElement(graph)) },
  { path: "analytics", element: withSuspense(createElement(analytics)) },
  { path: "analytics/:repositoryId", element: withSuspense(createElement(analytics)) },
  { path: "settings", element: withSuspense(createElement(settings)) },
  { path: "*", element: createElement(notFound) },
]}]);
