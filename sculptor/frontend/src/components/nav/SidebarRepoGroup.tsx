// One collapsible repo group in the workspace sidebar: the repo header row (collapse
// chevron, hover-revealed repository settings, and an always-visible "+" that
// direct-creates a workspace in this repo, falling back to the new-workspace dialog
// pre-scoped to the repo when the branch can't be resolved or the create fails),
// followed by the repo's children while expanded. The children are one mixed,
// re-orderable lane: loose workspace rows interleaved with workspace-group cards,
// composed in visible order by sidebarWorkspaceOrder (with the workspace-groups
// flag off the lane is exactly the workspace rows). Cross-group concerns — building
// the groups, the shared action list, and the delete confirmation — stay in
// WorkspaceSidebar and arrive as props; per-group state (collapse, rename) is read
// from its atoms here.
//
// The group is itself a sortable item of WorkspaceSidebar's repo-group DndContext
// (dragged by its header), and it hosts its OWN DndContext for its children — a
// workspace belongs to its repo, so scoping the children context per repo section
// makes cross-repo drops structurally impossible rather than merely rejected.
// Within the section, though, rows travel BETWEEN containers (the loose lane and
// the group cards): such a drop is a membership change, so it flips membership
// through the canonical mutation and only then commits the visual order (see
// handleSectionDragEnd).

import type { DragEndEvent } from "@dnd-kit/core";
import { closestCenter, DndContext, useDndContext, useDroppable } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { ChevronDown, ChevronRight, Plus, Settings } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef } from "react";

import type { Workspace } from "~/api";
import { ElementIds, updateWorkspace } from "~/api";
import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { workspaceGroupErrorToastAtom, workspaceRenameErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import {
  useAddWorkspaceGroupMemberMutation,
  useRemoveWorkspaceGroupMemberMutation,
} from "~/common/state/mutations/workspaceGroups.ts";
import { renamingWorkspaceIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { OpenInRuntime } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceAction } from "~/components/CommandPalette/contextActions/types.ts";
import { useCreateWorkspaceFromSidebar } from "~/components/newWorkspace/useCreateWorkspaceFromSidebar.ts";
import { ToastType } from "~/components/Toast.tsx";

import { adjustSidebarDragCountAtom, collapsedRepoGroupsAtom, isRepoCollapsedAtomFamily } from "./navAtoms.ts";
import {
  buildRepoSectionDndModifiers,
  getSidebarDragData,
  LOOSE_CONTAINER_ID,
  REPO_SECTION_RELEASE_SLOT_ID,
  useSidebarDndSensors,
} from "./sidebarDnd.ts";
import styles from "./SidebarRepoGroup.module.scss";
import type { RepoGroup } from "./sidebarWorkspaceOrder.ts";
import {
  commitWorkspaceMembershipOrderAtom,
  reorderSidebarRepoChildAtom,
  reorderWorkspaceGroupMemberAtom,
} from "./sidebarWorkspaceOrder.ts";
import { SidebarWorkspaceRow } from "./SidebarWorkspaceRow.tsx";
import { WorkspaceGroupCard } from "./WorkspaceGroupCard.tsx";
import { repoSectionChildKey } from "./workspaceGroupComposition.ts";

/**
 * The dashed "Drop to remove from group" slot at the end of the section's
 * children while a member row is dragged. It is the release drop target that
 * always exists (loose rows are targets too, but there may be none) and the
 * only way to drop a released row at the END of the lane (dropping on a loose
 * row inserts before it). Tinted in the dragged member's group color via the
 * accent stamp. Mounted for the whole drag, like the group cards' drop slots.
 */
const RepoSectionReleaseSlot = (): ReactElement | null => {
  const { active } = useDndContext();
  const activeData = getSidebarDragData(active ?? null);
  const isMemberDragActive = activeData?.sidebarKind === "workspace" && activeData.containerId !== LOOSE_CONTAINER_ID;
  const { setNodeRef, isOver } = useDroppable({
    id: REPO_SECTION_RELEASE_SLOT_ID,
    disabled: !isMemberDragActive,
    data: { sidebarKind: "release-slot" },
  });
  if (!isMemberDragActive) {
    return null;
  }
  return (
    <div
      ref={setNodeRef}
      className={styles.releaseSlot}
      data-accent-color={activeData.accentColor}
      data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_RELEASE_SLOT}
      data-drop-active={isOver ? "true" : undefined}
    >
      Drop to remove from group
    </div>
  );
};

