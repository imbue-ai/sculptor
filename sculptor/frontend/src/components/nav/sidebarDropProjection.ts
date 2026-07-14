// The flat-lane drop projection for a repo section's children (REQ-DND-1..7).
//
// A repo section renders as ONE flat sortable lane: loose workspace rows, group
// header rows, and member rows are all siblings of a single SortableContext,
// and a group is just a nesting level — membership is DERIVED FROM POSITION
// (a row sitting between a group's header and the end of its member run is in
// the group). This module is the single source of truth for that derivation:
// the drag-over preview, the keyboard path, and the drop commit all call
// `projectSectionDrop` and apply its result with `applySectionProjection`, so
// what the user sees mid-drag is exactly what a drop commits.
//
// Everything here is pure and operates on `RepoSectionChild` trees; the React
// layer (SidebarRepoGroup) applies every projection to the rendered lane
// mid-drag, so the drop gap is always real layout and a group's painted box
// always wraps exactly its rows.

import { arrayMove } from "@dnd-kit/sortable";

import type { Workspace } from "~/api";

import type { RepoSectionChild } from "./workspaceGroupComposition.ts";
import { repoSectionChildKey } from "./workspaceGroupComposition.ts";

/** Where a workspace row would land: a group's member lane, or loose (null). */
export type SectionParent = string | null;

/**
 * The user's depth choice at the one geometrically ambiguous slot — right
 * after a group's last member, which is also right after the group itself
 * (REQ-DND-6). "inside" is the default (reading order); pointer-x left of the
 * member indent or a Left-arrow press flips to "outside".
 */
export type SectionDepthIntent = "inside" | "outside";

export type SectionRowProjection = {
  kind: "row";
  activeId: string;
  parentGroupId: SectionParent;
  /** Insertion index within the parent lane (top-level children, or the group's members). */
  index: number;
  /** True when this location is the ambiguous tail-of-group slot where depth intent applies. */
  isBoundary: boolean;
};

/** A whole-group move within the top-level lane (dragged by its header, REQ-DND-4). */
export type SectionGroupProjection = {
  kind: "group";
  activeId: string;
  index: number;
};

/**
 * A row dropped onto a COLLAPSED group's header: appends to the group without
 * a visible gap (its members can't show one), so the display children never
 * change — only the commit does (REQ-DND-6).
 */
export type SectionAppendProjection = {
  kind: "append-collapsed";
  activeId: string;
  parentGroupId: string;
};

export type SectionProjection = SectionRowProjection | SectionGroupProjection | SectionAppendProjection;

// One visible row of the flattened lane, tagged with what it is so neighbor
// inspection (which decides a projected row's parent) never guesses from ids.
type FlatEntry = {
  id: string;
  /** The group whose member run this row belongs to; null for loose rows and headers. */
  parentGroupId: SectionParent;
  isHeader: boolean;
};

const flattenChildren = (
  children: ReadonlyArray<RepoSectionChild>,
  collapsedGroupIds: ReadonlySet<string>,
  hiddenMembersGroupId?: string,
): Array<FlatEntry> => {
  const entries: Array<FlatEntry> = [];
  for (const child of children) {
    if (child.kind === "workspace") {
      entries.push({ id: child.workspace.objectId, parentGroupId: null, isHeader: false });
      continue;
    }
    const groupId = child.group.objectId;
    entries.push({ id: groupId, parentGroupId: null, isHeader: true });
    if (!collapsedGroupIds.has(groupId) && groupId !== hiddenMembersGroupId) {
      for (const member of child.members) {
        entries.push({ id: member.objectId, parentGroupId: groupId, isHeader: false });
      }
    }
  }
  return entries;
};

/**
 * The SortableContext item ids for the section in visible top-to-bottom order:
 * loose workspace ids, group ids (their header rows), and member workspace ids.
 * A collapsed group contributes only its header. While a group header is being
 * dragged its members collapse into the drag (REQ-DND-4), so they leave the
 * lane — pass that group as `draggingGroupId`.
 */
export const flatSectionItemIds = (
  children: ReadonlyArray<RepoSectionChild>,
  collapsedGroupIds: ReadonlySet<string>,
  draggingGroupId?: string,
): Array<string> => flattenChildren(children, collapsedGroupIds, draggingGroupId).map((entry) => entry.id);

