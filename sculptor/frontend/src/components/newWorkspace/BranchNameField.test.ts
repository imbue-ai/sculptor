import { describe, expect, it } from "vitest";

import { sanitizeBranchName } from "./sanitizeBranchName.ts";

describe("sanitizeBranchName", () => {
  it("collapses runs of whitespace to a single hyphen", () => {
    expect(sanitizeBranchName("foo bar")).toBe("foo-bar");
    expect(sanitizeBranchName("foo   bar")).toBe("foo-bar");
    expect(sanitizeBranchName("foo\tbar")).toBe("foo-bar");
  });

  it("drops the reserved ref characters", () => {
    expect(sanitizeBranchName("foo~^:?*[]\\@{}bar")).toBe("foobar");
  });

  it("collapses runs of dots (git forbids '..')", () => {
    expect(sanitizeBranchName("a..b")).toBe("a.b");
    expect(sanitizeBranchName("a....b")).toBe("a.b");
  });

  it("collapses runs of slashes (git forbids '//')", () => {
    expect(sanitizeBranchName("a//b")).toBe("a/b");
    expect(sanitizeBranchName("a///b")).toBe("a/b");
  });

  it("strips a dot that starts a path component", () => {
    expect(sanitizeBranchName("foo/.bar")).toBe("foo/bar");
    expect(sanitizeBranchName("foo/./bar")).toBe("foo/bar");
  });

  it("removes a leading dot, slash, or dash", () => {
    expect(sanitizeBranchName(".foo")).toBe("foo");
    expect(sanitizeBranchName("/foo")).toBe("foo");
    expect(sanitizeBranchName("-foo")).toBe("foo");
    expect(sanitizeBranchName("--foo")).toBe("foo");
    expect(sanitizeBranchName("./-foo")).toBe("foo");
  });

  it("preserves valid names, including mid-name dots and slashes", () => {
    expect(sanitizeBranchName("feature/foo")).toBe("feature/foo");
    expect(sanitizeBranchName("user/my-branch")).toBe("user/my-branch");
    expect(sanitizeBranchName("release-1.0")).toBe("release-1.0");
  });

  it("leaves a trailing separator in place so it can't eat a character mid-typing", () => {
    // A trailing "/" or "." is an intermediate state while the user types
    // "feature/foo" or "release-1.0"; stripping it on every keystroke would make
    // those names impossible to type. The create call rejects a name that is
    // still invalid at submit time.
    expect(sanitizeBranchName("feature/")).toBe("feature/");
    expect(sanitizeBranchName("release-1.")).toBe("release-1.");
  });
});
