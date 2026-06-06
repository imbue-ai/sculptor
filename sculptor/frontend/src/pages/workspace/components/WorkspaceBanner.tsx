import { Flex, Skeleton, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { GitBranchIcon, PanelBottom, PanelLeft, PanelLeftOpen, PanelRight } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds, updateWorkspace } from "~/api";
import { useActiveProjectID, useWorkspacePageParams } from "~/common/NavigateUtils";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig";
import { useRepoInfo } from "~/common/state/hooks/useRepoInfo";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch";
import { navSidebarCollapsedAtom } from "~/components/nav/navAtoms.ts";
import { zenModeActiveAtom } from "~/components/panels/atoms.ts";
import {
  BOTTOM_ZONE,
  LEFT_SECTION_ZONE,
  RIGHT_SECTION_ZONE,
  useSectionToggle,
} from "~/components/panels/sectionHooks.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { getBranchName } from "~/pages/home/Utils";

import { useWorkspaceRemoteBranches } from "../hooks/useWorkspaceRemoteBranches";
import { DiffSummary } from "./DiffSummary";
import { PrButton } from "./PrButton";
import { TargetBranchSelector } from "./TargetBranchSelector";
import styles from "./WorkspaceBanner.module.scss";

/**
 * Full-width top bar (REQ-TOPBAR-1..8). Spans the width minus the nav sidebar.
 * Left: sidebar-expand toggle (only when the sidebar is collapsed) + Left-section
 * toggle. Center: branch name, target-branch selector, repo folder icon, diff
 * summary. Right: PR button, terminal toggle, Right-section toggle. No
 * progressive collapse — going full-width relieves the space pressure (REQ-TOPBAR-8).
 */
