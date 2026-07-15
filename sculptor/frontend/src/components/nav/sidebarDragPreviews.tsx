// The floating copies a sidebar drag shows under the pointer (rendered in the
// repo section's DragOverlay). The row/group left in the flow is an invisible
// placeholder holding the drop gap open; these previews carry the "picked up"
// read instead. They are built from the REAL row and card chrome — the same
// SCSS modules the in-flow elements use — so the dragged copy is a faithful,
// non-interactive clone of what was picked up (chevron, badges, and action
// affordances included), with only a lift treatment (solid surface, shadow,
// free movement) layered on top.

import { Flex, IconButton, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { ChevronDown, ChevronRight, MoreHorizontal } from "lucide-react";
import type { ReactElement } from "react";

import type { Workspace, WorkspaceGroup } from "~/api";
import { workspaceDotStatusAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { WorkspaceStatusDots } from "~/components/statusDot";

import styles from "./sidebarDragPreviews.module.scss";
import rowStyles from "./SidebarRepoGroup.module.scss";
import cardStyles from "./WorkspaceGroupCard.module.scss";

/**
 * A non-interactive clone of a workspace row (status dots + name) in the real
 * row chrome. The hover-revealed action buttons are omitted: they are
 * invisible on a resting row, which is what a picked-up copy portrays.
 */
const PreviewWorkspaceRow = ({
  workspace,
  isGroupMember = false,
}: {
  workspace: Workspace;
  isGroupMember?: boolean;
}): ReactElement => {
  const status = useAtomValue(workspaceDotStatusAtomFamily(workspace.objectId));
  return (
    <div className={`${rowStyles.workspaceRow} ${isGroupMember ? rowStyles.workspaceRowNested : ""}`}>
      <span className={rowStyles.workspaceRowButton}>
        <span className={rowStyles.workspaceDot}>
          <WorkspaceStatusDots status={status} />
        </span>
        <span className={rowStyles.workspaceName}>{workspace.description ?? "Untitled"}</span>
      </span>
    </div>
  );
};

/**
 * The floating card for a dragged workspace row. While the drop is projected
 * inside a group the card borrows the group's accent as a membership cue —
 * tint ONLY: the dragged content's layout never changes mid-drag.
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
    <PreviewWorkspaceRow workspace={workspace} />
  </div>
);

/**
 * The floating card for a dragged group: the whole run travels as one unit
 * (REQ-DND-4) in the group card's own chrome — chevron, accent name, CLI
 * chip, and the "⋯" affordance. A collapsed group travels as just its header,
 * exactly like the collapsed card it lifted out of.
 */
export const WorkspaceGroupDragPreview = ({
  group,
  members,
  isCollapsed,
}: {
  group: WorkspaceGroup;
  members: ReadonlyArray<Workspace>;
  isCollapsed: boolean;
}): ReactElement => {
  const Chevron = isCollapsed ? ChevronRight : ChevronDown;
  return (
    <div className={`${cardStyles.groupCard} ${styles.groupPreview}`} data-accent-color={group.color}>
      <div className={cardStyles.groupHeader}>
        <span className={cardStyles.groupHeaderButton}>
          <Chevron size={15} className={cardStyles.groupChevron} />
          <Text className={cardStyles.groupName} truncate>
            {group.name}
          </Text>
          {group.createdViaCli === true && <span className={cardStyles.cliBadge}>CLI</span>}
        </span>
        <Flex className={cardStyles.rowActions}>
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            className={rowStyles.rowActionButton}
            aria-hidden
            tabIndex={-1}
          >
            <MoreHorizontal size={12} />
          </IconButton>
        </Flex>
      </div>
      {!isCollapsed && members.length > 0 && (
        <div className={cardStyles.groupMembers}>
          {members.map((member) => (
            <PreviewWorkspaceRow key={member.objectId} workspace={member} isGroupMember />
          ))}
        </div>
      )}
    </div>
  );
};
