import type { LucideIcon } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

// Zone IDs. "center" is the uniform-panels Center section (iteration 2) — a
// normal panel section rendered by the same component as the peripheral zones.
//
// The "<zone>:split" ids back the secondary sub-section a section gains when it
// is split once (panel-section splitting). They are real zones so that the
// existing per-zone machinery (panelsInZoneAtom, zoneAssignments persistence,
// the add-panel "+", PanelRegistryProvider's valid-zone check) works on a split
// sub-section unchanged. A section is split at most once, so each primary
// section zone has exactly one paired split zone.
export const ZONE_IDS = [
  "top-left",
  "bottom-left",
  "bottom",
  "top-right",
  "bottom-right",
  "center",
  "top-left:split",
  "center:split",
  "top-right:split",
  "bottom:split",
] as const;
export type ZoneId = (typeof ZONE_IDS)[number];

// ── Split-zone helpers ──────────────────────────────────────────────
// A split adds a second sub-section bound to "<primaryZone>:split".
export const SPLIT_ZONE_SUFFIX = ":split";

/** The split (secondary) zone paired with a primary section zone. */
export const toSplitZone = (zone: ZoneId): ZoneId => `${zone}${SPLIT_ZONE_SUFFIX}` as ZoneId;

/** Whether a zone is the split (secondary) half of a section. */
export const isSplitZone = (zone: ZoneId): boolean => zone.endsWith(SPLIT_ZONE_SUFFIX);

/** The primary zone a split zone belongs to (identity for non-split zones). */
export const toPrimaryZone = (zone: ZoneId): ZoneId =>
  isSplitZone(zone) ? (zone.slice(0, -SPLIT_ZONE_SUFFIX.length) as ZoneId) : zone;

// Panel IDs — dynamic string type since panels are registered at runtime
export type PanelId = string;

// Panel kind. "static" panels come from the static registry (Files, Changes,
// Terminal-less side panels, …). "agent" and "terminal" panels are created at
// runtime, one per task / per terminal instance, and are single-instance per
// workspace (REQ-AGENT-1 / REQ-TERM-2 / REQ-INST-1).
export type PanelKind = "static" | "agent" | "terminal";

// Context menu item type
export type ContextMenuItem = {
  label: string;
  action: () => void;
};

// Panel definition type
export type PanelDefinition = {
  id: PanelId;
  displayName: string;
  description: string;
  icon: LucideIcon;
  defaultZone: ZoneId;
  defaultShortcut: string;
  component: ComponentType;
  /** Defaults to "static" when omitted. */
  kind?: PanelKind;
  /**
   * Custom tab-strip icon, overriding `icon`. Used by agent panels to render a
   * live status dot. The node should subscribe to its own state so it updates
   * without rebuilding the registry.
   */
  tabIcon?: ReactNode;
  getFocusTarget?: () => HTMLElement | null;
  contextMenuItems?: ReadonlyArray<ContextMenuItem>;
  isBuiltin?: boolean;
  defaultEnabled?: boolean;
};

// Layout sides — groups of zones toggled together by the bottom bar buttons
export const LAYOUT_SIDES = ["left", "bottom", "right"] as const;
export type LayoutSide = (typeof LAYOUT_SIDES)[number];

/** Maps each layout side to the zone IDs it controls. */
export const SIDE_ZONE_MAP: Readonly<Record<LayoutSide, ReadonlyArray<ZoneId>>> = {
  left: ["top-left", "bottom-left"],
  bottom: ["bottom"],
  right: ["top-right", "bottom-right"],
} as const;

// Default layout configuration for first-time initialization
export type DefaultPanelLayout = {
  zoneAssignments: Record<PanelId, ZoneId>;
  activePanelPerZone: Partial<Record<ZoneId, PanelId>>;
  zoneVisibility: Partial<Record<ZoneId, boolean>>;
  zoneOrder: Partial<Record<ZoneId, Array<PanelId>>>;
};
