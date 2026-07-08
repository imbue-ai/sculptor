/**
 * Shared helpers for painting and scrolling Pierre diff/file line rows. Pierre
 * renders each line as a `div[data-line="<lineNumber>"]` inside the
 * `<diffs-container>` shadow root; both the drag-capture hook and the
 * hover/scroll overlay hook reach in through here so the DOM contract lives in
 * one place.
 */

/** The shadow root of the Pierre `<diffs-container>` under `container`, if mounted. */
export const shadowRootOf = (container: HTMLElement | null): ShadowRoot | null =>
  container?.querySelector("diffs-container")?.shadowRoot ?? null;

/**
 * Paint the inclusive line range blue and clear every other line, in a single
 * sweep. Re-querying (rather than tracking element refs) keeps the React
 * Compiler happy and is cheap for the line counts on screen.
 */
export const paintLineRange = (shadowRoot: ShadowRoot, start: number, end: number): void => {
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  for (const el of shadowRoot.querySelectorAll<HTMLElement>("[data-line]")) {
    const n = parseInt(el.getAttribute("data-line") ?? "", 10);
    el.style.backgroundColor = !Number.isNaN(n) && n >= lo && n <= hi ? "var(--blue-a5)" : "";
  }
};

/** Clear any spotlight paint from every line row. */
export const clearLinePaint = (shadowRoot: ShadowRoot): void => {
  for (const el of shadowRoot.querySelectorAll<HTMLElement>("[data-line]")) {
    el.style.backgroundColor = "";
  }
};

/** The literal text of the inclusive line range, one line per row, `\n`-joined. */
export const snippetForRange = (shadowRoot: ShadowRoot, start: number, end: number): string => {
  const lines: Array<string> = [];
  for (const el of shadowRoot.querySelectorAll("[data-line]")) {
    const n = parseInt(el.getAttribute("data-line") ?? "", 10);
    if (!Number.isNaN(n) && n >= start && n <= end) {
      lines.push(el.textContent ?? "");
    }
  }
  return lines.join("\n");
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
