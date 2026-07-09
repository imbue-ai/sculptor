/**
 * Parse the spotlight anchors present in a chat-input draft. The draft is a
 * markdown string in which each spotlight chip serializes as a
 * `<span data-sculptor-node data-spotlight-*="…">` element (see TipTapConfig's
 * renderMarkdown). This extracts the navigational half (`SpotlightAnchor`) of
 * every such span so the diff panes can draw a persistent gutter bar per chip.
 *
 * Only the anchor fields are read — snippet / branch / HEAD are irrelevant to
 * the bars. Ordering follows document order, which keeps each anchor's rotating
 * colour stable as the user edits around it.
 */

import type { SpotlightAnchor } from "./types.ts";
import { lineRangeFromStrings, spotlightScopeFromStrings } from "./types.ts";

export const parseSpotlightDraftAnchors = (draft: string | null | undefined): Array<SpotlightAnchor> => {
  if (!draft || !draft.includes("data-spotlight-file")) return [];
  const doc = new DOMParser().parseFromString(draft, "text/html");
  const anchors: Array<SpotlightAnchor> = [];
  for (const span of doc.querySelectorAll("span[data-spotlight-file]")) {
    const file = span.getAttribute("data-spotlight-file");
    if (!file) continue;
    anchors.push({
      file,
      previousFileLines: lineRangeFromStrings(
        span.getAttribute("data-spotlight-previous-start"),
        span.getAttribute("data-spotlight-previous-end"),
      ),
      currentFileLines: lineRangeFromStrings(
        span.getAttribute("data-spotlight-current-start"),
        span.getAttribute("data-spotlight-current-end"),
      ),
      scope: spotlightScopeFromStrings(
        span.getAttribute("data-spotlight-scope"),
        span.getAttribute("data-spotlight-commit-hash"),
      ),
    });
  }
  return anchors;
};
