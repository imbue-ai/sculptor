export const truncateAtHunkBoundary = (diff: string, maxLines: number): string => {
  const lines = diff.split("\n");
  if (lines.length <= maxLines) return diff;

  // Search backward from the limit for a hunk header to avoid splitting a hunk mid-way.
  // If we find one, cut just before it so we only show complete hunks.
  for (let i = maxLines - 1; i >= 0; i--) {
    if (lines[i].startsWith("@@")) {
      // Only cut here if it leaves meaningful content (not just file headers).
      if (i > maxLines / 2) {
        return lines.slice(0, i).join("\n");
      }
      break;
    }
  }

  // No good hunk boundary found — just truncate at the line limit.
  return lines.slice(0, maxLines).join("\n");
};
