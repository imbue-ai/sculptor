import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";

import { spotlightHoverAtom, spotlightScrollTargetAtom } from "./atoms.ts";
import { clearLinePaint, paintLineRange, scrollLineIntoView, shadowRootOf } from "./spotlightPaint.ts";

type UseSpotlightOverlayOptions = {
  /** Wraps the Pierre `<diffs-container>` whose shadow root holds the lines. */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** The file this viewer is currently showing; anchors only match this file. */
  file: string | undefined;
  /** Overlay work is inert until Pierre has painted its lines. */
  isHighlighterReady: boolean;
};

// Pierre streams line rows in as Shiki tokenises, so a freshly-opened file may
// not have the target row yet. Retry the scroll on a bounded rAF loop until the
// row appears (or we give up), rather than firing once into an empty container.
const MAX_SCROLL_ATTEMPTS = 60;

/**
 * Wires a diff/file viewer to the two chip-driven overlays:
 *  - hover a spotlight chip → paint its source lines blue in the matching file
 *  - click a spotlight chip → scroll its source line into view once painted
 *
 * Both are no-ops unless the hovered/clicked anchor's file matches this
 * viewer's file, so an unrelated pane never lights up.
 */
export const useSpotlightOverlay = ({ containerRef, file, isHighlighterReady }: UseSpotlightOverlayOptions): void => {
  const hover = useAtomValue(spotlightHoverAtom);
  const scrollTarget = useAtomValue(spotlightScrollTargetAtom);
  const setScrollTarget = useSetAtom(spotlightScrollTargetAtom);

  // Hover highlight.
  useEffect(() => {
    const shadowRoot = shadowRootOf(containerRef.current);
    if (!shadowRoot || !isHighlighterReady) return;
    const isMatch = hover !== null && file !== undefined && hover.file === file;
    if (isMatch) {
      paintLineRange(shadowRoot, hover.lineStart, hover.lineEnd);
      return (): void => clearLinePaint(shadowRoot);
    }
    clearLinePaint(shadowRoot);
    return undefined;
  }, [hover, file, isHighlighterReady, containerRef]);

  // Click scroll.
  useEffect(() => {
    if (!scrollTarget || file === undefined || scrollTarget.file !== file || !isHighlighterReady) return;

    let attempts = 0;
    let frame = 0;
    const tryScroll = (): void => {
      const shadowRoot = shadowRootOf(containerRef.current);
      if (shadowRoot && scrollLineIntoView(shadowRoot, scrollTarget.lineStart)) {
        setScrollTarget(null);
        return;
      }
      attempts += 1;
      if (attempts < MAX_SCROLL_ATTEMPTS) frame = requestAnimationFrame(tryScroll);
    };
    frame = requestAnimationFrame(tryScroll);
    return (): void => cancelAnimationFrame(frame);
  }, [scrollTarget, file, isHighlighterReady, containerRef, setScrollTarget]);
};
