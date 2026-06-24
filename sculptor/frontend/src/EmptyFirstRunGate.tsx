import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { Outlet } from "react-router-dom";

import { useImbueLocation } from "./common/NavigateUtils.ts";
import { isWorkspaceListEmptyAtom } from "./components/newWorkspace/newWorkspaceAtoms.ts";
import { EmptyFirstRunPage } from "./pages/workspace/EmptyFirstRunPage.tsx";

/**
 * App gate for the empty first-run experience (FIRST-01/FIRST-05). Wraps every
 * page route. When the workspace list is genuinely empty it renders
 * `EmptyFirstRunPage` instead of the matched route, so the post-onboarding /
 * post-signup landing (and any other destination) shows the inline new-workspace
 * form with the sidebar open. Settings stays reachable so the user can still
 * reach preferences — it's the one allowed destination in the empty state.
 *
 * `isWorkspaceListEmptyAtom` is `false` while the workspace list is still
 * loading (`undefined`) and whenever any workspace exists, so this is a no-op
 * for the entire has-workspaces flow — the matched route renders unchanged, and
 * the empty page never flashes during load. Once the first workspace is created
 * the atom flips false and the normal layouts take back over (FIRST-05).
 */
export const EmptyFirstRunGate = (): ReactElement => {
  const isWorkspaceListEmpty = useAtomValue(isWorkspaceListEmptyAtom);
  const { isSettingsRoute } = useImbueLocation();

  if (isWorkspaceListEmpty && !isSettingsRoute) {
    return <EmptyFirstRunPage />;
  }

  return <Outlet />;
};
