import type { ZoneId } from "~/components/panels/types.ts";

// Panel size defaults (pixels). The layout is pixel-native; flexbox handles
// "fill the remaining space" for the center panel.
export const DEFAULT_SIDE_PANEL_WIDTH_PX = 300;
export const DEFAULT_BOTTOM_PANEL_HEIGHT_PX = 300;
export const DEFAULT_INNER_BOTTOM_HEIGHT_PX = 200;
export const SIDE_PANEL_MIN_WIDTH_PX = 245;
// Minimum usable width for the chat interface. When the window is too narrow
// to fit both side panels and this, side panels auto-collapse (right first).
export const CENTER_PANEL_MIN_WIDTH_PX = 400;
// Hard floor for any panel so it can always be grabbed and dragged back out.
export const PANEL_MIN_PX = 60;

// Maps each bottom zone to the top zone that must remain non-empty on the same side.
export const SIBLING_TOP_ZONE: Partial<Record<ZoneId, ZoneId>> = {
  "bottom-left": "top-left",
  "bottom-right": "top-right",
};

// Zone display names for UI. The "<zone>:split" entries name the secondary
// sub-section a section gains when split; they are filtered out of the
// layout/settings UIs (a split is created from a tab's right-click menu, not
// picked as a move target).
export const ZONE_DISPLAY_NAMES: Readonly<Record<ZoneId, string>> = {
  "top-left": "Top Left",
  "bottom-left": "Bottom Left",
  bottom: "Bottom",
  "top-right": "Top Right",
  "bottom-right": "Bottom Right",
  center: "Center",
  "top-left:split": "Left (split)",
  "center:split": "Center (split)",
  "top-right:split": "Right (split)",
  "bottom:split": "Bottom (split)",
};
