import { Button, Dialog, DropdownMenu, Flex, IconButton, TextField } from "@radix-ui/themes";
import { Ellipsis, Layers, Pencil, Plus, Settings, SquareMenu, Terminal } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useWorkspaceRename } from "~/common/state/hooks/useWorkspaceRename.ts";

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
  const [isRenameOpen, setIsRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  const workspaceName = workspace?.description?.trim() || "Workspace";

  const openRename = (): void => {
    setRenameValue(workspace?.description ?? "");
    setIsRenameOpen(true);
  };

  // The shared optimistic rename (same path as the desktop sidebar): the new
  // name shows immediately; a rejected write rolls back and toasts.
  const renameWorkspace = useWorkspaceRename();
  const handleRenameSave = (): void => {
    const trimmed = renameValue.trim();
    setIsRenameOpen(false);
    if (!workspaceID || !trimmed || trimmed === workspace?.description) return;
    renameWorkspace(workspaceID, trimmed);
  };

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
          <DropdownMenu.Item onSelect={openRename}>
            <Pencil size={16} /> Rename workspace
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={() => navigateToGlobalSettings()}>
            <Settings size={16} /> Workspace settings
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>

      {/* A dialog (not an inline field) because the header sits next to the chat
          editor, which would otherwise reclaim the soft keyboard on mobile; a
          modal traps focus so the rename field keeps it. */}
      <Dialog.Root open={isRenameOpen} onOpenChange={setIsRenameOpen}>
        <Dialog.Content maxWidth="400px" className="mobileTheme">
          <Dialog.Title>Rename workspace</Dialog.Title>
          <TextField.Root
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void handleRenameSave();
              }
            }}
            placeholder="Workspace name"
            aria-label="Workspace name"
          />
          <Flex gap="3" mt="4" justify="end">
            <Dialog.Close>
              <Button variant="soft" color="gray">
                Cancel
              </Button>
            </Dialog.Close>
            <Button onClick={() => void handleRenameSave()}>Save</Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </header>
  );
};