export const WorkspaceBanner = (): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const { workspaceID } = useWorkspacePageParams();
  const projectID = useActiveProjectID();

  const workspace = useWorkspace(workspaceID);
  const workspaceBranchInfo = useWorkspaceBranch(workspaceID);
  const { repoInfo } = useRepoInfo(projectID ?? "");
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);

  const prStatus = useAtomValue(prStatusAtomFamily(workspaceID));
  const remoteBranches = useWorkspaceRemoteBranches(workspaceID);

  const isNavCollapsed = useAtomValue(navSidebarCollapsedAtom);
  const setNavCollapsed = useSetAtom(navSidebarCollapsedAtom);
  const leftSection = useSectionToggle(LEFT_SECTION_ZONE);
  const rightSection = useSectionToggle(RIGHT_SECTION_ZONE);
  const terminalSection = useSectionToggle(BOTTOM_ZONE);

  const branchName = getBranchName(workspaceBranchInfo?.currentBranch);

  const [isCopied, setIsCopied] = useState(false);
  const [isTargetBranchOpen, setIsTargetBranchOpen] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return (): void => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopyBranch = useCallback((): void => {
    if (!branchName) return;
    navigator.clipboard.writeText(branchName);
    setIsCopied(true);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setIsCopied(false), 1500);
  }, [branchName]);

  const handleTargetBranchChange = useCallback(
    async (branch: string) => {
      try {
        await updateWorkspace({ path: { workspace_id: workspaceID }, body: { targetBranch: branch } });
      } catch (e) {
        console.error("Failed to change target branch:", e);
      }
    },
    [workspaceID],
  );

  const gitProvider: "gitlab" | "github" | null = repoInfo?.isGitlabOrigin
    ? "gitlab"
    : repoInfo?.isGithubOrigin
      ? "github"
      : null;
  const isGitLab = gitProvider === "gitlab";
  const currentTargetBranch = workspace?.targetBranch ?? prDefaultTargetBranch;

  const currentTargetBare = currentTargetBranch.replace(/^[^/]+\//, "");
  const hasMismatch =
    prStatus?.prState === "none" &&
    prStatus.mismatchedPrIid != null &&
    prStatus.mismatchedPrTargetBranch != null &&
    prStatus.mismatchedPrTargetBranch !== currentTargetBare;
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

  const shouldShowTargetBranch = repoInfo?.isGitlabOrigin || repoInfo?.isGithubOrigin;

  const mismatchedFullBranch = hasMismatch
    ? (remoteBranches.find((b) => b === `origin/${prStatus.mismatchedPrTargetBranch}`) ??
      remoteBranches.find((b) => b.endsWith(`/${prStatus.mismatchedPrTargetBranch}`)) ??
      `origin/${prStatus.mismatchedPrTargetBranch}`)
    : null;
  const isMismatched = mismatchedFullBranch != null;

  return (
    <div
      className={styles.banner}
      style={isNavCollapsed ? { paddingLeft: getTitleBarLeftPadding(false) } : undefined}
      data-testid={ElementIds.WORKSPACE_BANNER}
    >
      {/* Left controls (REQ-TOPBAR-2/5) */}
      <Flex align="center" gap="3" flexShrink="0">
        {isNavCollapsed && (
          <TooltipIconButton
            tooltipText="Show sidebar"
            variant="ghost"
            size="1"
            color="gray"
            onClick={() => setNavCollapsed(false)}
            aria-label="Show sidebar"
            data-testid="topbar-sidebar-toggle"
          >
            <PanelLeftOpen size={16} />
          </TooltipIconButton>
        )}
        <TooltipIconButton
          tooltipText={leftSection.isVisible ? "Hide left section" : "Show left section"}
          variant="ghost"
          size="1"
          color="gray"
          className={leftSection.isVisible ? styles.toggleActive : undefined}
          onClick={() => leftSection.toggle()}
          aria-label="Toggle left section"
          data-testid="topbar-left-section-toggle"
        >
          <PanelLeft size={16} />
        </TooltipIconButton>
      </Flex>

      {/* Branch name */}
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
      {shouldShowTargetBranch && (
        <>
          <span className={styles.arrowSeparator}>&rarr;</span>
          <Tooltip content="Target branch" side="bottom" open={isTargetBranchOpen ? false : undefined}>
            <span>
              <TargetBranchSelector
                currentTargetBranch={currentTargetBranch}
                remoteBranches={remoteBranches}
                onBranchChange={handleTargetBranchChange}
                onOpenChange={setIsTargetBranchOpen}
                variant={isMismatched ? "amber" : "default"}
                mismatch={mismatchForSelector}
              />
            </span>
          </Tooltip>
        </>
      )}

      {/* "from" + source branch (non-GitLab/GitHub repos) */}
      {!shouldShowTargetBranch && workspace.sourceBranch && (
        <>
          <Text size="1" className={styles.fromLabel}>
            from
          </Text>
          <Text size="1" className={styles.sourceBranch}>
            {workspace.sourceBranch}
          </Text>
        </>
      )}

      {/* Draggable spacer so the frameless window can be moved by the top bar. */}
      <div className={styles.spacer} data-spacer />

      {/* Right cluster: diff summary right-aligned next to the PR button, then
          the section/terminal toggles, spaced apart (REQ-TOPBAR-2/3). */}
      <Flex align="center" gap="3" flexShrink="0">
        <DiffSummary workspaceId={workspaceID} />
        {shouldShowTargetBranch && (
          <PrButton workspaceId={workspaceID} targetBranch={currentTargetBranch} gitProvider={gitProvider} />
        )}
        <TooltipIconButton
          tooltipText={terminalSection.isVisible ? "Hide bottom section" : "Show bottom section"}
          variant="ghost"
          size="1"
          color="gray"
          className={terminalSection.isVisible ? styles.toggleActive : undefined}
          onClick={() => terminalSection.toggle()}
          aria-label="Toggle bottom section"
          data-testid="topbar-bottom-section-toggle"
        >
          <PanelBottom size={16} />
        </TooltipIconButton>
        <TooltipIconButton
          tooltipText={rightSection.isVisible ? "Hide right section" : "Show right section"}
          variant="ghost"
          size="1"
          color="gray"
          className={rightSection.isVisible ? styles.toggleActive : undefined}
          onClick={() => rightSection.toggle()}
          aria-label="Toggle right section"
          data-testid="topbar-right-section-toggle"
        >
          <PanelRight size={16} />
        </TooltipIconButton>
      </Flex>
    </div>
  );
};
