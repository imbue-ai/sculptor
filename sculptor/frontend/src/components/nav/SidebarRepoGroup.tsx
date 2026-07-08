// One collapsible repo group in the workspace sidebar: the repo header row (collapse
// chevron, hover-revealed repository settings, and an always-visible "+" that
// direct-creates a workspace in this repo, falling back to the new-workspace dialog
// pre-scoped to the repo when the branch can't be resolved or the create fails),
// followed by the repo's children while expanded. The children are ONE flat sortable
// lane (REQ-DND-1): loose workspace rows, group header rows, and member rows are all
// siblings of a single SortableContext, composed in visible order by
// sidebarWorkspaceOrder (with the workspace-groups flag off the lane is exactly the
// workspace rows). Cross-group concerns — building the groups, the shared action
// list, and the delete confirmation — stay in WorkspaceSidebar and arrive as props.
//
// The group is itself a sortable item of WorkspaceSidebar's repo-group DndContext
// (dragged by its header), and it hosts its OWN DndContext for its children — a
// workspace belongs to its repo, so scoping the children context per repo section
// makes cross-repo drops structurally impossible rather than merely rejected.
//
// Within the section, a drag works Dia-style: a DragOverlay copy follows the
// pointer freely while the dragged row's in-flow placeholder holds a real gap
// open at the projected drop position. Where that gap lands — and whether it
// is inside a group (a membership change) — is computed by the pure projection
// module (sidebarDropProjection.ts) and drives the rendered order mid-drag:
// same-parent moves preview via the sortable strategy's transforms, while a
// projection that crosses a group boundary re-renders the lane so the group's
// painted container physically wraps the gap (REQ-DND-6). Drops commit
// instantly — order lanes and the membership mutation apply optimistically,
// and a server rejection rolls both back with an error toast (REQ-DND-7).

import type { DragMoveEvent, DragOverEvent, DragStartEvent } from "@dnd-kit/core";
import { closestCenter, DndContext, DragOverlay, MeasuringStrategy } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { ChevronDown, ChevronRight, Plus, Settings } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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

import {
  adjustSidebarDragCountAtom,
  collapsedRepoGroupsAtom,
  collapsedWorkspaceGroupsAtom,
  isRepoCollapsedAtomFamily,
} from "./navAtoms.ts";
import { useSidebarDndSensors } from "./sidebarDnd.ts";
import { WorkspaceGroupDragPreview, WorkspaceRowDragPreview } from "./sidebarDragPreviews.tsx";
import type { SectionDepthIntent, SectionProjection, SectionRowProjection } from "./sidebarDropProjection.ts";
import {
  applySectionProjection,
  flatSectionItemIds,
  locateWorkspaceParent,
  projectSectionDrop,
  toggleBoundaryDepth,
} from "./sidebarDropProjection.ts";
import styles from "./SidebarRepoGroup.module.scss";
import type { RepoGroup } from "./sidebarWorkspaceOrder.ts";
import { commitSectionDropAtom, restoreSectionOrderAtom } from "./sidebarWorkspaceOrder.ts";
import { SidebarWorkspaceRow } from "./SidebarWorkspaceRow.tsx";
import { WorkspaceGroupCard } from "./WorkspaceGroupCard.tsx";
import type { RepoSectionChild } from "./workspaceGroupComposition.ts";

// Pointer x-position (relative to the section's left edge) below which the
// depth intent at a tail-of-group boundary reads as "outside" (REQ-DND-6).
// Sits between the loose-row indent and the member-row indent, so holding the
// pointer where loose rows live pulls the row out, and holding it over the
// member text keeps it in.
const DEPTH_INTENT_THRESHOLD_PX = 32;

