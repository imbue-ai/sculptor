/**
 * Shared helpers for painting and scrolling Pierre diff/file line rows. Pierre
 * renders each line as a `div[data-line="<lineNumber>"]` with a
 * `data-line-type` of `addition` / `deletion` / `context` /
 * `change-addition` / `change-deletion` inside the `<diffs-container>` shadow
 * root; both the drag-capture hook and the hover/scroll overlay hook reach in
 * through here so the DOM contract lives in one place.
 */

import type { LineRange, SpotlightAnchor } from "./types.ts";

/** Which file a Pierre row belongs to. `null` = context (shared by both). */
export type RowVersion = "previous" | "current" | null;

/** The shadow root of the Pierre `<diffs-container>` under `container`, if mounted. */
export const shadowRootOf = (container: HTMLElement | null): ShadowRoot | null =>
  container?.querySelector("diffs-container")?.shadowRoot ?? null;

/**
 * Map a Pierre row to the file version it belongs to. Additions (and the new
 * side of a change) live in the CURRENT file; deletions (and the old side of a
 * change) live in the PREVIOUS file; context rows are shared. Handling the
 * `change-*` variants is what fixes the "modified line has no side" bug.
 */
export const fileVersionOfRow = (el: HTMLElement | null): RowVersion => {
  const type = el?.getAttribute("data-line-type");
  if (type === "addition" || type === "change-addition") return "current";
  if (type === "deletion" || type === "change-deletion") return "previous";
  return null;
};

const lineRows = (shadowRoot: ShadowRoot): Array<HTMLElement> =>
  Array.from(shadowRoot.querySelectorAll<HTMLElement>("[data-line]"));

const lineNumberOf = (el: HTMLElement): number => parseInt(el.getAttribute("data-line") ?? "", 10);

const inRange = (range: LineRange | null, n: number): boolean =>
  range !== null && n >= range.firstLine && n <= range.lastLine;

/** Clear any spotlight paint from every line row. */
export const clearLinePaint = (shadowRoot: ShadowRoot): void => {
  for (const el of lineRows(shadowRoot)) {
    el.style.backgroundColor = "";
  }
};

/**
 * Paint the rows an anchor's ranges cover with `color`, clearing all others. A
 * row matches when its `data-line` number falls in the range for the VERSION it
 * belongs to; a context row (shared by both files) matches either range. This
 * is what bifurcates a changed line's red vs green rows — a `(new)` anchor
 * paints only the green row, `(old)` only the red, `(changed)` both.
 */
export const paintAnchorRanges = (
  shadowRoot: ShadowRoot,
  previous: LineRange | null,
  current: LineRange | null,
  color: string,
): void => {
  for (const el of lineRows(shadowRoot)) {
    const n = lineNumberOf(el);
    if (Number.isNaN(n)) {
      el.style.backgroundColor = "";
      continue;
    }
    const version = fileVersionOfRow(el);
    const isMatch =
      (version === "previous" && inRange(previous, n)) ||
      (version === "current" && inRange(current, n)) ||
      (version === null && (inRange(previous, n) || inRange(current, n)));
    el.style.backgroundColor = isMatch ? color : "";
  }
};

/**
 * Paint the contiguous run of rows between two row elements (inclusive), in DOM
 * (visual) order, with `color`. Used for the live drag preview, where a
 * red→green cross-side drag should highlight everything the pointer swept —
 * DOM order spans both sides naturally.
 */
export const paintRowRun = (shadowRoot: ShadowRoot, fromEl: HTMLElement, toEl: HTMLElement, color: string): void => {
  const rows = lineRows(shadowRoot);
  const a = rows.indexOf(fromEl);
  const b = rows.indexOf(toEl);
  if (a === -1 || b === -1) return;
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  rows.forEach((el, index) => {
    el.style.backgroundColor = index >= lo && index <= hi ? color : "";
  });
};

/** The per-version ranges + literal text of a captured contiguous row run. */
export type CapturedRun = {
  previousFileLines: LineRange | null;
  currentFileLines: LineRange | null;
  /** Old-file reading of the selection: deletions + shared context, in order. */
  previousSnippet: string;
  /** New-file reading: additions + shared context — and the sole text of a file view. */
  currentSnippet: string;
};

const extendRange = (range: LineRange | null, n: number): LineRange =>
  range === null
    ? { firstLine: n, lastLine: n }
    : { firstLine: Math.min(range.firstLine, n), lastLine: Math.max(range.lastLine, n) };

/**
 * From the contiguous DOM run between two rows (inclusive), derive the
 * per-version line ranges and each file's reading of the selection. A row's
 * text lands in the previous snippet when it is a deletion or shared context,
 * and in the current snippet when it is an addition or shared context — so a
 * modified span reconstructs BOTH the old and new file's view of those lines
 * (context appears in each, exactly as it does on both sides of a diff). For a
 * plain file view every row is context, so both snippets are identical and the
 * consumer shows the current one. Context rows are attributed to the current
 * file for range purposes (that's where they live now). Returns `null` when
 * either endpoint has left the DOM.
 */
