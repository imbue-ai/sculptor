// One collapsible repo group in the workspace sidebar: the repo header row (collapse
// chevron, hover-revealed repository settings, and an always-visible "+" that
// direct-creates a workspace in this repo, falling back to the new-workspace dialog
// pre-scoped to the repo when the branch can't be resolved or the create fails),
// followed by the repo's children while expanded. The children are ONE flat lane
// (REQ-DND-1): loose workspace rows, group header rows, and member rows are all
// draggable siblings, composed in visible order by sidebarWorkspaceOrder (with the
// workspace-groups flag off the lane is exactly the workspace rows). The lane
// registers no droppables: pointer drags resolve geometrically on the move stream
// and keyboard drags step through the projection engine, so dnd-kit's collision
// machinery has no part to play. Cross-group concerns — building the groups, the shared action
// list, and the delete confirmation — stay in WorkspaceSidebar and arrive as props.
//
// The group is itself a sortable item of WorkspaceSidebar's repo-group DndContext
// (dragged by its header), and it hosts its OWN DndContext for its children — a
// workspace belongs to its repo, so scoping the children context per repo section
// makes cross-repo drops structurally impossible rather than merely rejected.
//
// Within the section, a drag works Dia-style: a DragOverlay copy rides the
// rail under the pointer while the dragged row's in-flow placeholder holds a
// real gap open at the projected drop position. Where that gap lands — and
// whether it is inside a group (a membership change) — is computed by the
// pure projection module (sidebarDropProjection.ts) and drives the rendered
// order mid-drag: every projection re-renders the lane, so the preview is
// always real layout and a group's box always wraps exactly its rows
// (REQ-DND-6). Drops commit instantly — order lanes and the membership
// mutation apply optimistically, and a server rejection rolls both back with
// an error toast (REQ-DND-7).

