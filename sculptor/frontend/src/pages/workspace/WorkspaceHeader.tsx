import { Flex, Skeleton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { GitBranchIcon, PanelBottom, PanelLeft, PanelRight } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds, updateWorkspace } from "~/api";
import { useActiveProjectID, useWorkspacePageParams } from "~/common/NavigateUtils";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig";
import { useRepoInfo } from "~/common/state/hooks/useRepoInfo";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch";
import { sidebarCollapsedAtom } from "~/components/layout/sidebarAtoms.ts";
import { toggleSectionAtom } from "~/components/sections/sectionActions.ts";
import { isSectionExpandedAtom } from "~/components/sections/sectionAtoms.ts";
import type { SectionId } from "~/components/sections/sectionTypes.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { getBranchName } from "~/pages/home/Utils";

import { DiffSummary } from "./components/DiffSummary";
import { PrButton } from "./components/PrButton";
import { TargetBranchSelector } from "./components/TargetBranchSelector";
import { useWorkspaceTargetBranches } from "./hooks/useWorkspaceTargetBranches";
import styles from "./WorkspaceHeader.module.scss";

type SectionToggleProps = {
  section: SectionId;
  icon: ReactElement;
  label: string;
  testId: string;
};

// One collapse/expand toggle for a side/bottom section. Reads the per-section
// expanded slice and writes through the shared toggleSectionAtom so the header,
// keyboard shortcuts, and drag-to-expand (via the collapsed-section drop rail) all
// funnel through one reducer.
const SectionToggle = ({ section, icon, label, testId }: SectionToggleProps): ReactElement => {
  const isExpanded = useAtomValue(isSectionExpandedAtom(section));
  const toggleSection = useSetAtom(toggleSectionAtom);

  return (
    <TooltipIconButton
      tooltipText={isExpanded ? `Hide ${label}` : `Show ${label}`}
      variant="ghost"
      size="1"
      color="gray"
      className={isExpanded ? styles.toggleActive : undefined}
      onClick={() => toggleSection({ section })}
      aria-label={`Toggle ${label}`}
      data-testid={testId}
    >
      {icon}
    </TooltipIconButton>
  );
};

/**
 * The simplified workspace header above the section grid (component_hierarchy.md →
 * "The workspace layout shell"). Left cluster: the left-section toggle. Center:
 * the branch pill + target-branch selector. A draggable spacer lets the frameless
 * window be moved by the header. Right cluster: the re-homed diff summary + PR
 * button, then the bottom- and right-section toggles. Hidden by WorkspaceLayoutShell
 * when a section is maximized.
 */
export const WorkspaceHeader = (): ReactElement | null => {
  // External atoms
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);

  // External hooks
  const { workspaceID } = useWorkspacePageParams();
  const projectID = useActiveProjectID();
  const workspace = useWorkspace(workspaceID);
  const workspaceBranchInfo = useWorkspaceBranch(workspaceID);
  const { repoInfo } = useRepoInfo(projectID ?? "");
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);
  const prStatus = useAtomValue(prStatusAtomFamily(workspaceID));
  const targetBranches = useWorkspaceTargetBranches(workspaceID);

  // Internal state
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [isTargetBranchOpen, setIsTargetBranchOpen] = useState<boolean>(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const branchName = getBranchName(workspaceBranchInfo?.currentBranch);

  // Effects
  // Prevent setState-on-unmount from the "Copied!" timer.
  useEffect(() => {
    return (): void => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  // Functions and callbacks
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
    async (branch: string): Promise<void> => {
      try {
        await updateWorkspace({ path: { workspace_id: workspaceID }, body: { targetBranch: branch } });
      } catch (e) {
        console.error("Failed to change target branch:", e);
      }
    },
    [workspaceID],
  );

  const handleSwitchTarget = useCallback(
    async (newTarget: string): Promise<void> => {
      // MRs live on the origin remote, so prefer "origin/{bare}".
      const fullBranch =
        targetBranches.find((b) => b === `origin/${newTarget}`) ??
        targetBranches.find((b) => b.endsWith(`/${newTarget}`)) ??
        `origin/${newTarget}`;
      try {
        await updateWorkspace({ path: { workspace_id: workspaceID }, body: { targetBranch: fullBranch } });
      } catch (e) {
        console.error("Failed to switch target branch:", e);
      }
    },
    [workspaceID, targetBranches],
  );

  // JSX and rendering logic
  const gitProvider: "gitlab" | "github" | null = repoInfo?.isGitlabOrigin
    ? "gitlab"
    : repoInfo?.isGithubOrigin
      ? "github"
      : null;
  const isGitLab = gitProvider === "gitlab";
  const currentTargetBranch = workspace?.targetBranch ?? prDefaultTargetBranch;

  // Only show mismatch when the MR's target branch differs from the current
  // workspace target. Compare bare names (strip remote prefix like "origin/").
  const currentTargetBare = currentTargetBranch.replace(/^[^/]+\//, "");
  const hasMismatch =
    prStatus?.prState === "none" &&
    prStatus.mismatchedPrIid != null &&
    prStatus.mismatchedPrTargetBranch != null &&
    prStatus.mismatchedPrTargetBranch !== currentTargetBare;
  // Stable reference so the useMemo inside TargetBranchSelector doesn't thrash.
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

  if (!workspace) {
    return null;
  }

  // The target-branch selector is host-agnostic, but PR/MR creation needs the
  // GitHub or GitLab CLI, so the PR button stays gated on the git provider.
  const canCreatePr = gitProvider !== null;
  const isMismatched = mismatchForSelector != null;

  return (
    <div
      className={styles.header}
      style={isSidebarCollapsed ? { paddingLeft: getTitleBarLeftPadding(false) } : undefined}
      data-testid={ElementIds.WORKSPACE_HEADER}
    >
      {/* Left cluster: the left-section toggle. */}
      <Flex align="center" gap="2" flexShrink="0">
        <SectionToggle
          section="left"
          icon={<PanelLeft size={16} />}
          label="left section"
          testId={ElementIds.HEADER_SECTION_TOGGLE_LEFT}
        />
      </Flex>

      {/* Branch pill */}
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
      <Tooltip content="Target branch" side="bottom" open={isTargetBranchOpen ? false : undefined}>
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

      {/* Draggable spacer so the frameless window can be moved by the header. */}
      <div className={styles.spacer} data-spacer />

      {/* Right cluster: re-homed diff summary + PR button, then bottom/right toggles. */}
      <Flex align="center" gap="2" flexShrink="0">
        <DiffSummary workspaceId={workspaceID} />
        {canCreatePr && (
          <PrButton
            workspaceId={workspaceID}
            targetBranch={currentTargetBranch}
            gitProvider={gitProvider}
            onSwitchTarget={handleSwitchTarget}
          />
        )}
        <SectionToggle
          section="bottom"
          icon={<PanelBottom size={16} />}
          label="bottom section"
          testId={ElementIds.HEADER_SECTION_TOGGLE_BOTTOM}
        />
        <SectionToggle
          section="right"
          icon={<PanelRight size={16} />}
          label="right section"
          testId={ElementIds.HEADER_SECTION_TOGGLE_RIGHT}
        />
      </Flex>
    </div>
  );
};
