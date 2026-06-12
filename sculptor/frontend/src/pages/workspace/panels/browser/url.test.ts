import { describe, expect, it } from "vitest";

import { normalizeUrlInput } from "./url";

describe("normalizeUrlInput", () => {
  it.each([
    ["localhost:3000", "http://localhost:3000"],
    ["foo.com", "http://foo.com"],
    ["http://foo.com", "http://foo.com"],
    ["https://foo.com", "https://foo.com"],
    ["file:///tmp/x.html", "file:///tmp/x.html"],
    ["  https://foo.com  ", "https://foo.com"],
    ["localhost:3000/path?x=1", "http://localhost:3000/path?x=1"],
    ["chrome://settings", "chrome://settings"],
  ])("normalizes %j to %j", (input, expected) => {
    const result = normalizeUrlInput(input);
    expect(result).toEqual({ kind: "ok", url: expected });
  });

  it.each([
    ["/Users/me/notes.html", "file:///Users/me/notes.html"],
    ["/tmp/x.html", "file:///tmp/x.html"],
    ["C:\\Users\\me\\notes.html", "file:///C:/Users/me/notes.html"],
    ["C:/Users/me/notes.html", "file:///C:/Users/me/notes.html"],
  ])("normalizes absolute file path %j to %j", (input, expected) => {
    const result = normalizeUrlInput(input);
    expect(result).toEqual({ kind: "ok", url: expected });
  });

  it.each(["", "   ", "\t\n"])("returns empty for whitespace-only input %j", (input) => {
    expect(normalizeUrlInput(input)).toEqual({ kind: "empty" });
  });

  it.each([
    "not a url",
    "foo bar baz",
    // Schemed URLs with whitespace are also invalid. Chromium's URL parser
    // silently accepts these (truncating the host at the space), so they
    // must be caught explicitly rather than via ``new URL``.
    "http://bad host/",
    "https://example.com /path",
  ])("returns invalid for input %j", (input) => {
    const result = normalizeUrlInput(input);
    expect(result.kind).toBe("invalid");
  });
});