import type { DragEndEvent, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, DragOverlay } from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { DropdownMenu, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { ChevronDown, ChevronRight, MoreHorizontal, Plus } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { Workspace } from "~/api";
import { ElementIds } from "~/api";
import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { workspaceGroupErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useWorkspaceRename } from "~/common/state/hooks/useWorkspaceRename.ts";
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
import type { SectionAppendProjection, SectionDepthIntent, SectionProjection } from "./sidebarDropProjection.ts";
import {
  applySectionProjection,
  locateWorkspaceParent,
  projectGroupBesideChild,
  projectRowAtSlot,
  projectSectionDrop,
  sectionKeyboardStepTarget,
  toggleBoundaryDepth,
} from "./sidebarDropProjection.ts";
import { layoutRect, useSectionFlipAnimation } from "./sidebarFlip.ts";
import styles from "./SidebarRepoGroup.module.scss";
import type { RepoGroup } from "./sidebarWorkspaceOrder.ts";
import { commitSectionDropAtom, restoreSectionOrderAtom } from "./sidebarWorkspaceOrder.ts";
import { SidebarWorkspaceRow } from "./SidebarWorkspaceRow.tsx";
import { WorkspaceGroupCard } from "./WorkspaceGroupCard.tsx";
import type { RepoSectionChild } from "./workspaceGroupComposition.ts";

// The dragged card is the section's DragOverlay copy; locking it to the
// vertical axis keeps the drag reading as list reordering (the overlay rides
// the rail instead of trailing the pointer sideways off it).
const sectionDndModifiers = [restrictToVerticalAxis];

// The DOM-geometry reads on the move stream measure the lane's group boxes
// and workspace row buttons; queries run against the section's own children
// container, so sibling repo sections never leak in.
const GROUP_CARD_SELECTOR = `[data-testid="${ElementIds.SIDEBAR_WORKSPACE_GROUP_CARD}"]`;
const WORKSPACE_ROW_SELECTOR = `[data-testid="${ElementIds.SIDEBAR_WORKSPACE_ROW}"]`;

// How far inside a group box's top/bottom edge the pointer must be before the
// depth intent reads "inside". The raw gap between two adjacent boxes is only
// a few pixels — without this inset, dropping a row loose between two groups
// would demand pixel-perfect aim; with it, the box's edge zones count as
// "between" too. Sized so the full between-band (gap + both edge zones) spans
// roughly one row height: a mid-drag box also GROWS by the drop gap it holds
// open, so anything much smaller forces a long overshoot past the grown box
// before a downward drag can land between boxes. Anything much larger starts
// eating the header/member rows of short boxes.
const BOX_EDGE_INSET_PX = 12;

// One in-flight drag within the section's flat lane. `display` is the children
// tree the lane currently renders — every projection is applied to it
// mid-drag, except a collapsed-header append (no visible slot to re-render),
// which waits in `pending` for the drop.
type SectionDragState = {
  activeId: string;
  kind: "row" | "group";
  /** The group the row belonged to at pickup; the drop diffs against it to flip membership. */
  startParentGroupId: string | null;
  display: ReadonlyArray<RepoSectionChild>;
  pending: SectionAppendProjection | null;
  depthIntent: SectionDepthIntent;
};

type SidebarRepoGroupProps = {
  group: RepoGroup;
  // The shared workspace action list (rename/delete/git/open-in), built once in
  // WorkspaceSidebar so every group and the command palette agree on the entries.
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
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
  onWorkspaceClick,
  onWorkspaceHover,
  onBeginDelete,
}: SidebarRepoGroupProps): ReactElement => {
  // External atoms
  const isRepoCollapsed = useAtomValue(isRepoCollapsedAtomFamily(group.projectId));
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);
  const collapsedGroups = useAtomValue(collapsedWorkspaceGroupsAtom);
  const setGroupErrorToast = useSetAtom(workspaceGroupErrorToastAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
  const adjustDragCount = useSetAtom(adjustSidebarDragCountAtom);
  const commitSectionDrop = useSetAtom(commitSectionDropAtom);
  const restoreSectionOrder = useSetAtom(restoreSectionOrderAtom);
  const store = useStore();
  const renameWorkspace = useWorkspaceRename();

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
  // The pointer's last known y, while a POINTER drag is active (null for
  // keyboard drags): the per-commit re-resolution below must never replay a
  // stale pointer against a drag the keyboard is driving.
  const lastPointerYRef = useRef<number | null>(null);
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
    activeIndex: groupActiveIndex,
    overIndex: groupOverIndex,
  } = useSortable({ id: group.projectId });

  // Which edge of this group the dragged group will land against, for the
  // drop-indicator line during repo-group drags: "after" (below) when dragging
  // down onto it, "before" (above) when dragging up. Only meaningful while
  // this group is the drop target.
  const groupDropSide =
    isGroupOver && !isGroupDragging ? (groupActiveIndex < groupOverIndex ? "after" : "before") : undefined;

  const sectionChildrenRef = useRef<HTMLDivElement | null>(null);

  // Fold a projection into the drag state. Row and group projections apply to
  // the DISPLAY immediately — the lane re-renders with the placeholder at the
  // projected slot, so the preview is always real layout and a group's painted
  // box always wraps exactly its rows (a transform preview would slide rows
  // out from under a box that cannot move with them). The one exception is
  // the collapsed-header append, which has no visible slot to re-render; it
  // stays pending and the drop applies it.
  const acceptProjection = useCallback(
    (state: SectionDragState, projection: SectionProjection | null, depthIntent: SectionDepthIntent): void => {
      if (projection === null) {
        // A null resolution means "stay where the display shows" — that
        // outranks a stale pending append, whose target the pointer has left.
        if (state.pending !== null || depthIntent !== state.depthIntent) {
          updateDragState({ ...state, pending: null, depthIntent });
        }
        return;
      }

      if (projection.kind === "append-collapsed") {
        updateDragState({ ...state, pending: projection, depthIntent });
        return;
      }
      updateDragState({
        ...state,
        display: applySectionProjection(state.display, projection),
        pending: null,
        depthIntent,
      });
    },
    [updateDragState],
  );

  const handleSectionDragStart = useCallback(
    (event: DragStartEvent): void => {
      beginOwnedDrag();
      lastPointerYRef.current = null;
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

  // A depth-intent change with no new over target (pointer crossing the member
  // indent while parked at a boundary, or a Left/Right arrow press): flip the
  // projected side of the tail boundary directly (REQ-DND-6).
  const applyDepthIntent = useCallback(
    (intent: SectionDepthIntent): void => {
      const state = dragStateRef.current;
      if (state === null || state.kind !== "row" || state.depthIntent === intent) {
        return;
      }
      const projection = toggleBoundaryDepth(state.display, collapsedGroupIds, state.activeId, intent);
      acceptProjection(state, projection, intent);
    },
    [collapsedGroupIds, acceptProjection],
  );

  // The keyboard mirror of resolveSectionPointer below: Up/Down steps the drag
  // one lane entry through the same projection engine (a pure function of the
  // display tree — never dnd-kit collisions, whose rects the lane's mid-drag
  // re-renders move out from under a parked drag). Returns the target entry's
  // rest-layout top so the sensor rides the DragOverlay to the slot.
  const handleStepKey = useCallback(
    (direction: "up" | "down"): number | undefined => {
      const state = dragStateRef.current;
      const section = sectionChildrenRef.current;
      if (state === null || section === null) {
        return undefined;
      }
      const targetId = sectionKeyboardStepTarget({
        children: state.display,
        collapsedGroupIds,
        activeId: state.activeId,
        direction,
        pendingGroupId: state.pending?.parentGroupId ?? null,
      });
      if (targetId === null) {
        return undefined;
      }

      if (targetId === state.activeId) {
        // Stepped back onto the drag's own placeholder: the display already
        // shows the drop there, so only a stale pending append needs clearing.
        acceptProjection(state, null, state.depthIntent);
      } else {
        acceptProjection(
          state,
          projectSectionDrop({
            children: state.display,
            collapsedGroupIds,
            activeId: state.activeId,
            overId: targetId,
            depthIntent: state.depthIntent,
          }),
          state.depthIntent,
        );
      }
      const target = section.querySelector(`[data-flip-id="${targetId}"]`);
      return target === null ? undefined : layoutRect(target, section).top;
    },
    [collapsedGroupIds, acceptProjection],
  );

  // THE pointer-geometry resolution: a dragged group's whole slot, and a
  // dragged row's parent and slot below. It is a pure function of the pointer
  // position and the lane's committed layout (the FLIP pass's stamps), and it
  // runs whenever EITHER input changes: every pointer sample
  // (handleSectionDragMove), and once per commit after the stamps refresh
  // (the layout effect below) — a rapid gesture's last sample can outrun
  // React and compute against the previous commit's stamps, and with the
  // pointer then parked, no further move event would ever correct it.
  const resolveSectionPointer = useCallback(
    (pointerY: number): void => {
      const state = dragStateRef.current;
      const section = sectionChildrenRef.current;
      if (state === null || section === null) {
        return;
      }

      // A dragged GROUP resolves its slot geometrically against every OTHER
      // top-level item — group boxes AND loose rows — on EVERY move, and this
      // is the ONLY authority for pointer group drags (the over handler defers
      // wholesale; see the matching guard there). The rule is total over the
      // whole rail: the group lands BEFORE the first other item whose midpoint
      // is at or below the pointer, else AFTER the last one — a pointer in a
      // box's top half, over a loose row, above everything, in a gap, or
      // dwelling in the empty space beneath the lane all resolve to a definite
      // slot. Side-of-midpoint keeps projectGroupBesideChild a fixed point, so
      // a stationary pointer settles without re-slotting.
      if (state.kind === "group") {
        const items: Array<{ id: string; rect: { top: number; bottom: number } }> = [];
        for (const element of section.querySelectorAll(`${GROUP_CARD_SELECTOR}, ${WORKSPACE_ROW_SELECTOR}`)) {
          const isCard = element.matches(GROUP_CARD_SELECTOR);
          if (!isCard && element.closest(GROUP_CARD_SELECTOR) !== null) {
            // Member rows travel with their box; only the box competes for a slot.
            continue;
          }
          const id = element.getAttribute(isCard ? "data-group-id" : "data-workspace-id");
          if (id === null || id === state.activeId) {
            continue;
          }
          items.push({ id, rect: layoutRect(element, section) });
        }

        if (items.length === 0) {
          return;
        }
        const before = items.find((item) => pointerY <= (item.rect.top + item.rect.bottom) / 2);
        const projection =
          before !== undefined
            ? projectGroupBesideChild(state.display, state.activeId, before.id, "before")
            : projectGroupBesideChild(state.display, state.activeId, items[items.length - 1].id, "after");
        acceptProjection(state, projection, state.depthIntent);
        return;
      }

      // A dragged ROW resolves the same way — geometrically, totally, on every
      // move. WHICH lane it is in comes from the box under the pointer,
      // Dia-style: inside an expanded box (minus the edge inset) the row slots
      // among that box's members by midpoint; over a collapsed box it appends
      // on drop; outside every box it slots loose among the top-level items by
      // midpoint. The edge inset keeps the loose band between two adjacent
      // boxes reachable (REQ-DND-6), and a box growing around the gap it holds
      // open gives natural hysteresis on either side of that band. Every rule
      // is a fixed point (projectRowAtSlot returns null for the row's current
      // slot), so a stationary pointer settles without re-rendering.
      const pointerCard = [...section.querySelectorAll(GROUP_CARD_SELECTOR)].find((card) => {
        const rect = layoutRect(card, section);
        return pointerY >= rect.top + BOX_EDGE_INSET_PX && pointerY <= rect.bottom - BOX_EDGE_INSET_PX;
      });
      const pointerGroupId = pointerCard?.getAttribute("data-group-id") ?? null;

      if (pointerCard !== undefined && pointerGroupId !== null) {
        if (pointerCard.getAttribute("data-collapsed") === "true") {
          // A collapsed run shows no member lane to hold a gap open, so the
          // append stays pending and the drop applies it (REQ-DND-6).
          if (state.pending === null || state.pending.parentGroupId !== pointerGroupId) {
            acceptProjection(
              state,
              { kind: "append-collapsed", activeId: state.activeId, parentGroupId: pointerGroupId },
              "inside",
            );
          }
          return;
        }
        const memberMidpoints = [...pointerCard.querySelectorAll(WORKSPACE_ROW_SELECTOR)]
          // The active row's own placeholder may sit in this box; the slot is
          // measured against the OTHER members (post-removal basis).
          .filter((row) => row.getAttribute("data-workspace-id") !== state.activeId)
          .map((row) => {
            const rect = layoutRect(row, section);
            return (rect.top + rect.bottom) / 2;
          });
        const memberIndex = memberMidpoints.filter((midpoint) => midpoint < pointerY).length;
        acceptProjection(
          state,
          projectRowAtSlot({
            children: state.display,
            activeId: state.activeId,
            parentGroupId: pointerGroupId,
            index: memberIndex,
            // The head and tail slots double as the loose slots beside the
            // box, so both stay flippable by depth intent.
            isBoundary: memberIndex === 0 || memberIndex === memberMidpoints.length,
          }),
          "inside",
        );
        return;
      }

      // Outside every box: the same total midpoint rule as the group branch,
      // over the OTHER top-level items (a pointer in a box's edge inset reads
      // the box's midpoint, so the top zone lands before it and the bottom
      // zone after it).
      const slots: Array<{ isCard: boolean; midpoint: number }> = [];
      for (const element of section.querySelectorAll(`${GROUP_CARD_SELECTOR}, ${WORKSPACE_ROW_SELECTOR}`)) {
        const isCard = element.matches(GROUP_CARD_SELECTOR);
        if (!isCard && element.closest(GROUP_CARD_SELECTOR) !== null) {
          // Member rows travel with their box; only the box holds a slot.
          continue;
        }

        if (!isCard && element.getAttribute("data-workspace-id") === state.activeId) {
          continue;
        }
        const rect = layoutRect(element, section);
        slots.push({ isCard, midpoint: (rect.top + rect.bottom) / 2 });
      }
      const looseIndex = slots.filter((slot) => slot.midpoint < pointerY).length;
      acceptProjection(
        state,
        projectRowAtSlot({
          children: state.display,
          activeId: state.activeId,
          parentGroupId: null,
          index: looseIndex,
          // Beside a box, the loose slot doubles as that box's head or tail.
          isBoundary: (slots[looseIndex - 1]?.isCard ?? false) || (slots[looseIndex]?.isCard ?? false),
        }),
        "outside",
      );
    },
    [acceptProjection],
  );

  const handleSectionDragMove = useCallback(
    (event: DragMoveEvent): void => {
      const activator = event.activatorEvent;
      // Keyboard drags flip depth via Left/Right (see useSidebarDndSensors);
      // only pointer drags carry a live position.
      if (!(activator instanceof PointerEvent)) {
        return;
      }
      const pointerY = activator.clientY + event.delta.y;
      lastPointerYRef.current = pointerY;
      resolveSectionPointer(pointerY);
    },
    [resolveSectionPointer],
  );

  const resetSectionDrag = useCallback((): void => {
    endOwnedDrag();
    lastPointerYRef.current = null;
    updateDragState(null);
  }, [endOwnedDrag, updateDragState]);

  // Commit the drop: materialize the final tree into the order lanes and, when
  // the row's group changed, flip membership through the canonical mutation.
  // Both writes are optimistic; the mutation's onError restores the lanes (the
  // hook itself restores the membership flip) and surfaces a toast. The drop
  // event's own `over` is deliberately unused: it goes null whenever the
  // pointer rests outside any target, but the drop must land at the last
  // previewed gap — exactly what the drag state holds.
  const handleSectionDragEnd = useCallback(
    (event: DragEndEvent): void => {
      // One last resolution at the drop's OWN coordinates before committing:
      // when the main thread stalls, the final move's dispatch can coalesce
      // into the drop itself, leaving the drag state one pointer sample
      // behind the position the user actually released at — and a drop is
      // final, so no later re-resolution could heal it.
      const activator = event.activatorEvent;
      if (activator instanceof PointerEvent) {
        resolveSectionPointer(activator.clientY + event.delta.y);
      }
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
    },
    [
      resolveSectionPointer,
      resetSectionDrag,
      group.children,
      group.projectId,
      store,
      commitSectionDrop,
      restoreSectionOrder,
      addGroupMember,
      removeGroupMember,
      setGroupErrorToast,
    ],
  );

  const rowDndSensors = useSidebarDndSensors({ onDepthKey: applyDepthIntent, onStepKey: handleStepKey });

  // The lane's motion: a FLIP pass over the rows and group cards after every
  // commit (see sidebarFlip.ts). The drag's own element — the invisible
  // placeholder holding the gap — is excluded; its movement IS the projection.
  useSectionFlipAnimation(sectionChildrenRef, dragState?.activeId);

  // Re-resolve a parked pointer once per commit, AFTER the FLIP pass above
  // has restamped the lane (layout effects run in hook order). The chain is
  // bounded: a resolution that changes nothing returns the projections' null
  // fixed point, accepts no state, and triggers no further render.
  useLayoutEffect(() => {
    const pointerY = lastPointerYRef.current;
    if (dragStateRef.current !== null && pointerY !== null) {
      resolveSectionPointer(pointerY);
    }
  });

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

  const handleBeginRename = useCallback(
    (workspaceId: string): void => {
      setRenamingWorkspaceId(workspaceId);
    },
    [setRenamingWorkspaceId],
  );

  // Reference-stable (the rows are memoized on their props): the rename
  // callbacks depend only on reference-stable atom setters and hooks.
  // Optimistic write + rollback + error toast live in the shared
  // useWorkspaceRename, the ONE rename path for every surface.
  const handleRenameCommit = useCallback(
    (workspaceId: string, newName: string): void => {
      setRenamingWorkspaceId(null);
      renameWorkspace(workspaceId, newName);
    },
    [setRenamingWorkspaceId, renameWorkspace],
  );

  const handleRenameCancel = useCallback((): void => {
    setRenamingWorkspaceId(null);
  }, [setRenamingWorkspaceId]);

  // JSX and rendering logic
  const displayChildren = dragState?.display ?? group.children;

  // The group whose container surface should light up because the active row
  // would land inside it: the applied display position, or a pending
  // collapsed-header append (REQ-DND-1/6).
  const projectedTargetGroupId = useMemo((): string | null => {
    if (dragState === null || dragState.kind !== "row") {
      return null;
    }

    if (dragState.pending !== null) {
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
          data-sidebar-group-drop-side={groupDropSide}
        >
          <Chevron size={16} className={styles.repoChevron} />
          <Text className={styles.repoName} truncate>
            {group.name}
          </Text>
        </button>
        <Flex className={styles.rowActions}>
          <DropdownMenu.Root>
            <Tooltip content="Repository actions" side="bottom">
              <DropdownMenu.Trigger>
                <IconButton
                  variant="ghost"
                  size="1"
                  color="gray"
                  className={`${styles.rowActionButton} ${styles.hoverReveal}`}
                  aria-label="Repository actions"
                  data-testid={ElementIds.SIDEBAR_REPO_MENU}
                  data-project-id={group.projectId}
                >
                  <MoreHorizontal size={12} />
                </IconButton>
              </DropdownMenu.Trigger>
            </Tooltip>
            <DropdownMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
              <DropdownMenu.Item
                onSelect={() => openSettings("REPOSITORIES", group.projectId)}
                data-testid={ElementIds.SIDEBAR_REPO_SETTINGS}
                data-project-id={group.projectId}
              >
                Configure repo
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
          <Tooltip content="New workspace in this repo" side="right">
            {/* Direct-create in THIS repo (fresh auto branch, last-used or
                default settings); failures fall back to the dialog
                pre-selecting the repo. The nav "New Workspace" above is the
                open-the-dialog affordance. */}
            <IconButton
              variant="ghost"
              size="1"
              color="gray"
              className={styles.rowActionButton}
              disabled={isCreating}
              onClick={() => void createFromSidebar(group.projectId)}
              aria-label="New workspace in this repo"
              data-testid={ElementIds.SIDEBAR_REPO_ADD_WORKSPACE}
              data-project-id={group.projectId}
            >
              <Plus size={12} />
            </IconButton>
          </Tooltip>
        </Flex>
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
            modifiers={sectionDndModifiers}
            onDragStart={handleSectionDragStart}
            onDragMove={handleSectionDragMove}
            onDragEnd={handleSectionDragEnd}
            onDragCancel={resetSectionDrag}
          >
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
                  onBeginRename={handleBeginRename}
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
                  onWorkspaceBeginRename={handleBeginRename}
                  onWorkspaceRenameCommit={handleRenameCommit}
                  onWorkspaceRenameCancel={handleRenameCancel}
                  onBeginDelete={onBeginDelete}
                />
              ),
            )}
            {/* No drop animation: the drop commits instantly and the lane
                already renders the row/run at its final slot, so the default
                animation drags an overlay clone across the settled lane —
                doubled text converging on the real element. Matches the
                other DragOverlay surfaces (PanelDndProvider, Actions). */}
            <DragOverlay dropAnimation={null}>
              {overlayRowWorkspace !== null ? (
                <WorkspaceRowDragPreview
                  workspace={overlayRowWorkspace}
                  projectedGroupAccent={projectedTargetGroupColor}
                />
              ) : overlayGroupChild !== null ? (
                <WorkspaceGroupDragPreview
                  group={overlayGroupChild.group}
                  members={overlayGroupChild.members}
                  isCollapsed={collapsedGroupIds.has(overlayGroupChild.group.objectId)}
                />
              ) : null}
            </DragOverlay>
          </DndContext>
        </div>
      )}
    </div>
  );
};
