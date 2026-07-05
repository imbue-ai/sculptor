import { ContextMenu, IconButton } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import type { RecentWorkspaceResponse } from "~/api";
import { ElementIds } from "~/api";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig.ts";
import { useGitProvider } from "~/common/state/hooks/useGitProvider.ts";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";
import { formatRelativeTime } from "~/common/utils/formatRelativeTime.ts";
import { computeWorkspaceDotStatus, EMPTY_WORKSPACE_DOT_STATUS } from "~/common/utils/statusDot.ts";
import { PrButton } from "~/components/prButton/PrButton.tsx";
import { WorkspaceStatusDots } from "~/components/statusDot";

import styles from "./WorkspaceRow.module.scss";

type WorkspaceRowProps = {
  workspace: RecentWorkspaceResponse;
  isFocused: boolean;
  onClick: (e: React.MouseEvent) => void;
  onOpenInNewTab: () => void;
  onDelete: (workspace: RecentWorkspaceResponse) => void;
};

const StatusDot = ({ workspace }: { workspace: WorkspaceRowProps["workspace"] }): ReactElement => {
  const tasks = useAtomValue(tasksArrayAtom);

  const status = useMemo(() => {
    if (!workspace.isOpen) {
      return EMPTY_WORKSPACE_DOT_STATUS;
    }
    const workspaceTasks = (tasks ?? []).filter((task) => task.workspaceId === workspace.objectId);
    return computeWorkspaceDotStatus(workspaceTasks);
  }, [tasks, workspace.objectId, workspace.isOpen]);

  return <WorkspaceStatusDots status={status} size={8} />;
};

export const WorkspaceRow = ({
  workspace,
  isFocused,
  onClick,
  onOpenInNewTab,
  onDelete,
}: WorkspaceRowProps): ReactElement => {
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);
  const branchInfo = useWorkspaceBranch(workspace.objectId);
  const displayBranch = branchInfo?.currentBranch ?? workspace.sourceBranch;
  const gitProvider = useGitProvider(workspace.projectId);

  const rowContent = (
    <div
      className={`${styles.row} ${isFocused ? styles.focused : ""}`}
      data-workspace-row
      data-testid={ElementIds.WORKSPACE_ROW}
      onClick={onClick}
      role="button"
      tabIndex={-1}
    >
      <div className={styles.dot}>
        <StatusDot workspace={workspace} />
      </div>

      <div className={styles.leftGroup}>
        <span className={styles.name}>{workspace.description}</span>
        {displayBranch && (
          <span className={styles.branch} data-testid={ElementIds.WORKSPACE_ROW_BRANCH}>
            {displayBranch}
          </span>
        )}
      </div>

      <div className={styles.rightGroup}>
        {displayBranch && (
          <div className={styles.prButton} onClick={(e) => e.stopPropagation()}>
            <PrButton
              workspaceId={workspace.objectId}
              targetBranch={prDefaultTargetBranch}
              hideCreateAction
              gitProvider={gitProvider}
            />
          </div>
        )}
        <span className={styles.repo}>{workspace.projectName}</span>
        <span className={styles.time}>{formatRelativeTime(workspace.lastActivityAt)}</span>
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.deleteButton}
          data-testid={ElementIds.WORKSPACE_ROW_CONTEXT_MENU_DELETE}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(workspace);
          }}
        >
          <Trash2 size={14} />
        </IconButton>
      </div>
    </div>
  );

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{rowContent}</ContextMenu.Trigger>
      <ContextMenu.Content>
        <ContextMenu.Item onSelect={onOpenInNewTab}>Open in New Tab</ContextMenu.Item>
        <ContextMenu.Item color="red" onSelect={() => onDelete(workspace)}>
          Delete Workspace
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
