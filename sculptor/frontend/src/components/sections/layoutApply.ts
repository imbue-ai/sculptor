// Pure reducers for applying a Layout to a workspace and computing what "Tidy"
// would close. No atoms, no React, no DOM — the write actions in layoutActions.ts
// wrap these, and they are directly unit-testable.
//
// The two invariants from design.md live here:
//   Rule 2 (safety): apply is ADDITIVE — it keeps every currently-open panel,
//   moves/opens only the layout's declared static panels, and sets geometry. It
//   never deletes a placement, so it can never close an agent, terminal, or any
//   other panel. Collapsing a section (geometry) hides but does not close.
//   Rule 1 (portability): only static panels are ever declared, so apply only
//   ever repositions statics — agents/terminals are left exactly where they are.
//
// Tidy is the explicit escape hatch: it closes the static panels the layout does
// not declare (never agents/terminals).

import { openPanelsInSubSection } from "./layoutQueries.ts";
import type { CapturedLayout, SavedLayout, WorkspaceLayoutState } from "./persistence/types.ts";
import { isMultiInstancePanelId } from "./registry/dynamicPanels.tsx";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";
import { isSecondary, toSection } from "./sectionTypes.ts";
import { SYSTEM_DEFAULT_LAYOUT_ID } from "./systemDefaultLayout.ts";

export type ApplyLayoutResult = {
  layout: WorkspaceLayoutState;
  // maximize lives in the transient atom, so the caller applies it separately.
  maximizedSection: SectionId | null;
};

function isSectionExpandedIn(expanded: Partial<Record<SectionId, boolean>>, section: SectionId): boolean {
  return section === "center" ? true : (expanded[section] ?? false);
}

// Apply a captured Layout additively onto the current workspace arrangement.
export function applyCapturedLayout(current: WorkspaceLayoutState, captured: CapturedLayout): ApplyLayoutResult {
  // A — merged placement: keep every current panel, then move/open each declared
  // static panel to its captured sub-section. No key is ever deleted, so nothing
  // closes.
  const placement: Partial<Record<PanelId, SubSectionId>> = { ...current.placement };
  for (const panelId of Object.keys(captured.placement) as Array<PanelId>) {
    const subSection = captured.placement[panelId];
    if (subSection !== undefined) {
      placement[panelId] = subSection;
    }
  }

  // Normalize placements against the layout's splits: a panel stranded in a split
  // half this layout does not split moves back to the primary, so the emptied
  // half never lingers with an orphan.
  for (const panelId of Object.keys(placement) as Array<PanelId>) {
    const subSection = placement[panelId];
    if (subSection !== undefined && isSecondary(subSection) && captured.splits[toSection(subSection)] === undefined) {
      placement[panelId] = toSection(subSection);
    }
  }

  // B — order per sub-section: the layout's declared statics first (in captured
  // order), then the section's residual panels in their current relative order.
  const order: Partial<Record<SubSectionId, Array<PanelId>>> = {};
  const subSections = new Set<SubSectionId>();
  for (const subSection of Object.values(placement)) {
    if (subSection !== undefined) {
      subSections.add(subSection);
    }
  }

  for (const subSection of subSections) {
    const members = (Object.keys(placement) as Array<PanelId>).filter((panelId) => placement[panelId] === subSection);
    const memberSet = new Set(members);
    const declared = (captured.order[subSection] ?? []).filter((panelId) => memberSet.has(panelId));
    const declaredSet = new Set(declared);
    const residual = openPanelsInSubSection(current, subSection).filter(
      (panelId) => memberSet.has(panelId) && !declaredSet.has(panelId),
    );
    const seen = new Set<PanelId>([...declared, ...residual]);
    const leftover = members.filter((panelId) => !seen.has(panelId));
    order[subSection] = [...declared, ...residual, ...leftover];
  }

  // C — active tabs: best-effort restore of the captured active panel wherever it
  // is present after the merge; leave every other sub-section's active as-is (the
  // read slice tolerates a now-absent active by falling back to the first tab).
  const activePanel: Partial<Record<SubSectionId, PanelId>> = { ...current.activePanel };
  for (const subSection of Object.keys(captured.activePanel) as Array<SubSectionId>) {
    const panelId = captured.activePanel[subSection];
    if (panelId !== undefined && placement[panelId] === subSection) {
      activePanel[subSection] = panelId;
    }
  }

  // D — geometry, verbatim from the layout.
  const expanded = { ...captured.expanded };
  const splits = { ...captured.splits };
  const sectionSizes = { ...captured.sectionSizes };

  // Focus: keep the captured active sub-section only if its section ends up
  // expanded; a collapsed section can't be the active pane, so fall back to center.
  let activeSubSection = captured.activeSubSection;
  if (activeSubSection !== null && !isSectionExpandedIn(expanded, toSection(activeSubSection))) {
    activeSubSection = "center";
  }

  // E — maximize: a collapsed section can't stay maximized.
  let maximizedSection = captured.maximizedSection;
  if (maximizedSection !== null && !isSectionExpandedIn(expanded, maximizedSection)) {
    maximizedSection = null;
  }

  return {
    layout: { ...current, placement, order, activePanel, expanded, splits, sectionSizes, activeSubSection },
    maximizedSection,
  };
}

// Compose a freshly-seeded workspace layout with the resolved default Layout, so a
// new workspace opens in whatever the user set as their default (its static panels
// + geometry) around the default dynamic seeding (the seeded agent + terminal). The
// applied pointer is stamped so the new workspace shows the default as "Current".
// Maximize is deliberately not seeded — it is transient and rarely part of a default.
export function seedWorkspaceFromDefault(base: WorkspaceLayoutState, defaultLayout: SavedLayout): WorkspaceLayoutState {
  // System Default's captured shape already equals the freshly-built base, so
  // applying it is a redundant no-op — just stamp the pointer.
  if (defaultLayout.id === SYSTEM_DEFAULT_LAYOUT_ID) {
    return { ...base, appliedLayoutId: defaultLayout.id };
  }
  return { ...applyCapturedLayout(base, defaultLayout.captured).layout, appliedLayoutId: defaultLayout.id };
}

export type TidyClosureEntry = { panelId: PanelId; subSection: SubSectionId };

// The static panels currently open that the layout does NOT declare — exactly what
// Tidy would close. Agents/terminals are excluded (multi-instance), so a session is
// never in the closure. The subSection is where the panel currently lives, for the
// confirmation dialog's "<panel> · <section> section" line.
export function computeTidyClosure(layout: WorkspaceLayoutState, captured: CapturedLayout): Array<TidyClosureEntry> {
  const declared = new Set<PanelId>(Object.keys(captured.placement));
  const closure: Array<TidyClosureEntry> = [];
  for (const panelId of Object.keys(layout.placement) as Array<PanelId>) {
    const subSection = layout.placement[panelId];
    if (subSection !== undefined && !isMultiInstancePanelId(panelId) && !declared.has(panelId)) {
      closure.push({ panelId, subSection });
    }
  }
  return closure;
}
