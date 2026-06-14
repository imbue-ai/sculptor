import { IconButton } from "@radix-ui/themes";
import { CircleChevronLeft, Settings } from "lucide-react";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { CombinedDiffView } from "../../components/diffPanel/CombinedDiffView.tsx";
import { useMobileChangeSummary } from "../useMobileChangeSummary.ts";
import styles from "./Overlay.module.scss";

/**
 * ReviewAllOverlay (R1-R5) — full-screen overlay over the chat showing the
 * reused combined diff (CombinedDiffView) forced to unified (R3). "Back" closes
 * the overlay and returns to chat (R5). Review-all is always-on inside the
 * mobile shell (not gated on the desktop isReviewAllEnabled flag).
 */
export const ReviewAllOverlay = ({ onBack }: { onBack: () => void }): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const summary = useMobileChangeSummary(workspaceID);

  return (
    <div className={styles.overlay} role="dialog" aria-label="Review all changes">
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
          <div className={styles.headerTitle}>Review all changes</div>
          <div className={styles.headerSubtitle}>
            <span className={styles.add}>+{summary.added}</span> <span className={styles.del}>−{summary.removed}</span>{" "}
            · {summary.filesChanged} {summary.filesChanged === 1 ? "file" : "files"}
          </div>
        </div>
        <span className={styles.iconButton} aria-hidden="true">
          <Settings size={20} />
        </span>
      </header>
      <div className={styles.body}>
        <CombinedDiffView workspaceId={workspaceID} viewType="unified" isActive={true} forceThemeType="light" />
      </div>
    </div>
  );
};
