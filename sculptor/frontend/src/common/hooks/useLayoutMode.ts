import { useSyncExternalStore } from "react";

import { isElectron } from "~/electron/utils.ts";

/**
 * useLayoutMode — the single source of truth for "mobile vs desktop".
 *
 * **Never mobile in the Electron renderer.** The mobile UX is an experimental
 * web-only surface: the desktop app must keep the desktop layout no matter how
 * narrow the window is dragged or whether the machine has a touchscreen
 * (`pointer: coarse`). The check is `isElectron()` (the contextBridge API),
 * decided once at module load — the preload script runs before any page
 * script, so the verdict is available synchronously and never changes.
 *
 * In a browser, the view is **mobile** when EITHER the viewport is narrow
 * (< 768px, i.e. Radix's `sm` breakpoint) OR the platform is a real touch
 * phone. The width trigger keeps the mobile shell developable/testable in a
 * narrow desktop-browser window; the platform signal is computed once and
 * exposed separately so future platform-only conventions (back gesture,
 * system font) can key off it. Safe-area insets are handled in CSS via
 * `env(safe-area-inset-*)` and are NOT keyed off `platform` here.
 *
 * The current verdict is mirrored onto `<html>` as the `mobileUx` class, and
 * every mobile-only stylesheet rule keys off that class INSTEAD of repeating
 * media queries: one decider, so CSS and JS can never disagree (and the
 * Electron exemption applies to CSS for free). Do not add
 * `@media (max-width: 767px)` / `(pointer: coarse)` mobile rules — scope them
 * under `html.mobileUx`.
 *
 * Render discipline (F1): consumers re-render **only when the mode flips**,
 * never on every resize. We subscribe to the `MediaQueryList` `change` event
 * (not `resize`) and only notify listeners when the boolean actually flips.
 * `getSnapshot` returns a cached, frozen object so `useSyncExternalStore`
 * bails out of re-rendering until the flip.
 */

export type LayoutMode = "mobile" | "desktop";
export type Platform = "ios" | "android" | "other";

export type LayoutState = {
  /** "mobile" when narrow OR a real touch phone. */
  mode: LayoutMode;
  /** Convenience === (mode === "mobile"). */
  isMobile: boolean;
  /** True device platform, computed once at startup. */
  platform: Platform;
  /** True for coarse-pointer / touch devices. */
  isTouch: boolean;
};

// < 768px === Radix `sm`. Kept in sync with CSS responsive props ({ initial, sm }).
const NARROW_QUERY = "(max-width: 767px)";

type PlatformInfo = {
  platform: Platform;
  isTouch: boolean;
  /** A real mobile **phone** (drives platform-mobile, distinct from a wide tablet). */
  isPhone: boolean;
};

// Platform detection — static, computed once.
function detectPlatform(): PlatformInfo {
  if (typeof navigator === "undefined" || typeof window === "undefined") {
    return { platform: "other", isTouch: false, isPhone: false };
  }
  const isTouch =
    (typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches) ||
    navigator.maxTouchPoints > 0;

  // Modern UA-Client-Hints when available.
  const uaData = (navigator as unknown as { userAgentData?: { mobile?: boolean; platform?: string } }).userAgentData;
  if (uaData?.mobile) {
    const isAndroid = (uaData.platform ?? "").toLowerCase().includes("android");
    return { platform: isAndroid ? "android" : "ios", isTouch, isPhone: true };
  }

  const ua = navigator.userAgent ?? "";
  if (/Android/i.test(ua)) {
    // Android phones report "Mobile"; Android tablets typically do not.
    return { platform: "android", isTouch, isPhone: /Mobile/i.test(ua) };
  }

  if (/iPhone|iPod/i.test(ua)) {
    return { platform: "ios", isTouch, isPhone: true };
  }

  if (/iPad/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) {
    // iPadOS reports as desktop Safari ("MacIntel"); treat as iOS but NOT a
    // phone — a wide iPad in landscape should stay on the desktop layout and
    // only flip to mobile via the width trigger.
    return { platform: "ios", isTouch, isPhone: false };
  }
  return { platform: "other", isTouch, isPhone: false };
}

const platformInfo: PlatformInfo = detectPlatform();

// Decided once at module load: the preload's contextBridge API exists before
// any page script runs, and a renderer can't change flavor afterwards.
const isElectronRenderer = isElectron();

let mediaQueryList: MediaQueryList | null = null;
function getMediaQueryList(): MediaQueryList | null {
  if (mediaQueryList === null && typeof window !== "undefined" && typeof window.matchMedia === "function") {
    mediaQueryList = window.matchMedia(NARROW_QUERY);
  }
  return mediaQueryList;
}

function computeIsMobile(): boolean {
  // The desktop app never flips to the mobile layout (see the module doc).
  if (isElectronRenderer) return false;
  const mql = getMediaQueryList();
  const isNarrow = mql !== null ? mql.matches : false;
  return isNarrow || platformInfo.isPhone;
}

/**
 * Mirror the verdict onto `<html>` so stylesheets key off `html.mobileUx`
 * instead of their own media queries (see the module doc). Kept in lockstep
 * with `cachedState` by the two call sites: module init and the flip handler.
 */
function syncMobileUxClass(isMobile: boolean): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("mobileUx", isMobile);
}

function buildState(isMobile: boolean): LayoutState {
  return Object.freeze({
    mode: isMobile ? "mobile" : "desktop",
    isMobile,
    platform: platformInfo.platform,
    isTouch: platformInfo.isTouch,
  });
}

// Cached snapshot — replaced only on a true mode flip so consumers don't
// re-render on every resize.
let cachedState: LayoutState = buildState(computeIsMobile());
const listeners = new Set<() => void>();
// Main.tsx imports this module before the first render, so the class is on
// <html> before any mobile-gated rule could matter.
syncMobileUxClass(cachedState.isMobile);

function handleChange(): void {
  const isNextMobile = computeIsMobile();
  if (isNextMobile !== cachedState.isMobile) {
    cachedState = buildState(isNextMobile);
    syncMobileUxClass(isNextMobile);
    for (const listener of listeners) listener();
  }
}

function subscribe(onStoreChange: () => void): () => void {
  // The Electron verdict is static — no flip is possible, so don't wire the
  // media-query listener at all.
  const mql = isElectronRenderer ? null : getMediaQueryList();
  if (listeners.size === 0 && mql !== null) {
    mql.addEventListener("change", handleChange);
  }
  listeners.add(onStoreChange);
  return (): void => {
    listeners.delete(onStoreChange);
    if (listeners.size === 0 && mql !== null) {
      mql.removeEventListener("change", handleChange);
    }
  };
}

function getSnapshot(): LayoutState {
  return cachedState;
}

/** Full layout state: mode / isMobile / platform / isTouch. */
export function useLayoutMode(): LayoutState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Convenience hook for the common "am I mobile?" check (re-renders only on flip). */
export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot).isMobile;
}
