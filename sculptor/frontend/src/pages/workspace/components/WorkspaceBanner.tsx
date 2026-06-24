import { Skeleton, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { GitBranchIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds, updateWorkspace, WorkspaceInitializationStrategy } from "~/api";
import { useActiveProjectID, useWorkspacePageParams } from "~/common/NavigateUtils";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig";
import { useProject } from "~/common/state/hooks/useProjects";
import { useRepoInfo } from "~/common/state/hooks/useRepoInfo";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch";
import { zenModeActiveAtom } from "~/components/panels/atoms.ts";
import { getBranchName } from "~/pages/home/Utils";
import { pluginWorkspaceWidgetsAtom } from "~/plugins/pluginRegistry.ts";

import { useProgressiveCollapse } from "../hooks/useProgressiveCollapse";
import { useWorkspaceTargetBranches } from "../hooks/useWorkspaceTargetBranches";
import { DiffSummary } from "./DiffSummary";
import { PrButton } from "./PrButton";
import { RepoSegment } from "./RepoSegment";
import { TargetBranchSelector } from "./TargetBranchSelector";
import styles from "./WorkspaceBanner.module.scss";

export const WorkspaceBanner = (): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const { workspaceID } = useWorkspacePageParams();
  const projectID = useActiveProjectID();

  const workspace = useWorkspace(workspaceID);
  const project = useProject(projectID ?? "");
  const workspaceBranchInfo = useWorkspaceBranch(workspaceID);
  const { repoInfo } = useRepoInfo(projectID ?? "");
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);

  const prStatus = useAtomValue(prStatusAtomFamily(workspaceID));
  const targetBranches = useWorkspaceTargetBranches(workspaceID);
  const containerRef = useRef<HTMLDivElement>(null);
  const { hiddenPriorities } = useProgressiveCollapse(containerRef);
  const workspaceWidgets = useAtomValue(pluginWorkspaceWidgetsAtom);

  const branchName = getBranchName(workspaceBranchInfo?.currentBranch);

  const [isCopied, setIsCopied] = useState(false);
  const [isTargetBranchOpen, setIsTargetBranchOpen] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Prevent setState-on-unmount from the "Copied!" timer
  useEffect(() => {
    return (): void => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopyBranch = useCallback((): void => {
    if (!branchName) {
      return;
    }

    navigator.clipboard.writeText(branchName);
    setIsCopied(true);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setIsCopied(false), 1500);
  }, [branchName]);

  const handleTargetBranchChange = useCallback(
    async (branch: string) => {
      try {
        await updateWorkspace({
          path: { workspace_id: workspaceID },
          body: { targetBranch: branch },
        });
      } catch (e) {
        console.error("Failed to change target branch:", e);
      }
    },
    [workspaceID],
  );

  const handleSwitchTarget = useCallback(
    async (newTarget: string) => {
      // MRs live on the origin remote, so prefer "origin/{bare}".
      const fullBranch =
        targetBranches.find((b) => b === `origin/${newTarget}`) ??
        targetBranches.find((b) => b.endsWith(`/${newTarget}`)) ??
        `origin/${newTarget}`;
      try {
        await updateWorkspace({
          path: { workspace_id: workspaceID },
          body: { targetBranch: fullBranch },
        });
      } catch (e) {
        console.error("Failed to switch target branch:", e);
      }
    },
    [workspaceID, targetBranches],
  );

  const gitProvider: "gitlab" | "github" | null = repoInfo?.isGitlabOrigin
    ? "gitlab"
    : repoInfo?.isGithubOrigin
      ? "github"
      : null;
  const isGitLab = gitProvider === "gitlab";
  const currentTargetBranch = workspace?.targetBranch ?? prDefaultTargetBranch;

  // Only show mismatch when the MR's target branch differs from the current
  // workspace target. Compare bare names (strip remote prefix like "origin/")
  // to handle repos that use non-origin remotes.
  const currentTargetBare = currentTargetBranch.replace(/^[^/]+\//, "");
  const hasMismatch =
    prStatus?.prState === "none" &&
    prStatus.mismatchedPrIid != null &&
    prStatus.mismatchedPrTargetBranch != null &&
    prStatus.mismatchedPrTargetBranch !== currentTargetBare;
  // Stable reference so the useMemo inside TargetBranchSelector doesn't
  // thrash on every parent render (it depends on this `mismatch` prop).
  const mismatchForSelector = useMemo(
    () =>
      hasMismatch
        ? {
            targetBranch: prStatus.mismatchedPrTargetBranch!,
            badge: {
              text: `${isGitLab ? "MR" : "PR"} ${isGitLab ? "!" : "#"}${prStatus.mismatchedPrIid}`,
              tooltip: `Open ${isGitLab ? "MR" : "PR"} targets this branch`,
            },
          }
        : null,
    [hasMismatch, prStatus?.mismatchedPrTargetBranch, prStatus?.mismatchedPrIid, isGitLab],
  );

  if (isZenModeActive || !workspace) {
    return null;
  }

  const repoPath = repoInfo?.repoPath || null;
  const strategy = workspace.initializationStrategy;
  // Worktree is the default mode, so it gets no badge — only clone and
  // in-place workspaces are visually marked so users can spot the non-default
  // ones in a mixed list.
  const shouldShowModeBadge = strategy !== WorkspaceInitializationStrategy.WORKTREE;
  // The target-branch selector is host-agnostic — it just edits the
  // workspace's merge target — so it is shown for every repo regardless of
  // remote host (SCU-1526). PR/MR creation, on the other hand, requires the
  // GitHub or GitLab CLI, so the PR button stays gated on the git provider.
  const canCreatePr = gitProvider !== null;

  // Resolve the full remote branch name for the mismatch target (e.g. "upstream/main")
  const mismatchedFullBranch = hasMismatch
    ? (targetBranches.find((b) => b === `origin/${prStatus.mismatchedPrTargetBranch}`) ??
      targetBranches.find((b) => b.endsWith(`/${prStatus.mismatchedPrTargetBranch}`)) ??
      `origin/${prStatus.mismatchedPrTargetBranch}`)
    : null;
  const mismatchInfo = hasMismatch
    ? {
        mismatchedPrIid: prStatus.mismatchedPrIid!,
        fullBranch: mismatchedFullBranch!,
      }
    : null;
  const isMismatched = mismatchInfo != null;

  return (
    <div ref={containerRef} className={styles.banner} data-testid={ElementIds.WORKSPACE_BANNER}>
      {!hiddenPriorities.has(2) &&
        (repoPath ? (
          <div data-collapse-priority="2">
            <RepoSegment
              sourcePath={repoPath}
              environmentPath={workspace.environmentId ?? null}
              strategy={strategy}
              shouldShowModeBadge={shouldShowModeBadge}
              projectName={project?.name ?? repoPath.split("/").pop() ?? repoPath}
            />
          </div>
        ) : (
          <Skeleton width="120px" height="16px" />
        ))}

      <span className={styles.chevronSeparator}>&rsaquo;</span>

      {branchName ? (
        <Tooltip
          content={isCopied ? "Copied!" : "Workspace branch — click to copy"}
          open={isCopied || undefined}
          side="bottom"
        >
          <span className={styles.branchSection} onClick={handleCopyBranch} data-testid={ElementIds.BRANCH_NAME}>
            <GitBranchIcon size={12} className={styles.branchIcon} />
            <span className={styles.branchName}>{branchName}</span>
          </span>
        </Tooltip>
      ) : (
        <Skeleton width="160px" height="16px" />
      )}

      {/* Arrow + target branch */}
      <span className={styles.arrowSeparator}>&rarr;</span>
      <Tooltip
        content={
          isMismatched
            ? `${isGitLab ? "MR" : "PR"} ${isGitLab ? "!" : "#"}${mismatchInfo.mismatchedPrIid} targets ${mismatchInfo.fullBranch} — retarget?`
            : "Target branch"
        }
        side="bottom"
        open={isTargetBranchOpen ? false : undefined}
      >
        <span>
          <TargetBranchSelector
            currentTargetBranch={currentTargetBranch}
            targetBranches={targetBranches}
            onBranchChange={handleTargetBranchChange}
            onOpenChange={setIsTargetBranchOpen}
            variant={isMismatched ? "amber" : "default"}
            mismatch={mismatchForSelector}
          />
        </span>
      </Tooltip>

      <div className={styles.spacer} data-spacer />

      {!hiddenPriorities.has(1) && (
        <div data-collapse-priority="1">
          <DiffSummary workspaceId={workspaceID} />
        </div>
      )}

      {/* Plugin-contributed workspace widgets (e.g. the Linear ticket
          shortcut). Rendered as direct banner children so they share the PR
          button's progressive-collapse row: each opts in with its own
          data-collapse-priority and is hidden when that priority collapses. */}
      {workspaceWidgets.map(({ id, component: Widget, collapsePriority }) =>
        hiddenPriorities.has(collapsePriority) ? null : (
          <div key={id} data-collapse-priority={collapsePriority}>
            <Widget />
          </div>
        ),
      )}

      {/* PR button */}
      {!hiddenPriorities.has(4) && canCreatePr && (
        <div data-collapse-priority="4">
          <PrButton
            workspaceId={workspaceID}
            targetBranch={currentTargetBranch}
            gitProvider={gitProvider}
            onSwitchTarget={handleSwitchTarget}
          />
        </div>
      )}
    </div>
  );
};
