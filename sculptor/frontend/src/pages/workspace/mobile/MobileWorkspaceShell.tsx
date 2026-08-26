import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { ChatPanelContent } from "../components/ChatPanelContent.tsx";
import { AgentSheet } from "./AgentSheet.tsx";
import { AgentSwitcher } from "./AgentSwitcher.tsx";
import { ChangesPill } from "./ChangesPill.tsx";
import { MobileWorkspaceHeader } from "./MobileWorkspaceHeader.tsx";
import styles from "./MobileWorkspaceShell.module.scss";
import { ReviewAllOverlay } from "./overlays/ReviewAllOverlay.tsx";
import { TerminalOverlay } from "./overlays/TerminalOverlay.tsx";
import { WorkspaceDrawer } from "./WorkspaceDrawer.tsx";

type Overlay = "review" | "terminal" | null;

/**
 * MobileWorkspaceShell — single-column, chat-first Workspace view for narrow
 * viewports (S1). Top → bottom: workspace header · chat stream (fills) · chat
 * input. The status row (agent switcher + changes pill) floats over the top of
 * the chat with a transparent background, so the stream scrolls behind the
 * pills. Secondary surfaces (drawer, review-all, terminal) open over the chat as
 * in-shell state; "back" closes the overlay rather than navigating the router
 * (Open Q9). It reuses the real chat (ChatPanelContent) and its real ChatInput
 * unchanged — ChatInput adapts itself to a compact toolbar on mobile, so the
 * shell no longer supplies a bespoke input. In the status row the agent switcher
 * sits on the left, the changes pill on the right (S/C).
 */
export const MobileWorkspaceShell = ({ taskID }: { taskID: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isAgentSheetOpen, setIsAgentSheetOpen] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>(null);

  // Switching agent/workspace closes any open secondary surface so it doesn't
  // float over an unrelated chat. Reset-on-identity-change: these are user-toggled
  // transient flags, not derivable during render, so the sync lives in an effect.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setOverlay(null);
    setIsDrawerOpen(false);
    setIsAgentSheetOpen(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [taskID, workspaceID]);

  return (
    <div className={`mobileTheme ${styles.shell}`} data-testid={ElementIds.MOBILE_WORKSPACE_SHELL}>
      <MobileWorkspaceHeader
        onOpenDrawer={() => setIsDrawerOpen(true)}
        onOpenReview={() => setOverlay("review")}
        onOpenTerminal={() => setOverlay("terminal")}
      />

      <div className={styles.chatArea}>
        {/* The status row floats over the top of the chat (transparent
            background, click-through gaps) so the stream scrolls behind the
            pills. */}
        <div className={styles.statusRow}>
          <AgentSwitcher onOpenSheet={() => setIsAgentSheetOpen(true)} />
          <ChangesPill onReviewAll={() => setOverlay("review")} />
        </div>
        {/* The panel model keys the chat on an explicit taskId (never the
            route), so the shell passes its agent through — same contract as a
            desktop agent panel. */}
        <ChatPanelContent taskId={taskID} />
      </div>

      <div
        className={`${styles.backdrop} ${isDrawerOpen || isAgentSheetOpen ? styles.open : ""}`}
        onClick={() => {
          setIsDrawerOpen(false);
          setIsAgentSheetOpen(false);
        }}
        aria-hidden={!(isDrawerOpen || isAgentSheetOpen)}
      />
      <WorkspaceDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} currentWorkspaceID={workspaceID} />
      <AgentSheet isOpen={isAgentSheetOpen} onClose={() => setIsAgentSheetOpen(false)} />

      {overlay === "review" && <ReviewAllOverlay onBack={() => setOverlay(null)} />}
      {overlay === "terminal" && <TerminalOverlay onBack={() => setOverlay(null)} />}
    </div>
  );
};
