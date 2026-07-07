// Non-interactive copies of a sidebar workspace row / repo-group header, drawn in
// the dnd-kit DragOverlay while one is dragged. Each is a full-width replica of the
// element it copies — same layout, indent, and metrics as the real row — elevated
// with the same shadow language as the panel-tab drag overlay (TabPill), so the
// drag reads as "the row itself is moving".

import { useAtomValue } from "jotai";
import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";

import type { Workspace } from "~/api";
import { workspaceDotStatusAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { WorkspaceStatusDots } from "~/components/statusDot";

import styles from "./SidebarDragPreview.module.scss";

export const WorkspaceRowDragPreview = ({ workspace }: { workspace: Workspace }): ReactElement => {
  const status = useAtomValue(workspaceDotStatusAtomFamily(workspace.objectId));
  return (
    <div className={`${styles.preview} ${styles.workspaceRow}`}>
      <span className={styles.dot}>
        <WorkspaceStatusDots status={status} />
      </span>
      <span className={styles.label}>{workspace.description ?? "Untitled"}</span>
    </div>
  );
};

export const RepoGroupHeaderDragPreview = ({ name }: { name: string }): ReactElement => (
  <div className={`${styles.preview} ${styles.repoHeader}`}>
    <ChevronDown size={16} className={styles.chevron} />
    <span className={styles.label}>{name}</span>
  </div>
);
