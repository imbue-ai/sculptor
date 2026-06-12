import { atomWithStorage } from "jotai/utils";

export const ZOOM_STEP = 1.1;
export const ZOOM_MIN_LEVEL = -5;
export const ZOOM_MAX_LEVEL = 9;

export const clampZoomLevel = (level: number): number =>
  Math.max(ZOOM_MIN_LEVEL, Math.min(ZOOM_MAX_LEVEL, Math.round(level)));

export const factorForZoomLevel = (level: number): number => Math.pow(ZOOM_STEP, level);

export const zoomLevelAtom = atomWithStorage<number>("sculptor-zoom-level", 0);
