import type { MutableRefObject, ReactElement, ReactNode, RefObject } from "react";
import { createContext, useContext, useEffect, useMemo, useRef } from "react";

// A single subscription point for "the alpha chat just scrolled" events.
// Popover-owning components deep in the chat tree can subscribe via
// `useCloseOnChatScroll` to dismiss their popover when the user scrolls
// — without each component having to discover the scroll container ref
// themselves. Centralizing the listener also means one passive scroll
// handler instead of N independent ones competing for main-thread time.

type ChatScrollContextValue = {
  subscribe: (cb: () => void) => () => void;
};

const ChatScrollContext = createContext<ChatScrollContextValue | null>(null);

type ChatScrollProviderProps = {
  scrollContainerRef: RefObject<HTMLElement>;
  // Owned by `useAlphaAutoScroll`. True for ~150ms after a wheel / touch /
  // keydown on the scroll container. The provider treats only user-initiated
  // scrolls as dismissal signals: if the user hasn't touched the surface
  // recently, the scroll event was almost certainly system-driven
  // (virtualizer item-size corrections, ResizeObserver-driven re-anchoring,
  // browser scroll anchoring, focus-into-view, etc.) and the popover the
  // user just opened should stay open.
  isUserScrollingRef?: MutableRefObject<boolean>;
  children: ReactNode;
};

export const ChatScrollProvider = ({
  scrollContainerRef,
  isUserScrollingRef,
  children,
}: ChatScrollProviderProps): ReactElement => {
  const subscribersRef = useRef<Set<() => void>>(new Set());

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    let lastScrollTop = el.scrollTop;
    const onScroll = (): void => {
      const currentScrollTop = el.scrollTop;
      const didMove = currentScrollTop !== lastScrollTop;
      lastScrollTop = currentScrollTop;
      if (!didMove) return;
      if (isUserScrollingRef && !isUserScrollingRef.current) return;
      // Snapshot to allow callbacks that unsubscribe themselves during
      // dispatch (e.g. an unmount-on-close popover).
      const snapshot = Array.from(subscribersRef.current);
      for (const cb of snapshot) cb();
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return (): void => {
      el.removeEventListener("scroll", onScroll);
    };
  }, [scrollContainerRef, isUserScrollingRef]);

  const value = useMemo<ChatScrollContextValue>(
    () => ({
      subscribe: (cb) => {
        subscribersRef.current.add(cb);
        return (): void => {
          subscribersRef.current.delete(cb);
        };
      },
    }),
    [],
  );

  return <ChatScrollContext.Provider value={value}>{children}</ChatScrollContext.Provider>;
};

// Calls `onClose` whenever the alpha chat scroll container fires a
// scroll event, but only while `enabled` is true. The callback is
// re-subscribed when it changes, so passing a fresh closure each render
// is fine — but stable callbacks avoid the churn.
// eslint-disable-next-line react-refresh/only-export-components
export const useCloseOnChatScroll = (onClose: () => void, enabled: boolean): void => {
  const ctx = useContext(ChatScrollContext);
  useEffect(() => {
    if (!ctx || !enabled) return;
    return ctx.subscribe(onClose);
  }, [ctx, onClose, enabled]);
};
