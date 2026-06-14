import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { CircleEllipsis, Layers, Settings, SquareMenu, Terminal } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useProject } from "~/common/state/hooks/useProjects.ts";
import { useTask } from "~/common/state/hooks/useTaskHelpers.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { WorkspaceStatusDots } from "~/components/statusDot/StatusDot.tsx";
import { computeWorkspaceDotStatus } from "~/components/statusDot/statusUtils.ts";

import styles from "./MobileWorkspaceHeader.module.scss";
import { useMobileChangeSummary } from "./useMobileChangeSummary.ts";

type MobileWorkspaceHeaderProps = {
  onOpenDrawer: () => void;
  onOpenReview: () => void;
  onOpenTerminal: () => void;
};

/**
 * MobileWorkspaceHeader (H1-H4) — replaces the global TopBar on the mobile
 * Workspace view. Left: ☰ opens the drawer. Center: workspace name + an
 * `agent · repo` subtitle with a live status dot. Right: ⋮ jump dropdown
 * (Radix, anchored, no dim). Owns the top safe-area inset (H4).
 */
export const MobileWorkspaceHeader = ({
  onOpenDrawer,
  onOpenReview,
  onOpenTerminal,
}: MobileWorkspaceHeaderProps): ReactElement => {
  const { workspaceID, agentID: taskID } = useWorkspacePageParams();
  const { navigateToGlobalSettings } = useImbueNavigate();
  const workspace = useWorkspace(workspaceID);
  const task = useTask(taskID ?? "");
  const project = useProject(workspace?.projectId ?? "");
  const allTasks = useAtomValue(tasksArrayAtom);
  const { filesChanged } = useMobileChangeSummary(workspaceID);

  const dotStatus = useMemo(
    () => computeWorkspaceDotStatus((allTasks ?? []).filter((t) => t.workspaceId === workspaceID)),
    [allTasks, workspaceID],
  );

  const workspaceName = workspace?.description?.trim() || "Workspace";
  const agentName = task?.titleOrSomethingLikeIt?.trim() || "Agent";
  const repoName = project?.name ?? "";

  return (
    <header className={styles.header}>
      <IconButton
        variant="ghost"
        color="gray"
        className={styles.iconButton}
        aria-label="Open workspaces"
        onClick={onOpenDrawer}
      >
        <SquareMenu size={22} />
      </IconButton>

      <div className={styles.title}>
        <div className={styles.name} title={workspaceName}>
          {workspaceName}
        </div>
        <div className={styles.subtitle}>
          <WorkspaceStatusDots status={dotStatus} size={7} />
          <span className={styles.subtitleText}>
            {agentName}
            {repoName ? ` · ${repoName}` : ""}
          </span>
        </div>
      </div>

      <DropdownMenu.Root>
        <DropdownMenu.Trigger>
          <IconButton variant="ghost" color="gray" className={styles.iconButton} aria-label="Workspace actions">
            <CircleEllipsis size={22} />
          </IconButton>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="end" variant="soft" className="sandTheme">
          <DropdownMenu.Item onSelect={onOpenTerminal}>
            <Terminal size={16} /> Open terminal
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={onOpenReview}>
            <Layers size={16} /> Review all changes
            {filesChanged > 0 ? <span className={styles.menuMeta}>{filesChanged} files</span> : null}
          </DropdownMenu.Item>
          <DropdownMenu.Separator />
          <DropdownMenu.Item onSelect={() => navigateToGlobalSettings()}>
            <Settings size={16} /> Workspace settings
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    </header>
  );
};
