// Shared override stylesheet for Pierre's open shadow DOM. Every surface that
// embeds a Pierre `<diffs-container>` (the diff viewer, the read-only file
// preview, the chat chip popover) adopts a sheet built here so the background
// override — and how it is injected — stays in one place.
//
// Background: light mode uses `--color-panel-solid` (white) while dark mode
// uses `--color-background` (set in index.css) so the diff blends with
// Sculptor's actual surfaces instead of Pierre's Shiki theme background. The
// `--diffs-bg` override via `light-dark()` is a safety net in case Pierre's own
// variable resolution doesn't pick up the overridden light/dark-bg values.

const BG_OVERRIDE_CSS = [
  "[data-diffs], [data-diffs-header], [data-error-wrapper] {",
  "  --diffs-light-bg: var(--color-panel-solid) !important;",
  "  --diffs-dark-bg: var(--color-background) !important;",
  "  --diffs-bg: light-dark(var(--color-panel-solid), var(--color-background)) !important;",
  "}",
].join("\n");

// Hides Pierre's native horizontal scrollbar for surfaces that replace it with
// StickyHorizontalScrollbar pinned to the panel bottom (always visible).
export const HIDE_NATIVE_HSCROLLBAR_CSS = [
  "[data-code] { scrollbar-width: none; }",
  "[data-code]::-webkit-scrollbar { display: none; }",
].join("\n");

/**
 * Builds a constructed stylesheet with the shared background override plus any
 * caller-specific rules, for module-level reuse (one sheet per embedding
 * surface, adopted into every shadow root that surface creates).
 */
export function createPierreOverrideSheet(...extraCss: Array<string>): CSSStyleSheet {
  const sheet = new CSSStyleSheet();
  // jsdom constructs CSSStyleSheet but does not implement replaceSync; guard so
  // component tests can import Pierre-embedding modules without crashing.
  if (typeof sheet.replaceSync === "function") {
    sheet.replaceSync([BG_OVERRIDE_CSS, ...extraCss].join("\n"));
  }
  return sheet;
}

/**
 * Adopts `sheet` into the shadow root of the `<diffs-container>` under `host`,
 * once. Callers run this from a `useLayoutEffect` — the sheet must land between
 * React's commit and the browser's next paint, or Pierre's first paint flashes
 * the Shiki theme background (passed inline on the `<pre>`) against the app
 * background in dark mode. Pierre's web component upgrades synchronously on
 * element creation, so the shadow root is already attached when the effect runs.
 */
export function adoptPierreOverrideSheet(host: HTMLElement | null, sheet: CSSStyleSheet): void {
  const shadowRoot = host?.querySelector("diffs-container")?.shadowRoot;
  if (!shadowRoot) {
    return;
  }

  if (!shadowRoot.adoptedStyleSheets.includes(sheet)) {
    shadowRoot.adoptedStyleSheets = [...shadowRoot.adoptedStyleSheets, sheet];
  }
}
