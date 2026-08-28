import { areThemesAttached, getSharedHighlighter, isHighlighterLoaded } from "@pierre/diffs";
import { useEffect, useState } from "react";
import type { BundledTheme } from "shiki/bundle/web";

type ShikiThemePair = { light: BundledTheme; dark: BundledTheme };

/**
 * True once Pierre's shared syntax highlighter has `themes` attached — the
 * precondition for a Pierre component's FIRST render to paint synchronously.
 *
 * Pierre paints nothing when it mounts with the themes unattached: it leaves a
 * bare `<pre>` behind and relies on an async recovery re-render once the
 * themes load. Under React StrictMode (the dev bundle) the simulated remount
 * severs that recovery — the remounted instance finds the aborted mount's
 * empty `<pre>`, mistakes it for prerendered content, and never renders — so
 * the first diff of a dev session stays permanently blank. Gating the Pierre
 * mount on this hook makes the first real render synchronous and
 * remount-safe; attachment resolves in milliseconds, so the gate is not a
 * visible loading state.
 *
 * Readiness never flips back to false: a runtime theme SWITCH is handled by
 * the already-live Pierre instance, whose recovery re-render wiring is intact
 * (only the mount-time cold start is remount-fragile).
 */
export const usePierreHighlighterReady = (themes: ShikiThemePair): boolean => {
  const [isReady, setIsReady] = useState<boolean>(() => isHighlighterLoaded() && areThemesAttached(themes));

  useEffect(() => {
    if (isReady) {
      return;
    }
    let isCancelled = false;
    const markReady = (): void => {
      if (!isCancelled) {
        setIsReady(true);
      }
    };
    getSharedHighlighter({ themes: [themes.light, themes.dark], langs: [] }).then(markReady, (error: unknown) => {
      // Loading failed (e.g. a dropped chunk request): mount Pierre anyway and
      // let its own recovery path retry — never gate the diff forever.
      console.warn("Pierre highlighter preload failed; mounting without it", error);
      markReady();
    });
    return (): void => {
      isCancelled = true;
    };
  }, [isReady, themes]);

  return isReady;
};
