import { Button, IconButton } from "@radix-ui/themes";
import { GitBranch, Plus, Settings, SquareMenu } from "lucide-react";
import type { KeyboardEvent, ReactElement, RefObject } from "react";
import { useState } from "react";

import type { Project } from "~/api";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { RepoSelector } from "~/components/RepoSelector.tsx";
import { WorkspaceDrawer } from "~/pages/workspace/mobile/WorkspaceDrawer.tsx";

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
  sourceBranch: string | undefined;
};

/**
 * MobileNewWorkspace (L1-L4) — the default landing on mobile. Minimal: a
 * "Name your workspace" hero, one focused name input, a subtle tappable
 * `repo · origin/main` meta line (the branch is the inherited global default,
 * not re-implemented here), and a full-width Create button. It is pure
 * presentation over AddWorkspacePage's create-workspace submit core, which is
 * passed in via props (so the creation path is shared, not duplicated).
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
  sourceBranch,
}: MobileNewWorkspaceProps): ReactElement => {
  const { navigateToGlobalSettings } = useImbueNavigate();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter" && !isPending) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className={`sandTheme ${styles.shell}`}>
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

      <div className={styles.landing}>
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>Name your workspace</h1>
        </div>

        <input
          ref={nameInputRef}
          className={styles.nameField}
          value={workspaceName}
          placeholder="Workspace name"
          autoFocus
          onChange={(e) => onWorkspaceNameChange(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Workspace name"
        />

        <div className={styles.metaLine}>
          <RepoSelector
            projects={projects}
            selectedProjectId={selectedProjectId}
            onProjectChange={onProjectChange}
            className={styles.repoSelector}
          />
          <span className={styles.metaDot}>·</span>
          <span className={styles.branch}>
            <GitBranch size={14} />
            {sourceBranch ?? "origin/main"}
          </span>
        </div>

        <Button size="3" className={styles.createButton} disabled={isPending} onClick={onSubmit}>
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
