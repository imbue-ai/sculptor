import { describe, expect, it } from "vitest";

import { parseDiffStats } from "./parseDiffStats.ts";

describe("parseDiffStats", () => {
  it("returns all zeros for empty string", () => {
    expect(parseDiffStats("")).toEqual({ additions: 0, deletions: 0, filesChanged: 0 });
  });

  it("returns all zeros for null", () => {
    expect(parseDiffStats(null)).toEqual({ additions: 0, deletions: 0, filesChanged: 0 });
  });

  it("returns all zeros for undefined", () => {
    expect(parseDiffStats(undefined)).toEqual({ additions: 0, deletions: 0, filesChanged: 0 });
  });

  it("counts additions only in a single file", () => {
    const diff = [
      "diff --git a/file.ts b/file.ts",
      "--- a/file.ts",
      "+++ b/file.ts",
      "@@ -1,3 +1,5 @@",
      " unchanged line",
      "+added line 1",
      "+added line 2",
      " unchanged line",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 2, deletions: 0, filesChanged: 1 });
  });

  it("counts deletions only in a single file", () => {
    const diff = [
      "diff --git a/file.ts b/file.ts",
      "--- a/file.ts",
      "+++ b/file.ts",
      "@@ -1,5 +1,3 @@",
      " unchanged line",
      "-deleted line 1",
      "-deleted line 2",
      " unchanged line",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 0, deletions: 2, filesChanged: 1 });
  });

  it("counts both additions and deletions in a single file", () => {
    const diff = [
      "diff --git a/file.ts b/file.ts",
      "--- a/file.ts",
      "+++ b/file.ts",
      "@@ -1,4 +1,4 @@",
      " unchanged line",
      "-old line",
      "+new line",
      " unchanged line",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 1, deletions: 1, filesChanged: 1 });
  });

  it("counts across multiple files", () => {
    const diff = [
      "diff --git a/file1.ts b/file1.ts",
      "--- a/file1.ts",
      "+++ b/file1.ts",
      "@@ -1,3 +1,4 @@",
      " unchanged",
      "+added in file1",
      " unchanged",
      "diff --git a/file2.ts b/file2.ts",
      "--- a/file2.ts",
      "+++ b/file2.ts",
      "@@ -1,3 +1,2 @@",
      " unchanged",
      "-deleted in file2",
      " unchanged",
      "diff --git a/file3.ts b/file3.ts",
      "--- a/file3.ts",
      "+++ b/file3.ts",
      "@@ -1,3 +1,3 @@",
      " unchanged",
      "-old line in file3",
      "+new line in file3",
      " unchanged",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 2, deletions: 2, filesChanged: 3 });
  });

  it("handles binary file diff (no +/- lines, but counts as changed file)", () => {
    const diff = ["diff --git a/image.png b/image.png", "Binary files a/image.png and b/image.png differ"].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 0, deletions: 0, filesChanged: 1 });
  });

  it("handles rename-only diff (no +/- lines, but counts as changed file)", () => {
    const diff = [
      "diff --git a/old-name.ts b/new-name.ts",
      "similarity index 100%",
      "rename from old-name.ts",
      "rename to new-name.ts",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 0, deletions: 0, filesChanged: 1 });
  });

  it("does not count +++ header lines as additions", () => {
    const diff = [
      "diff --git a/file.ts b/file.ts",
      "--- a/file.ts",
      "+++ b/file.ts",
      "@@ -1,2 +1,3 @@",
      " unchanged",
      "+actual addition",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 1, deletions: 0, filesChanged: 1 });
  });

  it("does not count --- header lines as deletions", () => {
    const diff = [
      "diff --git a/file.ts b/file.ts",
      "--- a/file.ts",
      "+++ b/file.ts",
      "@@ -1,3 +1,2 @@",
      " unchanged",
      "-actual deletion",
    ].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 0, deletions: 1, filesChanged: 1 });
  });

  it("counts +/- lines even without a diff --git header", () => {
    const diff = ["+added line", "-deleted line"].join("\n");

    expect(parseDiffStats(diff)).toEqual({ additions: 1, deletions: 1, filesChanged: 0 });
  });
});
