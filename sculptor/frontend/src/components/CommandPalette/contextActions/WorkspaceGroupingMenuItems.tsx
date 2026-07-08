// The grouping section at the top of the workspace row's context/dropdown
// menu (rendered only while the workspace-groups experiment is on): "New
// group from workspace" wraps the workspace in a fresh group, and the "Add to
// group" submenu lists the repo's existing groups (each with its color dot,
// the current membership checked/disabled) with a "New group…" escape hatch.
// A workspace already in a group also gets "Remove from group".
//
// Renders through the same dual menu primitives as the rest of the workspace
// menu (see WorkspaceMenuComponents in menu.tsx), so the right-click menu and
// the row's "⋯" dropdown stay in lockstep.

import { useAtomValue, useSetAtom } from "jotai";
import { Check } from "lucide-react";
import type { ReactElement } from "react";

import type { Workspace } from "~/api";
import { ElementIds } from "~/api";
import { workspaceGroupErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { workspaceGroupsForProjectAtomFamily } from "~/common/state/atoms/workspaceGroups.ts";
import {
  useAddWorkspaceGroupMemberMutation,
  useCreateWorkspaceGroupMutation,
  useRemoveWorkspaceGroupMemberMutation,
} from "~/common/state/mutations/workspaceGroups.ts";
import { ToastType } from "~/components/Toast.tsx";

import type { WorkspaceMenuComponents } from "./menu.tsx";
import styles from "./WorkspaceGroupingMenuItems.module.scss";

export const WorkspaceGroupingMenuItems = ({
  menu,
  workspace,
}: {
  menu: WorkspaceMenuComponents;
  workspace: Workspace;
}): ReactElement => {
  // External atoms
  const groups = useAtomValue(workspaceGroupsForProjectAtomFamily(workspace.projectId));
  const setGroupErrorToast = useSetAtom(workspaceGroupErrorToastAtom);

  // External hooks
  const createGroup = useCreateWorkspaceGroupMutation();
  const addMember = useAddWorkspaceGroupMemberMutation();
  const removeMember = useRemoveWorkspaceGroupMemberMutation();

  // Functions and callbacks
  // No optimistic write for any of these: membership truth lives on the
  // workspace and streams in on success, so the mutation's error state (and
  // this toast) is the entire failure path.
  const handleNewGroup = (): void => {
    createGroup.mutate(
      { projectId: workspace.projectId, workspaceIds: [workspace.objectId] },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: "Failed to create group",
            description: "The workspace is unchanged. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  const handleAddToGroup = (groupId: string, groupName: string): void => {
    addMember.mutate(
      { groupId, workspaceId: workspace.objectId },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: `Failed to add to "${groupName}"`,
            description: "The workspace is unchanged. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  const handleRemoveFromGroup = (): void => {
    if (workspace.groupId == null) {
      return;
    }
    removeMember.mutate(
      { groupId: workspace.groupId, workspaceId: workspace.objectId },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: "Failed to remove from group",
            description: "The workspace is unchanged. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  // JSX and rendering logic
  return (
    <>
      <menu.Item data-testid={ElementIds.WORKSPACE_MENU_NEW_GROUP} onSelect={handleNewGroup}>
        New group from workspace
      </menu.Item>
      <menu.Sub>
        <menu.SubTrigger data-testid={ElementIds.WORKSPACE_MENU_ADD_TO_GROUP}>Add to group</menu.SubTrigger>
        <menu.SubContent>
          {groups.length > 0 && <menu.Label>Move to group</menu.Label>}
          {groups.map((group) => {
            const isCurrentGroup = group.objectId === workspace.groupId;
            return (
              <menu.Item
                key={group.objectId}
                data-testid={ElementIds.WORKSPACE_MENU_ADD_TO_GROUP_ITEM}
                data-group-id={group.objectId}
                disabled={isCurrentGroup}
                onSelect={(): void => handleAddToGroup(group.objectId, group.name)}
              >
                <span className={styles.groupColorDot} data-accent-color={group.color} />
                {group.name}
                {isCurrentGroup ? <Check size={14} className={styles.currentGroupCheck} /> : null}
              </menu.Item>
            );
          })}
          {groups.length > 0 && <menu.Separator />}
          <menu.Item data-testid={ElementIds.WORKSPACE_MENU_ADD_TO_NEW_GROUP} onSelect={handleNewGroup}>
            New group…
          </menu.Item>
        </menu.SubContent>
      </menu.Sub>
      {workspace.groupId != null && (
        <menu.Item data-testid={ElementIds.WORKSPACE_MENU_REMOVE_FROM_GROUP} onSelect={handleRemoveFromGroup}>
          Remove from group
        </menu.Item>
      )}
      <menu.Separator />
    </>
  );
};
