// Pure ordering + selection helpers for the Layouts switcher. No atoms, no React —
// directly unit-testable.

import type { SavedLayout } from "~/components/sections/persistence/types.ts";

const NEVER_APPLIED_RANK = Number.MAX_SAFE_INTEGER;

// Order the candidate layouts by the MRU list (most-recently-applied first). A
// layout that has never been applied keeps its stable input order after all the
// applied ones (System Default is a normal participant, seeded first in the input).
// This is the switcher's list order — PyCharm ⌘E semantics.
export function orderLayoutsByMru(layouts: ReadonlyArray<SavedLayout>, mru: ReadonlyArray<string>): Array<SavedLayout> {
  const rankById = new Map<string, number>(mru.map((id, index) => [id, index]));
  return layouts
    .map((layout, index) => ({ layout, index }))
    .sort((a, b) => {
      const rankA = rankById.get(a.layout.id) ?? NEVER_APPLIED_RANK;
      const rankB = rankById.get(b.layout.id) ?? NEVER_APPLIED_RANK;
      // Preserve the input order as the stable tiebreaker (System Default first).
      return rankA === rankB ? a.index - b.index : rankA - rankB;
    })
    .map((entry) => entry.layout);
}

// The row the switcher opens highlighted: the first one that is NOT the workspace's
// current layout, so ⌘⇧L lands on the "previous" layout (and, cross-workspace, on
// the most-recent layout you are not already using). Falls back to the first row.
export function initialHighlightIndex(
  ordered: ReadonlyArray<SavedLayout>,
  appliedLayoutId: string | undefined,
): number {
  if (ordered.length === 0) {
    return 0;
  }
  const index = ordered.findIndex((layout) => layout.id !== appliedLayoutId);
  return index === -1 ? 0 : index;
}
