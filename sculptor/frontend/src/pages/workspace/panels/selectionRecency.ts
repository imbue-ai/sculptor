// Shared recency reconciliation for the Files / Changes / Commits panels: each
// panel holds its own LOCAL click selection (stamped with a wall-clock `at`)
// while agent opens write the shared active diff tab (stamped `viewedAt`).
// Whichever was activated last drives the panel's embedded viewer, so a local
// click still takes effect after an agent open and vice-versa.

import type { DiffTab } from "~/pages/workspace/components/diffPanel/types.ts";
import type { DiffSelection } from "~/pages/workspace/components/diffViewer/types.ts";

type ReconcileParams<TLocal extends { at: number }> = {
  /** The panel's own click selection, or null when nothing was clicked. */
  local: TLocal | null;
  /** The shared active diff tab (any kind), or null when no tab is active. */
  tab: DiffTab | null;
  /** The tab kind that belongs to the calling panel; other kinds never render here. */
  tabKind: DiffTab["kind"];
  /** Maps a winning local selection to the panel's viewer selection. */
  toSelection: (local: TLocal) => DiffSelection;
  /** Maps the active tab to the panel's viewer selection (null for foreign kinds). */
  fromTab: (tab: DiffTab | null) => DiffSelection | null;
};

/**
 * Picks the most recently activated of the two selection sources and maps it to
 * the panel's {@link DiffSelection}. A tab of a foreign kind never has a
 * timestamp here, so the local selection wins over it regardless of age — an
 * agent-opened diff must not clear the Files panel's open file, and vice-versa.
 * Ties go to the local click.
 */
export function reconcileSelectionByRecency<TLocal extends { at: number }>({
  local,
  tab,
  tabKind,
  toSelection,
  fromTab,
}: ReconcileParams<TLocal>): DiffSelection | null {
  const tabViewedAt = tab !== null && tab.kind === tabKind ? tab.viewedAt : null;
  const isLocalNewer = local !== null && (tabViewedAt === null || local.at >= tabViewedAt);
  if (local !== null && isLocalNewer) {
    return toSelection(local);
  }
  return fromTab(tab);
}
