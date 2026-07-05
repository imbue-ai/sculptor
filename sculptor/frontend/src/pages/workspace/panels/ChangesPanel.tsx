// The Changes panel: a single-instance left-section panel that pairs the changes
// browser (the list — scope picker, commit button, changed-file tree, discard) with
// an embedded DiffViewer (the detail). It owns its own selection — a scoped diff of
// the clicked file — and feeds it to its own viewer instance, so there is no shared
// "active diff" singleton.

import { Flex } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import {
  activeDiffTabAtomFamily,
  changesSelectionFromTab,
  closeDiffTabAtom,
} from "~/pages/workspace/diffPanel/atoms.ts";
import { DiffScopePicker } from "~/pages/workspace/diffPanel/DiffScopePicker.tsx";
import type { DiffSelection, TreeViewOptions } from "~/pages/workspace/diffViewer/index.ts";
import { DiffViewer } from "~/pages/workspace/diffViewer/index.ts";
import { activeWorkspaceIdAtom } from "~/pages/workspace/layout/atoms/section.ts";

import styles from "./ChangesPanel.module.scss";
import { DiscardDialog } from "./changesPanel/DiscardDialog.tsx";
import { useDiscardFile } from "./changesPanel/useDiscardFile.ts";
import { ExplorerLayout } from "./ExplorerLayout.tsx";
import {
  changesPanelSelectionAtomFamily,
  changesScopeAtomFamily,
  collapseAllChangesFoldersAtom,
  fileBrowserViewModeAtomFamily,
  toggleViewModeAtom,
} from "./fileBrowser/atoms.ts";
import { ChangesTreeView } from "./fileBrowser/ChangesTreeView.tsx";
import { CommitButton } from "./fileBrowser/CommitButton.tsx";
import { useFileStatusMap } from "./fileBrowser/hooks.ts";
import type { FileStatus } from "./fileBrowser/types.ts";
import { reconcileSelectionByRecency } from "./selectionRecency.ts";

const ChangesPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const workspace = useWorkspace(workspaceId);
  const hasTargetBranch = workspace?.targetBranch != null;

  const [scope, setScope] = useAtom(changesScopeAtomFamily(workspaceId));
  const viewMode = useAtomValue(fileBrowserViewModeAtomFamily(workspaceId));
  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const collapseAllChangesFolders = useSetAtom(collapseAllChangesFoldersAtom);

  const uncommittedStatusMap = useFileStatusMap(workspaceId, "uncommitted");
  const allStatusMap = useFileStatusMap(workspaceId, "vs-target-branch");
  const { discardFile } = useDiscardFile(workspaceId);

  // Clicked-file selection, persisted per-workspace so it survives the panel
  // unmounting on a section-tab switch (reconciled with the atom-driven one below).
  const [selected, setSelected] = useAtom(changesPanelSelectionAtomFamily(workspaceId));
  const [discardTarget, setDiscardTarget] = useState<string | null>(null);

  // The shared active diff tab — written when an agent opens a diff (a chat file-chip,
  // sculpt open-file --mode diff). Reading it here makes those opens render in this
  // panel's single embedded viewer, not just reveal the panel.
  const activeTab = useAtomValue(activeDiffTabAtomFamily(workspaceId));
  const closeDiffTab = useSetAtom(closeDiffTabAtom);

  const isUncommitted = scope === "uncommitted";

  const handleSelectFile = useCallback(
    (filePath: string, status: FileStatus): void => {
      setSelected({ filePath, status, at: Date.now() });
    },
    [setSelected],
  );

  const handleDiscardRequest = useCallback((filePath: string): void => {
    setDiscardTarget(filePath);
  }, []);

  const handleDiscardConfirm = useCallback((): void => {
    if (discardTarget) {
      void discardFile(discardTarget);
      // Clear the viewer if the discarded file is the one being shown, whether it
      // is driven by the local click or by a shared single-kind diff tab (an agent
      // open / chat file-chip). Clearing only the local half would leave the tab
      // still resolving to the just-discarded file.
      setSelected((prev) => (prev?.filePath === discardTarget ? null : prev));
      if (activeTab?.kind === "single" && changesSelectionFromTab(activeTab)?.filePath === discardTarget) {
        closeDiffTab({ workspaceId, filePath: activeTab.filePath });
      }
      setDiscardTarget(null);
    }
  }, [discardTarget, discardFile, setSelected, activeTab, closeDiffTab, workspaceId]);

  // After committing, the uncommitted changes clear, so reset the viewer. Drop
  // the local click and close the shared single-kind tab as well; otherwise the
  // tab wins the recency reconcile and a stale agent-opened diff resurfaces.
  const handleCommit = useCallback((): void => {
    setSelected(null);
    if (activeTab?.kind === "single") {
      closeDiffTab({ workspaceId, filePath: activeTab.filePath });
    }
  }, [setSelected, activeTab, closeDiffTab, workspaceId]);

  // Dismiss a deleted file from the viewer's banner: drop the local click
  // selection only when it points at that file, so an unrelated clicked file
  // (the deleted view came from an agent open) survives the close. The viewer
  // closes the shared diff tab itself.
  const handleCloseFile = useCallback(
    (filePath: string): void => {
      setSelected((prev) => (prev?.filePath === filePath ? null : prev));
    },
    [setSelected],
  );

  const handleToggleViewMode = useCallback((): void => {
    toggleViewMode({ workspaceId });
  }, [toggleViewMode, workspaceId]);

  const handleCollapseAll = useCallback((): void => {
    collapseAllChangesFolders({ workspaceId });
  }, [collapseAllChangesFolders, workspaceId]);

  // The selection carries the active scope so switching All/Uncommitted re-renders the
  // same file against the newly chosen base. Reconcile the local click selection with
  // the atom-driven one (an agent open) by recency: whichever was activated last wins.
  const selection = useMemo(
    (): DiffSelection | null =>
      reconcileSelectionByRecency({
        local: selected,
        tab: activeTab,
        tabKind: "single",
        toSelection: (local) => ({ kind: "diff", filePath: local.filePath, status: local.status, scope }),
        fromTab: changesSelectionFromTab,
      }),
    [selected, scope, activeTab],
  );

  // The path highlighted in the tree mirrors whatever the viewer is showing.
  const selectedPath = selection?.kind === "diff" ? selection.filePath : null;

  const treeOptions: TreeViewOptions = {
    viewMode,
    onToggleViewMode: handleToggleViewMode,
    onCollapseAll: handleCollapseAll,
    collapseLabel: "Collapse folders",
  };

  const list = (
    <Flex
      direction="column"
      height="100%"
      overflow="hidden"
      className={styles.list}
      data-testid={ElementIds.CHANGES_PANEL}
    >
      <Flex flexShrink="0" px="3" py="2" direction="column">
        <DiffScopePicker
          scope={scope}
          onScopeChange={setScope}
          hasTargetBranch={hasTargetBranch}
          uncommittedCount={uncommittedStatusMap.size}
          allCount={allStatusMap.size}
        />
      </Flex>
      <ChangesTreeView
        workspaceId={workspaceId}
        viewMode={viewMode}
        scope={scope}
        onSelectFile={handleSelectFile}
        selectedPath={selectedPath}
        onDiscardFile={isUncommitted ? handleDiscardRequest : undefined}
      />
      {/* The commit action is a footer pinned under the tree (which flexes to
          fill), separated from the rows by its own top border. */}
      <Flex flexShrink="0" px="3" py="2" className={styles.commitFooter}>
        <CommitButton changesCount={uncommittedStatusMap.size} onCommit={handleCommit} />
      </Flex>
      <DiscardDialog
        open={discardTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDiscardTarget(null);
        }}
        filePath={discardTarget ?? ""}
        onConfirm={handleDiscardConfirm}
      />
    </Flex>
  );

  return (
    <ExplorerLayout
      list={list}
      detail={(sidebarToggle) => (
        <DiffViewer
          workspaceId={workspaceId}
          selection={selection}
          treeOptions={treeOptions}
          sidebarToggle={sidebarToggle}
          onCloseFile={handleCloseFile}
        />
      )}
    />
  );
};

export const ChangesPanel = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return null;
  }
  // Key on the workspace id so switching workspaces resets the panel's local
  // selection state instead of carrying a stale file path across workspaces.
  return <ChangesPanelContent key={workspaceId} workspaceId={workspaceId} />;
};
