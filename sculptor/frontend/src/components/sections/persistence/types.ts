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
//
// The section-sizes move (global → per-workspace) and the saved-layout fields
// are deliberately NOT a version bump: they are additive/tolerated shape growth
// (a workspace snapshot missing sectionSizes reads back with the default; a
// global snapshot's now-orphaned sectionSizes is inert), and a bump would reset
// every user's whole layout on upgrade.
export const LAYOUT_SNAPSHOT_VERSION = 1;

// Percentages of the workspace content area occupied by the surrounding sections;
// the center fills the remainder. Per-workspace (see WorkspaceLayoutState) so a
// Layout can capture and restore sizes without rewriting every other workspace's.
export type SectionSizes = { left: number; right: number; bottom: number };

export const DEFAULT_SECTION_SIZES: SectionSizes = { left: 20, right: 20, bottom: 30 };

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
  // Per-section size percentages. Moved here from the global store so applying a
  // Layout restores this workspace's sizes without touching others. A snapshot
  // written before this field existed reads back as DEFAULT_SECTION_SIZES.
  sectionSizes: SectionSizes;
  // The active sub-section (the focused pane); null → defaults to center on load.
  activeSubSection: SubSectionId | null;
  // The Layout last applied to this workspace, if any. A pointer only — the
  // arrangement is a detached copy, so it diverges freely and the pointer just
  // marks the "Current" row and backs a light dirty check. Undefined once the
  // user has never applied a Layout (or after the pointed-to Layout is deleted).
  appliedLayoutId?: string;
};

// The captured subset of a workspace arrangement that a Layout stores. Only STATIC
// panels are recorded in placement/order/activePanel (agent/terminal ids are
// instance-bound and unportable); the geometry fields are captured whole.
// maximizedSection comes from the transient maximize atom, not the persisted
// layout, so it is captured separately here.
export type CapturedLayout = {
  placement: Partial<Record<PanelId, SubSectionId>>;
  order: Partial<Record<SubSectionId, Array<PanelId>>>;
  activePanel: Partial<Record<SubSectionId, PanelId>>;
  expanded: Partial<Record<SectionId, boolean>>;
  splits: Partial<Record<SectionId, SectionSplit>>;
  sectionSizes: SectionSizes;
  maximizedSection: SectionId | null;
  activeSubSection: SubSectionId | null;
};

// Schema version for a SavedLayout's captured shape, independent of the snapshot
// stamp above. Bumped only if the captured shape changes incompatibly; a layout
// with an unrecognized version is skipped on read (see savedLayoutAtoms).
export const SAVED_LAYOUT_VERSION = 1;

// A named, reusable arrangement the user can switch between and set as the
// new-workspace default. A portable template, not a snapshot of one workspace:
// it captures structure + stateless content only.
export type SavedLayout = {
  id: string;
  name: string;
  captured: CapturedLayout;
  version: number;
  // When true, applying this Layout also tidies (closes the static panels it does
  // not declare) after the additive apply, via the usual Tidy confirmation. A
  // per-Layout property set at save time or from the ⌘J menu — not part of the
  // captured arrangement, so it lives on the Layout, not in `captured`. Optional:
  // Layouts saved before it existed read back without it (treated as false).
  tidyOnApply?: boolean;
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
  // The user's named Layouts. Optional because global snapshots persisted before
  // this field existed load without it; readers default to []. System Default is
  // NOT stored here — it is synthesized from buildDefaultWorkspaceLayout.
  savedLayouts?: ReadonlyArray<SavedLayout>;
  // Which SavedLayout new workspaces seed from and "switch to default" applies.
  // Undefined (or pointing at a since-deleted id) resolves to System Default.
  defaultLayoutId?: string;
  // Layout ids in most-recently-applied order (front = most recent), across all
  // workspaces. Orders the switcher list (PyCharm ⌘E semantics) and, with the
  // active workspace's appliedLayoutId, decides the opening highlight. Optional
  // for the same back-compat reason as the fields above.
  layoutMru?: ReadonlyArray<string>;
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
  sectionSizes: DEFAULT_SECTION_SIZES,
  activeSubSection: null,
};

export const DEFAULT_GLOBAL_LAYOUT: GlobalLayoutState = {
  sidebarWidthPx: 240,
  sidebarCollapsed: false,
  explorerListWidthPx: 240,
  sidebarOrder: { repos: [], workspaces: {} },
  explorerSidebarHiddenByPanel: {},
};
