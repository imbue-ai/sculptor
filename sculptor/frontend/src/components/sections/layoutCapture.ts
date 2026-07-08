// Capture the current workspace arrangement into a portable CapturedLayout — the
// static-only subset a SavedLayout stores. Pure: no atoms, no React, no DOM, so it
// is directly unit-testable and shared by the save action and the System Default
// derivation.
//
// A Layout is a portable template (design.md Rule 1), so only STATIC panels are
// recorded in placement/order/activePanel — agent/terminal ids are instance-bound
// and don't exist in another workspace. The geometry fields (expanded, splits,
// sizes, active sub-section) are captured whole; maximize lives in the transient
// atom, so the caller passes it in.

import type { CapturedLayout, WorkspaceLayoutState } from "./persistence/types.ts";
import { isMultiInstancePanelId } from "./registry/dynamicPanels.tsx";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";

function isStaticPanel(panelId: PanelId): boolean {
  return !isMultiInstancePanelId(panelId);
}

export function captureLayout(layout: WorkspaceLayoutState, maximizedSection: SectionId | null): CapturedLayout {
  const placement: Partial<Record<PanelId, SubSectionId>> = {};
  for (const panelId of Object.keys(layout.placement) as Array<PanelId>) {
    const subSection = layout.placement[panelId];
    if (subSection !== undefined && isStaticPanel(panelId)) {
      placement[panelId] = subSection;
    }
  }

  // Filter each sub-section's tab order to its static panels; drop a sub-section
  // that ends up empty (it held only agents/terminals) so summaries stay clean.
  const order: Partial<Record<SubSectionId, Array<PanelId>>> = {};
  for (const subSection of Object.keys(layout.order) as Array<SubSectionId>) {
    const staticIds = (layout.order[subSection] ?? []).filter(isStaticPanel);
    if (staticIds.length > 0) {
      order[subSection] = staticIds;
    }
  }

  // The active tab is best-effort: keep it only when it is a static panel, so it
  // is restored on apply just when the layout also places that panel.
  const activePanel: Partial<Record<SubSectionId, PanelId>> = {};
  for (const subSection of Object.keys(layout.activePanel) as Array<SubSectionId>) {
    const active = layout.activePanel[subSection];
    if (active !== undefined && isStaticPanel(active)) {
      activePanel[subSection] = active;
    }
  }

  return {
    placement,
    order,
    activePanel,
    expanded: { ...layout.expanded },
    splits: { ...layout.splits },
    sectionSizes: { ...layout.sectionSizes },
    maximizedSection,
    activeSubSection: layout.activeSubSection,
  };
}
