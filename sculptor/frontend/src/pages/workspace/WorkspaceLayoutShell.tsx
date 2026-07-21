// The desktop workspace shell: the workspace header above the four-section grid,
// both wrapped in the app-level drag-and-drop context. The header is hidden while
// a section is maximized (the full maximize presentation is handled elsewhere;
// here we just gate the render). Content components below the grid read no
// layout/route state.

// Side-effect import: registers the panel components (agent, …) with the registry.
import "./panels/registerPanels.ts";

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { PanelDndProvider } from "~/components/sections/PanelDndProvider.tsx";
import { useOrphanedLayoutGc } from "~/components/sections/persistence/orphanedLayoutGc.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import { SectionGrid } from "~/components/sections/SectionGrid.tsx";
import { isAnySectionMaximizedAtom } from "~/components/sections/transientAtoms.ts";
import { useActiveSectionRing } from "~/components/sections/useActiveSectionRing.ts";
import { useLayoutShortcutDispatcher } from "~/components/sections/useLayoutShortcutDispatcher.ts";
import { useWorkspaceShortcuts } from "~/components/sections/useWorkspaceShortcuts.ts";

import { AgentDeleteConfirmation } from "./components/AgentDeleteConfirmation.tsx";
import { TerminalCloseConfirmation } from "./components/TerminalCloseConfirmation.tsx";
import { WorkspaceHeader } from "./WorkspaceHeader.tsx";
import styles from "./WorkspaceLayoutShell.module.scss";

export const WorkspaceLayoutShell = (): ReactElement => {
  const isMaximized = useAtomValue(isAnySectionMaximizedAtom);
  // Settle signal for the first-commit workspace-switch transient. On a workspace
  // switch the route changes a render before the layout scope flips: the flip lands
  // in useWorkspaceShellBootstrap's layout effect (switchActiveWorkspaceAtom), so the
  // first commit after the new route still renders the PREVIOUS workspace's panels.
  // Stamping activeWorkspaceIdAtom — the post-flip scope, NOT the route — means this
  // attribute equals the target id only once the layout atoms describe the new
  // workspace. Tests and tools key on it to know a switch has settled before
  // snapshotting panels (see navigate_to_workspace in playwright_utils.py).
  const activeWorkspaceId = useAtomValue(activeWorkspaceIdAtom);

  // The active-section ring fade timer, mounted once for the whole shell.
  useActiveSectionRing();
  // The new-shell section/panel keyboard shortcuts (collapse/cycle/maximize/sidebar/
  // new-agent), registered through the keybindings registry.
  useWorkspaceShortcuts();
  // Per-Layout "apply" shortcuts (dynamic, not in the static registry).
  useLayoutShortcutDispatcher();
  // Once-per-session idle sweep of layout snapshots whose workspace no longer exists.
  useOrphanedLayoutGc();

  return (
    <PanelDndProvider>
      <div className={styles.shell} data-active-workspace-id={activeWorkspaceId ?? ""}>
        {!isMaximized && <WorkspaceHeader />}
        <SectionGrid />
      </div>
      {/* Headless owners of the panel-tab close confirmations, driven by the shared
          close-target atoms set from a tab's close button: the terminal close
          confirmation and the agent delete confirmation. */}
      <TerminalCloseConfirmation />
      <AgentDeleteConfirmation />
    </PanelDndProvider>
  );
};
