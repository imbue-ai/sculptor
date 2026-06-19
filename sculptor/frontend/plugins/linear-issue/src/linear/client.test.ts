import { describe, expect, it } from "vitest";

import { isPullRequestAttachment, type LinearAttachment, prLabel } from "./client.ts";

const attachment = (url: string): LinearAttachment => ({ url, sourceType: "github", title: null });

describe("isPullRequestAttachment", () => {
  it("matches GitHub pull and GitLab merge-request URLs", () => {
    expect(isPullRequestAttachment(attachment("https://github.com/o/r/pull/74"))).toBe(true);
    expect(isPullRequestAttachment(attachment("https://gitlab.com/o/r/-/merge_requests/12"))).toBe(true);
  });

  it("rejects non-PR URLs", () => {
    expect(isPullRequestAttachment(attachment("https://github.com/o/r/commit/abc123"))).toBe(false);
    expect(isPullRequestAttachment(attachment("https://example.com/pulls"))).toBe(false);
  });
});

describe("prLabel", () => {
  it("labels GitHub pulls with #<n>", () => {
    expect(prLabel("https://github.com/o/r/pull/74")).toBe("#74");
  });

  it("labels GitLab merge requests with !<n>", () => {
    expect(prLabel("https://gitlab.com/o/r/-/merge_requests/12")).toBe("!12");
  });

  it("falls back to 'PR' when there is no number", () => {
    expect(prLabel("https://github.com/o/r")).toBe("PR");
  });

  it("keys the sigil off the matched route, not a substring of the whole URL", () => {
    // A GitHub pull whose query string mentions "/merge_requests/" must still
    // read as "#", not "!".
    expect(prLabel("https://github.com/o/r/pull/74?ref=/merge_requests/9")).toBe("#74");
  });
});
