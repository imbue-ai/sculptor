import type { ReactElement } from "react";
import { redirect } from "react-router-dom";
import { createHashRouter, RouterProvider } from "react-router-dom";

import type { TabEntry, TabsState } from "./common/state/atoms/workspaces.ts";
import {
  INVALID_ACTIVE_INDEX,
  isValidTabsState,
  parseDraftIdFromTabId,
  SCULPTOR_TABS_STORAGE_KEY,
  WORKSPACE_TAB_ID_PREFIX,
} from "./common/state/atoms/workspaces.ts";
import { COMPONENT_GALLERY_TAB_ID, HOME_TAB_ID, SETTINGS_TAB_ID } from "./components/workspaceTabIds.ts";
import { EmptyFirstRunGate } from "./EmptyFirstRunGate.tsx";
import { PageLayout } from "./layouts/PageLayout";
import { AddWorkspacePage } from "./pages/add-workspace/AddWorkspacePage.tsx";
import { ComponentGalleryPage } from "./pages/debug/ComponentGalleryPage.tsx";
import { NotFoundErrorPage } from "./pages/error/NotFound.tsx";
import { RouteErrorPage } from "./pages/error/RouteErrorPage.tsx";
import { HomePage } from "./pages/home/HomePage.tsx";
import { SettingsPage } from "./pages/settings/SettingsPage.tsx";
import { WorkspacePage } from "./pages/workspace/WorkspacePage";
import { WorkspaceShellLayout } from "./pages/workspace/WorkspaceShellLayout";

const DEFAULT_TABS_STATE: TabsState = { order: [], activeIndex: INVALID_ACTIVE_INDEX };

/**
 * Read `sculptor-tabs` synchronously from localStorage. Returns the empty
 * default on any parse / shape error so the loader always has something to
 * work with.  Intentionally separate from `tabsAtom` because the loader runs
 * before any React/Jotai code mounts.
 */
const readSculptorTabs = (): TabsState => {
  try {
    const raw = localStorage.getItem(SCULPTOR_TABS_STORAGE_KEY);
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
  const draftId = parseDraftIdFromTabId(entry.tabId);
  if (draftId !== null) return `/ws/new/${draftId}`;
  if (entry.tabId.startsWith(WORKSPACE_TAB_ID_PREFIX)) {
    return entry.agentId !== null ? `/ws/${entry.tabId}/agent/${entry.agentId}` : `/ws/${entry.tabId}`;
  }
  return null;
};

const rootLoader = (): Response => {
  const tabs = readSculptorTabs();
  const entry = tabs.order[tabs.activeIndex];
  if (!entry) return redirect("/ws/new");
  const target = entryToUrl(entry);
  return redirect(target ?? "/ws/new");
};

const router = createHashRouter([
  {
    path: "/",
    loader: rootLoader,
    errorElement: <RouteErrorPage />,
  },
  {
    path: "/ws/new",
    loader: (): Response => redirect(`/ws/new/${crypto.randomUUID()}`),
    errorElement: <RouteErrorPage />,
  },
  // Pathless layout route hosting every page destination. Its element
  // (`EmptyFirstRunGate`) renders the matched route normally unless the
  // workspace list is genuinely empty, in which case it swaps in the
  // EmptyFirstRunPage (FIRST-01) — except on Settings, which stays reachable.
  // The has-workspaces flow is unaffected: the gate falls through to <Outlet/>.
  {
    element: <EmptyFirstRunGate />,
    children: [
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
        path: "/ws/new/:draftId",
        element: <PageLayout />,
        errorElement: <RouteErrorPage />,
        children: [
          {
            index: true,
            element: <AddWorkspacePage />,
          },
        ],
      },
      {
        path: "/ws/:workspaceID",
        element: <WorkspaceShellLayout />,
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