type SidebarRepoGroupProps = {
  group: RepoGroup;
  // The shared workspace action list (rename/delete/git/open-in), built once in
  // WorkspaceSidebar so every group and the command palette agree on the entries.
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
  // Whether to render the per-repo header actions (settings gear + direct-create
  // "+"). Suppressed on the first-run page: that page doesn't mount AppShell, so
  // the "+"'s dialog fallback and its error toast wouldn't render — the inline
  // first-run form is the only create affordance while the workspace list is empty.
  showActions: boolean;
  onWorkspaceClick: (workspaceId: string) => void;
  onWorkspaceHover: (workspaceId: string) => void;
  // Delete is confirmed by a dialog owned by WorkspaceSidebar (shared across
  // groups), so beginning one hands the target back up.
  onBeginDelete: (workspace: Workspace) => void;
};

export const SidebarRepoGroup = ({
  group,
  actions,
  openInRuntime,
  showActions,
  onWorkspaceClick,
  onWorkspaceHover,
  onBeginDelete,
}: SidebarRepoGroupProps): ReactElement => {
  // External atoms
  const isRepoCollapsed = useAtomValue(isRepoCollapsedAtomFamily(group.projectId));
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);
  const setRenameErrorToast = useSetAtom(workspaceRenameErrorToastAtom);
  const setGroupErrorToast = useSetAtom(workspaceGroupErrorToastAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
  const adjustDragCount = useSetAtom(adjustSidebarDragCountAtom);
  const reorderRepoChild = useSetAtom(reorderSidebarRepoChildAtom);
  const reorderGroupMember = useSetAtom(reorderWorkspaceGroupMemberAtom);
  const commitMembershipOrder = useSetAtom(commitWorkspaceMembershipOrderAtom);
  const store = useStore();

  // Membership is a backend fact: a drop that moves a row into or out of a
  // group goes through these mutations, and the order lanes are only written
  // once the server confirms (see handleSectionDragEnd).
  const { mutate: addGroupMember } = useAddWorkspaceGroupMemberMutation();
  const { mutate: removeGroupMember } = useRemoveWorkspaceGroupMemberMutation();

  // Whether the in-flight sidebar drag was started by THIS group's children
  // context. Every drag context adjusts the shared drag count, so
  // end/cancel/cleanup must only decrement for a drag they own — an unowning
  // cleanup (collapsing a different group mid-drag) would otherwise release
  // another context's drag.
  const ownsActiveDragRef = useRef(false);
  const beginOwnedDrag = useCallback((): void => {
    if (!ownsActiveDragRef.current) {
      ownsActiveDragRef.current = true;
      adjustDragCount(1);
    }
  }, [adjustDragCount]);
  const endOwnedDrag = useCallback((): void => {
    if (ownsActiveDragRef.current) {
      ownsActiveDragRef.current = false;
      adjustDragCount(-1);
    }
  }, [adjustDragCount]);

  // External hooks
  const openSettings = useOpenSettings();
  const { workspaceId: activeWorkspaceId } = useImbueLocation();
  const dangerColor = useThemeDangerColor();

  // The group is a sortable item of WorkspaceSidebar's repo-group context: the
  // whole group (header + children) is the measured node so its children travel
  // with it, and the header button is the drag activator.
  const {
    attributes: groupAttributes,
    listeners: groupListeners,
    setNodeRef: setGroupNodeRef,
    setActivatorNodeRef: setGroupActivatorNodeRef,
    transform: groupTransform,
    transition: groupTransition,
    isDragging: isGroupDragging,
    isOver: isGroupOver,
  } = useSortable({ id: group.projectId });

  // The children's own drag context; see the module comment for why it lives
  // per repo section. Its modifiers clamp a dragged child to the children box
  // (measured live), which is what lets a row cross between the loose lane and
  // the group cards without ever leaving its repo section.
  const rowDndSensors = useSidebarDndSensors();
  const sectionChildrenRef = useRef<HTMLDivElement | null>(null);
  // eslint-disable-next-line react-hooks/refs -- the modifier factory only closes over the ref; .current is read inside the modifier, which dnd-kit invokes on drag moves (event time), never during render.
  const sectionDndModifiers = useMemo(() => buildRepoSectionDndModifiers(sectionChildrenRef), []);

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedRepos((prev) => ({ ...prev, [group.projectId]: !(prev[group.projectId] ?? false) }));
  };

  // Enter toggles collapse from the keyboard, like a click; every other key falls
  // through to the dnd-kit keyboard sensor so Space picks the group up (see the
  // matching handler on SidebarWorkspaceRow).
  const handleHeaderKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isGroupDragging) {
      event.preventDefault();
      handleToggleCollapsed();
      return;
    }
    groupListeners?.onKeyDown?.(event);
  };

  // Resolve a drop within the section: a reorder inside one container commits
  // its lane directly; a drop that crosses containers is a membership change,
  // so it flips membership through the canonical mutation and commits the
  // destination lane only on success — a rejected drop (409, network) leaves
  // the lanes untouched, so the order can never claim a membership the server
  // refused. Classification rides on the drag data every sortable/droppable in
  // the section registers (see sidebarDnd.ts).
  const handleSectionDragEnd = useCallback(
    (event: DragEndEvent): void => {
      endOwnedDrag();
      const { active, over } = event;
      if (over === null || over.id === active.id) {
        return;
      }
      const activeId = String(active.id);
      const overId = String(over.id);
      const activeData = getSidebarDragData(active);
      const overData = getSidebarDragData(over);

      const findWorkspaceName = (workspaceId: string): string => {
        for (const child of group.children) {
          if (child.kind === "workspace" && child.workspace.objectId === workspaceId) {
            return child.workspace.description ?? "workspace";
          }

          if (child.kind === "group") {
            const member = child.members.find((candidate) => candidate.objectId === workspaceId);
            if (member !== undefined) {
              return member.description ?? "workspace";
            }
          }
        }
        return "workspace";
      };

      const findGroupName = (groupId: string): string => {
        const child = group.children.find(
          (candidate) => candidate.kind === "group" && candidate.group.objectId === groupId,
        );
        return child?.kind === "group" ? child.group.name : "group";
      };

      const moveIntoGroup = (workspaceId: string, groupId: string, beforeWorkspaceId: string | undefined): void => {
        // One mutation covers loose→group AND group→group: the backend moves a
        // workspace that is already in another group, dissolving the source if
        // that empties it.
        addGroupMember(
          { groupId, workspaceId },
          {
            onSuccess: (): void =>
              commitMembershipOrder({
                projectId: group.projectId,
                workspaceId,
                target: { kind: "group", groupId, beforeWorkspaceId },
              }),
            onError: (): void =>
              setGroupErrorToast({
                title: `Failed to move "${findWorkspaceName(workspaceId)}" into "${findGroupName(groupId)}"`,
                description: "The workspace was left where it was. Try again or check your connection.",
                type: ToastType.ERROR_PROMINENT,
                action: null,
              }),
          },
        );
      };

      const releaseFromGroup = (workspaceId: string, groupId: string, beforeChildId: string | undefined): void => {
        removeGroupMember(
          { groupId, workspaceId },
          {
            onSuccess: (): void =>
              commitMembershipOrder({
                projectId: group.projectId,
                workspaceId,
                target: { kind: "loose", beforeChildId },
              }),
            onError: (): void =>
              setGroupErrorToast({
                title: `Failed to remove "${findWorkspaceName(workspaceId)}" from its group`,
                description: "The workspace was left where it was. Try again or check your connection.",
                type: ToastType.ERROR_PROMINENT,
                action: null,
              }),
          },
        );
      };

      // A group card drags only within the mixed lane. A drop on a member row
      // or drop slot means the pointer rests inside another card — take that
      // card's slot in the lane.
      if (activeData?.sidebarKind === "workspace-group") {
        const overLaneKey =
          overData?.sidebarKind === "workspace-group"
            ? overId
            : overData?.sidebarKind === "workspace"
              ? overData.containerId === LOOSE_CONTAINER_ID
                ? overId
                : overData.containerId
              : overData?.sidebarKind === "workspace-group-drop-slot"
                ? overData.groupId
                : null;
        if (overLaneKey !== null && overLaneKey !== activeId) {
          reorderRepoChild({ projectId: group.projectId, activeChildId: activeId, overChildId: overLaneKey });
        }
        return;
      }

      if (activeData?.sidebarKind !== "workspace") {
        return;
      }
      const sourceContainerId = activeData.containerId;

      if (overData?.sidebarKind === "workspace") {
        if (overData.containerId === sourceContainerId) {
          // Same container: a plain reorder of whichever lane both rows share.
          if (sourceContainerId === LOOSE_CONTAINER_ID) {
            reorderRepoChild({ projectId: group.projectId, activeChildId: activeId, overChildId: overId });
          } else {
            reorderGroupMember({
              projectId: group.projectId,
              groupId: sourceContainerId,
              activeWorkspaceId: activeId,
              overWorkspaceId: overId,
            });
          }
          return;
        }

        // Cross-container onto a row: join that row's container, taking its slot.
        if (overData.containerId === LOOSE_CONTAINER_ID) {
          releaseFromGroup(activeId, sourceContainerId, overId);
        } else {
          moveIntoGroup(activeId, overData.containerId, overId);
        }
        return;
      }

      if (overData?.sidebarKind === "workspace-group" && overId !== sourceContainerId) {
        moveIntoGroup(activeId, overId, undefined);
        return;
      }

      if (overData?.sidebarKind === "workspace-group-drop-slot" && overData.groupId !== sourceContainerId) {
        moveIntoGroup(activeId, overData.groupId, undefined);
        return;
      }

      if (overData?.sidebarKind === "release-slot" && sourceContainerId !== LOOSE_CONTAINER_ID) {
        releaseFromGroup(activeId, sourceContainerId, undefined);
      }
    },
    [
      endOwnedDrag,
      group.projectId,
      group.children,
      reorderRepoChild,
      reorderGroupMember,
      commitMembershipOrder,
      addGroupMember,
      removeGroupMember,
      setGroupErrorToast,
    ],
  );

  // dnd-kit does not fire onDragCancel when its context unmounts (see
  // PanelDndProvider), and the children's context unmounts whenever the group
  // collapses — which can happen mid-drag (a keyboard drag is parked while the
  // header stays clickable). Without this release a stranded drag leaves the
  // shared drag count held forever, silently disabling the hover peek.
  useEffect(() => {
    if (isRepoCollapsed) {
      return undefined;
    }
    return endOwnedDrag;
  }, [isRepoCollapsed, endOwnedDrag]);

  // Reference-stable (the rows are memoized on their props): the rename
  // callbacks depend only on reference-stable atom setters and the store.
  const handleRenameCommit = useCallback(
    (workspaceId: string, newName: string): void => {
      setRenamingWorkspaceId(null);
      const workspaceAtom = workspaceAtomFamily(workspaceId);
      const previous = store.get(workspaceAtom);
      // Optimistically show the new name and let the WebSocket frame reconcile
      // with the server-authoritative value; roll back and surface a toast if the
      // write is rejected so the rename never fails silently.
      if (previous !== null) {
        store.set(workspaceAtom, { ...previous, description: newName });
      }
      updateWorkspace({
        path: { workspace_id: workspaceId },
        body: { description: newName },
      }).catch((error: unknown) => {
        console.error("Failed to rename workspace:", error);
        if (previous !== null) {
          store.set(workspaceAtom, previous);
        }
        setRenameErrorToast({
          title: `Failed to rename "${previous?.description ?? "workspace"}"`,
          description: "The name has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: null,
        });
      });
    },
    [setRenamingWorkspaceId, setRenameErrorToast, store],
  );

  const handleRenameCancel = useCallback((): void => {
    setRenamingWorkspaceId(null);
  }, [setRenamingWorkspaceId]);

  // JSX and rendering logic
  const Chevron = isRepoCollapsed ? ChevronRight : ChevronDown;

  return (
    <div
      ref={setGroupNodeRef}
      className={`${styles.repoGroup} ${isGroupDragging ? styles.rowDragging : ""}`}
      style={{ transform: CSS.Translate.toString(groupTransform), transition: groupTransition }}
    >
      <div className={styles.repoHeader}>
        <button
          type="button"
          ref={setGroupActivatorNodeRef}
          className={styles.repoHeaderButton}
          {...groupAttributes}
          {...groupListeners}
          // After the listeners spread so this composed handler REPLACES the
          // sensor's raw onKeyDown (it delegates every non-Enter key back to it).
          onKeyDown={handleHeaderKeyDown}
          onClick={handleToggleCollapsed}
          data-testid={ElementIds.SIDEBAR_REPO_GROUP}
          data-project-id={group.projectId}
          data-sidebar-dragging={isGroupDragging ? "true" : undefined}
          data-sidebar-drop-target={isGroupOver && !isGroupDragging ? "true" : undefined}
        >
          <Chevron size={16} className={styles.repoChevron} />
          <Text className={styles.repoName} truncate>
            {group.name}
          </Text>
        </button>
        {showActions && (
          <Flex className={styles.rowActions} gap="2">
            <Tooltip content="Repository settings" side="right">
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                className={styles.hoverReveal}
                onClick={() => openSettings("REPOSITORIES", group.projectId)}
                aria-label="Repository settings"
                data-testid={ElementIds.SIDEBAR_REPO_SETTINGS}
                data-project-id={group.projectId}
              >
                <Settings size={13} />
              </IconButton>
            </Tooltip>
            <Tooltip content="New workspace in this repo" side="right">
              {/* Direct-create in THIS repo (fresh auto branch, last-used or
                  default settings); failures fall back to the dialog
                  pre-selecting the repo. The nav "New Workspace" above is the
                  open-the-dialog affordance. */}
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                disabled={isCreating}
                onClick={() => void createFromSidebar(group.projectId)}
                aria-label="New workspace in this repo"
                data-testid={ElementIds.SIDEBAR_REPO_ADD_WORKSPACE}
                data-project-id={group.projectId}
              >
                <Plus size={13} />
              </IconButton>
            </Tooltip>
          </Flex>
        )}
      </div>
      {!isRepoCollapsed && group.children.length === 0 && (
        <Text className={styles.noWorkspacesHint} data-testid={ElementIds.SIDEBAR_NO_WORKSPACES_HINT}>
          No workspaces yet
        </Text>
      )}
      {!isRepoCollapsed && group.children.length > 0 && (
        // The children get their own container (rather than sitting directly in
        // the group) so the section modifiers clamp a dragged child to the
        // children's extent — a row slides across the loose rows and the group
        // cards but never up over the repo header or out of the section.
        <div ref={sectionChildrenRef} className={styles.repoRows}>
          <DndContext
            sensors={rowDndSensors}
            collisionDetection={closestCenter}
            modifiers={sectionDndModifiers}
            onDragStart={beginOwnedDrag}
            onDragEnd={handleSectionDragEnd}
            onDragCancel={endOwnedDrag}
          >
            <SortableContext items={group.children.map(repoSectionChildKey)} strategy={verticalListSortingStrategy}>
              {group.children.map((child) =>
                child.kind === "workspace" ? (
                  <SidebarWorkspaceRow
                    key={child.workspace.objectId}
                    workspace={child.workspace}
                    isRenaming={renamingWorkspaceId === child.workspace.objectId}
                    isActive={child.workspace.objectId === activeWorkspaceId}
                    actions={actions}
                    openInRuntime={openInRuntime}
                    destructiveColor={dangerColor}
                    onNavigate={onWorkspaceClick}
                    onHover={onWorkspaceHover}
                    onRenameCommit={handleRenameCommit}
                    onRenameCancel={handleRenameCancel}
                    onBeginDelete={onBeginDelete}
                  />
                ) : (
                  <WorkspaceGroupCard
                    key={child.group.objectId}
                    group={child.group}
                    members={child.members}
                    actions={actions}
                    openInRuntime={openInRuntime}
                    destructiveColor={dangerColor}
                    renamingWorkspaceId={renamingWorkspaceId}
                    activeWorkspaceId={activeWorkspaceId}
                    onWorkspaceClick={onWorkspaceClick}
                    onWorkspaceHover={onWorkspaceHover}
                    onWorkspaceRenameCommit={handleRenameCommit}
                    onWorkspaceRenameCancel={handleRenameCancel}
                    onBeginDelete={onBeginDelete}
                  />
                ),
              )}
            </SortableContext>
            <RepoSectionReleaseSlot />
          </DndContext>
        </div>
      )}
    </div>
  );
};