export const capturedRunBetween = (
  shadowRoot: ShadowRoot,
  fromEl: HTMLElement,
  toEl: HTMLElement,
): CapturedRun | null => {
  const rows = lineRows(shadowRoot);
  const a = rows.indexOf(fromEl);
  const b = rows.indexOf(toEl);
  if (a === -1 || b === -1) return null;
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  let previous: LineRange | null = null;
  let current: LineRange | null = null;
  const previousLines: Array<string> = [];
  const currentLines: Array<string> = [];
  for (let index = lo; index <= hi; index++) {
    const el = rows[index];
    const n = lineNumberOf(el);
    const version = fileVersionOfRow(el);
    const text = el.textContent ?? "";
    if (version === "previous") {
      if (!Number.isNaN(n)) previous = extendRange(previous, n);
      previousLines.push(text);
    } else if (version === "current") {
      if (!Number.isNaN(n)) current = extendRange(current, n);
      currentLines.push(text);
    } else {
      // Context row — shared by both files.
      if (!Number.isNaN(n)) current = extendRange(current, n);
      previousLines.push(text);
      currentLines.push(text);
    }
  }
  return {
    previousFileLines: previous,
    currentFileLines: current,
    previousSnippet: previousLines.join("\n"),
    currentSnippet: currentLines.join("\n"),
  };
};

// --- Persistent gutter bars --------------------------------------------------
// Injected as <div> children of [data-line] rows. A single fixed-width bar per
// line: solid-coloured when one spotlight covers the line, repeating diagonal
// stripes cycling through all present colours when two or more overlap.

const GUTTER_BAR_SELECTOR = "[data-spotlight-bar]";
const GUTTER_BAR_WIDTH = 4; // px
const STRIPE_SEGMENT = 2; // px per colour segment — tight candy-cane alternation

/** Remove every previously-injected gutter bar from the shadow root. */
const clearGutterBars = (shadowRoot: ShadowRoot): void => {
  for (const bar of shadowRoot.querySelectorAll(GUTTER_BAR_SELECTOR)) {
    bar.remove();
  }
};

/**
 * Build a `repeating-linear-gradient` background that cycles through `colors` in
 * diagonal segments. For N colours the pattern is 1,2,…,N,1,2,…,N with each
 * segment `STRIPE_SEGMENT` px.
 */
const stripeBackground = (colors: ReadonlyArray<string>): string => {
  const n = colors.length;
  const stops = colors
    .map((c, i) => {
      const start = i * STRIPE_SEGMENT;
      const end = (i + 1) * STRIPE_SEGMENT;
      return `${c} ${start}px ${end}px`;
    })
    .join(", ");
  const size = n * STRIPE_SEGMENT;
  return `repeating-linear-gradient(to right bottom, ${stops}) 0 0 / ${size}px ${size}px`;
};

/**
 * Paint persistent gutter bars for the given set of anchors. One bar per
 * matching line: solid when one anchor covers it, repeating diagonal stripes
 * when two or more overlap. Row matching mirrors `paintAnchorRanges`.
 */
export const paintGutterBars = (
  shadowRoot: ShadowRoot,
  anchors: ReadonlyArray<SpotlightAnchor>,
  file: string,
  colorFn: (anchor: SpotlightAnchor) => string,
): void => {
  clearGutterBars(shadowRoot);

  const relevant = anchors.filter((a) => a.file === file);
  if (relevant.length === 0) return;

  for (const el of lineRows(shadowRoot)) {
    const n = lineNumberOf(el);
    if (Number.isNaN(n)) continue;
    const version = fileVersionOfRow(el);
    const colors = relevant
      .filter(
        (anchor) =>
          (version === "previous" && inRange(anchor.previousFileLines, n)) ||
          (version === "current" && inRange(anchor.currentFileLines, n)) ||
          (version === null && (inRange(anchor.previousFileLines, n) || inRange(anchor.currentFileLines, n))),
      )
      .map(colorFn);
    if (colors.length === 0) continue;

    const bg = colors.length === 1 ? colors[0] : stripeBackground(colors);

    const bar = el.ownerDocument.createElement("div");
    bar.setAttribute("data-spotlight-bar", "");
    bar.style.cssText = [
      `position: absolute`,
      `left: 0`,
      `top: 0`,
      `width: ${GUTTER_BAR_WIDTH}px`,
      `height: 100%`,
      `background: ${bg}`,
      `pointer-events: none`,
      `z-index: 0`,
    ].join("; ");
    el.style.position = "relative";
    el.appendChild(bar);
  }
};

/**
 * Scroll a specific line into view (centred). Returns true when the row exists,
 * false when Pierre has not painted it yet (the caller can retry).
 */
export const scrollLineIntoView = (shadowRoot: ShadowRoot, line: number): boolean => {
  const el = shadowRoot.querySelector(`[data-line="${line}"]`);
  if (!el) return false;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  return true;
};
