import { describe, expect, it } from "vitest";

import { filterFilesBySubstring } from "./utils.ts";

// ── filterFilesBySubstring ──────────────────────────────────────────

describe("filterFilesBySubstring", () => {
  const files = [
    { path: "src/components/Button.tsx", type: "file" as const },
    { path: "src/components/ButtonGroup.tsx", type: "file" as const },
    { path: "src/utils/format.ts", type: "file" as const },
    { path: "src/utils/formatDate.ts", type: "file" as const },
    { path: "src/pages/Home.tsx", type: "file" as const },
    { path: "README.md", type: "file" as const },
  ];

  it("returns files whose path contains the query as a substring", () => {
    const result = filterFilesBySubstring(files, "Button");
    expect(result.matchingPaths).toEqual(new Set(["src/components/Button.tsx", "src/components/ButtonGroup.tsx"]));
  });

  it("is case-insensitive", () => {
    const result = filterFilesBySubstring(files, "button");
    expect(result.matchingPaths).toEqual(new Set(["src/components/Button.tsx", "src/components/ButtonGroup.tsx"]));
  });

  it("does not fuzzy-match — only exact substrings", () => {
    // "Buttn" is close to "Button" but should NOT match
    const result = filterFilesBySubstring(files, "Buttn");
    expect(result.matchingPaths.size).toBe(0);
  });

  it("matches anywhere in the path", () => {
    const result = filterFilesBySubstring(files, "utils/format");
    expect(result.matchingPaths).toEqual(new Set(["src/utils/format.ts", "src/utils/formatDate.ts"]));
  });

  it("returns empty results for empty query", () => {
    const result = filterFilesBySubstring(files, "");
    expect(result.matchingPaths.size).toBe(0);
    expect(result.results.length).toBe(0);
  });

  it("returns empty results when nothing matches", () => {
    const result = filterFilesBySubstring(files, "zzz_no_match");
    expect(result.matchingPaths.size).toBe(0);
  });
});
