import { describe, expect, it } from "vitest";

import { detectHomeDirPrefix } from "./detectHomeDirPrefix.ts";

describe("detectHomeDirPrefix", () => {
  it("returns undefined for non-tilde paths", () => {
    expect(detectHomeDirPrefix("/usr/local", "/usr/local/bin")).toBeUndefined();
  });

  it("detects prefix from ~/foo with result /Users/bob/foo/bar", () => {
    expect(detectHomeDirPrefix("~/foo", "/Users/bob/foo/bar")).toBe("/Users/bob");
  });

  it("detects prefix from ~/Documents with result /home/alice/Documents/work", () => {
    expect(detectHomeDirPrefix("~/Documents", "/home/alice/Documents/work")).toBe("/home/alice");
  });

  it("detects prefix from ~ with result /Users/bob/Documents", () => {
    expect(detectHomeDirPrefix("~", "/Users/bob/Documents")).toBe("/Users/bob");
  });

  it("detects prefix from ~/ with result /Users/bob/Documents", () => {
    expect(detectHomeDirPrefix("~/", "/Users/bob/Documents")).toBe("/Users/bob");
  });

  it("returns undefined when tilde rest is not found in result path", () => {
    expect(detectHomeDirPrefix("~/nonexistent", "/Users/bob/Documents")).toBeUndefined();
  });

  it("detects prefix from deeper tilde path", () => {
    expect(detectHomeDirPrefix("~/projects/app", "/home/user/projects/app/src")).toBe("/home/user");
  });

  it("returns undefined for ~/ when result has no slash", () => {
    expect(detectHomeDirPrefix("~/", "rootfile")).toBeUndefined();
  });
});
