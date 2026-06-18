/**
 * The custom `sculptor://app` protocol used to serve the packaged renderer.
 *
 * In production the renderer is loaded from a real, secure origin
 * (`sculptor://app/index.html`) served by the Electron main process out of the
 * built frontend bundle, instead of from `file://`. A stable origin is what
 * makes absolute-path resolution, `fetch`, dynamic `import()`, and CSP behave
 * like a normal web page — the prerequisite for runtime-loaded frontend
 * plugins, which will later be served under this same origin (e.g.
 * `sculptor://app/plugins/<id>/...` and `sculptor://app/plugin-runtime/...`).
 *
 * This module currently owns only host-bundle serving; the `app` host prefix
 * is deliberately reserved so the plugin work can hang `/plugins/` and
 * `/plugin-runtime/` paths off the same origin (no cross-origin CORS plumbing
 * between host and plugins, and the plugin import map's absolute paths resolve
 * against this origin).
 *
 * The helpers here are intentionally free of any Electron imports — they carry
 * the URL→file mapping and the path-traversal guard so they can be unit-tested
 * without an Electron runtime. The actual `registerSchemesAsPrivileged` /
 * `protocol.handle` wiring lives in `main.ts`.
 */
import * as path from "node:path";

/** The custom scheme the packaged renderer (and, later, plugins) are served from. */
export const APP_SCHEME = "sculptor";

/**
 * The single host under the scheme. Everything is served from one origin so
 * the (future) plugin import map and same-origin plugin loading need no CORS
 * plumbing; the host bundle and plugins differ only by path prefix.
 */
export const APP_HOST = "app";

/** The renderer's origin — also what the backend CORS allowlist must accept. */
export const APP_ORIGIN = `${APP_SCHEME}://${APP_HOST}`;

/** The URL the production renderer is loaded from. */
export const getAppRendererUrl = (): string => `${APP_ORIGIN}/index.html`;

/**
 * Map a request URL on the app scheme to an absolute file path inside
 * `bundleDir`. Returns `null` only when the request is malformed or targets
 * another scheme or host; a valid app-host request always resolves to a path
 * *within* `bundleDir`.
 *
 * Traversal is contained by two layers: the scheme is registered as
 * "standard", so the URL parser normalizes `../` dot-segments away at the
 * origin root, and the `path.resolve` + prefix check below is a defense-in-
 * depth net for anything that survives decoding. The returned path is not
 * guaranteed to exist — existence and SPA fallback are the caller's concern
 * (see `shouldFallbackToIndex`).
 */
export const resolveRequestToFilePath = (bundleDir: string, requestUrl: string): string | null => {
  let parsed: URL;
  try {
    parsed = new URL(requestUrl);
  } catch {
    return null;
  }

  if (parsed.protocol !== `${APP_SCHEME}:` || parsed.host !== APP_HOST) {
    return null;
  }

  let pathname: string;
  try {
    pathname = decodeURIComponent(parsed.pathname);
  } catch {
    // Malformed percent-encoding.
    return null;
  }

  if (pathname === "" || pathname === "/") {
    pathname = "/index.html";
  }

  const root = path.resolve(bundleDir);
  // `pathname` always starts with "/"; join it onto the root and re-resolve so
  // any "../" segments collapse, then confirm the result is still inside root.
  const resolved = path.resolve(root, `.${pathname}`);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    return null;
  }
  return resolved;
};

/**
 * Whether a not-found request should fall back to the SPA shell
 * (`index.html`) rather than 404. The renderer uses a hash router, so a deep
 * link keeps its route in the URL fragment and the path is just "/"; this
 * fallback only catches extensionless (route-like) paths and leaves a
 * genuinely missing asset (`.js`, `.css`, an image) as a real 404 so such
 * bugs stay visible.
 */
export const shouldFallbackToIndex = (filePath: string): boolean => path.extname(filePath) === "";
