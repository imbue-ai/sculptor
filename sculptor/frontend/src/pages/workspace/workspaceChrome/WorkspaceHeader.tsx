import { Badge, Flex, Skeleton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { GitBranchIcon, PanelBottom, PanelLeft, PanelRight } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds, updateWorkspace, WorkspaceInitializationStrategy } from "~/api";
import { useActiveProjectID, useWorkspacePageParams } from "~/common/hooks/navigation";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus";
import { prDefaultTargetBranchAtom } from "~/common/state/atoms/userConfig";
import { useGitProvider } from "~/common/state/hooks/useGitProvider";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { getCollapsedSidebarToggleClearance } from "~/electron/platform.ts";
import { isSectionExpandedAtom } from "~/pages/workspace/layout/atoms/section.ts";
import { toggleSectionAtom } from "~/pages/workspace/layout/atoms/sectionActions.ts";
import { sidebarCollapsedAtom } from "~/pages/workspace/layout/atoms/sidebar.ts";
import { isDropTargetAtom } from "~/pages/workspace/layout/atoms/transient.ts";
import type { SectionId } from "~/pages/workspace/layout/types/section.ts";
import { primaryOf } from "~/pages/workspace/layout/types/section.ts";
import { pluginWorkspaceWidgetsAtom } from "~/plugins/pluginRegistry.ts";

import { DiffSummary } from "../../../components/diffSummary/DiffSummary";
import { PrButton } from "../../../components/prButton/PrButton";
import { useWorkspaceTargetBranches } from "./hooks/useWorkspaceTargetBranches";
import { TargetBranchSelector } from "./TargetBranchSelector";
import styles from "./WorkspaceHeader.module.scss";

// Per-mode badge label. Worktree is the product default and shows no badge; the
// non-default modes are surfaced so the user knows a workspace edits files in place
// (in-place) or in a clone.
const MODE_BADGE_LABEL: Record<WorkspaceInitializationStrategy, string> = {
  [WorkspaceInitializationStrategy.IN_PLACE]: "in-place",
  [WorkspaceInitializationStrategy.CLONE]: "clone",
  [WorkspaceInitializationStrategy.WORKTREE]: "worktree",
};

type SectionToggleProps = {
  section: SectionId;
  icon: ReactElement;
  label: string;
  testId: string;
};

// One collapse/expand toggle for a side/bottom section. Reads the per-section
// expanded slice and writes through the shared toggleSectionAtom so the header,
// keyboard shortcuts, and drag-to-expand (via the collapsed-section drop overlay)
// all funnel through one reducer.
const SectionToggle = ({ section, icon, label, testId }: SectionToggleProps): ReactElement => {
  const isExpanded = useAtomValue(isSectionExpandedAtom(section));
  // While a dragged panel hovers a collapsed section's drop overlay, light this
  // toggle up — it is the section that dropping will pop open.
  const isDropTarget = useAtomValue(isDropTargetAtom(primaryOf(section)));
  const toggleSection = useSetAtom(toggleSectionAtom);

  const isDropHighlight = isDropTarget && !isExpanded;

  return (
    <TooltipIconButton
      tooltipText={isExpanded ? `Hide ${label}` : `Show ${label}`}
      variant="ghost"
      size="1"
      color="gray"
      className={isDropHighlight ? styles.toggleDropTarget : isExpanded ? styles.toggleActive : undefined}
      onClick={() => toggleSection({ section })}
      aria-label={`Toggle ${label}`}
      data-testid={testId}
    >
      {icon}
    </TooltipIconButton>
  );
};

/**
 * The simplified workspace header above the section grid, part of the workspace
 * layout shell. Left cluster: the left-section toggle. Center:
 * the branch pill + target-branch selector. A draggable spacer lets the frameless
 * window be moved by the header. Right cluster: the re-homed diff summary + PR
 * button, then the bottom- and right-section toggles. Hidden by WorkspaceLayoutShell
 * when a section is maximized.
 *
 * Memoized (it takes no props) so parent re-renders never cascade into it — it
 * re-renders only from its own atom/hook subscriptions.
 */
