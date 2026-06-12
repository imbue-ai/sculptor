import { Flex } from "@radix-ui/themes";
import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import { ElementIds } from "~/api";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { DiffScopePicker } from "~/pages/workspace/components/diffPanel/DiffScopePicker.tsx";

import { DiscardDialog } from "../changesPanel/DiscardDialog.tsx";
import { useDiscardFile } from "../changesPanel/useDiscardFile.ts";
import { changesScopeAtomFamily } from "./atoms.ts";
import styles from "./ChangesTabContent.module.scss";
import { ChangesTreeView } from "./ChangesTreeView.tsx";
import { CommitButton } from "./CommitButton.tsx";
import { useFileStatusMap } from "./hooks.ts";
import type { ViewMode } from "./types.ts";

type ChangesTabContentProps = {
  workspaceId: string;
  viewMode: ViewMode;
};

export const ChangesTabContent = ({ workspaceId, viewMode }: ChangesTabContentProps): ReactElement => {
  const workspace = useWorkspace(workspaceId);
  const hasTargetBranch = workspace?.targetBranch != null;
  const [scope, setScope] = useAtom(changesScopeAtomFamily(workspaceId));
  const uncommittedStatusMap = useFileStatusMap(workspaceId, "uncommitted");
  const allStatusMap = useFileStatusMap(workspaceId, "vs-target-branch");
  const { discardFile } = useDiscardFile(workspaceId);

  const [discardTarget, setDiscardTarget] = useState<string | null>(null);

  const handleDiscardRequest = useCallback((filePath: string): void => {
    setDiscardTarget(filePath);
  }, []);

  const handleDiscardConfirm = useCallback((): void => {
    if (discardTarget) {
      discardFile(discardTarget);
      setDiscardTarget(null);
    }
  }, [discardTarget, discardFile]);

  const isUncommitted = scope === "uncommitted";

  return (
    <Flex direction="column" flexGrow="1" height="100%" overflow="hidden" data-testid={ElementIds.CHANGES_PANEL}>
      <Flex flexShrink="0" px="2" py="1">
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
        onDiscardFile={isUncommitted ? handleDiscardRequest : undefined}
      />
      <Flex flexShrink="0" p="2" className={styles.commitFooter}>
        <CommitButton changesCount={uncommittedStatusMap.size} fullWidth />
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
};
