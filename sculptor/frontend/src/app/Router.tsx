import type { ReactElement } from "react";
import { redirect } from "react-router-dom";
import { createHashRouter, RouterProvider } from "react-router-dom";

import type { TabEntry, TabsState } from "../common/state/atoms/workspaces.ts";
import {
  INVALID_ACTIVE_INDEX,
  isValidTabsState,
  parseDraftIdFromTabId,
  SCULPTOR_TABS_STORAGE_KEY,
  WORKSPACE_TAB_ID_PREFIX,
} from "../common/state/atoms/workspaces.ts";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "../common/utils/workspaceTabIds.ts";
import { NotFoundErrorPage } from "../pages/error/NotFound.tsx";
import { RouteErrorPage } from "../pages/error/RouteErrorPage.tsx";
import { HomePage } from "../pages/home/HomePage.tsx";
import { SettingsPage } from "../pages/settings/SettingsPage.tsx";
import { WorkspacePage } from "../pages/workspace/WorkspacePage";
import { AppShell } from "./AppShell";
import { EmptyFirstRunGate } from "./EmptyFirstRunGate.tsx";

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
  const draftId = parseDraftIdFromTabId(entry.tabId);
  if (draftId !== null) return null;
  if (entry.tabId.startsWith(WORKSPACE_TAB_ID_PREFIX)) {
    return entry.agentId !== null ? `/ws/${entry.tabId}/agent/${entry.agentId}` : `/ws/${entry.tabId}`;
  }
  return null;
};

const rootLoader = (): Response => {
  const tabs = readSculptorTabs();
  const entry = tabs.order[tabs.activeIndex];
  if (!entry) return redirect("/home");
  const target = entryToUrl(entry);
  return redirect(target ?? "/home");
};

const router = createHashRouter([
  {
    path: "/",
    loader: rootLoader,
    errorElement: <RouteErrorPage />,
  },
  // Pathless layout route hosting every page destination. Its element
  // (`EmptyFirstRunGate`) renders the matched route normally unless the
  // workspace list is genuinely empty, in which case it swaps in the
  // EmptyFirstRunPage — except on Settings, which stays reachable.
  // The has-workspaces flow is unaffected: the gate falls through to <Outlet/>.
  {
    element: <EmptyFirstRunGate />,
    // The gate route is top-level, so its own subtree (EmptyFirstRunPage,
    // AutoUpdateToasts, the gate hooks) has no error boundary above it — give
    // it one here so a render error shows the styled RouteErrorPage instead of
    // React Router's default screen.
    errorElement: <RouteErrorPage />,
    children: [
      // The app-wide sidebar shell hosts Home, Settings, and the workspace route, so
      // the sidebar + chrome stay mounted as the user moves between them.
      {
        element: <AppShell />,
        errorElement: <RouteErrorPage />,
        children: [
          {
            path: "/home",
            element: <HomePage />,
          },
          {
            path: "/settings",
            element: <SettingsPage />,
          },
          {
            path: "/ws/:workspaceID",
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
        ],
      },
    ],
  },
  {
    path: "*",
    element: <NotFoundErrorPage />,
  },
]);

export const Router = (): ReactElement => {
  return <RouterProvider router={router} />;
};
