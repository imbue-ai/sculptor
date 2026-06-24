// The desktop workspace shell (component_hierarchy.md → "The workspace layout
// shell"): the workspace header above the four-section grid, both wrapped in the
// app-level drag-and-drop context. The header is hidden while a section is
// maximized (the full maximize presentation lands in Task 4.3; here we just gate
// the render). Content components below the grid read no layout/route state.

// Side-effect import: registers the panel components (agent, …) with the registry.
import "./panels/registerPanels.ts";

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { PanelDndProvider } from "~/components/sections/PanelDndProvider.tsx";
import { SectionGrid } from "~/components/sections/SectionGrid.tsx";
import { maximizedSectionAtom } from "~/components/sections/transientAtoms.ts";

import { AgentDeleteConfirmation } from "./components/AgentDeleteConfirmation.tsx";
import { TerminalCloseConfirmation } from "./components/TerminalCloseConfirmation.tsx";
import { WorkspaceHeader } from "./WorkspaceHeader.tsx";
import styles from "./WorkspaceLayoutShell.module.scss";

export const WorkspaceLayoutShell = (): ReactElement => {
  const maximizedSection = useAtomValue(maximizedSectionAtom);
  const isMaximized = maximizedSection !== null;

  return (
    <PanelDndProvider>
      <div className={styles.shell}>
        {!isMaximized && <WorkspaceHeader />}
        <SectionGrid />
      </div>
      {/* Headless owners of the panel-tab close confirmations, driven by the shared
          close-target atoms set from a tab's close button: the terminal close
          confirmation (TERM-02) and the agent delete confirmation (AGENT-04). */}
      <TerminalCloseConfirmation />
      <AgentDeleteConfirmation />
    </PanelDndProvider>
  );
};
