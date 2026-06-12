import { describe, expect, it } from "vitest";

import { safeUrlTransform } from "./markdownPlugins.ts";

// `safeUrlTransform` is currently react-markdown's `defaultUrlTransform`,
// re-exported under an explicit name. These tests pin the contract so the
// non-`react-markdown` diff path (which has to call this directly) doesn't
// silently regress if the upstream default ever changes.
describe("safeUrlTransform", () => {
  it("preserves https/http/mailto", () => {
    expect(safeUrlTransform("https://example.com")).toBe("https://example.com");
    expect(safeUrlTransform("http://example.com/path?q=1")).toBe("http://example.com/path?q=1");
    expect(safeUrlTransform("mailto:user@example.com")).toBe("mailto:user@example.com");
  });

  it("preserves relative URLs and fragments", () => {
    expect(safeUrlTransform("/local/path")).toBe("/local/path");
    expect(safeUrlTransform("#section")).toBe("#section");
    expect(safeUrlTransform("./neighbor.md")).toBe("./neighbor.md");
  });

  it("blocks javascript:, data:, vbscript: and other unknown protocols", () => {
    expect(safeUrlTransform("javascript:alert(1)")).toBe("");
    expect(safeUrlTransform("JavaScript:alert(1)")).toBe("");
    expect(safeUrlTransform("data:text/html,<script>alert(1)</script>")).toBe("");
    expect(safeUrlTransform("vbscript:msgbox(1)")).toBe("");
    expect(safeUrlTransform("file:///etc/passwd")).toBe("");
  });
});