/** The group a workspace currently belongs to within the children, or null if loose/absent. */
export const locateWorkspaceParent = (
  children: ReadonlyArray<RepoSectionChild>,
  workspaceId: string,
): SectionParent => {
  for (const child of children) {
    if (child.kind === "group" && child.members.some((member) => member.objectId === workspaceId)) {
      return child.group.objectId;
    }
  }
  return null;
};

/** The top-level index of the child that is, or contains, the given id; -1 if absent. */
const topLevelIndexOf = (children: ReadonlyArray<RepoSectionChild>, id: string): number =>
  children.findIndex(
    (child) =>
      repoSectionChildKey(child) === id ||
      (child.kind === "group" && child.members.some((member) => member.objectId === id)),
  );

/** The group that `id` is the header of or a member of, or null for loose rows and unknown ids. */
export const locateTopLevelGroupId = (children: ReadonlyArray<RepoSectionChild>, id: string): string | null => {
  const child = children[topLevelIndexOf(children, id)];
  return child !== undefined && child.kind === "group" ? child.group.objectId : null;
};

/**
 * Project a dragged group to the top-level slot directly before or after
 * another top-level child — a group box or a loose row (REQ-DND-4). The side
 * comes from the caller — pointer position against the target's midpoint —
 * NOT from the `over` slot: an over-slot arrayMove is side-agnostic and
 * unstable when the pointer rests inside a multi-row box, because the dragged
 * header's placeholder is one row tall while the target box is many, so every
 * application lands the group on the other side of a target the pointer is
 * still inside — re-slotting the lane under a stationary pointer, re-firing
 * `over`, and looping until React aborts with "Maximum update depth
 * exceeded". Side-of-midpoint is a fixed point: a stationary pointer projects
 * the same order every time, and the steady state returns null (no move).
 */
export const projectGroupBesideChild = (
  children: ReadonlyArray<RepoSectionChild>,
  activeId: string,
  targetId: string,
  side: "before" | "after",
): SectionGroupProjection | null => {
  const from = topLevelIndexOf(children, activeId);
  const target = topLevelIndexOf(children, targetId);
  if (from === -1 || target === -1 || from === target) {
    return null;
  }
  // arrayMove removes the active group first, so a target below the active
  // slot shifts up by one: "directly before" is target-1 from above, target
  // from below (and mirrored for "after").
  const index = side === "before" ? (from < target ? target - 1 : target) : from < target ? target : target + 1;
  return index === from ? null : { kind: "group", activeId, index };
};

/**
 * Project the active row to an explicit slot — `index` within
 * `parentGroupId`'s member lane, or within the top-level lane when null —
 * returning null when the row already sits there. The caller derives the slot
 * from pointer geometry (side-of-midpoint over the visible rows and boxes),
 * and the null steady state is what lets it re-resolve on every move without
 * re-rendering a settled lane. `index` is in post-removal basis: the slot's
 * position counting every lane entry EXCEPT the active row — exactly what a
 * DOM measurement of the other elements yields, and what
 * `applySectionProjection` (which removes the row first) splices with.
 */
export const projectRowAtSlot = (args: {
  children: ReadonlyArray<RepoSectionChild>;
  activeId: string;
  parentGroupId: SectionParent;
  index: number;
  isBoundary: boolean;
}): SectionRowProjection | null => {
  const { children, activeId, parentGroupId, index, isBoundary } = args;
  if (locateWorkspaceParent(children, activeId) === parentGroupId) {
    if (parentGroupId === null) {
      const current = children.findIndex(
        (child) => child.kind === "workspace" && child.workspace.objectId === activeId,
      );
      // A loose row's top-level index counts the children above it, none of
      // which is itself — already post-removal basis.
      if (current !== -1 && current === index) {
        return null;
      }
    } else {
      const parent = children.find((child) => child.kind === "group" && child.group.objectId === parentGroupId);
      const current =
        parent?.kind === "group" ? parent.members.findIndex((member) => member.objectId === activeId) : -1;
      if (current !== -1 && current === index) {
        return null;
      }
    }
  }
  return { kind: "row", activeId, parentGroupId, index, isBoundary };
};

/**
 * Project where the active item would land if dropped at `overId`'s slot.
 *
 * `children` must be the CURRENTLY DISPLAYED children (cross-parent moves are
 * applied to the display mid-drag, so successive projections compose).
 * Standard flat-sortable semantics: the active row takes `overId`'s flat slot
 * (arrayMove), then its parent is read off its new neighbors — a row directly
 * below a group header or a member row is in that group. Returns null when the
 * drop resolves to no movement or the ids don't resolve.
 */
