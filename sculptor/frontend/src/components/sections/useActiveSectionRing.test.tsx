import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { activeSectionRingNonceAtom, activeSectionRingVisibleAtom, RING_VISIBLE_MS } from "./transientAtoms.ts";
import { useActiveSectionRing } from "./useActiveSectionRing.ts";

describe("useActiveSectionRing", () => {
  let store: ReturnType<typeof createStore>;

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  // Production mounts under <React.StrictMode> (Main.tsx), which re-runs effects while
  // preserving refs. The mount guard must stay idempotent under that double invocation.
  const strictWrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <StrictMode>
      <Provider store={store}>{children}</Provider>
    </StrictMode>
  );

  beforeEach(() => {
    vi.useFakeTimers();
    store = createStore();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not flash the ring on initial mount", () => {
    renderHook(() => useActiveSectionRing(), { wrapper });
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
    act(() => vi.advanceTimersByTime(RING_VISIBLE_MS + 1));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
  });

  it("does not flash the ring on initial mount under StrictMode's double effect run", () => {
    renderHook(() => useActiveSectionRing(), { wrapper: strictWrapper });
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
    act(() => vi.advanceTimersByTime(RING_VISIBLE_MS + 1));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
  });

  it("shows the ring on a nonce bump and hides it after the fade window", () => {
    renderHook(() => useActiveSectionRing(), { wrapper });

    act(() => store.set(activeSectionRingNonceAtom, (n) => n + 1));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(true);

    act(() => vi.advanceTimersByTime(RING_VISIBLE_MS + 1));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
  });

  it("restarts the fade window when re-triggered mid-fade", () => {
    renderHook(() => useActiveSectionRing(), { wrapper });

    act(() => store.set(activeSectionRingNonceAtom, (n) => n + 1));
    act(() => vi.advanceTimersByTime(RING_VISIBLE_MS / 2));
    act(() => store.set(activeSectionRingNonceAtom, (n) => n + 1));

    // Half of the original window has passed, but the fresh bump restarted it.
    act(() => vi.advanceTimersByTime(RING_VISIBLE_MS / 2 + 1));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(true);
    act(() => vi.advanceTimersByTime(RING_VISIBLE_MS / 2));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
  });

  it("resets the ring visibility when unmounted mid-fade", () => {
    const { unmount } = renderHook(() => useActiveSectionRing(), { wrapper });

    act(() => store.set(activeSectionRingNonceAtom, (n) => n + 1));
    expect(store.get(activeSectionRingVisibleAtom)).toBe(true);

    // Unmounting mid-fade must not strand the global atom in the visible state.
    unmount();
    expect(store.get(activeSectionRingVisibleAtom)).toBe(false);
  });
});
