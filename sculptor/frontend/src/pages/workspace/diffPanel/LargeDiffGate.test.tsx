import { describe, expect, it } from "vitest";

import { truncateAtHunkBoundary } from "./truncateAtHunkBoundary";

// Helper to build a unified diff string with the given number of content lines per hunk.
const makeSingleHunkDiff = (contentLines: number): string => {
  const header = [
    "diff --git a/file.md b/file.md",
    "--- a/file.md",
    "+++ b/file.md",
    `@@ -1,${contentLines} +1,${contentLines} @@`,
  ];
  const content = Array.from({ length: contentLines }, (_, i) => `+line ${i + 1}`);
  return [...header, ...content].join("\n");
};

const makeTwoHunkDiff = (firstHunkLines: number, secondHunkLines: number): string => {
  const header = ["diff --git a/file.md b/file.md", "--- a/file.md", "+++ b/file.md"];
  const hunk1Header = `@@ -1,${firstHunkLines} +1,${firstHunkLines} @@`;
  const hunk1Content = Array.from({ length: firstHunkLines }, (_, i) => `+line ${i + 1}`);
  const hunk2Header = `@@ -100,${secondHunkLines} +100,${secondHunkLines} @@`;
  const hunk2Content = Array.from({ length: secondHunkLines }, (_, i) => `+line ${firstHunkLines + i + 1}`);
  return [...header, hunk1Header, ...hunk1Content, hunk2Header, ...hunk2Content].join("\n");
};

describe("truncateAtHunkBoundary", () => {
  it("returns the full diff when line count is within the threshold", () => {
    const diff = makeSingleHunkDiff(10);
    expect(truncateAtHunkBoundary(diff, 500)).toBe(diff);
  });

  it("returns a non-empty result for a single large hunk", () => {
    // A single hunk with 600 content lines → ~604 total lines (header + @@ + content).
    // The @@ is at line 3. Truncating before it would yield only the file header (empty diff).
    const diff = makeSingleHunkDiff(600);
    const result = truncateAtHunkBoundary(diff, 500);

    // Must include diff content, not just file headers
    expect(result.split("\n").length).toBeGreaterThan(10);
    // Must include the @@ hunk header so the diff viewer can render it
    expect(result).toContain("@@");
    // Must include some content lines
    expect(result).toContain("+line 1");
  });

  it("truncates at the second hunk boundary when two hunks exist", () => {
    // First hunk: 300 lines of content, second hunk: 300 lines of content.
    // Total: 3 (file header) + 1 (@@ hunk1) + 300 + 1 (@@ hunk2) + 300 = 605 lines.
    // The second @@ is at line 304. Truncating should cut before the second hunk.
    const diff = makeTwoHunkDiff(300, 300);
    const result = truncateAtHunkBoundary(diff, 500);

    // Should include the first hunk entirely
    expect(result).toContain("+line 1");
    expect(result).toContain("+line 300");
    // Should NOT include lines from the second hunk
    expect(result).not.toContain("+line 601");
  });
});
