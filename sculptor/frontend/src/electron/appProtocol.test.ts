/** Tests for the custom app-scheme URL→file mapping and its traversal guard.
 *
 * These cover the pure helpers in ``appProtocol.ts`` — the part of the
 * protocol that is testable without an Electron runtime. The live
 * ``protocol.handle`` wiring in ``main.ts`` is exercised by the Electron
 * integration tests (which set SCULPTOR_USE_APP_SCHEME=1, so the renderer
 * loads over sculptor://app and the handler proxies to Vite) and in packaged
 * builds; this file pins the security-critical path mapping directly.
 */
import * as path from "node:path";

import { describe, expect, it } from "vitest";

import {
  APP_ORIGIN,
  APP_SCHEME,
  getAppRendererUrl,
  resolveRequestToFilePath,
  shouldFallbackToIndex,
} from "./appProtocol";

const BUNDLE = path.resolve("/opt/sculptor/.vite/build/renderer");

describe("getAppRendererUrl", () => {
  it("points at index.html on the app origin", () => {
    expect(getAppRendererUrl()).toBe(`${APP_ORIGIN}/index.html`);
    expect(getAppRendererUrl()).toBe("sculptor://app/index.html");
  });
});

describe("resolveRequestToFilePath", () => {
  it("maps a normal asset path into the bundle directory", () => {
    expect(resolveRequestToFilePath(BUNDLE, "sculptor://app/assets/index-abc.js")).toBe(
      path.join(BUNDLE, "assets", "index-abc.js"),
    );
  });

  it("defaults the root path to index.html", () => {
    expect(resolveRequestToFilePath(BUNDLE, "sculptor://app/")).toBe(path.join(BUNDLE, "index.html"));
    expect(resolveRequestToFilePath(BUNDLE, "sculptor://app")).toBe(path.join(BUNDLE, "index.html"));
  });

  it("decodes percent-encoded paths", () => {
    expect(resolveRequestToFilePath(BUNDLE, "sculptor://app/a%20b/c.png")).toBe(path.join(BUNDLE, "a b", "c.png"));
  });

  it("ignores query strings and fragments (cache-bust tokens, hash routes)", () => {
    expect(resolveRequestToFilePath(BUNDLE, "sculptor://app/assets/x.js?t=123")).toBe(
      path.join(BUNDLE, "assets", "x.js"),
    );
    expect(resolveRequestToFilePath(BUNDLE, "sculptor://app/index.html#/settings")).toBe(
      path.join(BUNDLE, "index.html"),
    );
  });

  // Path traversal is contained by two layers: the scheme is registered as
  // "standard", so the URL parser normalizes dot-segments away at the origin
  // root, and `path.resolve` keeps anything that survives as a literal segment
  // inside the bundle. Either way the result stays within `bundleDir` (and a
  // nonexistent target 404s at the handler) rather than escaping to the disk.
  it("contains dot-segment traversal within the bundle directory", () => {
    for (const url of [
      "sculptor://app/../../etc/passwd",
      "sculptor://app/%2e%2e/%2e%2e/etc/passwd",
      "sculptor://app/assets/../../../secret",
      "sculptor://app/%252e%252e/%252e%252e/etc/passwd", // double-encoded
    ]) {
      const resolved = resolveRequestToFilePath(BUNDLE, url);
      expect(resolved, url).not.toBeNull();
      expect(resolved!.startsWith(BUNDLE + path.sep), url).toBe(true);
    }
  });

  it("rejects other schemes and other hosts", () => {
    expect(resolveRequestToFilePath(BUNDLE, "file:///etc/passwd")).toBeNull();
    expect(resolveRequestToFilePath(BUNDLE, "https://app/assets/x.js")).toBeNull();
    expect(resolveRequestToFilePath(BUNDLE, `${APP_SCHEME}://evil/assets/x.js`)).toBeNull();
  });

  it("rejects malformed URLs", () => {
    expect(resolveRequestToFilePath(BUNDLE, "not a url")).toBeNull();
  });
});

describe("shouldFallbackToIndex", () => {
  it("falls back for extensionless (route-like) paths", () => {
    expect(shouldFallbackToIndex(path.join(BUNDLE, "settings"))).toBe(true);
    expect(shouldFallbackToIndex(path.join(BUNDLE, "workspace", "abc"))).toBe(true);
  });

  it("does not mask a genuinely missing asset", () => {
    expect(shouldFallbackToIndex(path.join(BUNDLE, "assets", "x.js"))).toBe(false);
    expect(shouldFallbackToIndex(path.join(BUNDLE, "favicon.ico"))).toBe(false);
    expect(shouldFallbackToIndex(path.join(BUNDLE, "logo.svg"))).toBe(false);
  });
});
