import { IconButton } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { GitBranch, Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import type { RecentWorkspaceResponse } from "~/api";
import { ElementIds } from "~/api";
import { formatRelativeTime } from "~/common/formatRelativeTime.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig.ts";
import { useGitProvider } from "~/common/state/hooks/useGitProvider.ts";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";
import { computeWorkspaceDotStatus, WorkspaceStatusDots } from "~/components/statusDot";
import { PrButton } from "~/pages/workspace/components/PrButton.tsx";

import styles from "./ClosedWorkspaceRow.module.scss";

type ClosedWorkspaceRowProps = {
  workspace: RecentWorkspaceResponse;
  onReopen: (workspaceId: string) => void;
  onDelete: (workspace: RecentWorkspaceResponse) => void;
};

const formatInitStrategy = (strategy: string): string => {
  if (strategy === "IN_PLACE") return "in-place";
  if (strategy === "WORKTREE") return "worktree";
  return "clone";
};

const StatusDot = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const tasks = useAtomValue(tasksArrayAtom);

  const status = useMemo(() => {
    const workspaceTasks = (tasks ?? []).filter((task) => task.workspaceId === workspaceId);
    return computeWorkspaceDotStatus(workspaceTasks);
  }, [tasks, workspaceId]);

  return <WorkspaceStatusDots status={status} size={8} />;
};

export const ClosedWorkspaceRow = ({ workspace, onReopen, onDelete }: ClosedWorkspaceRowProps): ReactElement => {
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);
  const branchInfo = useWorkspaceBranch(workspace.objectId);
  const displayBranch = branchInfo?.currentBranch ?? workspace.sourceBranch;
  const gitProvider = useGitProvider(workspace.projectId);

  return (
    <div
      className={styles.row}
      data-testid={ElementIds.CLOSED_WORKSPACE_ROW}
      onClick={() => onReopen(workspace.objectId)}
      role="button"
      tabIndex={-1}
    >
      <div className={styles.topLine}>
        <div className={styles.dot}>
          <StatusDot workspaceId={workspace.objectId} />
        </div>
        <span className={styles.name}>{workspace.description}</span>
        {displayBranch && (
          <span className={styles.branchBadge}>
            <GitBranch size={12} />
            <span className={styles.branchName}>{displayBranch}</span>
          </span>
        )}
      </div>

      <div className={styles.bottomLine}>
        <span className={styles.meta}>
          {workspace.projectName} · {workspace.agentCount} {workspace.agentCount === 1 ? "agent" : "agents"},{" "}
          {formatInitStrategy(workspace.initializationStrategy)}
        </span>
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
        <span className={styles.time}>{formatRelativeTime(workspace.lastActivityAt)}</span>
      </div>

      <div className={styles.actions}>
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.deleteButton}
          data-testid={ElementIds.CLOSED_WORKSPACE_DELETE_BUTTON}
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
};
