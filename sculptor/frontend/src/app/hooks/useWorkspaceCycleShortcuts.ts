// Workspace cycling (Meta+] / Meta+[ and the palette's Next/Previous workspace rows).
// Mounted by AppShell, which renders on every sidebar-bearing route, so cycling works
// from Home and Settings — not only workspace pages. The keybinding and the palette
// command action share one implementation, and both step through the sidebar's
// visible order (sidebarOrderedWorkspacesAtom) so a jump always lands on a visually
// adjacent workspace. Reads live state through the Jotai store at press time to avoid
// stale closures and per-keystroke re-subscription, and anchors on the URL hash rather
// than activeWorkspaceIdAtom so rapid presses cycle from the live route (see
// getWorkspaceIdFromHash).

import { useSetAtom, useStore } from "jotai";
import { useCallback } from "react";

import { sidebarOrderedWorkspacesAtom } from "~/app/nav/sidebarWorkspaceOrder.ts";
import { useKeybindingHandler } from "~/common/keybindings";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { openWorkspaceTabAtom } from "~/common/state/atoms/workspaces.ts";
import { useRegisterCommandAction } from "~/components/commandPalette/utils/commandActions.ts";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

type CycleDirection = 1 | -1;

// A missing current (-1) anchors at index 0, so the step lands on the neighbour of the
// first element (forward → second, backward → last).
const stepIndex = (length: number, current: number, direction: CycleDirection): number => {
  const base = current === -1 ? 0 : current;
  return (base + direction + length) % length;
};

// The workspace id in the current URL hash, or null off workspace routes (Home,
// Settings). Matches the hash router's "#/ws/<id>[/agent/<id>]" shape, excluding
// "new" the same way NavigateUtils' isWorkspaceRoute does (a legacy /ws/new/...
// URL names a draft, not a workspace).
const getWorkspaceIdFromHash = (): string | null => {
  const pathname = window.location.hash.replace(/^#/, "").split("?")[0] ?? "";
  return pathname.match(/^\/ws\/(?!new\b)([^/]+)/)?.[1] ?? null;
};

export const useWorkspaceCycleShortcuts = (): void => {
  const store = useStore();
  const openWorkspaceTab = useSetAtom(openWorkspaceTabAtom);
  const { navigateToWorkspace } = useImbueNavigate();

  // Cycle to the adjacent workspace in the sidebar order, wrapping at the ends.
  // Opening the tab before navigating gives keyboard cycling the same end state as
  // clicking the workspace in the sidebar (the palette's navigate does the same).
  const cycleWorkspace = useCallback(
    (direction: CycleDirection): void => {
      const workspaces = store.get(sidebarOrderedWorkspacesAtom);
      if (workspaces.length < 2) {
        return;
      }
      // Anchor on the hash, not activeWorkspaceIdAtom: navigateToWorkspace updates
      // the hash synchronously, while the atom is only written by a layout effect
      // after React commits, so on a rapid second press the atom still names the
      // workspace the first press left. Off workspace routes (Home/Settings) the
      // hash has no workspace id and the atom anchors cycling at the last-visited
      // workspace.
      const currentId = getWorkspaceIdFromHash() ?? store.get(activeWorkspaceIdAtom);
      const currentIndex = workspaces.findIndex((workspace) => workspace.objectId === currentId);
      const next = workspaces[stepIndex(workspaces.length, currentIndex, direction)];
      openWorkspaceTab(next.objectId);
      navigateToWorkspace(next.objectId);
    },
    [store, openWorkspaceTab, navigateToWorkspace],
  );

  // next_tab/previous_tab keep their legacy ids (see definitions.ts).
  useKeybindingHandler(
    "next_tab",
    useCallback(() => cycleWorkspace(1), [cycleWorkspace]),
  );
  useKeybindingHandler(
    "previous_tab",
    useCallback(() => cycleWorkspace(-1), [cycleWorkspace]),
  );
  // The palette's "Next/Previous workspace" rows dispatch through the command-action
  // registry (runtime.ui.nextWorkspaceTab → "workspace.nextTab"), so register the same
  // handlers there — one implementation for the keybinding and the palette.
  useRegisterCommandAction(
    "workspace.nextTab",
    useCallback(() => cycleWorkspace(1), [cycleWorkspace]),
  );
  useRegisterCommandAction(
    "workspace.previousTab",
    useCallback(() => cycleWorkspace(-1), [cycleWorkspace]),
  );
};
