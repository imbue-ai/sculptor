import type { Virtualizer } from "@tanstack/react-virtual";

/**
 * Pixels from the bottom of the viewport to the bottom of the real content.
 *
 * The virtualizer inflates the scroll container with a dynamic `paddingEnd` so a
 * freshly-anchored user message can reach the top of the viewport. That padding
 * is empty space below the last message, so "at the bottom" means the last
 * message is in view — not that the padded scroll range is exhausted. Because
 * `scrollHeight` includes that padding, the distance subtracts `paddingEnd`.
 *
 * This is the single distance primitive for every "are we at the bottom" check.
 */
export const distanceFromContentBottom = (
  el: HTMLElement,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
): number => {
  const paddingEnd = virtualizer.options.paddingEnd ?? 0;
  return el.scrollHeight - paddingEnd - el.scrollTop - el.clientHeight;
};
