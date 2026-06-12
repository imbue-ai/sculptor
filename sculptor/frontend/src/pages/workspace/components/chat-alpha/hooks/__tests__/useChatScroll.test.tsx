import { act, render, renderHook } from "@testing-library/react";
import type { MutableRefObject, ReactNode, RefObject } from "react";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { ChatScrollProvider, useCloseOnChatScroll } from "../useChatScroll.tsx";

const flushTask = async (): Promise<void> => {
  await act(async () => {
    await Promise.resolve();
  });
};

// A "real" scroll: scrollTop changed since the last dispatch. The provider
// ignores scroll events whose position didn't actually move, so tests that
// want subscribers to fire must mutate scrollTop before dispatching.
const dispatchScroll = (el: HTMLElement): void => {
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    value: (el.scrollTop as number) + 10,
  });
  el.dispatchEvent(new Event("scroll"));
};

// A "spurious" scroll: scroll event fires but scrollTop is unchanged.
// Matches the browser behavior we want the provider to ignore (e.g. focus
// shift triggering "scroll into view if needed" on an already-visible
// element).
const dispatchSpuriousScroll = (el: HTMLElement): void => {
  el.dispatchEvent(new Event("scroll"));
};

const trueRef = (): MutableRefObject<boolean> => ({ current: true });

describe("ChatScrollProvider", () => {
  it("fires subscribers on user-initiated scroll", async () => {
    const el = document.createElement("div");
    const scrollRef: RefObject<HTMLElement> = { current: el };
    const onClose = vi.fn();

    const wrapper = ({ children }: { children: ReactNode }): JSX.Element => (
      <ChatScrollProvider scrollContainerRef={scrollRef} isUserScrollingRef={trueRef()}>
        {children}
      </ChatScrollProvider>
    );

    renderHook(() => useCloseOnChatScroll(onClose, true), { wrapper });
    await flushTask();

    dispatchScroll(el);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores spurious scroll events that don't change scrollTop", async () => {
    // Regression: chromium fires a `scroll` event with unchanged scrollTop
    // when focus shifts to a newly-clicked element and the browser runs
    // "scroll into view if needed" on something already in view. Treating
    // those as user scrolls dismissed every pinned popover ~15ms after the
    // click that opened it.
    const el = document.createElement("div");
    const scrollRef: RefObject<HTMLElement> = { current: el };
    const onClose = vi.fn();

    const wrapper = ({ children }: { children: ReactNode }): JSX.Element => (
      <ChatScrollProvider scrollContainerRef={scrollRef} isUserScrollingRef={trueRef()}>
        {children}
      </ChatScrollProvider>
    );

    renderHook(() => useCloseOnChatScroll(onClose, true), { wrapper });
    await flushTask();

    // Even with a preceding user input, a zero-delta scroll is ignored.
    el.dispatchEvent(new Event("wheel"));
    dispatchSpuriousScroll(el);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("ignores scrolls when isUserScrollingRef.current is false", async () => {
    // Regression: scroll events fire for many non-user reasons —
    // virtualizer item-size corrections, ResizeObserver-driven anchor
    // adjustments, browser scroll anchoring on content height changes,
    // Popover.Content portal mounting triggering layout shifts. The only
    // reliable way to tell user intent from system motion is to consult
    // the user-input ref owned by `useAlphaAutoScroll`.
    const el = document.createElement("div");
    const scrollRef: RefObject<HTMLElement> = { current: el };
    const isUserScrollingRef = { current: false };
    const onClose = vi.fn();

    const wrapper = ({ children }: { children: ReactNode }): JSX.Element => (
      <ChatScrollProvider scrollContainerRef={scrollRef} isUserScrollingRef={isUserScrollingRef}>
        {children}
      </ChatScrollProvider>
    );

    renderHook(() => useCloseOnChatScroll(onClose, true), { wrapper });
    await flushTask();

    dispatchScroll(el);
    expect(onClose).not.toHaveBeenCalled();

    isUserScrollingRef.current = true;
    dispatchScroll(el);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not fire subscribers when enabled is false", async () => {
    const el = document.createElement("div");
    const scrollRef: RefObject<HTMLElement> = { current: el };
    const onClose = vi.fn();

    const wrapper = ({ children }: { children: ReactNode }): JSX.Element => (
      <ChatScrollProvider scrollContainerRef={scrollRef} isUserScrollingRef={trueRef()}>
        {children}
      </ChatScrollProvider>
    );

    renderHook(() => useCloseOnChatScroll(onClose, false), { wrapper });
    await flushTask();

    dispatchScroll(el);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("supports multiple subscribers", async () => {
    const el = document.createElement("div");
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();

    const Subscriber = ({ onClose }: { onClose: () => void }): null => {
      useCloseOnChatScroll(onClose, true);
      return null;
    };

    const Harness = (): JSX.Element => {
      const ref = useRef(el);
      const isUserScrollingRef = useRef(true);
      return (
        <ChatScrollProvider scrollContainerRef={ref} isUserScrollingRef={isUserScrollingRef}>
          <Subscriber onClose={onCloseA} />
          <Subscriber onClose={onCloseB} />
        </ChatScrollProvider>
      );
    };

    render(<Harness />);
    await flushTask();

    dispatchScroll(el);

    expect(onCloseA).toHaveBeenCalledTimes(1);
    expect(onCloseB).toHaveBeenCalledTimes(1);
  });
});
