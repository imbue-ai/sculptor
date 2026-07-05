/**
 * React binding for the chat scroll state machine.
 *
 * Creates one machine per chat instance (created once, stable across renders),
 * attaches it to the scroll container so it can reflect
 * `data-scroll-phase` / `data-scroll-settled`, and installs the single
 * user-input listener: a genuine wheel/touch on the container means the user has
 * taken control of the scroll, which preempts any programmatic phase.
 *
 * See docs/development/scroll_state_unification.md.
 */
import type { RefObject } from "react";
import { useEffect, useLayoutEffect, useState } from "react";

import type { ScrollStateMachine } from "./scrollStateMachine.ts";
import { createScrollStateMachine } from "./scrollStateMachine.ts";

export const useScrollStateMachine = (scrollContainerRef: RefObject<HTMLDivElement | null>): ScrollStateMachine => {
  // One machine per chat instance, created lazily and never replaced — held in
  // state (not a ref) so it can be read during render to wire the hooks below.
  // eslint-disable-next-line react/hook-use-state -- stable instance; the setter is intentionally unused
  const [machine] = useState(createScrollStateMachine);

  // Reflect state onto the container so tests (and any observer) can await a
  // phase. Runs as a layout effect so the attribute is present before paint and
  // before the scroll hooks' own layout effects fire their first restore.
  useLayoutEffect(() => {
    machine.attach(scrollContainerRef.current);
    return (): void => machine.attach(null);
  }, [machine, scrollContainerRef]);

  // The single source of "the user grabbed the scroll". Programmatic scrolls
  // (virtualizer corrections, scrollToIndex, restore) fire `scroll` but never
  // `wheel`/`touch`, so this only ever flips authority on genuine input.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (el === null) return;
    const onUserInput = (): void => machine.dispatch({ kind: "userScrolled" });
    el.addEventListener("wheel", onUserInput, { passive: true });
    el.addEventListener("touchstart", onUserInput, { passive: true });
    el.addEventListener("touchmove", onUserInput, { passive: true });
    return (): void => {
      el.removeEventListener("wheel", onUserInput);
      el.removeEventListener("touchstart", onUserInput);
      el.removeEventListener("touchmove", onUserInput);
    };
  }, [machine, scrollContainerRef]);

  return machine;
};
