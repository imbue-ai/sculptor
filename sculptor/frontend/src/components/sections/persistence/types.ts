// Consolidated layout snapshot shapes persisted by the LayoutPersistenceAdapter.
// One consolidated object per scope (per-workspace or global) — not one
// localStorage key per field.

import type { PanelId, SectionId, SectionSplit, SubSectionId } from "../sectionTypes.ts";

// Schema version stamped onto every persisted snapshot by the adapter (the
// in-memory state types below stay version-free). Bump it when a snapshot's
// shape changes incompatibly; readers treat a MISSING version as this one
// (snapshots written before the stamp existed) and reject any OTHER version
// as "nothing stored" so the layout falls back to its defaults instead of
// hydrating a shape the atoms can't handle.
export const LAYOUT_SNAPSHOT_VERSION = 1;

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

// The sidebar's user-customized drag order. Both lists are materialized on every
// reorder (the full visible order is stored, not a delta); ids without a stored
// position — new workspaces, repos never reordered — follow the stored ones in the
// default alphabetical order, and stored ids that no longer exist are skipped on
// read, so the lists never need cleanup.
export type SidebarOrderState = {
  // projectIds in custom order.
  repos: Array<string>;
  // workspaceIds in custom order, per projectId.
  workspaces: Partial<Record<string, Array<string>>>;
};

export type GlobalLayoutState = {
  // Percentages of the workspace content area; the center fills the remainder.
  sectionSizes: { left: number; right: number; bottom: number };
  sidebarWidthPx: number;
  sidebarCollapsed: boolean;
  // Shared across Files/Changes/Commits.
  explorerListWidthPx: number;
  sidebarOrder: SidebarOrderState;
  // Whether each Explorer panel's list sidebar is hidden, keyed by panel id.
  // Per-panel (unlike the shared width) so hiding one panel's list leaves the
  // others alone. A panel absent from the map defaults to visible. Optional
  // because global snapshots persisted before this field existed load without
  // it; readers must optional-chain (the compiler enforces it via this `?`).
  explorerSidebarHiddenByPanel?: Partial<Record<PanelId, boolean>>;
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
  sidebarOrder: { repos: [], workspaces: {} },
  explorerSidebarHiddenByPanel: {},
};
