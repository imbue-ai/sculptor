import { IconButton } from "@radix-ui/themes";
import { CircleChevronLeft, CircleEllipsis } from "lucide-react";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useProject } from "~/common/state/hooks/useProjects.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";

import { TerminalInstance } from "../../panels/TerminalPanel.tsx";
import styles from "./Overlay.module.scss";

/**
 * TerminalOverlay (T1-T2) — full-screen overlay reached from the ⋮ menu.
 * Reuses the real terminal (TerminalInstance). The header is light
 * (`Terminal` · `repo · branch`); the terminal body is dark (--terminal-bg).
 * "Back" closes the overlay and returns to chat.
 */
export const TerminalOverlay = ({ onBack }: { onBack: () => void }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const workspace = useWorkspace(workspaceID);
  const project = useProject(workspace?.projectId ?? "");
  const branchInfo = useWorkspaceBranch(workspaceID);
  const branch = branchInfo?.currentBranch ?? workspace?.sourceBranch ?? "";
  const repoName = project?.name ?? "";

  return (
    <div className={styles.overlay} role="dialog" aria-label="Terminal">
      <header className={styles.header}>
        <IconButton
          variant="ghost"
          color="gray"
          className={styles.iconButton}
          aria-label="Back to chat"
          onClick={onBack}
        >
          <CircleChevronLeft size={22} />
        </IconButton>
        <div className={styles.headerInfo}>
          <div className={styles.headerTitle}>Terminal</div>
          {repoName || branch ? (
            <div className={styles.headerSubtitle}>
              {repoName}
              {repoName && branch ? " · " : ""}
              {branch}
            </div>
          ) : null}
        </div>
        <span className={styles.iconButton} aria-hidden="true">
          <CircleEllipsis size={20} />
        </span>
      </header>
      <div className={styles.terminalBody}>
        <TerminalInstance workspaceID={workspaceID} terminalIndex={0} isVisible={true} />
      </div>
    </div>
  );
};
