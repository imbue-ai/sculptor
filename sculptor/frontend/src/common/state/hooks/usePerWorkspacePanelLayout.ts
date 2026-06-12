import { useSetAtom } from "jotai";
import { useLayoutEffect, useRef } from "react";

import { markSwitchMilestone } from "~/common/perf/workspaceSwitchProfiler.ts";
import { activeWorkspaceIdAtom, switchActiveWorkspaceAtom } from "~/components/panels/atoms.ts";
import type { DefaultPanelLayout } from "~/components/panels/types.ts";

/**
 * Panel layout is per-workspace (REQ-PERSIST-1): every layout atom (panel
 * positions, active panel, section visibility/split/sizes, diff-panel state)
 * is an atomFamily keyed by the active workspace, persisted under
 * workspace-scoped localStorage keys (see `scopedLayoutStorageFamily`).
 *
 * This hook keeps the active layout scope in sync with the route: it flips
 * `activeWorkspaceIdAtom` (via `switchActiveWorkspaceAtom`, which also seeds
 * the default layout on a workspace's first visit, REQ-DEFAULT-1) in a LAYOUT
 * effect so the entire layout switches in one pre-paint commit — the previous
 * workspace's panels never paint under the new workspace's URL. Dynamic panels
 * (the active agent, the terminal) are placed afterward by
 * `useWorkspaceLayoutBootstrap` in the same flush.
 *
 * Must be called inside WorkspacePageContent where `workspaceId` is known.
 */
export const usePerWorkspacePanelLayout = (workspaceId: string, defaultLayout: DefaultPanelLayout): void => {
  const switchActiveWorkspace = useSetAtom(switchActiveWorkspaceAtom);
  const setActiveWorkspaceId = useSetAtom(activeWorkspaceIdAtom);

  const defaultLayoutRef = useRef(defaultLayout);
  defaultLayoutRef.current = defaultLayout;

  useLayoutEffect(() => {
    switchActiveWorkspace({ workspaceId, defaultLayout: defaultLayoutRef.current });
    markSwitchMilestone("layout-restored");
    return (): void => {
      setActiveWorkspaceId(null);
    };
  }, [workspaceId, switchActiveWorkspace, setActiveWorkspaceId]);
};
