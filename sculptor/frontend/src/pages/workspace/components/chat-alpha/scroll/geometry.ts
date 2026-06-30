import type { Virtualizer } from "@tanstack/react-virtual";

/**
 * Pixels from the bottom of the viewport to the bottom of the real content.
 *
 * The virtualizer inflates the scroll container with a dynamic `paddingEnd` so a
 * freshly-anchored user message can reach the top of the viewport. That padding
 * is empty space below the last message, so "at the bottom" means the last
 * message is in view — not that the padded scroll range is exhausted. Because
 * `scrollHeight` includes that padding, the distance subtracts `paddingEnd`.
 */
export const distanceFromContentBottom = (
  el: HTMLElement,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
): number => {
  const paddingEnd = virtualizer.options.paddingEnd ?? 0;
  return el.scrollHeight - paddingEnd - el.scrollTop - el.clientHeight;
};

/**
 * The `scrollTop` at which the last message's content bottom sits flush with the
 * viewport bottom — i.e. `distanceFromContentBottom === 0` — leaving the dynamic
 * `paddingEnd` as empty slack *below* `scrollTop`.
 *
 * Use this to pin to the bottom instead of `virtualizer.scrollToIndex(last,
 * { align: "end" })`. For the final item that call resolves to
 * `getMaxScrollOffset()` — the very bottom of the padded scroll range — which
 * parks `scrollTop` inside the `paddingEnd` gap with *zero* slack beneath it.
 * Two problems follow: the last line floats a `paddingEnd`-tall gap above the
 * viewport bottom while following, and (the turn-end jump) the last message has
 * no room to shrink when its streaming cursor is removed — the browser clamps
 * `scrollTop` down by the shrink and the whole view jumps up. Pinning to the
 * content bottom keeps `paddingEnd` as slack the shrink is absorbed into.
 */
export const contentBottomOffset = (el: HTMLElement, virtualizer: Virtualizer<HTMLDivElement, Element>): number => {
  const paddingEnd = virtualizer.options.paddingEnd ?? 0;
  return Math.max(0, el.scrollHeight - paddingEnd - el.clientHeight);
};
