import type { ComponentType } from "react";

import { AudioBarsAnimation } from "./AudioBarsAnimation";
import { BouncingDotsAnimation } from "./BouncingDotsAnimation";
import { CascadeAnimation } from "./CascadeAnimation";
import { OrbitAnimation } from "./OrbitAnimation";
import { PulsingDot } from "./PulsingDot";
import { SparkAnimation } from "./SparkAnimation";
import { SpinnerAnimation } from "./SpinnerAnimation";
import { WaveDotsAnimation } from "./WaveDotsAnimation";

type AnimationProps = Record<string, never>;

export const ANIMATION_POOL: ReadonlyArray<ComponentType<AnimationProps>> = [
  OrbitAnimation,
  BouncingDotsAnimation,
  WaveDotsAnimation,
  AudioBarsAnimation,
  CascadeAnimation,
  SparkAnimation,
];

/**
 * Global tracker for the last animation index picked. Shared across all
 * callers (StatusPill, SubagentPill, etc.) so consecutive animations are
 * always visually distinct.
 */
let lastPickedIndex: number | null = null;

/**
 * Pick a random animation index from `ANIMATION_POOL`, guaranteed to differ
 * from the previous pick across all callers.
 */
export function pickAnimationIndex(): number {
  const pool = ANIMATION_POOL.length;
  if (lastPickedIndex === null) {
    lastPickedIndex = Math.floor(Math.random() * pool);
    return lastPickedIndex;
  }
  const offset = Math.floor(Math.random() * (pool - 1));
  lastPickedIndex = offset >= lastPickedIndex ? offset + 1 : offset;
  return lastPickedIndex;
}

export { AudioBarsAnimation };
export { BouncingDotsAnimation };
export { CascadeAnimation };
export { OrbitAnimation };
export { PulsingDot };
export { SparkAnimation };
export { SpinnerAnimation };
export { WaveDotsAnimation };
export type { AnimationProps };
