// The Changes panel: a single-instance left-section panel that pairs the changes
// browser (the list — scope picker, commit button, changed-file tree, discard) with
// an embedded DiffViewer (the detail). It owns its own selection — a scoped diff of
// the clicked file — and feeds it to its own viewer instance, so there is no shared
// "active diff" singleton (FCC-01/02/03). The proven changes-browser behavior
// (All/Uncommitted scope, discard, commit-from-changes) is migrated, not redesigned.

import { Flex } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { registerPanelComponent } from "~/components/sections/registry/panelRegistry.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import { DiffScopePicker } from "~/pages/workspace/components/diffPanel/DiffScopePicker.tsx";
import type { DiffSelection, TreeViewOptions } from "~/pages/workspace/components/diffViewer/index.ts";
import { DiffViewer } from "~/pages/workspace/components/diffViewer/index.ts";

import styles from "./ChangesPanel.module.scss";
import { DiscardDialog } from "./changesPanel/DiscardDialog.tsx";
import { useDiscardFile } from "./changesPanel/useDiscardFile.ts";
import { EmptyDetail, ExplorerLayout } from "./ExplorerLayout.tsx";
import {
  changesScopeAtomFamily,
  collapseAllChangesFoldersAtom,
  fileBrowserStateAtomFamily,
  toggleViewModeAtom,
} from "./fileBrowser/atoms.ts";
import { ChangesTreeView } from "./fileBrowser/ChangesTreeView.tsx";
import { CommitButton } from "./fileBrowser/CommitButton.tsx";
import { useFileStatusMap } from "./fileBrowser/hooks.ts";
import type { FileStatus } from "./fileBrowser/types.ts";

/** The file the panel's viewer is currently showing, with the status the list reported. */
type ChangesSelection = { filePath: string; status: FileStatus };

const ChangesPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const workspace = useWorkspace(workspaceId);
  const hasTargetBranch = workspace?.targetBranch != null;

  const [scope, setScope] = useAtom(changesScopeAtomFamily(workspaceId));
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceId));
  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const collapseAllChangesFolders = useSetAtom(collapseAllChangesFoldersAtom);

  const uncommittedStatusMap = useFileStatusMap(workspaceId, "uncommitted");
  const allStatusMap = useFileStatusMap(workspaceId, "vs-target-branch");
  const { discardFile } = useDiscardFile(workspaceId);

  // Per-panel selection: the changed file currently shown in this panel's viewer.
  const [selected, setSelected] = useState<ChangesSelection | null>(null);
  const [discardTarget, setDiscardTarget] = useState<string | null>(null);

  const { viewMode } = fileBrowserState;
  const isUncommitted = scope === "uncommitted";

  const handleSelectFile = useCallback((filePath: string, status: FileStatus): void => {
    setSelected({ filePath, status });
  }, []);

  const handleDiscardRequest = useCallback((filePath: string): void => {
    setDiscardTarget(filePath);
  }, []);

  const handleDiscardConfirm = useCallback((): void => {
    if (discardTarget) {
      void discardFile(discardTarget);
      // Clear the viewer if the discarded file was the one being shown.
      setSelected((prev) => (prev?.filePath === discardTarget ? null : prev));
      setDiscardTarget(null);
    }
  }, [discardTarget, discardFile]);

  // After committing, the uncommitted changes clear, so reset the viewer.
  const handleCommit = useCallback((): void => {
    setSelected(null);
  }, []);

  const handleToggleViewMode = useCallback((): void => {
    toggleViewMode({ workspaceId });
  }, [toggleViewMode, workspaceId]);

  const handleCollapseAll = useCallback((): void => {
    collapseAllChangesFolders({ workspaceId });
  }, [collapseAllChangesFolders, workspaceId]);

  // The selection carries the active scope so switching All/Uncommitted re-renders
  // the same file against the newly chosen base.
  const selection = useMemo((): DiffSelection | null => {
    if (selected === null) return null;
    return { kind: "diff", filePath: selected.filePath, status: selected.status, scope };
  }, [selected, scope]);

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
      <Flex flexShrink="0" px="3" py="2" direction="column" gap="2">
        <DiffScopePicker
          scope={scope}
          onScopeChange={setScope}
          hasTargetBranch={hasTargetBranch}
          uncommittedCount={uncommittedStatusMap.size}
          allCount={allStatusMap.size}
        />
        <Flex justify="center">
          <CommitButton changesCount={uncommittedStatusMap.size} onCommit={handleCommit} />
        </Flex>
      </Flex>
      <ChangesTreeView
        workspaceId={workspaceId}
        viewMode={viewMode}
        scope={scope}
        onSelectFile={handleSelectFile}
        selectedPath={selected?.filePath ?? null}
        onDiscardFile={isUncommitted ? handleDiscardRequest : undefined}
      />
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
      hasSelection={selection !== null}
      detail={(sidebarToggle) => (
        <DiffViewer
          workspaceId={workspaceId}
          selection={selection}
          treeOptions={treeOptions}
          sidebarToggle={sidebarToggle}
        />
      )}
      emptyDetail={(sidebarToggle) => <EmptyDetail sidebarToggle={sidebarToggle} />}
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

registerPanelComponent("changes", ChangesPanel);
