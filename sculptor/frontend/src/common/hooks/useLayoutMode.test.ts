import { afterEach, describe, expect, it, vi } from "vitest";

import type * as LayoutModule from "./useLayoutMode.ts";

/**
 * useLayoutMode decides mobile-vs-desktop once per module load (Electron
 * detection, platform sniff) and caches a snapshot, so every case re-imports
 * the module fresh via vi.resetModules() after arranging the environment.
 */

type MediaQueryChangeListener = (event: { matches: boolean }) => void;

/** Install a matchMedia stub reporting `matches` for the narrow query and
 *  capture change listeners so a test can simulate a viewport flip. */
const stubMatchMedia = (
  matches: boolean,
): { listeners: Set<MediaQueryChangeListener>; setMatches: (m: boolean) => void } => {
  const listeners = new Set<MediaQueryChangeListener>();
  const state = { matches };
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches(): boolean {
      // The platform sniff also probes "(pointer: coarse)" — report false so
      // these tests exercise only the width trigger.
      return query.includes("max-width") ? state.matches : false;
    },
    media: query,
    addEventListener: (_type: string, listener: MediaQueryChangeListener): void => {
      listeners.add(listener);
    },
    removeEventListener: (_type: string, listener: MediaQueryChangeListener): void => {
      listeners.delete(listener);
    },
  }));
  return {
    listeners,
    setMatches: (m: boolean): void => {
      state.matches = m;
      for (const listener of listeners) listener({ matches: m });
    },
  };
};

const importFresh = async (): Promise<typeof LayoutModule> => {
  vi.resetModules();
  return import("./useLayoutMode.ts");
};

afterEach(() => {
  vi.unstubAllGlobals();
  // The module toggles this class at import time; reset between cases.
  document.documentElement.classList.remove("mobileUx");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test-only cleanup of the Electron marker
  delete (window as any).sculptor;
});

describe("useLayoutMode Electron gating", () => {
  it("never sets html.mobileUx at import in the Electron renderer, even when narrow", async () => {
    // window.sculptor is the contextBridge API — its presence IS the Electron check.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- installing the Electron marker
    (window as any).sculptor = {};
    stubMatchMedia(true); // narrow viewport — would be mobile in a browser

    await importFresh();

    expect(document.documentElement.classList.contains("mobileUx")).toBe(false);
  });

  it("reports mobile and sets html.mobileUx in a narrow browser viewport", async () => {
    stubMatchMedia(true);

    await importFresh();

    expect(document.documentElement.classList.contains("mobileUx")).toBe(true);
  });

  it("reports desktop in a wide browser viewport and mirrors flips onto html.mobileUx", async () => {
    const media = stubMatchMedia(false);

    const mod = await importFresh();
    expect(document.documentElement.classList.contains("mobileUx")).toBe(false);

    // Render the hook so the store wires its media listener, then flip the
    // viewport under it.
    const { renderHook, act } = await import("@testing-library/react");
    const { result } = renderHook(() => mod.useIsMobile());
    expect(result.current).toBe(false);

    act(() => {
      media.setMatches(true);
    });
    expect(result.current).toBe(true);
    expect(document.documentElement.classList.contains("mobileUx")).toBe(true);

    act(() => {
      media.setMatches(false);
    });
    expect(result.current).toBe(false);
    expect(document.documentElement.classList.contains("mobileUx")).toBe(false);
  });

  it("stays desktop in Electron even under the hook with a narrow viewport", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- installing the Electron marker
    (window as any).sculptor = {};
    const media = stubMatchMedia(true);

    const mod = await importFresh();
    const { renderHook, act } = await import("@testing-library/react");
    const { result } = renderHook(() => mod.useIsMobile());

    expect(result.current).toBe(false);
    // Even a (hypothetical) media flip cannot change the verdict — no listener
    // was ever attached.
    act(() => {
      media.setMatches(false);
      media.setMatches(true);
    });
    expect(result.current).toBe(false);
    expect(media.listeners.size).toBe(0);
    expect(document.documentElement.classList.contains("mobileUx")).toBe(false);
  });
});
