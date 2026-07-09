import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";

import {
  spotlightColorMapAtom,
  spotlightDraftAnchorsAtom,
  spotlightHoverAtom,
  spotlightScrollTargetAtom,
} from "./atoms.ts";
import {
  clearLinePaint,
  paintAnchorRanges,
  paintGutterBars,
  scrollLineIntoView,
  shadowRootOf,
} from "./spotlightPaint.ts";
import { spotlightBarColor, spotlightColorIndex, spotlightHoverHighlightColor } from "./spotlightPalette.ts";
import { spotlightPrimaryRange } from "./types.ts";
import { usePierreDomVersion } from "./usePierreDomVersion.ts";

type UseSpotlightOverlayOptions = {
  /**
   * The visible pane containing the Pierre `<diffs-container>`. Passed as an
   * element (from a callback ref) so the effects re-run exactly when it mounts.
   */
  paneElement: HTMLElement | null;
  /** The file this viewer is currently showing; anchors only match this file. */
  file: string | undefined;
};

/**
 * Wires a diff/file viewer to the two chip-driven overlays:
 *  - hover (or arrow-select) a spotlight chip → paint its source lines blue
 *  - click a spotlight chip → scroll its source line into view once painted
 *
 * Both are no-ops unless the anchor's file matches this viewer's file, so an
 * unrelated pane never lights up. Both key off `usePierreDomVersion` so they
 * re-run as Pierre streams rows in — no readiness gate, no polling.
 */
export const useSpotlightOverlay = ({ paneElement, file }: UseSpotlightOverlayOptions): void => {
  const hover = useAtomValue(spotlightHoverAtom);
  const scrollTarget = useAtomValue(spotlightScrollTargetAtom);
  const setScrollTarget = useSetAtom(spotlightScrollTargetAtom);
  const draftAnchors = useAtomValue(spotlightDraftAnchorsAtom);
  const colorMap = useAtomValue(spotlightColorMapAtom);
  const domVersion = usePierreDomVersion(paneElement, file !== undefined);

  // Hover highlight — repaints on every DOM version bump so a Pierre re-render
  // (which wipes inline styles) doesn't drop the highlight.
  useEffect(() => {
    const shadowRoot = shadowRootOf(paneElement);
    if (!shadowRoot) return;
    const isMatch = hover !== null && file !== undefined && hover.file === file;
    if (isMatch) {
      paintAnchorRanges(shadowRoot, hover.previousFileLines, hover.currentFileLines, spotlightHoverHighlightColor());
      return (): void => clearLinePaint(shadowRoot);
    }
    clearLinePaint(shadowRoot);
    return undefined;
  }, [hover, file, paneElement, domVersion, colorMap]);

  // Persistent gutter bars — one coloured strip per spotlight chip in the
  // current draft. Painted on every DOM version bump so Pierre re-renders
  // (which wipe all shadow-DOM children) don't drop the bars.
  useEffect(() => {
    const shadowRoot = shadowRootOf(paneElement);
    if (!shadowRoot || !file) return;
    paintGutterBars(
      shadowRoot,
      draftAnchors,
      file,
      (anchor) => spotlightBarColor(spotlightColorIndex(anchor, colorMap)),
      hover,
    );
  }, [draftAnchors, file, paneElement, domVersion, colorMap, hover]);

  // Click scroll — retries deterministically as rows stream in.
  useEffect(() => {
    if (!scrollTarget || file === undefined || scrollTarget.file !== file) return;
    const shadowRoot = shadowRootOf(paneElement);
    const primary = spotlightPrimaryRange(scrollTarget);
    if (primary !== null && shadowRoot && scrollLineIntoView(shadowRoot, primary.firstLine)) {
      setScrollTarget(null);
    }
  }, [scrollTarget, file, paneElement, domVersion, setScrollTarget]);
};
