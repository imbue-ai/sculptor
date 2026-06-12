import { EffortLevel } from "~/api";

export const EFFORT_DISPLAY_NAMES: Record<EffortLevel, string> = {
  [EffortLevel.LOW]: "Low",
  [EffortLevel.MEDIUM]: "Medium",
  [EffortLevel.HIGH]: "High",
  [EffortLevel.XHIGH]: "Extra High",
  [EffortLevel.MAX]: "Max",
};

/**
 * Ordered from highest to lowest effort — used for dropdown menus in the
 * chat input and settings page.
 */
export const EFFORT_OPTIONS: ReadonlyArray<EffortLevel> = [
  EffortLevel.MAX,
  EffortLevel.XHIGH,
  EffortLevel.HIGH,
  EffortLevel.MEDIUM,
  EffortLevel.LOW,
];
