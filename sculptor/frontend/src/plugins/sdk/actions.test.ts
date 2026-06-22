import { afterEach, describe, expect, it, vi } from "vitest";

import { openExternal } from "./actions.ts";

describe("openExternal", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens http(s) URLs in a new tab with noopener,noreferrer", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    openExternal("https://linear.app/issue/SCU-1");
    expect(open).toHaveBeenCalledWith("https://linear.app/issue/SCU-1", "_blank", "noopener,noreferrer");
    openExternal("http://example.com/x");
    expect(open).toHaveBeenCalledWith("http://example.com/x", "_blank", "noopener,noreferrer");
  });

  it("refuses non-http(s) schemes", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    for (const url of ["javascript:alert(1)", "data:text/html,<x>", "file:///etc/passwd", "mailto:a@b.com"]) {
      openExternal(url);
    }
    expect(open).not.toHaveBeenCalled();
  });
});
