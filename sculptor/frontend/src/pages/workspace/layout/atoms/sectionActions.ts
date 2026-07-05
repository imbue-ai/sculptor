// Write-only action atoms that mutate the consolidated per-workspace layout. Every
// action computes the full next snapshot and writes it once (one atomic persist),
// and the layout invariants live here in one place: center never collapses, the
// active sub-section stays in an expanded section, splits are capped at one per
// section and persist even when a half empties (only the explicit close-split
// action merges one back; an emptied half shows the empty-section state), and
// single-instance panels activate in place instead of duplicating.

import type { Setter } from "jotai";
import { atom } from "jotai";

import type { WorkspaceLayoutState } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { isMultiInstancePanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";
import type { PanelId, SectionId, SplitAxis, SubSectionId } from "~/pages/workspace/layout/types/section.ts";
import { canSplitAxis, toSecondary, toSection } from "~/pages/workspace/layout/types/section.ts";
import { isSectionExpanded, openPanelsInSubSection } from "~/pages/workspace/layout/utils/layoutQueries.ts";

import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./section.ts";
import { activeSectionRingNonceAtom, maximizedSectionAtom } from "./transient.ts";

export const SPLIT_RATIO_MIN = 0.15;
export const SPLIT_RATIO_MAX = 0.85;
const DEFAULT_SPLIT_RATIO = 0.5;

// Merge a section's split secondary back into its primary and drop the split.
// Membership is placement-based (see openPanelsInSubSection), so a dynamic panel
// that is placed but whose source has not loaded yet is still merged back.
const closeSplitInLayout = (layout: WorkspaceLayoutState, section: SectionId): WorkspaceLayoutState => {
  if (layout.splits[section] === undefined) {
    return layout;
  }
  const secondary = toSecondary(section);
  const secondaryPanels = openPanelsInSubSection(layout, secondary);
  const mergedOrder = [...openPanelsInSubSection(layout, section), ...secondaryPanels];

  const placement = { ...layout.placement };
  for (const id of secondaryPanels) {
    placement[id] = section;
  }
  const order = { ...layout.order, [section]: mergedOrder };
  delete order[secondary];
  const splits = { ...layout.splits };
  delete splits[section];

  const activePanel = { ...layout.activePanel };
  const primaryActive = activePanel[section];
  if (primaryActive === undefined || !mergedOrder.includes(primaryActive)) {
    if (mergedOrder.length > 0) {
      activePanel[section] = mergedOrder[0];
    } else {
      delete activePanel[section];
    }
  }
  delete activePanel[secondary];

  const activeSubSection = layout.activeSubSection === secondary ? section : layout.activeSubSection;
  return { ...layout, placement, order, splits, activePanel, activeSubSection };
};

const reassignActiveOnRemoval = (
  activePanel: Partial<Record<SubSectionId, PanelId>>,
  subSection: SubSectionId,
  removed: PanelId,
  remaining: ReadonlyArray<PanelId>,
): void => {
  if (activePanel[subSection] !== removed) {
    return;
  }

  if (remaining.length > 0) {
    activePanel[subSection] = remaining[0];
  } else {
    delete activePanel[subSection];
  }
};

// ── Pure reducers ─────────────────────────────────────────────────────────────

type MovePanelParams = { panelId: PanelId; to: SubSectionId; index?: number };
type OpenPanelParams = { panelId: PanelId; in: SubSectionId };
type ClosePanelParams = { panelId: PanelId };
type SetActivePanelParams = { panelId: PanelId; in: SubSectionId };
type ToggleSectionParams = { section: SectionId };
type SplitSectionParams = { section: SectionId; panelId: PanelId; axis: SplitAxis };
type CloseSplitParams = { section: SectionId };
type SetSplitRatioParams = { section: SectionId; ratio: number };
type SetActiveSectionParams = { subSection: SubSectionId };

const withExpandedSection = (layout: WorkspaceLayoutState, section: SectionId): WorkspaceLayoutState => {
  if (section === "center" || layout.expanded[section] === true) {
    return layout;
  }
  return { ...layout, expanded: { ...layout.expanded, [section]: true } };
};

const withMovePanel = (layout: WorkspaceLayoutState, { panelId, to, index }: MovePanelParams): WorkspaceLayoutState => {
  const from = layout.placement[panelId];
  const order = { ...layout.order };
  if (from !== undefined) {
    order[from] = (order[from] ?? []).filter((id) => id !== panelId);
  }
  const targetOrder = (order[to] ?? []).filter((id) => id !== panelId);
  targetOrder.splice(index ?? targetOrder.length, 0, panelId);
  order[to] = targetOrder;

  const placement = { ...layout.placement, [panelId]: to };
  const activePanel = { ...layout.activePanel };
  if (from !== to) {
    activePanel[to] = panelId;
    if (from !== undefined) {
      reassignActiveOnRemoval(activePanel, from, panelId, order[from] ?? []);
    }
  }

  // Moving the last panel out of a split half deliberately leaves the split in
  // place: the emptied half shows the empty-section state until the user closes
  // the split explicitly.
  return withExpandedSection({ ...layout, placement, order, activePanel }, toSection(to));
};

const withOpenPanel = (
  layout: WorkspaceLayoutState,
  { panelId, in: target }: OpenPanelParams,
): WorkspaceLayoutState => {
  const existing = layout.placement[panelId];
  if (!isMultiInstancePanelId(panelId)) {
    if (existing !== undefined) {
      // Single-instance already open: activate it in place (do not duplicate) and
      // expand its host section so re-opening a panel that lives in a collapsed
      // section reveals it. Without the expand, opening an already-placed panel in
      // a collapsed section would be a silent no-op visually.
      const activated = { ...layout, activePanel: { ...layout.activePanel, [existing]: panelId } };
      return withExpandedSection(activated, toSection(existing));
    }
  } else if (existing !== undefined && existing !== target) {
    // A multi-instance panel already placed in another sub-section is relocated, not
    // duplicated: route through the move reducer so the source sub-section's order and
    // active-panel entries are cleaned up on the same path as an explicit move.
    return withMovePanel(layout, { panelId, to: target });
  }
  const order = {
    ...layout.order,
    [target]: [...(layout.order[target] ?? []).filter((id) => id !== panelId), panelId],
  };
  const placement = { ...layout.placement, [panelId]: target };
  const activePanel = { ...layout.activePanel, [target]: panelId };
  return withExpandedSection({ ...layout, order, placement, activePanel }, toSection(target));
};

const withClosePanel = (layout: WorkspaceLayoutState, { panelId }: ClosePanelParams): WorkspaceLayoutState => {
  const subSection = layout.placement[panelId];
  if (subSection === undefined) {
    return layout;
  }
  const placement = { ...layout.placement };
  delete placement[panelId];
  const order = { ...layout.order, [subSection]: (layout.order[subSection] ?? []).filter((id) => id !== panelId) };
  const activePanel = { ...layout.activePanel };
  reassignActiveOnRemoval(activePanel, subSection, panelId, order[subSection] ?? []);
  // Closing the last panel in a split half deliberately leaves the split in place
  // (see withMovePanel): the emptied half shows the empty-section state.
  return { ...layout, placement, order, activePanel };
};

const withSetActivePanel = (
  layout: WorkspaceLayoutState,
  { panelId, in: target }: SetActivePanelParams,
): WorkspaceLayoutState => {
  if (layout.placement[panelId] !== target) {
    return layout;
  }
  return { ...layout, activePanel: { ...layout.activePanel, [target]: panelId } };
};

const withToggleSection = (layout: WorkspaceLayoutState, { section }: ToggleSectionParams): WorkspaceLayoutState => {
  if (section === "center") {
    return layout;
  }
  const willBeExpanded = !(layout.expanded[section] ?? false);
  const expanded = { ...layout.expanded, [section]: willBeExpanded };
  let activeSubSection = layout.activeSubSection;
  if (!willBeExpanded && activeSubSection !== null && toSection(activeSubSection) === section) {
    activeSubSection = "center";
  }
  return { ...layout, expanded, activeSubSection };
};

const withSplitSection = (
  layout: WorkspaceLayoutState,
  { section, panelId, axis }: SplitSectionParams,
): WorkspaceLayoutState => {
  if (layout.splits[section] !== undefined || !canSplitAxis(section, axis)) {
    return layout;
  }
  const secondary = toSecondary(section);
  const from = layout.placement[panelId];
  const order = { ...layout.order };
  if (from !== undefined) {
    order[from] = (order[from] ?? []).filter((id) => id !== panelId);
  }
  order[secondary] = [...(order[secondary] ?? []).filter((id) => id !== panelId), panelId];

  const placement = { ...layout.placement, [panelId]: secondary };
  const activePanel = { ...layout.activePanel, [secondary]: panelId };
  if (from !== undefined) {
    reassignActiveOnRemoval(activePanel, from, panelId, order[from] ?? []);
  }
  const splits = { ...layout.splits, [section]: { axis, ratio: DEFAULT_SPLIT_RATIO } };
  return withExpandedSection(
    { ...layout, splits, placement, order, activePanel, activeSubSection: secondary },
    section,
  );
};

const withSetSplitRatio = (
  layout: WorkspaceLayoutState,
  { section, ratio }: SetSplitRatioParams,
): WorkspaceLayoutState => {
  const split = layout.splits[section];
  if (split === undefined) {
    return layout;
  }
  const clamped = Math.min(SPLIT_RATIO_MAX, Math.max(SPLIT_RATIO_MIN, ratio));
  return { ...layout, splits: { ...layout.splits, [section]: { ...split, ratio: clamped } } };
};

// ── Action atoms ──────────────────────────────────────────────────────────────

export const movePanelAtom = atom(null, (_get, set, params: MovePanelParams) =>
  set(workspaceLayoutAtom, (prev) => withMovePanel(prev, params)),
);

export const openPanelAtom = atom(null, (_get, set, params: OpenPanelParams) =>
  set(workspaceLayoutAtom, (prev) => withOpenPanel(prev, params)),
);

export const closePanelAtom = atom(null, (_get, set, params: ClosePanelParams) =>
  set(workspaceLayoutAtom, (prev) => withClosePanel(prev, params)),
);

export const setActivePanelAtom = atom(null, (_get, set, params: SetActivePanelParams) =>
  set(workspaceLayoutAtom, (prev) => withSetActivePanel(prev, params)),
);

export const toggleSectionAtom = atom(null, (get, set, params: ToggleSectionParams) => {
  // A collapsed section must never stay maximized: the transient full-screen view
  // would otherwise show a section the persisted layout says is closed.
  const willCollapse = params.section !== "center" && isSectionExpanded(get(workspaceLayoutAtom), params.section);
  if (willCollapse && get(maximizedSectionAtom) === params.section) {
    set(maximizedSectionAtom, null);
  }
  set(workspaceLayoutAtom, (prev) => withToggleSection(prev, params));
});

export const splitSectionAtom = atom(null, (_get, set, params: SplitSectionParams) =>
  set(workspaceLayoutAtom, (prev) => withSplitSection(prev, params)),
);

export const closeSplitAtom = atom(null, (_get, set, params: CloseSplitParams) =>
  set(workspaceLayoutAtom, (prev) => closeSplitInLayout(prev, params.section)),
);

export const setSplitRatioAtom = atom(null, (_get, set, params: SetSplitRatioParams) =>
  set(workspaceLayoutAtom, (prev) => withSetSplitRatio(prev, params)),
);

// Plain-click active-section change: silent (does not pulse the ring).
export const setActiveSectionAtom = atom(null, (get, set, { subSection }: SetActiveSectionParams) => {
  const layout = get(workspaceLayoutAtom);
  if (!isSectionExpanded(layout, toSection(subSection))) {
    return;
  }
  set(workspaceLayoutAtom, { ...layout, activeSubSection: subSection });
});

// Deliberate jump (keyboard cycle / add / drop / workspace entry): sets active and
// pulses the ring.
export const jumpToSectionAtom = atom(null, (get, set, { subSection }: SetActiveSectionParams) => {
  const layout = get(workspaceLayoutAtom);
  if (!isSectionExpanded(layout, toSection(subSection))) {
    return;
  }
  set(workspaceLayoutAtom, { ...layout, activeSubSection: subSection });
  set(activeSectionRingNonceAtom, (nonce) => nonce + 1);
});

// ── Cross-workspace panel reveal ──────────────────────────────────────────────

type RevealPanelParams = { workspaceId: string; panelId: PanelId; in: SubSectionId };

// A reveal recorded for a workspace that is not the active layout scope yet. The
// workspace shell bootstrap consumes it right after flipping the scope (and after
// any first-visit seeding), so the reveal lands in the destination workspace's
// snapshot. Holds at most one reveal; recording a new one replaces the old.
const pendingPanelRevealAtom = atom<RevealPanelParams | null>(null);

const applyPanelReveal = (set: Setter, params: RevealPanelParams): void => {
  set(openPanelAtom, { panelId: params.panelId, in: params.in });
  set(jumpToSectionAtom, { subSection: params.in });
};

// Open a panel in a SPECIFIC workspace's layout and jump to its section. When that
// workspace is already the active scope the reveal applies immediately; otherwise
// it is deferred until the bootstrap flips the scope. The scope only flips after
// navigation mounts the destination workspace, so writing through the layout proxy
// before then would mutate — and persist — the layout of the workspace being left.
export const revealPanelInWorkspaceAtom = atom(null, (get, set, params: RevealPanelParams) => {
  if (get(activeWorkspaceIdAtom) === params.workspaceId) {
    applyPanelReveal(set, params);
    return;
  }
  set(pendingPanelRevealAtom, params);
});

// Apply any reveal recorded for `workspaceId` and clear the pending slot. A stale
// reveal targeting a different workspace (its navigation never landed) is dropped
// so it cannot fire on a later, unrelated visit to its target.
export const consumePendingPanelRevealAtom = atom(null, (get, set, params: { workspaceId: string }) => {
  const pending = get(pendingPanelRevealAtom);
  if (pending === null) {
    return;
  }
  set(pendingPanelRevealAtom, null);
  if (pending.workspaceId === params.workspaceId) {
    applyPanelReveal(set, pending);
  }
});
