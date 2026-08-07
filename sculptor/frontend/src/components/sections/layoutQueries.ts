// Pure read queries over the workspace layout snapshot (and the panel registry),
// shared by the layout atoms, the write actions, the keyboard shortcuts, and the
// add-panel surfaces. Each query has exactly one definition here so the read model
// cannot drift between those consumers.
//
// This module is pure — no Jotai atoms, no React, no DOM (the only registry
// dependency is a type import) — so every query is directly unit-testable.

import type { WorkspaceLayoutState } from "./persistence/types.ts";
import type { PanelDefinition } from "./registry/panelRegistry.ts";
import type { PanelId, SectionId, SubSectionId } from "./sectionTypes.ts";
import { isSecondary, SECTION_IDS, toSecondary, toSection } from "./sectionTypes.ts";

// Center is always expanded and is never in the collapsed set; the other sections
// are collapsed unless explicitly flagged expanded.
export function isSectionExpanded(layout: WorkspaceLayoutState, section: SectionId): boolean {
  return section === "center" ? true : (layout.expanded[section] ?? false);
}

// Open panels in a sub-section, ordered. A panel's presence in `placement` is its
// "open" state (so a dynamic panel that is placed but whose source has not loaded
// yet still counts as occupying its sub-section); `order` gives the tab order. Any
// placed-but-unordered panel is appended so the result never drops an open panel.
export function openPanelsInSubSection(layout: WorkspaceLayoutState, subSection: SubSectionId): ReadonlyArray<PanelId> {
  const placedHere = (Object.keys(layout.placement) as ReadonlyArray<PanelId>).filter(
    (panelId) => layout.placement[panelId] === subSection,
  );
  const placedSet = new Set(placedHere);
  const ordered = (layout.order[subSection] ?? []).filter((panelId) => placedSet.has(panelId));
  const orderedSet = new Set(ordered);
  return [...ordered, ...placedHere.filter((panelId) => !orderedSet.has(panelId))];
}

// The sub-sections enumerated in section order: each section's primary and, when the
// section is both expanded and split, its secondary half (a collapsed section only
// offers its primary — its split half is not listed until the section is expanded).
// `includeCollapsed` selects between the two consumers' filters: the keyboard
// section-cycle steps through the expanded (active-able) sub-sections only, while
// the add-panel locations include collapsed sections because adding a panel there
// expands the section.
export function listSubSections(
  layout: WorkspaceLayoutState,
  options: { includeCollapsed: boolean },
): ReadonlyArray<SubSectionId> {
  const subSections: Array<SubSectionId> = [];
  for (const section of SECTION_IDS) {
    const isExpanded = isSectionExpanded(layout, section);
    if (!isExpanded && !options.includeCollapsed) {
      continue;
    }
    subSections.push(section);
    if (isExpanded && layout.splits[section] !== undefined) {
      subSections.push(toSecondary(section));
    }
  }
  return subSections;
}

export type AddPanelLocation = { subSection: SubSectionId; label: string };

export const SECTION_LABELS: Readonly<Record<SectionId, string>> = {
  left: "Left",
  center: "Center",
  right: "Right",
  bottom: "Bottom",
};

// The locations a panel can be added to, labeled for the add-panel menus. A split
// section's halves are disambiguated as "(primary)" / "(secondary)"; an unsplit
// section is just its plain label.
export function listAvailableLocations(layout: WorkspaceLayoutState): ReadonlyArray<AddPanelLocation> {
  const subSections = listSubSections(layout, { includeCollapsed: true });
  const splitSections = new Set(subSections.filter(isSecondary).map(toSection));
  return subSections.map((subSection) => {
    const sectionLabel = SECTION_LABELS[toSection(subSection)];
    if (isSecondary(subSection)) {
      return { subSection, label: `${sectionLabel} (secondary)` };
    }
    return { subSection, label: splitSections.has(toSection(subSection)) ? `${sectionLabel} (primary)` : sectionLabel };
  });
}

export type AvailableStaticPanel = {
  id: PanelId;
  displayName: string;
  icon: PanelDefinition["icon"];
  description?: string;
};

// Single-instance static panels not currently open anywhere — the re-add list.
// Sourced from the live registry (not STATIC_PANEL_METADATA) so extension-contributed
// panels — also kind "static" — are offered too; the multi-instance agent/terminal
// panels are excluded by the kind filter.
export function listAvailableStaticPanels(
  registry: ReadonlyArray<PanelDefinition>,
  placement: WorkspaceLayoutState["placement"],
): ReadonlyArray<AvailableStaticPanel> {
  const openPanelIds = new Set<PanelId>(Object.keys(placement));
  return registry
    .filter((definition) => definition.kind === "static" && !openPanelIds.has(definition.id))
    .map((definition) => ({
      id: definition.id,
      displayName: definition.displayName,
      icon: definition.icon,
      description: definition.description,
    }));
}
