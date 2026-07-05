import { CircleHelpIcon, GitBranchIcon, SparklesIcon, UsersIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { useAgent } from "~/common/state/hooks/useAgentHelpers";
import { useProject } from "~/common/state/hooks/useProjects";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";

import { useChatAgent } from "./ChatAgentContext.tsx";
import styles from "./ChatIntro.module.scss";
import { SetupStatusCard } from "./SetupStatusCard";

const DETAIL_ICON_SIZE_PX = 14;

const formatTimestamp = (isoString: string): string => {
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

export const ChatIntro = (): ReactElement => {
  // The owning chat panel's agent + workspace, so the intro names the agent
  // this panel renders rather than the route's.
  const { workspaceId: workspaceID, agentId } = useChatAgent();

  const workspace = useWorkspace(workspaceID);
  const project = useProject(workspace?.projectId ?? "");
  const agent = useAgent(agentId);

  const isInPlace = workspace?.initializationStrategy === WorkspaceInitializationStrategy.IN_PLACE;
  const isWorktree = workspace?.initializationStrategy === WorkspaceInitializationStrategy.WORKTREE;
  const projectName = project?.name ?? "";
  const sourceBranch = workspace?.sourceBranch;
  const createdAt = workspace?.createdAt;
  const workspaceName = workspace?.description ?? "Untitled workspace";
  const agentName = agent?.titleOrSomethingLikeIt ?? "Agent";

  return (
    <div className={styles.wrapper} data-testid={ElementIds.ALPHA_CHAT_INTRO}>
      <div className={styles.detailRow}>
        <GitBranchIcon size={DETAIL_ICON_SIZE_PX} className={styles.detailIcon} />
        <span>
          {isInPlace ? "Working directly in" : isWorktree ? "Branched off" : "Cloned"}
          {!isInPlace && sourceBranch && (
            <>
              {" "}
              <span className={styles.highlight}>{sourceBranch}</span>
            </>
          )}
          {!isInPlace && projectName && <> from</>}
          {projectName && (
            <>
              {" "}
              <span className={styles.highlight}>{projectName}</span>
            </>
          )}
          {createdAt && <> at {formatTimestamp(createdAt)}</>}
        </span>
      </div>
      <div className={styles.detailRow}>
        <SparklesIcon size={DETAIL_ICON_SIZE_PX} className={styles.detailIcon} />
        <span>
          This is agent <span className={styles.highlight}>{agentName}</span> in workspace{" "}
          <span className={styles.highlight}>{workspaceName}</span>
        </span>
      </div>
      <div className={styles.detailRow}>
        <UsersIcon size={DETAIL_ICON_SIZE_PX} className={styles.detailIcon} />
        <span>
          All agents in this workspace share the same code and can see each other&apos;s changes, but are isolated from
          other workspaces
        </span>
      </div>
      <div className={styles.detailRow}>
        <CircleHelpIcon size={DETAIL_ICON_SIZE_PX} className={styles.detailIcon} />
        <span>
          Type <span className={styles.highlight}>/sculptor:help</span> to ask a question
        </span>
      </div>
      <SetupStatusCard workspaceId={workspaceID} />
    </div>
  );
};
