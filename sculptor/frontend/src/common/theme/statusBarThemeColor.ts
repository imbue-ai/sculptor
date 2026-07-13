/**
 * Keeps the document's `<meta name="theme-color">` in sync with the app's
 * top surface color. On Android, Chrome paints the standalone-PWA status
 * bar with this value (and picks light/dark status icons from its
 * luminance), so without it the bar stays the static manifest
 * `theme_color` — a light cream — even when the app renders dark.
 *
 * The color is read from the live `--gray-2` CSS variable (the surface
 * the sidebar, app shell, and workspace header share at the top of the
 * viewport) rather than hard-coded per appearance, so theme builder gray
 * overrides are reflected too.
 *
 * Dev builds instead pin a fixed orange, so an installed PWA pointed at a
 * Vite dev preview is instantly distinguishable from prod by its status
 * bar. Everywhere theme-color has no effect (Electron, desktop browsers)
 * the meta tag is inert.
 */

/** Radix orange-9 — the dev-preview status bar indicator. */
const DEV_PREVIEW_COLOR = "#f76b15";

export const syncStatusBarThemeColor = (themeRoot: HTMLElement, isDevPreview: boolean = import.meta.env.DEV): void => {
  const color = isDevPreview ? DEV_PREVIEW_COLOR : getComputedStyle(themeRoot).getPropertyValue("--gray-2").trim();
  if (color === "") {
    return;
  }

  let meta = document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta === null) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }
  meta.content = color;
};
