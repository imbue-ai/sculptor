/**
 * Shared helpers for painting and scrolling Pierre diff/file line rows. Pierre
 * renders each line as a `div[data-line="<lineNumber>"]` with a
 * `data-line-type` of `addition` / `deletion` / `context` /
 * `change-addition` / `change-deletion` inside the `<diffs-container>` shadow
 * root; both the drag-capture hook and the hover/scroll overlay hook reach in
 * through here so the DOM contract lives in one place.
 */

import type { LineRange } from "./types.ts";

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
  snippet: string;
};

const extendRange = (range: LineRange | null, n: number): LineRange =>
  range === null
    ? { firstLine: n, lastLine: n }
    : { firstLine: Math.min(range.firstLine, n), lastLine: Math.max(range.lastLine, n) };

/**
 * From the contiguous DOM run between two rows (inclusive), derive the
 * per-version line ranges and the literal snippet (both sides, in visual
 * order). Context rows are attributed to the current file (that's where they
 * live now, and it keeps a file-view selection in `currentFileLines`). Returns
 * `null` when either endpoint has left the DOM.
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
  const lines: Array<string> = [];
  for (let index = lo; index <= hi; index++) {
    const el = rows[index];
    const n = lineNumberOf(el);
    if (!Number.isNaN(n)) {
      if (fileVersionOfRow(el) === "previous") previous = extendRange(previous, n);
      else current = extendRange(current, n);
    }
    lines.push(el.textContent ?? "");
  }
  return { previousFileLines: previous, currentFileLines: current, snippet: lines.join("\n") };
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
