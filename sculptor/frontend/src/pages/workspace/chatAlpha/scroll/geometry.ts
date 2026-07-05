import type { Virtualizer } from "@tanstack/react-virtual";

/**
 * Visible breathing room kept below the content whenever the chat is
 * programmatically brought to the bottom (the following pin, the jump button,
 * the streaming-stop settle, a restore to the bottom). Without it the last
 * line sits flush against the viewport edge, underneath the absolutely
 * positioned bottom bar (StatusPill / jump button).
 */
export const PIN_BOTTOM_GAP = 64;

/**
 * Scrollable slack that must remain below `scrollTop` while pinned at
 * `bottomPinOffset` during a stream. When a turn ends, the removal of the
 * streaming cursor shrinks the content; if `scrollTop` sat at the very end of
 * the scroll range the browser would clamp it down by the shrink and the whole
 * conversation would visibly jump. The slack absorbs that shrink instead.
 */
export const TURN_END_SHRINK_SLACK = 64;

/**
 * Floor for the virtualizer's dynamic `paddingEnd` while the agent is idle.
 * Equal to the pin gap, so at rest the pin position IS the end of the scroll
 * range: scrolling below the content can reveal exactly the visible gap and no
 * more — no shrink is pending on an idle agent, so no extra slack is kept.
 */
export const IDLE_TAIL_PADDING = PIN_BOTTOM_GAP;

/**
 * Floor for the dynamic `paddingEnd` while a stream is active (or just ended
 * and still settling). It must fit the visible pin gap plus the shrink slack —
 * `bottomPinOffset` relies on `paddingEnd >= PIN_BOTTOM_GAP +
 * TURN_END_SHRINK_SLACK` to provide both while a turn-end shrink can still
 * land. Once the turn has settled the floor returns to `IDLE_TAIL_PADDING`;
 * the pinned `scrollTop` sits exactly at the shrunken range's end, so the drop
 * never clamps the scroll position.
 */
export const STREAMING_TAIL_PADDING = PIN_BOTTOM_GAP + TURN_END_SHRINK_SLACK;

/**
 * The turn-end settle window: how long after a followed turn ends late content
 * changes are still expected (the streaming cursor unmounting, the turn footer
 * mounting a beat after the stream stops). Two mechanisms share it: the content
 * observer keeps revealing the tail so the footer is not left below the fold
 * (useAlphaAutoScroll), and the virtualizer holds the streaming paddingEnd
 * floor so the shrink slack outlives the shrink (useAlphaVirtualizer).
 */
export const FOOTER_REVEAL_WINDOW_MS = 1200;

/** The largest scrollTop the browser will allow: the very end of the padded
 *  scroll range. For a chat whose last turn is short, the dynamic `paddingEnd`
 *  makes this exactly the anchored-turn rest position (last user message at
 *  the viewport top). */
export const maxScrollOffset = (el: HTMLElement): number => Math.max(0, el.scrollHeight - el.clientHeight);

/**
 * Pixels from the bottom of the viewport to the bottom of the real content.
 *
 * The virtualizer inflates the scroll container with a dynamic `paddingEnd` so a
 * freshly-anchored user message can reach the top of the viewport. That padding
 * is empty space below the last message, so "at the bottom" means the last
 * message is in view — not that the padded scroll range is exhausted. Because
 * `scrollHeight` includes that padding, the distance subtracts `paddingEnd`.
 * Negative when the viewport is scrolled past the content bottom, into the
 * padding.
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
 */
export const contentBottomOffset = (el: HTMLElement, virtualizer: Virtualizer<HTMLDivElement, Element>): number => {
  const paddingEnd = virtualizer.options.paddingEnd ?? 0;
  return Math.max(0, el.scrollHeight - paddingEnd - el.clientHeight);
};

/**
 * The `scrollTop` every "scroll to the bottom" site targets: the content bottom
 * plus `PIN_BOTTOM_GAP` of visible padding below the last message.
 *
 * Prefer this to `virtualizer.scrollToIndex(last, { align: "end" })`, which for
 * the final item resolves to `getMaxScrollOffset()` and parks `scrollTop` at the
 * very end of the padded range — flush against the scroll limit, with no slack
 * for a turn-end shrink to absorb (the padding floor guarantees
 * `TURN_END_SHRINK_SLACK` remains below this offset). Clamped to the browser's
 * scroll range for the windows where `paddingEnd` has not converged yet.
 */
export const bottomPinOffset = (el: HTMLElement, virtualizer: Virtualizer<HTMLDivElement, Element>): number => {
  const contentBottom = contentBottomOffset(el, virtualizer);
  // Content that still fits the viewport needs no gap — the padding can make the
  // range scrollable before the content overflows, and pinning into it would
  // only scroll the top of the chat out of view to show empty space.
  if (contentBottom === 0) return 0;
  return Math.min(contentBottom + PIN_BOTTOM_GAP, maxScrollOffset(el));
};
