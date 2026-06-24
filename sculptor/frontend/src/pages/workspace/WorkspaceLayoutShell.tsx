// The desktop workspace shell (component_hierarchy.md → "The workspace layout
// shell"): the workspace header above the four-section grid, both wrapped in the
// app-level drag-and-drop context. The header is hidden while a section is
// maximized (the full maximize presentation lands in Task 4.3; here we just gate
// the render). Content components below the grid read no layout/route state.

import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { PanelDndProvider } from "~/components/sections/PanelDndProvider.tsx";
import { SectionGrid } from "~/components/sections/SectionGrid.tsx";
import { maximizedSectionAtom } from "~/components/sections/transientAtoms.ts";

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
    </PanelDndProvider>
  );
};
