import { useAtomValue } from "jotai";
import { Check, Plus } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { formatRelativeTime } from "~/common/formatRelativeTime.ts";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { AgentStatusDot } from "~/components/statusDot/StatusDot.tsx";
import { type AgentDotStatus, getAgentDotStatus } from "~/components/statusDot/statusUtils.ts";

import styles from "./AgentSheet.module.scss";
import { useCreateAgent } from "./useCreateAgent.ts";

type AgentSheetProps = {
  isOpen: boolean;
  onClose: () => void;
};

/** Secondary line under an agent's name: the live state when notable, else "last active". */
const subLabel = (status: AgentDotStatus, updatedAt: string): string => {
  switch (status) {
    case "running":
      return "Running";
    case "waiting":
      return "Needs your input";
    case "error":
      return "Error";
    case "unread":
    case "read":
      return formatRelativeTime(updatedAt);
  }
};

/**
 * AgentSheet — the bottom drawer half of the agent switcher (Variant D). Lists
 * every agent in the workspace with a status dot + last-activity line, the
 * active one checked, and a "New agent" row at the bottom. The shell owns the
 * dimmed backdrop and the open state (mirrors WorkspaceDrawer); selecting a row
 * closes the sheet and navigates.
 */
export const AgentSheet = ({ isOpen, onClose }: AgentSheetProps): ReactElement => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const workspace = useWorkspace(workspaceID);
  const tasks = useAtomValue(tasksArrayAtom);
  const { createAgent } = useCreateAgent();

  const agents = useMemo(
    () =>
      (tasks ?? [])
        .filter((t) => t.workspaceId === workspaceID && !t.isDeleted)
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()),
    [tasks, workspaceID],
  );

  const workspaceName = workspace?.description?.trim() || "this workspace";

  return (
    <aside className={`${styles.sheet} ${isOpen ? styles.open : ""}`} aria-hidden={!isOpen}>
      <div className={styles.handle} />
      <div className={styles.title}>Agents in {workspaceName}</div>

      <div className={styles.list}>
        {agents.map((agent) => {
          const isCurrent = agent.id === agentID;
          const dotStatus = getAgentDotStatus(agent.status, agent.lastReadAt, agent.updatedAt);
          return (
            <button
              key={agent.id}
              type="button"
              className={`${styles.row} ${isCurrent ? styles.current : ""}`}
              aria-current={isCurrent}
              onClick={() => {
                onClose();
                navigateToAgent(workspaceID, agent.id);
              }}
            >
              <span className={styles.dot}>
                <AgentStatusDot status={dotStatus} size={8} />
              </span>
              <span className={styles.info}>
                <span className={styles.name}>{agent.titleOrSomethingLikeIt?.trim() || "Agent"}</span>
                <span className={styles.sub}>{subLabel(dotStatus, agent.updatedAt)}</span>
              </span>
              {isCurrent ? <Check size={16} className={styles.check} /> : null}
            </button>
          );
        })}
      </div>

      <div className={styles.separator} />
      <button
        type="button"
        className={styles.newAgent}
        onClick={() => {
          onClose();
          void createAgent();
        }}
      >
        <span className={styles.newIcon}>
          <Plus size={18} />
        </span>
        New agent
      </button>
    </aside>
  );
};
