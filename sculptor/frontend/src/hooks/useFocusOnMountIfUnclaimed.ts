import type { RefObject } from "react";
import { useEffect } from "react";

/**
 * Focus ``ref`` on mount only if no element currently claims focus.
 *
 * For components that mount in response to async events (server pushes, agent
 * tool calls) and replace another element. When the predecessor element had
 * focus, the browser drops focus to ``document.body`` as it unmounts — so
 * ``activeElement === body`` means "the thing I'm replacing had focus, or
 * nothing did" and we can take it. Anything else means another component
 * (terminal, file browser, sidebar) holds focus and we must not disturb it.
 */
export const useFocusOnMountIfUnclaimed = (ref: RefObject<HTMLElement | null>): void => {
  useEffect(() => {
    const active = document.activeElement;
    if (active === null || active === document.body) {
      ref.current?.focus();
    }
    // `ref` is a stable RefObject, so this runs once on mount.
  }, [ref]);
};