// One in-flight drag within the section's flat lane. `display` is the children
// tree the lane currently renders (cross-parent projections are applied to it
// mid-drag); `pending` is a projection previewed by transforms only (same-
// parent moves, collapsed-header appends) that the drop applies.
type SectionDragState = {
  activeId: string;
  kind: "row" | "group";
  /** The group the row belonged to at pickup; the drop diffs against it to flip membership. */
  startParentGroupId: string | null;
  display: ReadonlyArray<RepoSectionChild>;
  pending: SectionProjection | null;
  depthIntent: SectionDepthIntent;
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
  const collapsedGroups = useAtomValue(collapsedWorkspaceGroupsAtom);
  const setRenameErrorToast = useSetAtom(workspaceRenameErrorToastAtom);
  const setGroupErrorToast = useSetAtom(workspaceGroupErrorToastAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
  const adjustDragCount = useSetAtom(adjustSidebarDragCountAtom);
  const commitSectionDrop = useSetAtom(commitSectionDropAtom);
  const restoreSectionOrder = useSetAtom(restoreSectionOrderAtom);
  const store = useStore();

  const collapsedGroupIds = useMemo(
    () => new Set(Object.keys(collapsedGroups).filter((id) => collapsedGroups[id])),
    [collapsedGroups],
  );

  // Membership is a backend fact: a drop that moves a row into or out of a
  // group flips it through these mutations. The flip is optimistic (the hooks
  // snapshot and roll back the workspace), so the drop lands instantly and a
  // rejection restores both the membership and — via the drag handler's
  // onError below — the order lanes (REQ-DND-7).
  const { mutate: addGroupMember } = useAddWorkspaceGroupMemberMutation();
  const { mutate: removeGroupMember } = useRemoveWorkspaceGroupMemberMutation();

  // The in-flight drag owned by THIS section's context. State drives the
  // rendered lane; the ref lets sensor/handler callbacks read the latest drag
  // without re-subscribing mid-drag.
  const [dragState, setDragState] = useState<SectionDragState | null>(null);
  const dragStateRef = useRef<SectionDragState | null>(null);
  const updateDragState = useCallback((next: SectionDragState | null): void => {
    dragStateRef.current = next;
    setDragState(next);
  }, []);

  // Every drag context adjusts the shared drag count, so end/cancel/cleanup
  // must only decrement for a drag they own — an unowning cleanup (collapsing
  // a different repo mid-drag) would otherwise release another context's drag.
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

  const sectionChildrenRef = useRef<HTMLDivElement | null>(null);

  // Fold a projection into the drag state: a row projection that crosses a
  // group boundary — a parent change, or the ambiguous tail-of-group slot —
  // re-renders the lane so the gap is real layout and the group's painted
  // container physically wraps it exactly when the drop would land inside
  // (REQ-DND-6; a transform preview can't grow the container, so a
  // tail-slot gap would read as outside while dropping inside). Everything
  // else previews via transforms and is applied at the drop.
  const acceptProjection = useCallback(
    (state: SectionDragState, projection: SectionProjection | null, depthIntent: SectionDepthIntent): void => {
      if (projection === null) {
        if (depthIntent !== state.depthIntent) {
          updateDragState({ ...state, depthIntent });
        }
        return;
      }

      if (projection.kind === "row") {
        const currentParent = locateWorkspaceParent(state.display, state.activeId);
        if (projection.parentGroupId !== currentParent || projection.isBoundary) {
          updateDragState({
            ...state,
            display: applySectionProjection(state.display, projection),
            pending: null,
            depthIntent,
          });
          return;
        }
      }
      updateDragState({ ...state, pending: projection, depthIntent });
    },
    [updateDragState],
  );

  const handleSectionDragStart = useCallback(
    (event: DragStartEvent): void => {
      beginOwnedDrag();
      const activeId = String(event.active.id);
      const isGroupHeader = group.children.some((child) => child.kind === "group" && child.group.objectId === activeId);
      updateDragState({
        activeId,
        kind: isGroupHeader ? "group" : "row",
        startParentGroupId: locateWorkspaceParent(group.children, activeId),
        display: group.children,
        pending: null,
        depthIntent: "inside",
      });
    },
    [beginOwnedDrag, group.children, updateDragState],
  );

  const handleSectionDragOver = useCallback(
    (event: DragOverEvent): void => {
      const state = dragStateRef.current;
      if (state === null || event.over === null) {
        // over == null means the pointer rests outside every target: keep the
        // last preview — the drop must land where the gap shows.
        return;
      }
      const overId = String(event.over.id);
      if (overId === state.activeId) {
        // The drag returned to its own placeholder: the visual (transforms
        // reset, the row back in its slot) says "drop here", so a stale
        // pending preview must not out-vote it.
        if (state.pending !== null) {
          updateDragState({ ...state, pending: null });
        }
        return;
      }
      const projection = projectSectionDrop({
        children: state.display,
        collapsedGroupIds,
        activeId: state.activeId,
        overId,
        depthIntent: state.depthIntent,
      });
      acceptProjection(state, projection, state.depthIntent);
    },
    [collapsedGroupIds, acceptProjection, updateDragState],
  );

  // A depth-intent change with no new over target (pointer crossing the member
  // indent while parked at a boundary, or a Left/Right arrow press): flip the
  // projected side of the tail boundary directly (REQ-DND-6).
  const applyDepthIntent = useCallback(
    (intent: SectionDepthIntent): void => {
      const state = dragStateRef.current;
      if (state === null || state.kind !== "row" || state.depthIntent === intent) {
        return;
      }
      const pendingRow: SectionRowProjection | null = state.pending?.kind === "row" ? state.pending : null;
      const projection = toggleBoundaryDepth(state.display, collapsedGroupIds, state.activeId, intent, pendingRow);
      acceptProjection(state, projection, intent);
    },
    [collapsedGroupIds, acceptProjection],
  );

  const handleSectionDragMove = useCallback(
    (event: DragMoveEvent): void => {
      const bounds = sectionChildrenRef.current?.getBoundingClientRect();
      const activator = event.activatorEvent;
      // Keyboard drags flip depth via Left/Right (see useSidebarDndSensors);
      // only pointer drags carry a live x-position.
      if (bounds === undefined || !(activator instanceof PointerEvent)) {
        return;
      }
      const pointerX = activator.clientX + event.delta.x;
      applyDepthIntent(pointerX - bounds.left < DEPTH_INTENT_THRESHOLD_PX ? "outside" : "inside");
    },
    [applyDepthIntent],
  );

  const resetSectionDrag = useCallback((): void => {
    endOwnedDrag();
    updateDragState(null);
  }, [endOwnedDrag, updateDragState]);

  // Commit the drop: materialize the final tree into the order lanes and, when
  // the row's group changed, flip membership through the canonical mutation.
  // Both writes are optimistic; the mutation's onError restores the lanes (the
  // hook itself restores the membership flip) and surfaces a toast. The drop
  // event's own `over` is deliberately unused: it goes null whenever the
  // pointer rests outside any target, but the drop must land at the last
  // previewed gap — exactly what the drag state holds.
  const handleSectionDragEnd = useCallback((): void => {
    const state = dragStateRef.current;
    resetSectionDrag();
    if (state === null) {
      return;
    }
    const final = state.pending === null ? state.display : applySectionProjection(state.display, state.pending);
    if (final === group.children) {
      // Reference-untouched: the drag never accepted a projection.
      return;
    }

    const findWorkspaceName = (workspaceId: string): string => {
      const workspace = store.get(workspaceAtomFamily(workspaceId));
      return workspace?.description ?? "workspace";
    };

    const findGroupName = (groupId: string): string => {
      const child = final.find((candidate) => candidate.kind === "group" && candidate.group.objectId === groupId);
      return child?.kind === "group" ? child.group.name : "group";
    };

    const snapshot = commitSectionDrop({ projectId: group.projectId, children: final });
    if (state.kind !== "row") {
      return;
    }
    const finalParent = locateWorkspaceParent(final, state.activeId);
    if (finalParent === state.startParentGroupId) {
      return;
    }

    if (finalParent !== null) {
      // One mutation covers loose→group AND group→group: the backend moves a
      // workspace that is already in another group, dissolving the source if
      // that empties it.
      addGroupMember(
        { groupId: finalParent, workspaceId: state.activeId },
        {
          onError: (): void => {
            restoreSectionOrder(snapshot);
            setGroupErrorToast({
              title: `Failed to move "${findWorkspaceName(state.activeId)}" into "${findGroupName(finalParent)}"`,
              description: "The workspace was put back where it was. Try again or check your connection.",
              type: ToastType.ERROR_PROMINENT,
              action: null,
            });
          },
        },
      );
      return;
    }

    if (state.startParentGroupId !== null) {
      removeGroupMember(
        { groupId: state.startParentGroupId, workspaceId: state.activeId },
        {
          onError: (): void => {
            restoreSectionOrder(snapshot);
            setGroupErrorToast({
              title: `Failed to remove "${findWorkspaceName(state.activeId)}" from its group`,
              description: "The workspace was put back where it was. Try again or check your connection.",
              type: ToastType.ERROR_PROMINENT,
              action: null,
            });
          },
        },
      );
    }
  }, [
    resetSectionDrag,
    group.children,
    group.projectId,
    store,
    commitSectionDrop,
    restoreSectionOrder,
    addGroupMember,
    removeGroupMember,
    setGroupErrorToast,
  ]);

  const rowDndSensors = useSidebarDndSensors(applyDepthIntent);

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

  // dnd-kit does not fire onDragCancel when its context unmounts (see
  // PanelDndProvider), and the children's context unmounts whenever the group
  // collapses — which can happen mid-drag (a keyboard drag is parked while the
  // header stays clickable). Without this release a stranded drag leaves the
  // shared drag count held forever, silently disabling the hover peek.
  useEffect(() => {
    if (isRepoCollapsed) {
      return undefined;
    }

    return (): void => {
      endOwnedDrag();
      dragStateRef.current = null;
      setDragState(null);
    };
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
  const displayChildren = dragState?.display ?? group.children;
  const draggingGroupId = dragState?.kind === "group" ? dragState.activeId : undefined;
  const flatItemIds = useMemo(
    () => flatSectionItemIds(displayChildren, collapsedGroupIds, draggingGroupId),
    [displayChildren, collapsedGroupIds, draggingGroupId],
  );

  // The group whose container surface should light up because the active row
  // would land inside it: the applied display position, or a pending
  // collapsed-header append (REQ-DND-1/6).
  const projectedTargetGroupId = useMemo((): string | null => {
    if (dragState === null || dragState.kind !== "row") {
      return null;
    }

    if (dragState.pending !== null && dragState.pending.kind !== "group") {
      return dragState.pending.parentGroupId;
    }
    return locateWorkspaceParent(dragState.display, dragState.activeId);
  }, [dragState]);
  // Its accent color, so the overlay card can tint while the drop is inside.
  const projectedTargetGroupColor = useMemo((): string | undefined => {
    if (projectedTargetGroupId === null) {
      return undefined;
    }
    const child = displayChildren.find(
      (candidate) => candidate.kind === "group" && candidate.group.objectId === projectedTargetGroupId,
    );
    return child?.kind === "group" ? child.group.color : undefined;
  }, [projectedTargetGroupId, displayChildren]);

  // The dragged entities for the overlay previews, resolved from the display tree.
  const overlayRowWorkspace = useMemo((): Workspace | null => {
    if (dragState === null || dragState.kind !== "row") {
      return null;
    }

    for (const child of dragState.display) {
      if (child.kind === "workspace" && child.workspace.objectId === dragState.activeId) {
        return child.workspace;
      }

      if (child.kind === "group") {
        const member = child.members.find((candidate) => candidate.objectId === dragState.activeId);
        if (member !== undefined) {
          return member;
        }
      }
    }
    return null;
  }, [dragState]);
  const overlayGroupChild = useMemo(() => {
    if (dragState === null || dragState.kind !== "group") {
      return null;
    }
    const child = dragState.display.find(
      (candidate) => candidate.kind === "group" && candidate.group.objectId === dragState.activeId,
    );
    return child?.kind === "group" ? child : null;
  }, [dragState]);

  const Chevron = isRepoCollapsed ? ChevronRight : ChevronDown;

  return (
    <div
      ref={setGroupNodeRef}
      className={`${styles.repoGroup} ${isGroupDragging ? styles.repoGroupDragging : ""}`}
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
        <div ref={sectionChildrenRef} className={styles.repoRows}>
          <DndContext
            sensors={rowDndSensors}
            collisionDetection={closestCenter}
            // Cross-parent projections change the lane's real layout mid-drag
            // (a group's container grows around the gap), so droppable rects
            // must be re-measured continuously, not just at drag start.
            measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
            onDragStart={handleSectionDragStart}
            onDragOver={handleSectionDragOver}
            onDragMove={handleSectionDragMove}
            onDragEnd={handleSectionDragEnd}
            onDragCancel={resetSectionDrag}
          >
            <SortableContext items={flatItemIds} strategy={verticalListSortingStrategy}>
              {displayChildren.map((child) =>
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
                    isProjectedTarget={projectedTargetGroupId === child.group.objectId}
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
            <DragOverlay>
              {overlayRowWorkspace !== null ? (
                <WorkspaceRowDragPreview
                  workspace={overlayRowWorkspace}
                  projectedGroupAccent={projectedTargetGroupColor}
                />
              ) : overlayGroupChild !== null ? (
                <WorkspaceGroupDragPreview group={overlayGroupChild.group} members={overlayGroupChild.members} />
              ) : null}
            </DragOverlay>
          </DndContext>
        </div>
      )}
    </div>
  );
};
