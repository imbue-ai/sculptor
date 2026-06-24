import { Skeleton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { FolderIcon, GitBranchIcon } from "lucide-react";
import { type CSSProperties, type ReactElement, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CodingAgentTaskView, PrStatusInfo } from "~/api";
import { ElementIds, WorkspacePeekAgentStatus } from "~/api";
import { useTimedLatch } from "~/common/Hooks.ts";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus";
import { tasksArrayAtom } from "~/common/state/atoms/tasks";
import { useGitProvider } from "~/common/state/hooks/useGitProvider";
import { useProject, useProjects } from "~/common/state/hooks/useProjects";
import { useThemeDangerColor, useThemeSuccessColor, useThemeWarningColor } from "~/common/state/hooks/useThemeBuilder";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch";
import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff";
import { jumpToSectionAtom, openPanelAtom } from "~/components/sections/sectionActions.ts";

import { changesScopeAtomFamily } from "../panels/fileBrowser/atoms";
import { parseDiffStats } from "../utils/parseDiffStats";
import { AgentStatusDot } from "./AgentStatusDot";
import type { GitProvider } from "./PrButton";
import styles from "./WorkspacePeekPopover.module.scss";

type WorkspacePeekPopoverProps = {
  workspaceId: string;
  onNavigate: (workspaceId: string, agentId?: string) => void;
  onDismiss?: () => void;
};

const VISIBLE_AGENT_COUNT = 5;

// Holds the diff-stats shimmer on long enough to complete one full pulse cycle
// even when the underlying fetch returns in under a frame.
const SHIMMER_MIN_HOLD_MS = 1500;

// How long the branch name shows "Copied!" after the user copies it.
const COPY_FEEDBACK_DURATION_MS = 1500;

// Only collapse the agent list when doing so hides at least this many agents —
// hiding a single agent behind a "+N more" control isn't worth the extra click.
const MIN_HIDDEN_AGENTS_TO_COLLAPSE = 2;

const STATUS_SORT_ORDER: Record<WorkspacePeekAgentStatus, number> = {
  [WorkspacePeekAgentStatus.ERROR]: 0,
  [WorkspacePeekAgentStatus.WAITING]: 1,
  [WorkspacePeekAgentStatus.WORKING]: 2,
  [WorkspacePeekAgentStatus.COMPLETED]: 3,
  [WorkspacePeekAgentStatus.IDLE]: 4,
};

const BANNER_ICONS: Partial<Record<WorkspacePeekAgentStatus, string>> = {
  [WorkspacePeekAgentStatus.ERROR]: "✕",
  [WorkspacePeekAgentStatus.WAITING]: "⚠",
  [WorkspacePeekAgentStatus.COMPLETED]: "✓",
};

function computeWorkspaceStatus(agents: ReadonlyArray<CodingAgentTaskView>): WorkspacePeekAgentStatus {
  if (agents.some((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.ERROR))
    return WorkspacePeekAgentStatus.ERROR;
  if (agents.some((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.WAITING))
    return WorkspacePeekAgentStatus.WAITING;
  if (agents.some((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.WORKING))
    return WorkspacePeekAgentStatus.WORKING;
  if (agents.length > 0 && agents.every((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.COMPLETED)) {
    return WorkspacePeekAgentStatus.COMPLETED;
  }
  return WorkspacePeekAgentStatus.IDLE;
}

function formatTimeAgo(dateStr: string): string {
  const ms = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes !== 1 ? "s" : ""} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours !== 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days !== 1 ? "s" : ""} ago`;
}

function getSummary(status: WorkspacePeekAgentStatus, agents: ReadonlyArray<CodingAgentTaskView>): string {
  const totalCompleted = agents.reduce((sum, a) => sum + a.taskCompleted, 0);
  const totalTodos = agents.reduce((sum, a) => sum + a.taskTotal, 0);
  const firstWorking = agents.find((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.WORKING);
  const activity = firstWorking?.currentActivity;

  switch (status) {
    case WorkspacePeekAgentStatus.WORKING:
      if (totalTodos === 0) return activity ? `Just started — ${activity}` : "Just started";
      return `${totalCompleted} of ${totalTodos} tasks done${activity ? ` — ${activity}` : ""}`;
    case WorkspacePeekAgentStatus.WAITING:
      return totalTodos > 0 ? `${totalCompleted} of ${totalTodos} tasks done — waiting for input` : "Waiting for input";
    case WorkspacePeekAgentStatus.ERROR:
      return totalTodos > 0 ? `${totalCompleted} of ${totalTodos} tasks done — error encountered` : "Error encountered";
    case WorkspacePeekAgentStatus.COMPLETED:
      return `All ${totalTodos} tasks completed successfully. Ready for review.`;
    case WorkspacePeekAgentStatus.IDLE: {
      if (agents.length === 0) return "No activity yet";
      const mostRecent = agents.reduce((latest, a) => (a.updatedAt > latest.updatedAt ? a : latest));
      return `No active agents. Last activity ${formatTimeAgo(mostRecent.updatedAt)}.`;
    }
  }
}

function getPeekPipelineDotClass(status: PrStatusInfo["pipelineStatus"]): string {
  switch (status) {
    case "running":
      return styles.dotRunning;
    case "passed":
      return styles.dotPassed;
    case "failed":
      return styles.dotFailed;
    case null:
    case undefined:
    default:
      return styles.dotMuted;
  }
}

function getPeekReviewDotClass(prStatus: PrStatusInfo): string {
  if (!prStatus.approvals || prStatus.approvals.length === 0) return styles.dotMuted;
  if (prStatus.approvals.every((a) => a.approved)) return styles.dotApproved;
  return styles.dotPending;
}

const AgentRow = ({
  agent,
  onClick,
  attentionStatus,
}: {
  agent: CodingAgentTaskView;
  onClick: () => void;
  attentionStatus: WorkspacePeekAgentStatus | null;
}): ReactElement => {
  const status = agent.workspacePeekStatus;
  let description: string;

  switch (status) {
    case WorkspacePeekAgentStatus.WAITING:
      description = agent.waitingDetail ?? "Waiting for input";
      break;
    case WorkspacePeekAgentStatus.ERROR:
      description = agent.errorDetail ?? "Error encountered";
      break;
    case WorkspacePeekAgentStatus.COMPLETED:
      description = agent.taskTotal > 0 ? `${agent.taskCompleted}/${agent.taskTotal} done` : "Done";
      break;
    case WorkspacePeekAgentStatus.WORKING:
      description = agent.currentActivity ?? "Working...";
      break;
    case WorkspacePeekAgentStatus.IDLE: {
      if (agent.taskTotal > 0) {
        description = `Completed ${agent.taskCompleted} of ${agent.taskTotal} tasks · ${formatTimeAgo(agent.updatedAt)}`;
      } else {
        const activity = agent.lastActivity ?? agent.currentActivity;
        description = activity ? `${activity} · ${formatTimeAgo(agent.updatedAt)}` : formatTimeAgo(agent.updatedAt);
      }
      break;
    }
  }

  const hasTaskLink =
    status !== WorkspacePeekAgentStatus.WAITING &&
    status !== WorkspacePeekAgentStatus.ERROR &&
    agent.currentTaskSubject != null;

  return (
    <div
      className={styles.agentRow}
      data-testid={ElementIds.WORKSPACE_PEEK_AGENT_ROW}
      data-attention={attentionStatus ?? undefined}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
    >
      <div className={styles.agentNameLine}>
        <AgentStatusDot taskId={agent.id} workspaceCreatedAt={undefined} />
        <span className={styles.agentName}>{agent.title ?? "Agent"}</span>
      </div>
      <div className={styles.agentDescription} data-status={status}>
        {hasTaskLink ? agent.currentTaskSubject : description}
      </div>
      {hasTaskLink && <div className={styles.agentTask}>↳ {description}</div>}
    </div>
  );
};

const PeekBanner = ({
  status,
  message,
  onClick,
}: {
  status: WorkspacePeekAgentStatus;
  message: string;
  onClick: () => void;
}): ReactElement => (
  <div
    className={styles.banner}
    data-status={status}
    data-testid={ElementIds.WORKSPACE_PEEK_BANNER}
    onClick={onClick}
    role="button"
    tabIndex={0}
    onKeyDown={(e) => e.key === "Enter" && onClick()}
  >
    <span>{BANNER_ICONS[status]}</span>
    <span>{message}</span>
  </div>
);

const PeekHeader = ({
  workspaceName,
  prStatus,
  gitProvider,
  summary,
  workspaceStatus,
  onNavigate,
}: {
  workspaceName: string;
  prStatus: PrStatusInfo | null;
  gitProvider: GitProvider;
  summary: string;
  workspaceStatus: WorkspacePeekAgentStatus;
  onNavigate: () => void;
}): ReactElement => (
  <div
    className={styles.header}
    data-testid={ElementIds.WORKSPACE_PEEK_HEADER}
    onClick={onNavigate}
    role="button"
    tabIndex={0}
    onKeyDown={(e) => e.key === "Enter" && onNavigate()}
  >
    <div className={styles.nameRow}>
      <span className={styles.wsName}>{workspaceName}</span>
    </div>
    {prStatus != null && prStatus.prState !== "none" && (
      <div className={styles.mrRow}>
        <a
          className={styles.mrPill}
          href={prStatus.prWebUrl ?? "#"}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
        >
          {gitProvider === "github" ? "PR" : "MR"} {gitProvider === "github" ? "#" : "!"}
          {prStatus.prIid}
          {prStatus.prState === "open" && (
            <>
              <span className={`${styles.statusDot} ${getPeekPipelineDotClass(prStatus.pipelineStatus)}`} />
              <span className={`${styles.statusDot} ${getPeekReviewDotClass(prStatus)}`} />
            </>
          )}
        </a>
        {prStatus.prState === "merged" && <span className={styles.mergedBadge}>merged</span>}
        {prStatus.prState === "closed" && <span className={styles.mergedBadge}>closed</span>}
        {prStatus.prTitle != null && <span className={styles.mrTitle}>{prStatus.prTitle}</span>}
      </div>
    )}
    <div className={styles.summary} data-status={workspaceStatus}>
      {summary}
    </div>
  </div>
);

const PeekFooter = ({
  projectName,
  branchInfo,
  diffStats,
  isShimmering,
  isCopied,
  onCopyBranch,
  onDiffClick,
}: {
  projectName: string | null;
  branchInfo: { currentBranch: string } | null;
  diffStats: { additions: number; deletions: number };
  isShimmering: boolean;
  isCopied: boolean;
  onCopyBranch: () => void;
  onDiffClick: () => void;
}): ReactElement => {
  const hasChanges = diffStats.additions > 0 || diffStats.deletions > 0;
  return (
    <div className={styles.footer} data-testid={ElementIds.WORKSPACE_PEEK_FOOTER}>
      {projectName != null && (
        <div className={styles.repoName}>
          <FolderIcon className={styles.repoIcon} />
          <span className={styles.repoNameText}>{projectName}</span>
        </div>
      )}
      <div className={styles.footerRow}>
        {branchInfo != null ? (
          <>
            <div
              className={styles.branchInfo}
              onClick={onCopyBranch}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onCopyBranch()}
            >
              <GitBranchIcon className={styles.branchIcon} />
              <span className={styles.branchName}>{isCopied ? "Copied!" : branchInfo.currentBranch}</span>
            </div>
            <span className={styles.spacer} />
            {hasChanges ? (
              <div
                className={isShimmering ? `${styles.diffStats} ${styles.diffStatsRefreshing}` : styles.diffStats}
                onClick={onDiffClick}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onDiffClick()}
              >
                <span className={styles.diffAdditions}>+{diffStats.additions}</span>
                <span className={styles.diffDeletions}>−{diffStats.deletions}</span>
              </div>
            ) : (
              <span className={styles.noDiff}>no changes</span>
            )}
          </>
        ) : (
          <>
            <Skeleton width="80px" height="12px" />
            <span className={styles.spacer} />
            <Skeleton width="50px" height="12px" />
          </>
        )}
      </div>
    </div>
  );
};

export const WorkspacePeekPopover = ({
  workspaceId,
  onNavigate,
  onDismiss,
}: WorkspacePeekPopoverProps): ReactElement => {
  const workspace = useWorkspace(workspaceId);
  const project = useProject(workspace?.projectId ?? "");
  const projects = useProjects();
  const allTasks = useAtomValue(tasksArrayAtom);
  const branchInfo = useWorkspaceBranch(workspaceId);
  const prStatus = useAtomValue(prStatusAtomFamily(workspaceId));
  const gitProvider = useGitProvider(workspace?.projectId ?? "");
  const { data: diff, isFetching } = useWorkspaceDiff(workspaceId);
  const isShimmering = useTimedLatch(isFetching, SHIMMER_MIN_HOLD_MS);
  const diffStats = useMemo(() => parseDiffStats(diff?.targetBranchDiff), [diff?.targetBranchDiff]);
  const openPanel = useSetAtom(openPanelAtom);
  const jumpToSection = useSetAtom(jumpToSectionAtom);
  const setChangesScope = useSetAtom(changesScopeAtomFamily(workspaceId));
  const [isExpanded, setIsExpanded] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [shouldShowFade, setShouldShowFade] = useState(false);
  const agentListRef = useRef<HTMLDivElement>(null);

  const dangerColor = useThemeDangerColor();
  const warningColor = useThemeWarningColor();
  const successColor = useThemeSuccessColor();

  const semanticColorVars = useMemo(
    () =>
      ({
        "--color-danger": `var(--${dangerColor}-9)`,
        "--color-danger-a2": `var(--${dangerColor}-a2)`,
        "--color-danger-a3": `var(--${dangerColor}-a3)`,
        "--color-danger-text": `var(--${dangerColor}-11)`,
        "--color-danger-contrast": `var(--${dangerColor}-contrast)`,
        "--color-warning": `var(--${warningColor}-9)`,
        "--color-warning-a2": `var(--${warningColor}-a2)`,
        "--color-warning-a3": `var(--${warningColor}-a3)`,
        "--color-warning-text": `var(--${warningColor}-12)`,
        "--color-warning-contrast": `var(--${warningColor}-contrast)`,
        "--color-success": `var(--${successColor}-9)`,
        "--color-success-a2": `var(--${successColor}-a2)`,
        "--color-success-a3": `var(--${successColor}-a3)`,
        "--color-success-text": `var(--${successColor}-11)`,
        "--color-success-contrast": `var(--${successColor}-contrast)`,
      }) as CSSProperties,
    [dangerColor, warningColor, successColor],
  );

  const agents = useMemo(
    () => (allTasks ?? []).filter((t) => t.workspaceId === workspaceId && !t.isDeleted),
    [allTasks, workspaceId],
  );

  const sortedAgents = useMemo(
    () =>
      [...agents].sort((a, b) => {
        const statusDiff = STATUS_SORT_ORDER[a.workspacePeekStatus] - STATUS_SORT_ORDER[b.workspacePeekStatus];
        if (statusDiff !== 0) return statusDiff;
        // Within the same status group, show most recently updated first
        return b.updatedAt.localeCompare(a.updatedAt);
      }),
    [agents],
  );

  const workspaceStatus = useMemo(() => computeWorkspaceStatus(agents), [agents]);
  const summary = useMemo(() => getSummary(workspaceStatus, agents), [workspaceStatus, agents]);
  const bannerInfo = useMemo(() => {
    const errorAgents = sortedAgents.filter((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.ERROR);
    const waitingAgents = sortedAgents.filter((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.WAITING);

    if (errorAgents.length > 0) {
      const names = errorAgents.map((a) => a.title ?? "Agent").join(", ");
      const verb = errorAgents.length === 1 ? "encountered an error" : "encountered errors";
      return { message: `${names} ${verb}`, status: WorkspacePeekAgentStatus.ERROR };
    }

    if (waitingAgents.length > 0) {
      const names = waitingAgents.map((a) => a.title ?? "Agent").join(", ");
      const hasApproval = waitingAgents.some((a) => {
        const detail = a.waitingDetail?.toLowerCase() ?? "";
        return detail.includes("plan") || detail.includes("approval");
      });
      const suffix = hasApproval ? "approval" : "input";
      const verb = waitingAgents.length === 1 ? "needs" : "need";
      return { message: `${names} ${verb} your ${suffix}`, status: WorkspacePeekAgentStatus.WAITING };
    }

    const isAllCompleted =
      agents.length > 0 && agents.every((a) => a.workspacePeekStatus === WorkspacePeekAgentStatus.COMPLETED);
    if (isAllCompleted) {
      return { message: "All tasks completed", status: WorkspacePeekAgentStatus.COMPLETED };
    }

    return null;
  }, [agents, sortedAgents]);

  const handleBannerClick = useCallback(() => onNavigate(workspaceId), [onNavigate, workspaceId]);

  useEffect(() => {
    return (): void => clearTimeout(copyTimerRef.current);
  }, []);

  const handleCopyBranch = useCallback(() => {
    if (!branchInfo?.currentBranch) return;
    navigator.clipboard.writeText(branchInfo.currentBranch);
    setIsCopied(true);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_FEEDBACK_DURATION_MS);
  }, [branchInfo?.currentBranch]);

  const handleDiffClick = useCallback(() => {
    onNavigate(workspaceId);
    // Surface the Changes panel in the left section (vs the target branch),
    // mirroring DiffSummary's reveal in the new section shell.
    openPanel({ panelId: "changes", in: "left" });
    jumpToSection({ subSection: "left" });
    setChangesScope("vs-target-branch");
    onDismiss?.();
  }, [onNavigate, workspaceId, openPanel, jumpToSection, setChangesScope, onDismiss]);

  const hiddenCount = sortedAgents.length - VISIBLE_AGENT_COUNT;
  const canCollapse = hiddenCount >= MIN_HIDDEN_AGENTS_TO_COLLAPSE;
  const visibleAgents = isExpanded || !canCollapse ? sortedAgents : sortedAgents.slice(0, VISIBLE_AGENT_COUNT);
  const workspaceName = workspace?.description ?? "Workspace";

  const updateFade = useCallback((): void => {
    const el = agentListRef.current;
    if (!el) return;
    setShouldShowFade(el.scrollHeight - el.scrollTop - el.clientHeight > 1);
  }, []);

  // Recompute fade after layout — scrollHeight is only valid once rows have rendered.
  useEffect(() => {
    updateFade();
  }, [visibleAgents.length, updateFade]);

  const bannerStatus = bannerInfo?.status ?? null;
  const showProjectName = projects.length > 1 ? (project?.name ?? null) : null;

  return (
    <div className={styles.popover} data-testid={ElementIds.WORKSPACE_PEEK_POPOVER} style={semanticColorVars}>
      {bannerInfo != null && (
        <PeekBanner status={bannerInfo.status} message={bannerInfo.message} onClick={handleBannerClick} />
      )}

      <PeekHeader
        workspaceName={workspaceName}
        prStatus={prStatus}
        gitProvider={gitProvider}
        summary={summary}
        workspaceStatus={workspaceStatus}
        onNavigate={() => onNavigate(workspaceId)}
      />

      <div className={styles.agentList} ref={agentListRef} onScroll={updateFade}>
        {visibleAgents.map((agent) => (
          <AgentRow
            key={agent.id}
            agent={agent}
            onClick={() => onNavigate(workspaceId, agent.id)}
            attentionStatus={agent.workspacePeekStatus === bannerStatus ? bannerStatus : null}
          />
        ))}
        {canCollapse && !isExpanded && (
          <div
            className={styles.expandControl}
            data-testid={ElementIds.WORKSPACE_PEEK_EXPAND}
            onClick={() => setIsExpanded(true)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && setIsExpanded(true)}
          >
            + {hiddenCount} more agents
          </div>
        )}
        {shouldShowFade && <div className={styles.agentListFade} />}
      </div>

      <PeekFooter
        projectName={showProjectName}
        branchInfo={branchInfo}
        diffStats={diffStats}
        isShimmering={isShimmering}
        isCopied={isCopied}
        onCopyBranch={handleCopyBranch}
        onDiffClick={handleDiffClick}
      />
    </div>
  );
};
