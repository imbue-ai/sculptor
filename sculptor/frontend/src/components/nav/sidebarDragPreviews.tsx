// The floating copies a sidebar drag shows under the pointer (rendered in the
// repo section's DragOverlay). The row/group left in the flow is an invisible
// placeholder holding the drop gap open; these previews carry the "picked up"
// read instead — solid surface, shadow, free movement on both axes.

import { Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import type { Workspace, WorkspaceGroup } from "~/api";
import { workspaceDotStatusAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { WorkspaceStatusDots } from "~/components/statusDot";

import styles from "./sidebarDragPreviews.module.scss";

const PreviewRow = ({ workspace }: { workspace: Workspace }): ReactElement => {
  const status = useAtomValue(workspaceDotStatusAtomFamily(workspace.objectId));
  return (
    <div className={styles.previewRow}>
      <span className={styles.previewDot}>
        <WorkspaceStatusDots status={status} />
      </span>
      <span className={styles.previewName}>{workspace.description ?? "Untitled"}</span>
    </div>
  );
};

/**
 * The floating card for a dragged workspace row. While the drop is projected
 * inside a group the card indents to member depth and borrows the group's
 * accent — the standard tree-drop cue, reinforcing the container surface
 * wrapping the gap (REQ-DND-6).
 */
export const WorkspaceRowDragPreview = ({
  workspace,
  projectedGroupAccent,
}: {
  workspace: Workspace;
  /** The projected target group's color, or undefined when the drop is loose. */
  projectedGroupAccent: string | undefined;
}): ReactElement => (
  <div
    className={`${styles.rowPreview} ${projectedGroupAccent !== undefined ? styles.rowPreviewNested : ""}`}
    data-accent-color={projectedGroupAccent}
  >
    <PreviewRow workspace={workspace} />
  </div>
);

/**
 * The floating card for a dragged group: the whole run travels as one unit
 * (REQ-DND-4) — header plus member rows, tinted in the group's accent like the
 * in-flow run it lifted out of.
 */
export const WorkspaceGroupDragPreview = ({
  group,
  members,
}: {
  group: WorkspaceGroup;
  members: ReadonlyArray<Workspace>;
}): ReactElement => (
  <div className={styles.groupPreview} data-accent-color={group.color}>
    <div className={styles.previewHeader}>
      <Text className={styles.previewGroupName} truncate>
        {group.name}
      </Text>
    </div>
    {members.map((member) => (
      <div key={member.objectId} className={styles.previewMember}>
        <PreviewRow workspace={member} />
      </div>
    ))}
  </div>
);
