// Consolidated layout snapshot shapes persisted by the LayoutPersistenceAdapter.
// One object per scope (per-workspace or global) — never the prototype's many
// scattered keys.

import type { PanelId, SectionId, SectionSplit, SubSectionId } from "../sectionTypes.ts";

export type WorkspaceLayoutState = {
  // Open-panel set + placement: a panel's presence here means it is "open".
  placement: Partial<Record<PanelId, SubSectionId>>;
  // Tab order within each sub-section.
  order: Partial<Record<SubSectionId, Array<PanelId>>>;
  // Active (shown) panel per sub-section.
  activePanel: Partial<Record<SubSectionId, PanelId>>;
  // Expanded/collapsed per section (center omitted — always expanded).
  expanded: Partial<Record<SectionId, boolean>>;
  // Split state per section (absent = unsplit). Ratio rides here (per-workspace).
  splits: Partial<Record<SectionId, SectionSplit>>;
  // The active sub-section (the focused pane); null → defaults to center on load.
  activeSubSection: SubSectionId | null;
};

export type GlobalLayoutState = {
  // Percentages of the workspace content area; the center fills the remainder.
  sectionSizes: { left: number; right: number; bottom: number };
  sidebarWidthPx: number;
  sidebarCollapsed: boolean;
  // Shared across Files/Changes/Commits.
  explorerListWidthPx: number;
};

export type LayoutScope = { kind: "workspace"; workspaceId: string } | { kind: "global" };

export type LayoutSnapshotFor<TScope extends LayoutScope> = TScope extends { kind: "workspace" }
  ? WorkspaceLayoutState
  : GlobalLayoutState;

// Safe "nothing persisted yet" snapshots. The real default *arrangement* (center
// agent, left Files/Changes/Commits, bottom terminal) is seeded by the bootstrap;
// these are just inert empties/defaults so the atoms always have a valid initial value.
export const EMPTY_WORKSPACE_LAYOUT: WorkspaceLayoutState = {
  placement: {},
  order: {},
  activePanel: {},
  expanded: {},
  splits: {},
  activeSubSection: null,
};

export const DEFAULT_GLOBAL_LAYOUT: GlobalLayoutState = {
  sectionSizes: { left: 20, right: 20, bottom: 30 },
  sidebarWidthPx: 240,
  sidebarCollapsed: false,
  explorerListWidthPx: 240,
};