const WorkspaceHeaderComponent = (): ReactElement | null => {
  // External atoms
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);
  const workspaceWidgets = useAtomValue(pluginWorkspaceWidgetsAtom);

  // External hooks
  const { workspaceID } = useWorkspacePageParams();
  const projectID = useActiveProjectID();
  const workspace = useWorkspace(workspaceID);
  const workspaceBranchInfo = useWorkspaceBranch(workspaceID);
  const gitProvider = useGitProvider(projectID ?? "");
  const prDefaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);
  const prStatus = useAtomValue(prStatusAtomFamily(workspaceID));
  const targetBranches = useWorkspaceTargetBranches(workspaceID);

  // Internal state
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [isTargetBranchOpen, setIsTargetBranchOpen] = useState<boolean>(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Normalize an absent branch (loading or unavailable) to null so the header
  // renders a single empty state.
  const branchName = workspaceBranchInfo?.currentBranch ?? null;

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
    navigator.clipboard
      .writeText(branchName)
      .then(() => {
        setIsCopied(true);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setIsCopied(false), 1500);
      })
      .catch(() => {});
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
      // PRs live on the origin remote, so prefer "origin/{bare}".
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
  const currentTargetBranch = workspace?.targetBranch ?? prDefaultTargetBranch;

  // Only show mismatch when the PR's target branch differs from the current
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
              text: `PR #${prStatus.mismatchedPrIid}`,
              tooltip: "Open PR targets this branch",
            },
          }
        : null,
    [hasMismatch, prStatus?.mismatchedPrTargetBranch, prStatus?.mismatchedPrIid],
  );

  // Plugin-contributed workspace widgets sit in the banner's action row beside the
  // PR button (see pluginWorkspaceWidgetsAtom). Higher collapsePriority is the more
  // protected slot, so order it nearest the PR button (rendered last). Each widget
  // component already carries its own error boundary + Plugin/WorkspacePluginContext.
  const orderedWorkspaceWidgets = useMemo(
    () => [...workspaceWidgets].sort((a, b) => a.collapsePriority - b.collapsePriority),
    [workspaceWidgets],
  );

  if (!workspace) {
    return null;
  }

  // The target-branch selector is host-agnostic, but PR creation needs the
  // GitHub CLI, so the PR button stays gated on the git provider.
  const canCreatePr = gitProvider !== null;
  const isMismatched = mismatchForSelector != null;

  // Surface the workspace's init mode next to the branch — but only for the
  // non-default strategies (worktree is the default and stays unlabeled).
  const modeStrategy = workspace.initializationStrategy;
  const shouldShowModeBadge = modeStrategy !== WorkspaceInitializationStrategy.WORKTREE;

  return (
    <div
      className={styles.header}
      // When the sidebar is collapsed the floating CollapsedSidebarToggle occupies the
      // top-left gutter (traffic-light padding + its button); pad the header past both
      // so the left-section toggle isn't hidden underneath it.
      style={isSidebarCollapsed ? { paddingLeft: getCollapsedSidebarToggleClearance() } : undefined}
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

      {/* Branch pill: a real button so it is focusable and Enter/Space-activatable
          for free; the visible label is the branch name, so the aria-label spells
          out what pressing it does. */}
      {branchName ? (
        <Tooltip
          content={isCopied ? "Copied!" : "Workspace branch — click to copy"}
          open={isCopied || undefined}
          side="bottom"
        >
          <button
            type="button"
            className={styles.branchSection}
            onClick={handleCopyBranch}
            aria-label={`Copy branch name ${branchName}`}
            data-testid={ElementIds.BRANCH_NAME}
          >
            <GitBranchIcon size={12} className={styles.branchIcon} />
            <span className={styles.branchName}>{branchName}</span>
          </button>
        </Tooltip>
      ) : (
        <Skeleton width="160px" height="16px" />
      )}

      {/* Workspace init-mode badge (non-default modes only). */}
      {shouldShowModeBadge && (
        <Badge size="1" color="gray" variant="solid" data-testid={ElementIds.TASK_MODE_BADGE}>
          {MODE_BADGE_LABEL[modeStrategy]}
        </Badge>
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

      {/* Right cluster: re-homed diff summary + PR button, then bottom/right toggles.
          gap="3" spaces every item (including the two toggles) evenly so the toggles'
          active backgrounds don't touch while keeping the same gap as the PR button. */}
      <Flex align="center" gap="3" flexShrink="0">
        <DiffSummary workspaceId={workspaceID} />
        {orderedWorkspaceWidgets.map(({ id, component: Widget }) => (
          <Widget key={id} />
        ))}
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

export const WorkspaceHeader = memo(WorkspaceHeaderComponent);
