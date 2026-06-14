import { Button, IconButton } from "@radix-ui/themes";
import { GitBranch, Plus, Settings, Shuffle, SquareMenu } from "lucide-react";
import type { KeyboardEvent, ReactElement, RefObject } from "react";
import { useMemo, useState } from "react";

import type { Project, RepoInfo } from "~/api";
import { ElementIds } from "~/api";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { BranchSelectorCore, type BranchWithBadges } from "~/components/BranchSelectorCore.tsx";
import { RepoSelector } from "~/components/RepoSelector.tsx";
import { WorkspaceDrawer } from "~/pages/workspace/mobile/WorkspaceDrawer.tsx";

import type { BranchNameCollisionState } from "./hooks/useBranchNamePreview.ts";
import styles from "./MobileNewWorkspace.module.scss";

type MobileNewWorkspaceProps = {
  workspaceName: string;
  onWorkspaceNameChange: (value: string) => void;
  nameInputRef: RefObject<HTMLInputElement>;
  isPending: boolean;
  onSubmit: () => void;
  projects: ReadonlyArray<Project>;
  selectedProjectId: string | null;
  onProjectChange: (projectId: string) => void;
  repoInfo: RepoInfo | null;
  fetchRepoInfo: () => Promise<RepoInfo | undefined>;
  /** The generated/target branch name (override-or-preview from the parent). */
  branchName: string;
  isBranchNameLoading: boolean;
  branchNameCollision: BranchNameCollisionState;
  /** Called when the user edits the branch name (sets the parent override). */
  onBranchNameChange: (value: string) => void;
  /** Rerolls a fresh auto-generated branch name (clears the override). */
  onRegenerateBranchName: () => void;
  /** The source branch new work forks from (default origin/main). */
  sourceBranch: string | undefined;
  onSourceBranchChange: (branch: string) => void;
};

/**
 * MobileNewWorkspace — the default landing on mobile, aligned to the desktop
 * create-workspace modal. The workspace name is an inline "Untitled workspace"
 * title on top; below it the three options as stacked, full-width pills
 * (Repo · Branch · Source); an accent Create button is pinned to the bottom.
 * It is pure presentation over AddWorkspacePage's create-workspace core, which
 * is passed in via props (so the creation path is shared, not duplicated).
 */
export const MobileNewWorkspace = ({
  workspaceName,
  onWorkspaceNameChange,
  nameInputRef,
  isPending,
  onSubmit,
  projects,
  selectedProjectId,
  onProjectChange,
  repoInfo,
  fetchRepoInfo,
  branchName,
  isBranchNameLoading,
  branchNameCollision,
  onBranchNameChange,
  onRegenerateBranchName,
  sourceBranch,
  onSourceBranchChange,
}: MobileNewWorkspaceProps): ReactElement => {
  const { navigateToGlobalSettings } = useImbueNavigate();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const isBranchEmpty = branchName.trim() === "";
  const hasCollision = branchNameCollision === "exists";
  const isSubmitDisabled = isPending || isBranchEmpty || isBranchNameLoading || hasCollision;

  const handleSubmitKey = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter" && !isSubmitDisabled) {
      e.preventDefault();
      onSubmit();
    }
  };

  // Source-branch options for the dropdown, mirroring BranchSelector: recent
  // branches, with the repo's current branch badged.
  const sourceBranches: Array<BranchWithBadges> = useMemo(
    () =>
      (repoInfo?.recentBranches ?? []).map((branch) => ({
        branch,
        badges: branch === repoInfo?.currentBranch ? ["current"] : [],
      })),
    [repoInfo],
  );

  return (
    <div className={`mobileTheme ${styles.shell}`}>
      <header className={styles.header}>
        <IconButton
          variant="ghost"
          color="gray"
          className={styles.iconButton}
          aria-label="Open workspaces"
          onClick={() => setIsDrawerOpen(true)}
        >
          <SquareMenu size={22} />
        </IconButton>
        <div className={styles.wordmark}>Sculptor</div>
        <IconButton
          variant="ghost"
          color="gray"
          className={styles.iconButton}
          aria-label="Settings"
          onClick={() => navigateToGlobalSettings()}
        >
          <Settings size={22} />
        </IconButton>
      </header>

      <div className={styles.body}>
        <div className={styles.nameBlock}>
          <input
            ref={nameInputRef}
            className={styles.nameField}
            value={workspaceName}
            placeholder="Untitled workspace"
            autoFocus
            onChange={(e) => onWorkspaceNameChange(e.target.value)}
            onKeyDown={handleSubmitKey}
            aria-label="Workspace name"
            data-testid={ElementIds.WORKSPACE_NAME_INPUT}
          />
        </div>

        <div className={styles.pills}>
          {/* Repo */}
          <RepoSelector
            projects={projects}
            selectedProjectId={selectedProjectId}
            onProjectChange={onProjectChange}
            className={styles.pillTrigger}
            hideLabel
          />

          {/* Branch — the generated/target branch, editable + regenerate */}
          <div className={`${styles.pill} ${hasCollision ? styles.pillError : ""}`}>
            <GitBranch size={16} className={styles.pillIcon} />
            <input
              className={styles.branchInput}
              value={branchName}
              placeholder="branch name"
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              onChange={(e) => onBranchNameChange(e.target.value)}
              onKeyDown={handleSubmitKey}
              aria-label="Branch name"
              data-testid={ElementIds.BRANCH_NAME_INPUT}
            />
            <IconButton
              variant="ghost"
              color="gray"
              size="1"
              className={styles.regenButton}
              aria-label="Regenerate branch name"
              onClick={onRegenerateBranchName}
            >
              <Shuffle size={15} />
            </IconButton>
          </div>

          {/* Source — the branch new work forks from */}
          <BranchSelectorCore
            selectedBranch={sourceBranch ?? ""}
            onBranchSelected={onSourceBranchChange}
            branches={sourceBranches}
            isLoadingBranches={sourceBranches.length === 0}
            triggerVariant="ghost"
            className={styles.pillTrigger}
            testId={ElementIds.BRANCH_SELECTOR}
            triggerContent={
              <span className={styles.pillContent}>
                <GitBranch size={16} className={styles.pillIcon} />
                <span className={styles.pillLabel}>source</span>
                <span className={styles.pillValue}>{sourceBranch ?? "origin/main"}</span>
              </span>
            }
            onOpenChange={(open) => {
              if (open) void fetchRepoInfo();
            }}
          />

          {hasCollision ? (
            <span className={styles.collisionError} data-testid={ElementIds.BRANCH_NAME_COLLISION_ERROR}>
              Branch &apos;{branchName}&apos; already exists
            </span>
          ) : null}
        </div>
      </div>

      <div className={styles.footer}>
        <Button
          size="3"
          color="indigo"
          className={styles.createButton}
          disabled={isSubmitDisabled}
          onClick={onSubmit}
          data-testid={ElementIds.START_TASK_BUTTON}
        >
          <Plus size={18} /> Create workspace
        </Button>
      </div>

      <div
        className={`${styles.backdrop} ${isDrawerOpen ? styles.backdropOpen : ""}`}
        onClick={() => setIsDrawerOpen(false)}
        aria-hidden={!isDrawerOpen}
      />
      <WorkspaceDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} />
    </div>
  );
};
