import { ContextMenu, IconButton, Skeleton } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import type { RecentWorkspaceResponse } from "~/api";
import { ElementIds } from "~/api";
import { formatRelativeTime } from "~/common/formatRelativeTime.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig.ts";
import { useGitProvider } from "~/common/state/hooks/useGitProvider.ts";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";
import { computeWorkspaceDotStatus, EMPTY_WORKSPACE_DOT_STATUS, WorkspaceStatusDots } from "~/components/statusDot";
import { PrButton } from "~/pages/workspace/components/PrButton.tsx";

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
  // The workspace's own working branch arrives via the WebSocket stream (the
  // branch poller publishes it for every workspace with a worktree); until it
  // does, `branchInfo` is null. Don't fall back to `workspace.sourceBranch` —
  // that's the DIFFERENT base branch the workspace was forked from, so the row
  // would flash the wrong branch before the real one lands. Show a skeleton until
  // `currentBranch` is known instead.
  const currentBranch = branchInfo?.currentBranch;
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
        {currentBranch !== undefined ? (
          <span className={styles.branch} data-testid={ElementIds.WORKSPACE_ROW_BRANCH}>
            {currentBranch}
          </span>
        ) : (
          // Branch not yet streamed in — a delayed-reveal skeleton so a fast load
          // shows nothing then the real branch, and never the wrong one.
          <span className={styles.branchSkeletonWrap} data-testid={ElementIds.WORKSPACE_ROW_BRANCH_SKELETON}>
            <Skeleton className={styles.branchSkeleton} />
          </span>
        )}
      </div>

      <div className={styles.rightGroup}>
        {currentBranch !== undefined && (
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
