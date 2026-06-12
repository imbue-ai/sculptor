import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";

// Zone IDs
export const ZONE_IDS = ["top-left", "bottom-left", "bottom", "top-right", "bottom-right"] as const;
export type ZoneId = (typeof ZONE_IDS)[number];

// Panel IDs — dynamic string type since panels are registered at runtime
export type PanelId = string;

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
