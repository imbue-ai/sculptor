// The repo section's flat lane previews drags by re-rendering REAL layout
// (rows re-slot, a group's box grows around the drop gap) — transforms can't
// carry that preview because a group's painted box must wrap exactly its rows
// (see SidebarRepoGroup). Real-layout updates are instant, so this module owns
// the lane's motion instead: a FLIP pass over every keyed lane element — the
// workspace rows AND the group cards — that runs after each commit, measures
// what moved, and animates it from where the user last saw it to where it now
// sits. dnd-kit's own per-item layout animation is disabled on the lane's
// sortables (`neverAnimateLayoutChanges`): it only covers sortable items, so
// the non-sortable card surfaces would snap while their header/member rows
// glide — the box visibly tearing away from its own title.
//
// The drag logic reads the same elements' geometry on every pointer move, so
// the projections' fixed-point guarantees (a stationary pointer settles) hold
// only for LAYOUT rects — a box gliding toward its slot sweeps its midpoint
// through the pointer and would re-trigger the projection it is animating.
// `layoutRect` strips the in-flight FLIP translation for those reads.

import type { RefObject } from "react";
import { useLayoutEffect, useRef } from "react";

// Matches dnd-kit's default sortable timing so keyboard drags (whose active
// row still moves via dnd-kit transforms) and the lane's FLIP read as one
// motion language.
const FLIP_DURATION_MS = 200;
const FLIP_EASING = "ease";

/**
 * Disables dnd-kit's built-in layout animation on the lane's sortables; the
 * section FLIP pass below animates every lane element (including the
 * non-sortable card surfaces) instead, so letting dnd-kit also animate the
 * sortable subset would double the motion.
 */
export const neverAnimateLayoutChanges = (): boolean => false;

/** The translateY of a computed-style transform matrix; 0 for none/invalid. */
const translateYOf = (transform: string): number => {
  if (!transform.startsWith("matrix")) {
    return 0;
  }
  const values = transform.slice(transform.indexOf("(") + 1, -1).split(",");
  const value = Number.parseFloat(values[transform.startsWith("matrix3d") ? 13 : 5] ?? "");
  return Number.isFinite(value) ? value : 0;
};

/**
 * The vertical translation currently applied to `element` by in-flight FLIP
 * animations, composed with its animated ancestors up to (excluding) `root` —
 * a member row rides its card's animation as well as its own.
 */
const composedTranslateY = (element: Element, root: Element): number => {
  let translateY = 0;
  for (let node: Element | null = element; node !== null && node !== root; node = node.parentElement) {
    translateY += translateYOf(getComputedStyle(node).transform);
  }
  return translateY;
};

/**
 * `element`'s viewport rect with in-flight FLIP translations stripped: the
 * rect the element will occupy at rest. Every pointer-geometric read in the
 * drag handlers must use this instead of getBoundingClientRect — animated
 * rects break the projections' fixed points (see module comment).
 */
export const layoutRect = (element: Element, root: Element): { top: number; bottom: number } => {
  const rect = element.getBoundingClientRect();
  const translateY = composedTranslateY(element, root);
  return { top: rect.top - translateY, bottom: rect.bottom - translateY };
};

type FlipRecord = {
  /** Layout top relative to the section's top (scroll moves both together). */
  top: number;
  height: number;
};

/**
 * The lane's FLIP pass. After every commit of the section, measure each
 * element carrying `data-flip-id` (workspace rows keyed by workspace id,
 * group cards keyed by group id) and animate position — plus height, for a
 * card growing or shrinking around a drop gap — from where the user last saw
 * it. Interruptions compose: a re-slot landing mid-animation starts the new
 * animation from the element's current on-screen position, and a nested row's
 * own delta subtracts its card's so the pair never double-shifts.
 *
 * `activeDragId` is the in-flight drag's own element (the invisible
 * placeholder holding the gap): its movement IS the projection and must track
 * the pointer instantly, so it is recorded but never animated.
 */
export const useSectionFlipAnimation = (
  sectionRef: RefObject<HTMLElement | null>,
  activeDragId: string | undefined,
): void => {
  const recordsRef = useRef(new Map<string, FlipRecord>());
  const animationsRef = useRef(new Map<string, Animation>());

  useLayoutEffect(() => {
    const section = sectionRef.current;
    const records = recordsRef.current;
    const animations = animationsRef.current;
    if (section === null) {
      records.clear();
      for (const animation of animations.values()) {
        animation.cancel();
      }
      animations.clear();
      return;
    }

    const elements = [...section.querySelectorAll<HTMLElement>("[data-flip-id]")];

    // Capture the in-flight state BEFORE canceling anything: canceling a
    // card's animation snaps its member rows too, so all reads come first.
    const inFlight = new Map<HTMLElement, { translateY: number; visualHeight: number }>();
    for (const element of elements) {
      inFlight.set(element, {
        translateY: composedTranslateY(element, section),
        visualHeight: element.getBoundingClientRect().height,
      });
    }

    for (const animation of animations.values()) {
      animation.cancel();
    }
    animations.clear();

    // Pure layout, all transforms gone. Tops are section-relative so a
    // scrolled sidebar doesn't read as every element having moved.
    const sectionTop = section.getBoundingClientRect().top;
    const layouts = new Map<HTMLElement, FlipRecord>();
    for (const element of elements) {
      const rect = element.getBoundingClientRect();
      layouts.set(element, { top: rect.top - sectionTop, height: rect.height });
    }

    // Document order guarantees a card is processed before its member rows,
    // so a row's subtraction of its card's start delta always finds it.
    const startDeltas = new Map<HTMLElement, number>();
    const seen = new Set<string>();
    for (const element of elements) {
      const key = element.dataset.flipId as string;
      const layout = layouts.get(element) as FlipRecord;
      const previous = records.get(key);
      const flight = inFlight.get(element) as { translateY: number; visualHeight: number };
      seen.add(key);
      records.set(key, layout);
      if (previous === undefined || key === activeDragId || typeof element.animate !== "function") {
        continue;
      }

      // Where the user last saw the element, relative to where it now rests.
      const viewportDelta = previous.top + flight.translateY - layout.top;
      const card = element.parentElement?.closest<HTMLElement>("[data-flip-id]") ?? null;
      const ancestorDelta = card !== null && section.contains(card) ? (startDeltas.get(card) ?? 0) : 0;
      const startY = viewportDelta - ancestorDelta;
      const startHeight = flight.visualHeight;
      const shouldAnimateHeight = Math.abs(startHeight - layout.height) >= 1;
      if (Math.abs(startY) < 1 && !shouldAnimateHeight) {
        continue;
      }
      startDeltas.set(element, startY);
      const keyframes: Array<Keyframe> = shouldAnimateHeight
        ? [
            { transform: `translateY(${startY}px)`, height: `${startHeight}px` },
            { transform: "translateY(0px)", height: `${layout.height}px` },
          ]
        : [{ transform: `translateY(${startY}px)` }, { transform: "translateY(0px)" }];
      animations.set(key, element.animate(keyframes, { duration: FLIP_DURATION_MS, easing: FLIP_EASING }));
    }

    // Unmounted keys (a dragged group's collapsed members, a deleted row)
    // start fresh if they return: no record, no animation.
    for (const key of [...records.keys()]) {
      if (!seen.has(key)) {
        records.delete(key);
      }
    }
  });
};
