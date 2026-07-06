import { Button } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import { useTimedLatch } from "~/common/Hooks.ts";
import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff";
import { jumpToSectionAtom, openPanelAtom } from "~/components/sections/sectionActions.ts";

import { changesScopeAtomFamily } from "../panels/fileBrowser/atoms";
import { parseDiffStats } from "../utils/parseDiffStats";
import styles from "./DiffSummary.module.scss";

// Holds the shimmer on long enough to complete one full pulse cycle even when
// the underlying fetch returns in under a frame.
const SHIMMER_MIN_HOLD_MS = 1500;

type DiffSummaryProps = {
  workspaceId: string;
};

export const DiffSummary = ({ workspaceId }: DiffSummaryProps): ReactElement | null => {
  const { data: diff, isFetching, isGenerating } = useWorkspaceDiff(workspaceId);
  const isShimmering = useTimedLatch(isFetching || isGenerating, SHIMMER_MIN_HOLD_MS);
  const openPanel = useSetAtom(openPanelAtom);
  const jumpToSection = useSetAtom(jumpToSectionAtom);
  const setChangesScope = useSetAtom(changesScopeAtomFamily(workspaceId));

  const stats = useMemo(() => parseDiffStats(diff?.targetBranchDiff), [diff?.targetBranchDiff]);

  const handleClick = (): void => {
    // Surface the Changes panel in the left section (opening/expanding it) and pulse the
    // ring, then point it at the target-branch diff.
    openPanel({ panelId: "changes", in: "left" });
    jumpToSection({ subSection: "left" });
    setChangesScope("vs-target-branch");
  };

  if (!diff || (stats.additions === 0 && stats.deletions === 0 && stats.filesChanged === 0)) {
    return null;
  }

  // Background refetch (data is already shown): a shimmer sweeps left-to-right
  // across the button via a ::after overlay, signalling a refresh without
  // any layout shift.
  const className = isShimmering ? `${styles.summary} ${styles.refreshing}` : styles.summary;

  return (
    <Button variant="ghost" size="1" className={className} onClick={handleClick} data-testid={ElementIds.DIFF_SUMMARY}>
      <span className={styles.additions}>+{stats.additions}</span>
      <span className={styles.deletions}>-{stats.deletions}</span>
      <span className={styles.separator}>&middot;</span>
      <span className={styles.fileCount}>{stats.filesChanged} files</span>
    </Button>
  );
};
