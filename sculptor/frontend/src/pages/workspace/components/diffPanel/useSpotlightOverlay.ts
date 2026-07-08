import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";

import { spotlightHoverAtom, spotlightScrollTargetAtom } from "./atoms.ts";
import { clearLinePaint, paintLineRange, scrollLineIntoView, shadowRootOf } from "./spotlightPaint.ts";
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
  const domVersion = usePierreDomVersion(paneElement, file !== undefined);

  // Hover highlight — repaints on every DOM version bump so a Pierre re-render
  // (which wipes inline styles) doesn't drop the highlight.
  useEffect(() => {
    const shadowRoot = shadowRootOf(paneElement);
    if (!shadowRoot) return;
    const isMatch = hover !== null && file !== undefined && hover.file === file;
    if (isMatch) {
      paintLineRange(shadowRoot, hover.lineStart, hover.lineEnd);
      return (): void => clearLinePaint(shadowRoot);
    }
    clearLinePaint(shadowRoot);
    return undefined;
  }, [hover, file, paneElement, domVersion]);

  // Click scroll — retries deterministically as rows stream in: each DOM
  // version bump re-runs this effect; once the target row exists we scroll and
  // clear the request so later bumps are no-ops.
  useEffect(() => {
    if (!scrollTarget || file === undefined || scrollTarget.file !== file) return;
    const shadowRoot = shadowRootOf(paneElement);
    if (shadowRoot && scrollLineIntoView(shadowRoot, scrollTarget.lineStart)) {
      setScrollTarget(null);
    }
  }, [scrollTarget, file, paneElement, domVersion, setScrollTarget]);
};
