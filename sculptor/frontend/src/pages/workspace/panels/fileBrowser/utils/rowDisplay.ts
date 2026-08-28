import type { CSSProperties } from "react";

import type { FileStatus } from "../types/fileBrowser.ts";

/** Maps file status to its design-system color token (text level). */
const STATUS_COLORS: Record<FileStatus, string> = {
  M: "var(--amber-11)",
  A: "var(--green-11)",
  D: "var(--red-11)",
  R: "var(--purple-11)",
};

/** Pre-computed style objects for status colors, avoiding inline object creation on each render. */
export const STATUS_COLOR_STYLES: Record<FileStatus, CSSProperties> = {
  M: { color: STATUS_COLORS.M },
  A: { color: STATUS_COLORS.A },
  D: { color: STATUS_COLORS.D },
  R: { color: STATUS_COLORS.R },
};

/**
 * Truncate a directory path for display by keeping the first and last segments
 * and replacing the middle with "…". Prioritises showing the last segment
 * (closest parent) since it provides the most context about where a file lives.
 *
 *   "sculptor/frontend/src/components" → "sculptor/…/components"
 *   "imbue_core/imbue_core"            → "imbue_core/imbue_core" (unchanged)
 */
export const truncateMiddlePath = (dirPath: string, maxSegments: number = 3): string => {
  const segments = dirPath.split("/");
  if (segments.length <= maxSegments) return dirPath;

  const first = segments[0];
  const last = segments[segments.length - 1];
  return `${first}/…/${last}`;
};
