import { useAtomValue } from "jotai";
import { useState } from "react";

import {
  commitPromptSourceAtomFamily,
  prCreationPromptSourceAtomFamily,
} from "~/common/state/atoms/workspaceAgentActions.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import type { AgentPromptKind } from "~/common/utils/agentPrompts.ts";

type EditAgentPrompt = {
  menuLabel: string;
  /** Opens the prompt the workspace is sent: its jj prompt on the Jujutsu page, else the git prompt's dialog. */
  handleMenuSelect: () => void;
  isDialogOpen: boolean;
  handleDialogOpenChange: (open: boolean) => void;
  /** The dialog's git prompt is what this jj workspace is sent, since no jj prompt is set. */
  isJjFallback: boolean;
};

/** Where a Commit or Create PR button's "Edit prompt" menu leads, following the prompt its workspace is sent. */
export const useEditAgentPrompt = (inputs: { workspaceId: string; kind: AgentPromptKind }): EditAgentPrompt => {
  const { workspaceId, kind } = inputs;
  const source = useAtomValue(
    kind === "commit" ? commitPromptSourceAtomFamily(workspaceId) : prCreationPromptSourceAtomFamily(workspaceId),
  );
  const openSettings = useOpenSettings();
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);

  const handleMenuSelect = (): void => {
    if (source === "jj") {
      openSettings("JJ", kind);
    } else {
      setIsDialogOpen(true);
    }
  };

  return {
    menuLabel: source === "jj" ? "Edit jj prompt..." : "Edit prompt...",
    handleMenuSelect,
    isDialogOpen,
    handleDialogOpenChange: setIsDialogOpen,
    isJjFallback: source === "git-for-jj",
  };
};