export const projectSectionDrop = (args: {
  children: ReadonlyArray<RepoSectionChild>;
  collapsedGroupIds: ReadonlySet<string>;
  activeId: string;
  overId: string;
  depthIntent: SectionDepthIntent;
}): SectionProjection | null => {
  const { children, collapsedGroupIds, activeId, overId, depthIntent } = args;
  if (activeId === overId) {
    return null;
  }

  const activeGroupChild = children.find((child) => child.kind === "group" && child.group.objectId === activeId);

  // A group header drag moves the whole group within the top-level lane and
  // can never nest (REQ-DND-4): an `over` inside another group resolves to
  // that group's own top-level slot.
  if (activeGroupChild !== undefined) {
    const from = topLevelIndexOf(children, activeId);
    const to = topLevelIndexOf(children, overId);
    if (from === -1 || to === -1 || from === to) {
      return null;
    }
    return { kind: "group", activeId, index: to };
  }

  // Dropping onto a collapsed group's header appends to it — there is no
  // member run on screen to open a gap in, so this is the one projection the
  // display never reflects.
  const overGroupChild = children.find((child) => child.kind === "group" && child.group.objectId === overId);
  if (overGroupChild !== undefined && overGroupChild.kind === "group" && collapsedGroupIds.has(overId)) {
    return { kind: "append-collapsed", activeId, parentGroupId: overId };
  }

  const flat = flattenChildren(children, collapsedGroupIds);
  const from = flat.findIndex((entry) => entry.id === activeId);
  const to = flat.findIndex((entry) => entry.id === overId);
  if (from === -1 || to === -1 || from === to) {
    return null;
  }

  const moved = arrayMove(flat, from, to);
  const above: FlatEntry | undefined = moved[to - 1];
  const below: FlatEntry | undefined = moved[to + 1];

  // The parent is read off the row above: below a group's header or one of its
  // members means inside that group. (A collapsed header shows no member run,
  // so the slot below it is loose — joining a collapsed group goes through the
  // append-collapsed path above.)
  let parentGroupId: SectionParent = null;
  let isHeadSlot = false;
  if (above !== undefined) {
    if (above.isHeader && !collapsedGroupIds.has(above.id)) {
      parentGroupId = above.id;
      isHeadSlot = true;
    } else if (above.parentGroupId !== null) {
      parentGroupId = above.parentGroupId;
    }
  }

  // Both edges of a group's run sit at the same y-position as a loose slot —
  // the tail slot doubles as "right after the group", and the head slot
  // (directly under the header) doubles as "right before the group" (the gap
  // between two boxes IS that slot). The depth intent — pointer geometry
  // against the visible box, or the keyboard's Left/Right choice — resolves
  // which side wins (REQ-DND-6): outside flips the tail to after the group
  // and the head to before it.
  const isBoundary =
    parentGroupId !== null &&
    (isHeadSlot || !(below !== undefined && !below.isHeader && below.parentGroupId === parentGroupId));
  let didFlipBeforeGroup = false;
  if (isBoundary && depthIntent === "outside") {
    didFlipBeforeGroup = isHeadSlot;
    parentGroupId = null;
  }

  let index: number;
  if (parentGroupId !== null) {
    // Position within the group's member lane: the member rows sitting above it.
    index = moved.slice(0, to).filter((entry) => entry.parentGroupId === parentGroupId).length;
  } else {
    // Position within the top-level lane: each loose row or header above is one
    // child. A head-slot flip lands BEFORE the group, so its header — the
    // entry directly above — must not count.
    index = moved.slice(0, to).filter((entry) => entry.parentGroupId === null).length - (didFlipBeforeGroup ? 1 : 0);
  }
  return { kind: "row", activeId, parentGroupId, index, isBoundary };
};

/**
 * The explicit depth flip at the ambiguous tail-of-group slot (REQ-DND-6),
 * for intent changes that arrive WITHOUT a new `over` target — a Left/Right
 * arrow press on a parked keyboard drag. The active row's displayed location
 * must actually be a flippable boundary:
 *
 * - flip OUT: the active row is a group's last member → loose, directly
 *   after that group.
 * - flip IN: the active row sits loose directly after an expanded group → that
 *   group's member tail.
 *
 * Returns null when the current location is not a flippable boundary.
 */
