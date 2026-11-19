import { CircleHelpIcon, GitBranchIcon, InfoIcon, SparklesIcon, UsersIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { useAgent } from "~/common/state/hooks/useAgent.ts";
import { useProject } from "~/common/state/hooks/useProjects";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";
import { workspaceVcsOf } from "~/common/utils/workspaceVcs.ts";

import { useChatAgent } from "./ChatAgentContext.tsx";
import styles from "./ChatIntro.module.scss";
import { SetupStatusCard } from "./SetupStatusCard";

const DETAIL_ICON_SIZE_PX = 14;

// How the intro's first line opens; the source branch and repository follow.
const ORIGIN_PHRASE: Record<WorkspaceInitializationStrategy, string> = {
  [WorkspaceInitializationStrategy.IN_PLACE]: "Working directly in",
  [WorkspaceInitializationStrategy.CLONE]: "Cloned",
  [WorkspaceInitializationStrategy.WORKTREE]: "Branched off",
  [WorkspaceInitializationStrategy.JJ_WORKSPACE]: "jj workspace on",
};

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
  const isJj = workspace !== null && workspaceVcsOf(workspace) === "jj";
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
          {workspace && ORIGIN_PHRASE[workspace.initializationStrategy]}
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
      {isJj && (
        <div className={styles.detailRow}>
          <InfoIcon size={DETAIL_ICON_SIZE_PX} className={styles.detailIcon} />
          <span>This workspace has no git inside. Agents use jj for version control here.</span>
        </div>
      )}
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
