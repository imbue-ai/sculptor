// The Commits panel: a single-instance left-section panel that pairs the commit
// history (the list — commit graph, rows, popover, footer) with an embedded
// DiffViewer (the detail). It owns its own selection — a commit-scoped diff of the
// clicked file within a commit — and feeds it to its own viewer instance, so there
// is no shared "active diff" singleton. In a jj workspace the list is the
// workspace's revisions and the panel is labelled Revisions.

import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import type { RevisionInfo } from "~/api";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useWorkspaceRevisions } from "~/common/state/hooks/useWorkspaceRevisions.ts";
import { useWorkspaceVcs } from "~/common/state/hooks/useWorkspaceVcs.ts";
import { activeDiffTabAtomFamily, commitSelectionFromTab } from "~/pages/workspace/diffPanel/atoms/diffPanel.ts";
import type { DiffSelection, TreeViewOptions } from "~/pages/workspace/diffViewer/index.ts";
import { DiffViewer } from "~/pages/workspace/diffViewer/index.ts";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

import styles from "./CommitsPanel.module.scss";
import { ExplorerLayout } from "./ExplorerLayout.tsx";
import {
  collapseAllCommitsAtom,
  commitsPanelSelectionAtomFamily,
  expandedCommitsAtomFamily,
  revisionsPanelSelectionAtomFamily,
  toggleCommitExpandedAtom,
} from "./historyPanel/atoms/historyPanel.ts";
import { HistoryTabContent } from "./historyPanel/HistoryTabContent.tsx";
import { RevisionList } from "./historyPanel/RevisionList.tsx";
import { resolveSelectedRevisionCommitId } from "./historyPanel/revisionSelection.ts";
import { reconcileSelectionByRecency } from "./selectionRecency.ts";

/** The history list beside the panel's own embedded viewer. */
const HistoryExplorerLayout = ({
  workspaceId,
  list,
  selection,
  collapseLabel,
}: {
  workspaceId: string;
  list: ReactElement;
  selection: DiffSelection | null;
  collapseLabel: string;
}): ReactElement => {
  const collapseAllCommits = useSetAtom(collapseAllCommitsAtom);

  const handleCollapseAll = useCallback((): void => {
    collapseAllCommits({ workspaceId });
  }, [collapseAllCommits, workspaceId]);

  // The history has no flat/tree toggle; the menu only offers collapse-all.
  const treeOptions: TreeViewOptions = {
    onCollapseAll: handleCollapseAll,
    collapseLabel,
  };

  return (
    <ExplorerLayout
      panelId="commits"
      list={<div className={styles.list}>{list}</div>}
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

const CommitsPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
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

  return (
    <HistoryExplorerLayout
      workspaceId={workspaceId}
      list={<HistoryTabContent workspaceId={workspaceId} onSelectCommitFile={handleSelectCommitFile} />}
      selection={selection}
      collapseLabel="Collapse commits"
    />
  );
};

const RevisionsPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const workspace = useWorkspace(workspaceId);
  const { data, isPending } = useWorkspaceRevisions(workspaceId);
  const expandedChangeIds = useAtomValue(expandedCommitsAtomFamily(workspaceId));
  const toggleExpanded = useSetAtom(toggleCommitExpandedAtom);
  // Per-panel selection, persisted per-workspace like the Commits panel's.
  const [selected, setSelected] = useAtom(revisionsPanelSelectionAtomFamily(workspaceId));
  // The shared active diff tab, as in the Commits panel; its commit hash is a jj commit id.
  const activeTab = useAtomValue(activeDiffTabAtomFamily(workspaceId));

  const handleToggleRevision = useCallback(
    (changeId: string): void => {
      toggleExpanded({ workspaceId, commitHash: changeId });
    },
    [toggleExpanded, workspaceId],
  );

  const handleSelectFile = useCallback(
    (revision: RevisionInfo, filePath: string): void => {
      setSelected({ changeId: revision.changeId, commitId: revision.commitId, filePath, at: Date.now() });
    },
    [setSelected],
  );

  // The selection is keyed by change id and its diff fetched by commit id: the
  // revision's current commit, which changes whenever jj rewrites it.
  const revisions = data?.revisions;
  const selection = useMemo((): DiffSelection | null => {
    const commitId = selected === null ? null : resolveSelectedRevisionCommitId({ selection: selected, revisions });
    return reconcileSelectionByRecency({
      local: selected !== null && commitId !== null ? { ...selected, commitId } : null,
      tab: activeTab,
      tabKind: "commit-diff",
      toSelection: (local) => ({ kind: "commit-diff", commitHash: local.commitId, filePath: local.filePath }),
      fromTab: commitSelectionFromTab,
    });
  }, [selected, revisions, activeTab]);

  return (
    <HistoryExplorerLayout
      workspaceId={workspaceId}
      list={
        <RevisionList
          history={data}
          isPending={isPending}
          target={workspace?.targetBranch ?? null}
          expandedChangeIds={expandedChangeIds}
          onToggleRevision={handleToggleRevision}
          onSelectFile={handleSelectFile}
        />
      }
      selection={selection}
      collapseLabel="Collapse revisions"
    />
  );
};

export const CommitsPanel = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  const vcs = useWorkspaceVcs(workspaceId);
  if (workspaceId === null) {
    return null;
  }
  // Key on the workspace id so switching workspaces resets the panel's local
  // selection state instead of carrying a stale commit across workspaces.
  return vcs === "jj" ? (
    <RevisionsPanelContent key={workspaceId} workspaceId={workspaceId} />
  ) : (
    <CommitsPanelContent key={workspaceId} workspaceId={workspaceId} />
  );
};
