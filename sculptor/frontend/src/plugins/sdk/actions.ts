/**
 * Imperative host actions plugins can call. Unlike the hooks in `hooks.ts`,
 * these are plain functions, callable from event handlers or anywhere outside
 * a React render. The generated SDK runtime stub (served at
 * `/plugin-runtime/sculptor-plugin-sdk.js`) re-exports them from the
 * `window.__SCULPTOR_HOST__.sdk` object the host populates at boot.
 */

/**
 * Open a URL in the user's browser. In the web build this is a new tab; in the
 * Electron desktop app a `_blank` target is routed to `shell.openExternal` by
 * the main process, so the link opens in the system browser rather than inside
 * the app window.
 *
 * Plugins should use this instead of calling `window.open` directly: it is the
 * single host-blessed seam for outbound links, so behaviour stays consistent
 * and can be upgraded (e.g. to a dedicated Electron bridge) in one place.
 * `noopener,noreferrer` prevents the opened page from reaching back through
 * `window.opener`.
 */
export const openExternal = (url: string): void => {
  window.open(url, "_blank", "noopener,noreferrer");
};