export const toggleBoundaryDepth = (
  children: ReadonlyArray<RepoSectionChild>,
  collapsedGroupIds: ReadonlySet<string>,
  activeId: string,
  intent: SectionDepthIntent,
): SectionRowProjection | null => {
  if (intent === "outside") {
    // The flip applies only when the active row is a group's last member.
    let groupId: string | null = null;
    for (const child of children) {
      if (child.kind === "group" && child.members[child.members.length - 1]?.objectId === activeId) {
        groupId = child.group.objectId;
        break;
      }
    }

    if (groupId === null) {
      return null;
    }
    const groupIndex = children.findIndex((child) => child.kind === "group" && child.group.objectId === groupId);
    // A member's removal never shifts top-level indices, so the group's index
    // is valid as the after-removal insertion anchor.
    return { kind: "row", activeId, parentGroupId: null, index: groupIndex + 1, isBoundary: true };
  }

  const activeIndex = children.findIndex(
    (child) => child.kind === "workspace" && child.workspace.objectId === activeId,
  );
  const above = activeIndex > 0 ? children[activeIndex - 1] : undefined;
  if (
    activeIndex === -1 ||
    above === undefined ||
    above.kind !== "group" ||
    collapsedGroupIds.has(above.group.objectId)
  ) {
    // A collapsed group shows no member run, so the slot after it is simply
    // loose — joining a collapsed group goes through its header instead.
    return null;
  }
  return {
    kind: "row",
    activeId,
    parentGroupId: above.group.objectId,
    index: above.members.length,
    isBoundary: true,
  };
};

/** Remove the workspace with `workspaceId` from the tree, returning it and the remaining children. */
const removeWorkspace = (
  children: ReadonlyArray<RepoSectionChild>,
  workspaceId: string,
): { workspace: Workspace | null; children: Array<RepoSectionChild> } => {
  let removed: Workspace | null = null;
  const remaining: Array<RepoSectionChild> = [];
  for (const child of children) {
    if (child.kind === "workspace") {
      if (child.workspace.objectId === workspaceId) {
        removed = child.workspace;
        continue;
      }
      remaining.push(child);
      continue;
    }
    const member = child.members.find((candidate) => candidate.objectId === workspaceId);
    if (member !== undefined) {
      removed = member;
      // A group emptied mid-drag stays in the tree (its header remains a
      // visible drop-back target); the server dissolves it only if the drop
      // commits elsewhere, and the composition rebuilds from truth after.
      remaining.push({ ...child, members: child.members.filter((candidate) => candidate.objectId !== workspaceId) });
      continue;
    }
    remaining.push(child);
  }
  return { workspace: removed, children: remaining };
};

const clampIndex = (index: number, length: number): number => Math.max(0, Math.min(index, length));

/**
 * Apply a projection to the children, returning the new tree (or the original
 * array when the projection no longer resolves — a stale id mid-stream).
 * This is what the lane renders mid-drag for cross-parent moves and what the
 * drop commit materializes into the stored lanes.
 */
export const applySectionProjection = (
  children: ReadonlyArray<RepoSectionChild>,
  projection: SectionProjection,
): ReadonlyArray<RepoSectionChild> => {
  if (projection.kind === "group") {
    const from = children.findIndex((child) => child.kind === "group" && child.group.objectId === projection.activeId);
    if (from === -1) {
      return children;
    }
    return arrayMove([...children], from, clampIndex(projection.index, children.length - 1));
  }

  const { workspace, children: remaining } = removeWorkspace(children, projection.activeId);
  if (workspace === null) {
    return children;
  }

  if (projection.kind === "append-collapsed") {
    return remaining.map((child) =>
      child.kind === "group" && child.group.objectId === projection.parentGroupId
        ? { ...child, members: [...child.members, workspace] }
        : child,
    );
  }

  if (projection.parentGroupId === null) {
    const next = [...remaining];
    next.splice(clampIndex(projection.index, next.length), 0, { kind: "workspace", workspace });
    return next;
  }

  const groupIndex = remaining.findIndex(
    (child) => child.kind === "group" && child.group.objectId === projection.parentGroupId,
  );
  const group = remaining[groupIndex];
  if (group === undefined || group.kind !== "group") {
    return children;
  }
  const members = [...group.members];
  members.splice(clampIndex(projection.index, members.length), 0, workspace);
  const next = [...remaining];
  next[groupIndex] = { ...group, members };
  return next;
};
