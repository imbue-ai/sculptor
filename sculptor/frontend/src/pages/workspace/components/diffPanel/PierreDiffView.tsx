import type { FileDiffMetadata, FileDiffOptions } from "@pierre/diffs";
import { getSingularPatch, processFile } from "@pierre/diffs";
import { FileDiff, PatchDiff } from "@pierre/diffs/react";
import { useAtomValue, useSetAtom } from "jotai";
import { Plus } from "lucide-react";
import type { CSSProperties, ErrorInfo, ReactElement, ReactNode, RefObject } from "react";
import { Component, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";

import { ElementIds } from "~/api";
import { themeCodeThemeAtom } from "~/common/state/atoms/themeBuilder.ts";
import { getShikiThemes } from "~/common/theme/shikiThemes.ts";

import { splitDiffColumnRatioAtom, spotlightInsertAtom } from "./atoms.ts";
import styles from "./PierreDiffView.module.scss";
import {
  adoptPierreOverrideSheet,
  createPierreOverrideSheet,
  HIDE_NATIVE_HSCROLLBAR_CSS,
} from "./pierreShadowStyles.ts";
import { SplitDiffHandle } from "./SplitDiffHandle.tsx";
import { StickyHorizontalScrollbar } from "./StickyHorizontalScrollbar.tsx";
import type { DiffViewType, SpotlightData } from "./types.ts";
import { usePierreHighlighterReady } from "./usePierreHighlighterReady.ts";
import { type SpotlightCaptureResult, useSpotlightCapture } from "./useSpotlightCapture.ts";
import { useSpotlightOverlay } from "./useSpotlightOverlay.ts";

type PierreDiffViewProps = {
  diffString: string;
  viewType: DiffViewType;
  overflow: "wrap" | "scroll";
  themeType: "light" | "dark" | "system";
  className?: string;
  /** Full old-file lines (each ending with `\n`). Enables hunk expansion. */
  oldLines?: Array<string>;
  /** Full new-file lines (each ending with `\n`). Enables hunk expansion. */
  newLines?: Array<string>;
  /**
   * When true, the component does not render its own drag handle.
   * Use this when a parent component renders a single handle that spans
   * multiple diffs (e.g. the combined "Review all" view).
   */
  hideHandle?: boolean;
  /** The file path this diff/file view is showing. Enables spotlight capture. */
  spotlightFile?: string;
  /** Which diff side the view is anchored to, if any (null for plain file views). */
  spotlightSide?: "old" | "new" | null;
  /** Which pane the spotlight capture came from — drives the system-reminder shape. Defaults to "file-view". */
  spotlightScope?: SpotlightData["scope"];
  /** Commit hash — set only when scope is "commit-diff". */
  spotlightCommitRef?: string;
};

/**
 * Error boundary that catches Pierre render failures (e.g. when the diff
 * string and line arrays are temporarily out of sync) and falls back to
 * `PatchDiff` which doesn't require line arrays.
 *
 * React requires class components for error boundaries.
 */
type FileDiffErrorBoundaryProps = {
  children: ReactNode;
  fallback: ReactNode;
  /** When this key changes the boundary resets, giving FileDiff another try. */
  resetKey: string;
};

type FileDiffErrorBoundaryState = {
  hasError: boolean;
};

class FileDiffErrorBoundary extends Component<FileDiffErrorBoundaryProps, FileDiffErrorBoundaryState> {
  override state: FileDiffErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): FileDiffErrorBoundaryState {
    return { hasError: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("FileDiff render failed, falling back to PatchDiff", error.message, info.componentStack);
  }

  override componentDidUpdate(prevProps: FileDiffErrorBoundaryProps): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// The shared background override (see pierreShadowStyles.ts) plus this view's
// split-column override: inherited CSS custom properties
// (`--diffs-split-left` / `--diffs-split-right`) set on the outer container
// control the width ratio of each side in side-by-side mode.
const bgOverrideSheet = createPierreOverrideSheet(
  [
    "[data-type='split'][data-overflow='scroll'] {",
    "  grid-template-columns: var(--diffs-split-left, 1fr) var(--diffs-split-right, 1fr) !important;",
    "}",
    "[data-type='split'][data-overflow='wrap'] {",
    "  grid-template-columns:",
    "    minmax(min-content, max-content) var(--diffs-split-left, 1fr)",
    "    minmax(min-content, max-content) var(--diffs-split-right, 1fr) !important;",
    "}",
  ].join("\n"),
  HIDE_NATIVE_HSCROLLBAR_CSS,
);

export const PierreDiffView = ({
  diffString,
  viewType,
  overflow,
  themeType,
  className,
  oldLines,
  newLines,
  hideHandle = false,
  spotlightFile,
  spotlightSide,
  spotlightScope = "file-view",
  spotlightCommitRef,
}: PierreDiffViewProps): ReactElement => {
  const splitRatio = useAtomValue(splitDiffColumnRatioAtom);
  const codeTheme = useAtomValue(themeCodeThemeAtom);
  const shikiThemes = getShikiThemes(codeTheme);
  // Pierre must not MOUNT before its shared highlighter has these themes
  // attached — a cold-themes first mount paints nothing and does not survive
  // React StrictMode's remount (see usePierreHighlighterReady).
  const isHighlighterReady = usePierreHighlighterReady(shikiThemes);
  const options = useMemo(
    (): FileDiffOptions<undefined> => ({
      diffStyle: viewType,
      overflow,
      themeType,
      theme: shikiThemes,
      diffIndicators: "bars",
      lineDiffType: "word-alt",
      expandUnchanged: false,
      disableFileHeader: true,
    }),
    [viewType, overflow, themeType, shikiThemes],
  );

  /**
   * When full file content is available, parse the patch into FileDiffMetadata
   * and attach the line arrays so Pierre can render expandable hunk separators.
   */
  const fileDiffMetadata = useMemo((): FileDiffMetadata | null => {
    if (!oldLines || !newLines) return null;
    try {
      // Ensure the diff string ends with \n so Pierre's processLines correctly
      // delimits the last hunk line from expansion lines drawn from the full
      // file content.  Without this, the last hunk line and the first expansion
      // line merge into a single Shiki line, shifting all subsequent line numbers.
      const normalizedDiff = diffString.endsWith("\n") ? diffString : diffString + "\n";
      // @pierre/diffs 1.2 indexes hunks into deletionLines/additionLines, so
      // full file contents must be supplied at parse time via processFile —
      // overwriting the arrays on a getSingularPatch() result would leave the
      // hunk line indices pointing at partial-mode offsets and corrupt the
      // rendered diff.
      const parsed = getSingularPatch(normalizedDiff);
      return (
        processFile(normalizedDiff, {
          oldFile: { name: parsed.prevName ?? parsed.name, contents: oldLines.join("") },
          newFile: { name: parsed.name, contents: newLines.join("") },
        }) ?? null
      );
    } catch {
      return null;
    }
  }, [diffString, oldLines, newLines]);

  const pierreRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  /**
   * Inject our bg-override stylesheet into Pierre's shadow DOM (see
   * adoptPierreOverrideSheet for why this is a layout effect).
   *
   * Re-runs when `hasFileDiffMetadata` flips, because the inner Pierre
   * component may switch between `<FileDiff>` and `<PatchDiff>`, each of
   * which creates a *new* `<diffs-container>` with a fresh shadow root — and
   * when the highlighter gate opens, which is when the container first mounts.
   */
  const hasFileDiffMetadata = !!fileDiffMetadata;
  useLayoutEffect(() => {
    adoptPierreOverrideSheet(pierreRef.current, bgOverrideSheet);
  }, [hasFileDiffMetadata, isHighlighterReady]);

  /**
   * Forward horizontal wheel events from the empty space below the diff
   * content to Pierre's `[data-code]` element(s) inside the shadow DOM,
   * so horizontal scrolling works anywhere in the panel.
   */
  const getCodeElements = useCallback((): Array<Element> => {
    const shadowRoot = pierreRef.current?.querySelector("diffs-container")?.shadowRoot;
    if (!shadowRoot) return [];
    return Array.from(shadowRoot.querySelectorAll("[data-code]"));
  }, []);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper || overflow !== "scroll") return;

    const handleWheel = (e: WheelEvent): void => {
      // Only handle horizontal scrolling (shift+wheel or trackpad horizontal)
      const deltaX = e.deltaX || (e.shiftKey ? e.deltaY : 0);
      if (deltaX === 0) return;

      // If the event originated inside a [data-code] element, Pierre already
      // handles the scroll natively. Check composedPath() to see through the
      // shadow DOM boundary.
      const path = e.composedPath();
      if (path.some((el) => el instanceof Element && el.matches("[data-code]"))) return;

      const codeEls = getCodeElements();
      for (const el of codeEls) {
        el.scrollLeft += deltaX;
      }
    };

    wrapper.addEventListener("wheel", handleWheel, { passive: true });
    return (): void => {
      wrapper.removeEventListener("wheel", handleWheel);
    };
  }, [overflow, getCodeElements]);

  const isSplit = viewType === "split";
  const splitStyle = isSplit
    ? ({
        "--diffs-split-left": `${splitRatio}fr`,
        "--diffs-split-right": `${100 - splitRatio}fr`,
      } as CSSProperties)
    : undefined;

  const patchFallback = <PatchDiff patch={diffString} options={options} />;

  const hasScrollbar = overflow === "scroll";

  // --- Spotlight capture --------------------------------------------------
  const setSpotlight = useSetAtom(spotlightInsertAtom);

  const handleSpotlightCapture = useCallback(
    (result: SpotlightCaptureResult): void => {
      if (!spotlightFile) return;
      setSpotlight({
        file: spotlightFile,
        lineStart: result.lineStart,
        lineEnd: result.lineEnd,
        // Prefer the side derived from the captured line's `data-line-type`
        // (accurate for modified files where both sides are present); fall
        // back to the per-file hint for added/deleted single-side diffs.
        side: result.side ?? spotlightSide ?? null,
        snippet: result.snippet,
        snippetCapturedAt: new Date().toISOString(),
        scope: spotlightScope,
        commitRef: spotlightCommitRef,
      });
    },
    [spotlightFile, spotlightSide, spotlightScope, spotlightCommitRef, setSpotlight],
  );

  const spotlight = useSpotlightCapture({
    containerRef: pierreRef,
    boundsRef: wrapperRef,
    isHighlighterReady,
    enabled: spotlightFile !== undefined,
    onCapture: handleSpotlightCapture,
  });
  const handleSpotlightPillMouseDown = spotlight.onButtonMouseDown;
  // Hover-highlight + click-scroll driven by spotlight chips in the chat.
  useSpotlightOverlay({ containerRef: pierreRef, file: spotlightFile, isHighlighterReady });
  // --- end Spotlight capture ----------------------------------------------

  return (
    <div ref={wrapperRef} className={styles.splitWrapper} style={splitStyle}>
      <div className={styles.scrollColumn}>
        <div
          className={`${styles.container} ${className ?? ""}`}
          data-testid={viewType === "unified" ? ElementIds.DIFF_VIEW_UNIFIED : ElementIds.DIFF_VIEW_SPLIT}
        >
          {spotlight.buttonStyle && (
            <button
              type="button"
              data-testid={ElementIds.SPOTLIGHT_LINE_HOVER_BUTTON}
              className={styles.spotlightButton}
              style={spotlight.buttonStyle}
              onMouseDown={handleSpotlightPillMouseDown}
            >
              <Plus size={12} strokeWidth={2.5} />
              <span>Spotlight</span>
            </button>
          )}
          <div ref={pierreRef}>
            {isHighlighterReady &&
              (fileDiffMetadata ? (
                <FileDiffErrorBoundary resetKey={diffString} fallback={patchFallback}>
                  <FileDiff fileDiff={fileDiffMetadata} options={options} />
                </FileDiffErrorBoundary>
              ) : (
                patchFallback
              ))}
          </div>
        </div>
        {hasScrollbar && <StickyHorizontalScrollbar containerRef={pierreRef} />}
      </div>
      {isSplit && !hideHandle && <SplitDiffHandle containerRef={wrapperRef as RefObject<HTMLElement | null>} />}
    </div>
  );
};
