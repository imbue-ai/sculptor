import { describe, expect, it } from "vitest";

import { fuzzySearchFiles, scoreFilePath } from "./fuzzyFileScorer";

describe("scoreFilePath", () => {
  it("returns 0 for an empty query", () => {
    expect(scoreFilePath("", "src/foo.ts")).toBe(0);
  });

  it("returns 0 when the query is not a subsequence of the path", () => {
    expect(scoreFilePath("xyz", "src/foo.ts")).toBe(0);
  });

  it("returns a positive score for a subsequence match", () => {
    expect(scoreFilePath("foo", "src/foo.ts")).toBeGreaterThan(0);
  });

  it("is case-insensitive", () => {
    expect(scoreFilePath("FOO", "src/foo.ts")).toBeGreaterThan(0);
    expect(scoreFilePath("foo", "src/FOO.ts")).toBeGreaterThan(0);
  });

  it("scores an exact filename match higher than a partial match", () => {
    const exact = scoreFilePath("foo.ts", "src/foo.ts");
    const partial = scoreFilePath("fo", "src/foo.ts");
    expect(exact).toBeGreaterThan(partial);
  });

  it("prefers filename matches over path-only matches", () => {
    const filenameMatch = scoreFilePath("bar", "src/foo/bar.ts");
    const pathMatch = scoreFilePath("src", "src/foo/bar.ts");
    expect(filenameMatch).toBeGreaterThan(pathMatch);
  });

  it("scores consecutive character matches higher than scattered matches", () => {
    const consecutive = scoreFilePath("foo", "src/foo.ts");
    const scattered = scoreFilePath("fot", "src/foo.ts");
    expect(consecutive).toBeGreaterThan(scattered);
  });

  it("awards a bonus for word-boundary matches", () => {
    // "fb" matches word boundaries in "file-browser" (f at start, b after -)
    const boundary = scoreFilePath("fb", "file-browser.ts");
    // "il" doesn't hit word boundaries
    const interior = scoreFilePath("il", "file-browser.ts");
    expect(boundary).toBeGreaterThan(interior);
  });

  it("awards a bonus for camelCase boundary matches", () => {
    const camel = scoreFilePath("fS", "fuzzyFileScorer.ts");
    const noCamel = scoreFilePath("zy", "fuzzyFileScorer.ts");
    expect(camel).toBeGreaterThan(noCamel);
  });

  it("scores a start-of-string match higher than a mid-string match", () => {
    // Same query against paths where the match is in the full path (not filename)
    const startMatch = scoreFilePath("src", "src/zzz/zzz.ts");
    const midMatch = scoreFilePath("src", "zzz/src/zzz.ts");
    expect(startMatch).toBeGreaterThan(midMatch);
  });
});

describe("fuzzySearchFiles", () => {
  const paths = [
    "src/components/Editor.tsx",
    "src/components/EditorToolbar.tsx",
    "src/utils/helpers.ts",
    "src/pages/workspace/WorkspacePage.tsx",
    "README.md",
    "package.json",
  ];

  it("returns an empty array for an empty query", () => {
    expect(fuzzySearchFiles("", paths)).toEqual([]);
  });

  it("returns matching results sorted by descending score", () => {
    const results = fuzzySearchFiles("edit", paths);
    expect(results.length).toBeGreaterThan(0);
    for (let i = 1; i < results.length; i++) {
      expect(results[i - 1].score).toBeGreaterThanOrEqual(results[i].score);
    }
  });

  it("filters out non-matching paths", () => {
    const results = fuzzySearchFiles("xyz", paths);
    expect(results).toEqual([]);
  });

  it("respects the maxResults limit", () => {
    const results = fuzzySearchFiles("s", paths, 2);
    expect(results.length).toBeLessThanOrEqual(2);
  });

  it("ranks an exact filename match first", () => {
    const results = fuzzySearchFiles("helpers", paths);
    expect(results[0].path).toBe("src/utils/helpers.ts");
  });

  it("ranks a shorter, tighter match above a longer scattered one", () => {
    const results = fuzzySearchFiles("Editor", paths);
    expect(results[0].path).toBe("src/components/Editor.tsx");
    expect(results[1].path).toBe("src/components/EditorToolbar.tsx");
  });
});
