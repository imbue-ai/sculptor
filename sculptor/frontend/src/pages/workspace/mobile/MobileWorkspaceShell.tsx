import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { ChatPanelContent } from "../components/ChatPanelContent.tsx";
import { AgentPager } from "./AgentPager.tsx";
import { ChangesPill } from "./ChangesPill.tsx";
import { MobileChatInput } from "./MobileChatInput.tsx";
import { MobileWorkspaceHeader } from "./MobileWorkspaceHeader.tsx";
import styles from "./MobileWorkspaceShell.module.scss";
import { ReviewAllOverlay } from "./overlays/ReviewAllOverlay.tsx";
import { TerminalOverlay } from "./overlays/TerminalOverlay.tsx";
import { WorkspaceDrawer } from "./WorkspaceDrawer.tsx";

type Overlay = "review" | "terminal" | null;

/**
 * MobileWorkspaceShell — single-column, chat-first Workspace view for narrow
 * viewports (S1). Top → bottom: workspace header · optional changes pill ·
 * chat stream (fills) · chat input · agent pager. Secondary surfaces (drawer,
 * review-all, terminal) open over the chat as in-shell state; "back" closes the
 * overlay rather than navigating the router (Open Q9). It reuses the real chat
 * (ChatPanelContent) unchanged, suppressing only its built-in desktop input
 * (hideChatInput) so the shell can supply MobileChatInput (I1).
 */
export const MobileWorkspaceShell = ({ taskID }: { taskID: string }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>(null);

  // Switching agent/workspace closes any open secondary surface so it doesn't
  // float over an unrelated chat.
  useEffect(() => {
    setOverlay(null);
    setIsDrawerOpen(false);
  }, [taskID, workspaceID]);

  return (
    <div className={`sandTheme ${styles.shell}`}>
      <MobileWorkspaceHeader
        onOpenDrawer={() => setIsDrawerOpen(true)}
        onOpenReview={() => setOverlay("review")}
        onOpenTerminal={() => setOverlay("terminal")}
      />

      <div className={styles.chipSlot}>
        <ChangesPill onReviewAll={() => setOverlay("review")} />
      </div>

      <div className={styles.chatArea}>
        <ChatPanelContent hideChatInput />
      </div>

      <MobileChatInput taskID={taskID} />
      <AgentPager />

      <div
        className={`${styles.backdrop} ${isDrawerOpen ? styles.open : ""}`}
        onClick={() => setIsDrawerOpen(false)}
        aria-hidden={!isDrawerOpen}
      />
      <WorkspaceDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} currentWorkspaceID={workspaceID} />

      {overlay === "review" && <ReviewAllOverlay onBack={() => setOverlay(null)} />}
      {overlay === "terminal" && <TerminalOverlay onBack={() => setOverlay(null)} />}
    </div>
  );
};
