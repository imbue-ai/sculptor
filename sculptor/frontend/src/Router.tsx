import type { ReactElement } from "react";
import { redirect } from "react-router-dom";
import { createHashRouter, RouterProvider } from "react-router-dom";

import type { TabEntry, TabsState } from "./common/state/atoms/workspaces.ts";
import { INVALID_ACTIVE_INDEX } from "./common/state/atoms/workspaces.ts";
import { COMPONENT_GALLERY_TAB_ID, HOME_TAB_ID, SETTINGS_TAB_ID } from "./components/workspaceTabIds.ts";
import { PageLayout } from "./layouts/PageLayout";
import { ComponentGalleryPage } from "./pages/debug/ComponentGalleryPage.tsx";
import { NotFoundErrorPage } from "./pages/error/NotFound.tsx";
import { RouteErrorPage } from "./pages/error/RouteErrorPage.tsx";
import { HomePage } from "./pages/home/HomePage.tsx";
import { SettingsPage } from "./pages/settings/SettingsPage.tsx";
import { WorkspacePage } from "./pages/workspace/WorkspacePage";

const DEFAULT_TABS_STATE: TabsState = { order: [], activeIndex: INVALID_ACTIVE_INDEX };

const isValidTabsState = (value: unknown): value is TabsState => {
  if (value === null || typeof value !== "object") return false;
  const v = value as { order?: unknown; activeIndex?: unknown };
  if (!Array.isArray(v.order) || typeof v.activeIndex !== "number") return false;
  for (const entry of v.order) {
    if (entry === null || typeof entry !== "object") return false;
    const e = entry as { tabId?: unknown; agentId?: unknown };
    if (typeof e.tabId !== "string") return false;
    if (e.agentId !== null && typeof e.agentId !== "string") return false;
  }
  return true;
};

/**
 * Read `sculptor-tabs` synchronously from localStorage. Returns the empty
 * default on any parse / shape error so the loader always has something to
 * work with.  Intentionally separate from `tabsAtom` because the loader runs
 * before any React/Jotai code mounts.
 */
const readSculptorTabs = (): TabsState => {
  try {
    const raw = localStorage.getItem("sculptor-tabs");
    if (raw === null) return DEFAULT_TABS_STATE;
    const parsed: unknown = JSON.parse(raw);
    return isValidTabsState(parsed) ? parsed : DEFAULT_TABS_STATE;
  } catch {
    return DEFAULT_TABS_STATE;
  }
};

const entryToUrl = (entry: TabEntry): string | null => {
  if (entry.tabId === HOME_TAB_ID) return "/home";
  if (entry.tabId === SETTINGS_TAB_ID) return "/settings";
  if (entry.tabId === COMPONENT_GALLERY_TAB_ID) return "/component-gallery";
  if (entry.tabId.startsWith("ws_")) {
    return entry.agentId !== null ? `/ws/${entry.tabId}/agent/${entry.agentId}` : `/ws/${entry.tabId}`;
  }
  return null;
};

/**
 * No saved active tab (or it points at something we no longer route to —
 * e.g. a stale `__new_workspace_*__` draft tab from a pre-modal session).
 * Land on /home with `?firstLoad=true` so HomePage knows to pop the
 * new-workspace modal on top.
 */
const FALLBACK_REDIRECT = "/home?firstLoad=true";

const rootLoader = (): Response => {
  const tabs = readSculptorTabs();
  const entry = tabs.order[tabs.activeIndex];
  if (!entry) return redirect(FALLBACK_REDIRECT);
  const target = entryToUrl(entry);
  return redirect(target ?? FALLBACK_REDIRECT);
};

const router = createHashRouter([
  {
    path: "/",
    loader: rootLoader,
    errorElement: <RouteErrorPage />,
  },
  {
    path: "/home",
    element: <PageLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        element: <HomePage />,
      },
    ],
  },
  {
    path: "/ws/:workspaceID",
    element: <PageLayout showVersionIndicator={false} />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        element: <WorkspacePage />,
      },
      {
        path: "agent/:id",
        element: <WorkspacePage />,
      },
    ],
  },
  {
    path: "/settings",
    element: <PageLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        element: <SettingsPage />,
      },
    ],
  },
  {
    path: "/component-gallery",
    element: <PageLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        element: (
          <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <ComponentGalleryPage />
          </div>
        ),
      },
    ],
  },
  {
    path: "/debug/components",
    loader: (): Response => redirect("/debug/components/ws/gallery-demo/agent/demo"),
    errorElement: <RouteErrorPage />,
  },
  {
    path: "/debug/components/ws/:workspaceID/agent/:id",
    element: <ComponentGalleryPage />,
    errorElement: <RouteErrorPage />,
  },
  {
    path: "*",
    element: <NotFoundErrorPage />,
  },
]);

export const Router = (): ReactElement => {
  return <RouterProvider router={router} />;
};
