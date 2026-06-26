import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { Ellipsis, Layers, Plus, Settings, SquareMenu, Terminal } from "lucide-react";
import type { ReactElement } from "react";

import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";

import styles from "./MobileWorkspaceHeader.module.scss";
import { useCreateAgent } from "./useCreateAgent.ts";
import { useMobileChangeSummary } from "./useMobileChangeSummary.ts";

type MobileWorkspaceHeaderProps = {
  onOpenDrawer: () => void;
  onOpenReview: () => void;
  onOpenTerminal: () => void;
};

/**
 * MobileWorkspaceHeader (H1-H4) — replaces the global TopBar on the mobile
 * Workspace view. Left: ☰ opens the drawer. Center: the workspace name only
 * (the active agent now lives in the bottom AgentSwitcher). Right: ⋮ dropdown
 * (Radix, anchored, no dim). Owns the top safe-area inset (H4).
 */
export const MobileWorkspaceHeader = ({
  onOpenDrawer,
  onOpenReview,
  onOpenTerminal,
}: MobileWorkspaceHeaderProps): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const { navigateToGlobalSettings } = useImbueNavigate();
  const workspace = useWorkspace(workspaceID);
  const { filesChanged } = useMobileChangeSummary(workspaceID);
  const { createAgent } = useCreateAgent();

  const workspaceName = workspace?.description?.trim() || "Workspace";

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
      </div>

      <DropdownMenu.Root>
        <DropdownMenu.Trigger>
          <IconButton variant="ghost" color="gray" className={styles.iconButton} aria-label="Workspace actions">
            <Ellipsis size={22} />
          </IconButton>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="end" variant="soft" className="mobileTheme">
          <DropdownMenu.Item onSelect={() => void createAgent()}>
            <Plus size={16} /> Create new agent
          </DropdownMenu.Item>
          <DropdownMenu.Separator />
          <DropdownMenu.Item onSelect={onOpenReview}>
            <Layers size={16} /> Review all changes
            {filesChanged > 0 ? <span className={styles.menuMeta}>{filesChanged} files</span> : null}
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={onOpenTerminal}>
            <Terminal size={16} /> Open terminal
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
