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
// A card's height animation is special: unlike a transform, an animated
// height changes the REAL layout of everything below it on every frame. Left
// alone, that drift makes neighbors jump to a wrong position at commit and
// slide back (or move double-distance): a below-element's live layout starts
// offset by the card's full height delta and eases to rest. The pass
// compensates by subtracting the cumulative height delta of every
// height-animating card earlier in the flow from each later element's start
// offset — the compensation and the drift share one duration and easing, so
// they cancel exactly, frame for frame.
//
// The drag logic reads the same elements' geometry on every pointer move, so
// the projections' fixed-point guarantees (a stationary pointer settles) hold
// only for LAYOUT rects — an animating box sweeps its edges through a parked
// pointer and would re-trigger the very projection being animated. Each pass
// therefore stamps every keyed element with its committed layout
// (`data-flip-top`/`data-flip-height`, section-relative), and `layoutRect`
// serves geometry from those stamps.

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
 * `element`'s rest rect — where it sits once every in-flight animation
 * finishes. Every pointer-geometric read in the drag handlers must use this
 * instead of getBoundingClientRect: animated rects break the projections'
 * fixed points (see module comment). Served from the FLIP pass's committed
 * layout stamps on the nearest keyed ancestor (a row's button reads its row),
 * which no animation — translate OR height — can pollute; elements without a
 * stamp fall back to stripping the in-flight translation from the live rect.
 */
export const layoutRect = (element: Element, root: Element): { top: number; bottom: number } => {
  const keyed = element.closest<HTMLElement>("[data-flip-id]");
  if (keyed !== null && root.contains(keyed)) {
    const top = Number.parseFloat(keyed.dataset.flipTop ?? "");
    const height = Number.parseFloat(keyed.dataset.flipHeight ?? "");
    if (Number.isFinite(top) && Number.isFinite(height)) {
      const rootTop = root.getBoundingClientRect().top;
      return { top: rootTop + top, bottom: rootTop + top + height };
    }
  }
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
 * animation from the element's current on-screen position; a nested row
 * subtracts its card's raw delta so the pair never double-shifts; and
 * elements below a height-animating card subtract that card's height delta so
 * the live-layout drift it causes cancels out (see module comment).
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
    // scrolled sidebar doesn't read as every element having moved. The stamps
    // are what layoutRect serves to the drag handlers' geometry reads.
    const sectionTop = section.getBoundingClientRect().top;
    const layouts = new Map<HTMLElement, FlipRecord>();
    for (const element of elements) {
      const rect = element.getBoundingClientRect();
      const layout = { top: rect.top - sectionTop, height: rect.height };
      layouts.set(element, layout);
      element.dataset.flipTop = String(layout.top);
      element.dataset.flipHeight = String(layout.height);
    }

    // Document order guarantees a card is processed before its member rows
    // and before every element below it in the flow, so the nested-row and
    // height-drift subtractions always find their inputs.
    const rawDeltas = new Map<HTMLElement, number>();
    let precedingHeightDelta = 0;
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
      const rawDelta = previous.top + flight.translateY - layout.top;
      rawDeltas.set(element, rawDelta);
      const card = element.parentElement?.closest<HTMLElement>("[data-flip-id]") ?? null;
      const isNested = card !== null && section.contains(card);
      // A nested row rides its card's animation, so it subtracts the card's
      // RAW delta — the card's own height-drift compensation already reaches
      // the row through that shared transform. A top-level element instead
      // subtracts the accumulated height drift of the cards above it.
      const startY = isNested ? rawDelta - (rawDeltas.get(card) ?? 0) : rawDelta - precedingHeightDelta;
      // The height the user last saw. The live rect can't provide it by
      // default: by effect time React has already re-laid-out the element, so
      // its measured height IS the new layout height and the delta would read
      // zero (the box would slide while its bottom edge snaps). Only an
      // interrupted in-flight height animation still overrides the displayed
      // height — detectable as a live height that disagrees with layout — and
      // then the live value is the one on screen.
      const startHeight = Math.abs(flight.visualHeight - layout.height) >= 1 ? flight.visualHeight : previous.height;
      const heightDelta = startHeight - layout.height;
      const shouldAnimateHeight = Math.abs(heightDelta) >= 1;
      if (shouldAnimateHeight && !isNested) {
        // Only a top-level card's animated height re-lays-out the flow below;
        // a nested element's height stays inside its own box.
        precedingHeightDelta += heightDelta;
      }

      if (Math.abs(startY) < 1 && !shouldAnimateHeight) {
        continue;
      }
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
