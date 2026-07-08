// The Commits panel: a single-instance left-section panel that pairs the commit
// history (the list — commit graph, rows, popover, footer) with an embedded
// DiffViewer (the detail). It owns its own selection — a commit-scoped diff of the
// clicked file within a commit — and feeds it to its own viewer instance, so there
// is no shared "active diff" singleton.

import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import { activeDiffTabAtomFamily, commitSelectionFromTab } from "~/pages/workspace/components/diffPanel/atoms.ts";
import type { DiffSelection, TreeViewOptions } from "~/pages/workspace/components/diffViewer/index.ts";
import { DiffViewer } from "~/pages/workspace/components/diffViewer/index.ts";

import styles from "./CommitsPanel.module.scss";
import { ExplorerLayout } from "./ExplorerLayout.tsx";
import { collapseAllCommitsAtom, commitsPanelSelectionAtomFamily } from "./historyPanel/atoms.ts";
import { HistoryTabContent } from "./historyPanel/HistoryTabContent.tsx";
import { reconcileSelectionByRecency } from "./selectionRecency.ts";

const CommitsPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const collapseAllCommits = useSetAtom(collapseAllCommitsAtom);

  // Per-panel selection, persisted per-workspace so the open commit file survives the
  // panel unmounting on a section-tab switch.
  const [selected, setSelected] = useAtom(commitsPanelSelectionAtomFamily(workspaceId));

  // The shared active diff tab — written when a commit diff is opened outside the
  // history list (e.g. the header's recent-files dropdown). Reading it here makes
  // those opens render in this panel's single embedded viewer, mirroring the
  // Files / Changes panels.
  const activeTab = useAtomValue(activeDiffTabAtomFamily(workspaceId));

  const handleSelectCommitFile = useCallback(
    (commitHash: string, filePath: string): void => {
      setSelected({ commitHash, filePath, at: Date.now() });
    },
    [setSelected],
  );

  const handleCollapseAll = useCallback((): void => {
    collapseAllCommits({ workspaceId });
  }, [collapseAllCommits, workspaceId]);

  // Reconcile the local click selection with the atom-driven one by recency:
  // whichever was activated last wins.
  const selection = useMemo(
    (): DiffSelection | null =>
      reconcileSelectionByRecency({
        local: selected,
        tab: activeTab,
        tabKind: "commit-diff",
        toSelection: (local) => ({ kind: "commit-diff", commitHash: local.commitHash, filePath: local.filePath }),
        fromTab: commitSelectionFromTab,
      }),
    [selected, activeTab],
  );

  // The commit history has no flat/tree toggle; the menu only offers collapse-all.
  const treeOptions: TreeViewOptions = {
    onCollapseAll: handleCollapseAll,
    collapseLabel: "Collapse commits",
  };

  const list = (
    <div className={styles.list}>
      <HistoryTabContent workspaceId={workspaceId} onSelectCommitFile={handleSelectCommitFile} />
    </div>
  );

  return (
    <ExplorerLayout
      panelId="commits"
      list={list}
      detail={(sidebarToggle) => (
        <DiffViewer
          workspaceId={workspaceId}
          selection={selection}
          treeOptions={treeOptions}
          sidebarToggle={sidebarToggle}
        />
      )}
    />
  );
};

export const CommitsPanel = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return null;
  }
  // Key on the workspace id so switching workspaces resets the panel's local
  // selection state instead of carrying a stale commit across workspaces.
  return <CommitsPanelContent key={workspaceId} workspaceId={workspaceId} />;
};
