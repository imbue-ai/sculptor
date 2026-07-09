/**
 * Imperative host actions extensions can call. Unlike the hooks in `hooks.ts`,
 * these are plain functions, callable from event handlers or anywhere outside
 * a React render. The generated SDK runtime stub (served at
 * `/extension-runtime/sculptor-extension-sdk.js`) re-exports them from the
 * `window.__SCULPTOR_HOST__.sdk` object the host populates at boot.
 */

/**
 * Open a URL in the user's browser. In the web build this is a new tab; in the
 * Electron desktop app a `_blank` target is routed to `shell.openExternal` by
 * the main process, so the link opens in the system browser rather than inside
 * the app window.
 *
 * Extensions should use this instead of calling `window.open` directly: it is the
 * single host-blessed seam for outbound links, so behaviour stays consistent
 * and can be upgraded (e.g. to a dedicated Electron bridge) in one place.
 * `noopener,noreferrer` prevents the opened page from reaching back through
 * `window.opener`.
 *
 * Only `http(s)` URLs are opened. A URL that doesn't parse or uses another
 * scheme (`javascript:`, `data:`, …) is refused — this is the blessed seam, so
 * it stays safe even when the URL comes from external data (e.g. a Linear issue
 * or attachment URL), mirroring the host's safe-URL policy for rendered links.
 */
export const openExternal = (url: string): void => {
  let resolved: URL;
  try {
    resolved = new URL(url, window.location.href);
  } catch {
    return;
  }
  if (resolved.protocol !== "http:" && resolved.protocol !== "https:") return;
  window.open(resolved.href, "_blank", "noopener,noreferrer");
};
