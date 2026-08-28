import { describe, expect, it } from "vitest";

import { detectHomeDirPrefix } from "./detectHomeDirPrefix.ts";

describe("detectHomeDirPrefix", () => {
  it("returns undefined for non-tilde paths", () => {
    expect(detectHomeDirPrefix({ inputPath: "/usr/local", firstResultPath: "/usr/local/bin" })).toBeUndefined();
  });

  it("detects prefix from ~/foo with result /Users/bob/foo/bar", () => {
    expect(detectHomeDirPrefix({ inputPath: "~/foo", firstResultPath: "/Users/bob/foo/bar" })).toBe("/Users/bob");
  });

  it("detects prefix from ~/Documents with result /home/alice/Documents/work", () => {
    expect(detectHomeDirPrefix({ inputPath: "~/Documents", firstResultPath: "/home/alice/Documents/work" })).toBe(
      "/home/alice",
    );
  });

  it("detects prefix from ~ with result /Users/bob/Documents", () => {
    expect(detectHomeDirPrefix({ inputPath: "~", firstResultPath: "/Users/bob/Documents" })).toBe("/Users/bob");
  });

  it("detects prefix from ~/ with result /Users/bob/Documents", () => {
    expect(detectHomeDirPrefix({ inputPath: "~/", firstResultPath: "/Users/bob/Documents" })).toBe("/Users/bob");
  });

  it("returns undefined when tilde rest is not found in result path", () => {
    expect(
      detectHomeDirPrefix({ inputPath: "~/nonexistent", firstResultPath: "/Users/bob/Documents" }),
    ).toBeUndefined();
  });

  it("detects prefix from deeper tilde path", () => {
    expect(detectHomeDirPrefix({ inputPath: "~/projects/app", firstResultPath: "/home/user/projects/app/src" })).toBe(
      "/home/user",
    );
  });

  it("returns undefined for ~/ when result has no slash", () => {
    expect(detectHomeDirPrefix({ inputPath: "~/", firstResultPath: "rootfile" })).toBeUndefined();
  });
});
