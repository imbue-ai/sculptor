// Write-only action atoms that mutate the consolidated per-workspace layout. Every
// action computes the full next snapshot and writes it once (one atomic persist),
// and the layout invariants live here in one place: center never collapses, the
// active sub-section stays in an expanded section, splits self-heal and are capped
// at one per section, and single-instance panels activate in place instead of
// duplicating.

import { atom } from "jotai";

import type { WorkspaceLayoutState } from "./persistence/types.ts";
import { isMultiInstancePanelId } from "./registry/dynamicPanels.tsx";
import { workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { PanelId, SectionId, SplitAxis, SubSectionId } from "./sectionTypes.ts";
import { canSplitAxis, toSecondary, toSection } from "./sectionTypes.ts";
import { activeSectionRingNonceAtom, maximizedSectionAtom } from "./transientAtoms.ts";

export { removeWorkspaceLayoutAtom } from "./sectionAtoms.ts";

export const SPLIT_RATIO_MIN = 0.15;
export const SPLIT_RATIO_MAX = 0.85;
const DEFAULT_SPLIT_RATIO = 0.5;

function isSectionExpanded(layout: WorkspaceLayoutState, section: SectionId): boolean {
  return section === "center" ? true : (layout.expanded[section] ?? false);
}

// Open panels in a sub-section, ordered. Membership is placement-based, so a dynamic
// panel that is placed but whose source has not loaded yet still counts as occupying
// its sub-section (this is the self-heal reload guard).
function panelsIn(layout: WorkspaceLayoutState, subSection: SubSectionId): ReadonlyArray<PanelId> {
  const placed = (Object.keys(layout.placement) as ReadonlyArray<PanelId>).filter(
    (id) => layout.placement[id] === subSection,
  );
  const placedSet = new Set(placed);
  const ordered = (layout.order[subSection] ?? []).filter((id) => placedSet.has(id));
  const orderedSet = new Set(ordered);
  return [...ordered, ...placed.filter((id) => !orderedSet.has(id))];
}

// Merge a section's split secondary back into its primary and drop the split.
function closeSplitInLayout(layout: WorkspaceLayoutState, section: SectionId): WorkspaceLayoutState {
  if (layout.splits[section] === undefined) {
    return layout;
  }
  const secondary = toSecondary(section);
  const secondaryPanels = panelsIn(layout, secondary);
  const mergedOrder = [...panelsIn(layout, section), ...secondaryPanels];

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
}

// Self-heal a section's split when either half has emptied.
function selfHealSection(layout: WorkspaceLayoutState, section: SectionId): WorkspaceLayoutState {
  if (layout.splits[section] === undefined) {
    return layout;
  }
  const isPrimaryEmpty = panelsIn(layout, section).length === 0;
  const isSecondaryEmpty = panelsIn(layout, toSecondary(section)).length === 0;
  return isPrimaryEmpty || isSecondaryEmpty ? closeSplitInLayout(layout, section) : layout;
}

function reassignActiveOnRemoval(
  activePanel: Partial<Record<SubSectionId, PanelId>>,
  subSection: SubSectionId,
  removed: PanelId,
  remaining: ReadonlyArray<PanelId>,
): void {
  if (activePanel[subSection] !== removed) {
    return;
  }

  if (remaining.length > 0) {
    activePanel[subSection] = remaining[0];
  } else {
    delete activePanel[subSection];
  }
}

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

function withExpandedSection(layout: WorkspaceLayoutState, section: SectionId): WorkspaceLayoutState {
  if (section === "center" || layout.expanded[section] === true) {
    return layout;
  }
  return { ...layout, expanded: { ...layout.expanded, [section]: true } };
}

function withMovePanel(layout: WorkspaceLayoutState, { panelId, to, index }: MovePanelParams): WorkspaceLayoutState {
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

  let next: WorkspaceLayoutState = withExpandedSection({ ...layout, placement, order, activePanel }, toSection(to));
  if (from !== undefined && from !== to) {
    next = selfHealSection(next, toSection(from));
  }
  return next;
}

function withOpenPanel(layout: WorkspaceLayoutState, { panelId, in: target }: OpenPanelParams): WorkspaceLayoutState {
  if (!isMultiInstancePanelId(panelId)) {
    const existing = layout.placement[panelId];
    if (existing !== undefined) {
      // Single-instance already open: activate it in place (do not duplicate) and
      // expand its host section so re-opening a panel that lives in a collapsed
      // section reveals it. Without the expand, opening an already-placed panel in
      // a collapsed section would be a silent no-op visually.
      const activated = { ...layout, activePanel: { ...layout.activePanel, [existing]: panelId } };
      return withExpandedSection(activated, toSection(existing));
    }
  }
  const order = {
    ...layout.order,
    [target]: [...(layout.order[target] ?? []).filter((id) => id !== panelId), panelId],
  };
  const placement = { ...layout.placement, [panelId]: target };
  const activePanel = { ...layout.activePanel, [target]: panelId };
  return withExpandedSection({ ...layout, order, placement, activePanel }, toSection(target));
}

function withClosePanel(layout: WorkspaceLayoutState, { panelId }: ClosePanelParams): WorkspaceLayoutState {
  const subSection = layout.placement[panelId];
  if (subSection === undefined) {
    return layout;
  }
  const placement = { ...layout.placement };
  delete placement[panelId];
  const order = { ...layout.order, [subSection]: (layout.order[subSection] ?? []).filter((id) => id !== panelId) };
  const activePanel = { ...layout.activePanel };
  reassignActiveOnRemoval(activePanel, subSection, panelId, order[subSection] ?? []);
  return selfHealSection({ ...layout, placement, order, activePanel }, toSection(subSection));
}

function withSetActivePanel(
  layout: WorkspaceLayoutState,
  { panelId, in: target }: SetActivePanelParams,
): WorkspaceLayoutState {
  if (layout.placement[panelId] !== target) {
    return layout;
  }
  return { ...layout, activePanel: { ...layout.activePanel, [target]: panelId } };
}

function withToggleSection(layout: WorkspaceLayoutState, { section }: ToggleSectionParams): WorkspaceLayoutState {
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
}

function withSplitSection(
  layout: WorkspaceLayoutState,
  { section, panelId, axis }: SplitSectionParams,
): WorkspaceLayoutState {
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
}

function withSetSplitRatio(
  layout: WorkspaceLayoutState,
  { section, ratio }: SetSplitRatioParams,
): WorkspaceLayoutState {
  const split = layout.splits[section];
  if (split === undefined) {
    return layout;
  }
  const clamped = Math.min(SPLIT_RATIO_MAX, Math.max(SPLIT_RATIO_MIN, ratio));
  return { ...layout, splits: { ...layout.splits, [section]: { ...split, ratio: clamped } } };
}

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

// Smart panel visibility toggle for the Cmd+K "Toggle <panel>" commands: closes the
// panel when it is already open, active in its sub-section, and that section is
// expanded; otherwise activates it in its existing placement and jumps there.
// Callers only offer the toggle for placed panels, so a never-placed panel is a
// no-op. Mirrors the docking shell's togglePanel in the new section model.
type TogglePanelParams = { panelId: PanelId; fallbackSection: SubSectionId };

export const togglePanelAtom = atom(null, (get, set, { panelId }: TogglePanelParams) => {
  const layout = get(workspaceLayoutAtom);
  const placement = layout.placement[panelId];
  if (placement === undefined) {
    return;
  }

  const section = toSection(placement);
  const isExpanded = isSectionExpanded(layout, section);
  const isActive = layout.activePanel[placement] === panelId;
  if (isExpanded && isActive) {
    set(closePanelAtom, { panelId });
    return;
  }
  set(openPanelAtom, { panelId, in: placement });
  set(jumpToSectionAtom, { subSection: placement });
});
