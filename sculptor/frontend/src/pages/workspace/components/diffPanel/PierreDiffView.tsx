import type { FileDiffMetadata, FileDiffOptions } from "@pierre/diffs";
import { getSingularPatch } from "@pierre/diffs";
import { FileDiff, PatchDiff } from "@pierre/diffs/react";
import { useAtomValue } from "jotai";
import type { ErrorInfo, ReactElement, ReactNode, RefObject } from "react";
import { Component, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";

import { ElementIds } from "~/api";
import { themeCodeThemeAtom } from "~/common/state/atoms/themeBuilder.ts";
import { getShikiThemes } from "~/common/theme/shikiThemes.ts";

import { splitDiffColumnRatioAtom } from "./atoms.ts";
import styles from "./PierreDiffView.module.scss";
import { SplitDiffHandle } from "./SplitDiffHandle.tsx";
import { StickyHorizontalScrollbar } from "./StickyHorizontalScrollbar.tsx";
import type { DiffViewType } from "./types.ts";

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

/**
 * Stylesheet injected into Pierre's open shadow DOM to override the theme
 * background color so the diff blends with the rest of the app.
 *
 * Light mode uses `--color-panel-solid` (white) while dark mode uses
 * `--color-background` (#111, set in index.css) to match Sculptor's actual
 * dark background.  We also override `--diffs-bg` directly via `light-dark()`
 * as a safety net in case Pierre's own variable resolution doesn't pick up
 * the overridden light/dark-bg values.
 *
 * The split column override uses inherited CSS custom properties
 * (`--diffs-split-left` / `--diffs-split-right`) set on the outer container
 * to control the width ratio of each side in side-by-side mode.
 */
const bgOverrideSheet = new CSSStyleSheet();
bgOverrideSheet.replaceSync(
  [
    "[data-diffs], [data-diffs-header], [data-error-wrapper] {",
    "  --diffs-light-bg: var(--color-panel-solid) !important;",
    "  --diffs-dark-bg: var(--color-background) !important;",
    "  --diffs-bg: light-dark(var(--color-panel-solid), var(--color-background)) !important;",
    "}",
    "[data-type='split'][data-overflow='scroll'] {",
    "  grid-template-columns: var(--diffs-split-left, 1fr) var(--diffs-split-right, 1fr) !important;",
    "}",
    "[data-type='split'][data-overflow='wrap'] {",
    "  grid-template-columns:",
    "    minmax(min-content, max-content) var(--diffs-split-left, 1fr)",
    "    minmax(min-content, max-content) var(--diffs-split-right, 1fr) !important;",
    "}",
    // Hide Pierre's native horizontal scrollbar — replaced by StickyHorizontalScrollbar
    // at the bottom of the diff panel so it's always visible.
    "[data-code] { scrollbar-width: none; }",
    "[data-code]::-webkit-scrollbar { display: none; }",
  ].join("\n"),
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
}: PierreDiffViewProps): ReactElement => {
  const splitRatio = useAtomValue(splitDiffColumnRatioAtom);
  const codeTheme = useAtomValue(themeCodeThemeAtom);
  const shikiThemes = getShikiThemes(codeTheme);
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
      const metadata = getSingularPatch(normalizedDiff);
      metadata.oldLines = oldLines;
      metadata.newLines = newLines;
      return metadata;
    } catch {
      return null;
    }
  }, [diffString, oldLines, newLines]);

  const pierreRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  /**
   * Inject our bg-override stylesheet into Pierre's shadow DOM.
   *
   * `useLayoutEffect` so the sheet is adopted between React's commit and the
   * browser's next paint — without this, Pierre's first paint shows the
   * Shiki theme background (passed inline on the `<pre>`) until our override
   * lands, which flashes in dark mode against the surrounding `#111`.
   *
   * Re-runs when `hasFileDiffMetadata` flips, because the inner Pierre
   * component may switch between `<FileDiff>` and `<PatchDiff>`, each of
   * which creates a *new* `<diffs-container>` with a fresh shadow root.
   */
  const hasFileDiffMetadata = !!fileDiffMetadata;
  useLayoutEffect(() => {
    const el = pierreRef.current;
    if (!el) return;
    const shadowRoot = el.querySelector("diffs-container")?.shadowRoot;
    if (!shadowRoot) return;
    if (!shadowRoot.adoptedStyleSheets.includes(bgOverrideSheet)) {
      shadowRoot.adoptedStyleSheets = [...shadowRoot.adoptedStyleSheets, bgOverrideSheet];
    }
  }, [hasFileDiffMetadata]);

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
      } as Record<string, string>)
    : undefined;

  const patchFallback = <PatchDiff patch={diffString} options={options} />;

  const hasScrollbar = overflow === "scroll";

  return (
    <div ref={wrapperRef} className={styles.splitWrapper} style={splitStyle}>
      <div className={styles.scrollColumn}>
        <div
          className={`${styles.container} ${className ?? ""}`}
          data-testid={viewType === "unified" ? ElementIds.DIFF_VIEW_UNIFIED : ElementIds.DIFF_VIEW_SPLIT}
        >
          <div ref={pierreRef}>
            {fileDiffMetadata ? (
              <FileDiffErrorBoundary resetKey={diffString} fallback={patchFallback}>
                <FileDiff fileDiff={fileDiffMetadata} options={options} />
              </FileDiffErrorBoundary>
            ) : (
              patchFallback
            )}
          </div>
        </div>
        {hasScrollbar && <StickyHorizontalScrollbar containerRef={pierreRef} />}
      </div>
      {isSplit && !hideHandle && <SplitDiffHandle containerRef={wrapperRef as RefObject<HTMLElement>} />}
    </div>
  );
};
