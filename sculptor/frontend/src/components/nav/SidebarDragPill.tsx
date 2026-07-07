// Non-interactive copies of a sidebar workspace row / repo-group header, drawn in
// the dnd-kit DragOverlay while one is dragged. Mirrors the panel-tab TabPill
// "overlay" variant — an elevated pill follows the cursor while the source element
// dims in place — so sidebar drags read the same as panel-tab drags.

import { useAtomValue } from "jotai";
import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";

import type { Workspace } from "~/api";
import { workspaceDotStatusAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { WorkspaceStatusDots } from "~/components/statusDot";

import styles from "./SidebarDragPill.module.scss";

export const WorkspaceRowDragPill = ({ workspace }: { workspace: Workspace }): ReactElement => {
  const status = useAtomValue(workspaceDotStatusAtomFamily(workspace.objectId));
  return (
    <div className={styles.pill}>
      <span className={styles.dot}>
        <WorkspaceStatusDots status={status} />
      </span>
      <span className={styles.label}>{workspace.description ?? "Untitled"}</span>
    </div>
  );
};

export const RepoGroupDragPill = ({ name }: { name: string }): ReactElement => (
  <div className={styles.pill}>
    <ChevronDown size={16} className={styles.chevron} />
    <span className={styles.label}>{name}</span>
  </div>
);
