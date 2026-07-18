import { Skeleton } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./MobileChatSkeleton.module.scss";

// A short, alternating transcript silhouette: assistant turns are wide,
// left-aligned multi-line bubbles; user turns are narrower right-aligned
// bubbles. Uneven bubble widths, line counts, and a shorter last line so it
// reads as a conversation loading in rather than a uniform block. Purely
// decorative — the real chat replaces it the instant the task snapshot lands.
//
// `width` sizes the bubble (its lines are percentages of it); the final line of
// each bubble is intentionally short to mimic a wrapped paragraph's last line.
const PLACEHOLDER_TURNS: ReadonlyArray<{ role: "assistant" | "user"; width: string; lines: number }> = [
  { role: "assistant", width: "82%", lines: 3 },
  { role: "user", width: "56%", lines: 1 },
  { role: "assistant", width: "74%", lines: 2 },
  { role: "user", width: "64%", lines: 2 },
];

// Last line of a bubble is short (like a paragraph's final wrapped line); the
// rest fill the bubble.
const lineWidth = (lineIndex: number, lineCount: number): string => (lineIndex === lineCount - 1 ? "62%" : "100%");

/**
 * Placeholder skeleton for the mobile chat stream, shown in the workspace shell's
 * chat area while the task snapshot (and thus the chat-vs-terminal capability) is
 * still in flight — the window in which `ChatPanelContent` renders nothing. The
 * mobile shell mounts the chat directly (no section-mount skeleton like the
 * desktop layout), so without this the pane is blank on a cold load.
 *
 * The bubbles fade in after a short delay (see the stylesheet) so a fast reconnect
 * never flashes a skeleton — only a slow/cold backend surfaces it. `aria-hidden`
 * keeps the decorative bars out of the accessibility tree.
 */
export const MobileChatSkeleton = (): ReactElement => {
  return (
    <div className={styles.skeleton} aria-hidden="true" data-testid={ElementIds.MOBILE_CHAT_LOADING_SKELETON}>
      {PLACEHOLDER_TURNS.map((turn, turnIndex) => (
        <div key={turnIndex} className={turn.role === "user" ? styles.userTurn : styles.assistantTurn}>
          <div className={styles.bubble} style={{ width: turn.width }}>
            {Array.from({ length: turn.lines }, (_, lineIndex) => (
              <Skeleton key={lineIndex} className={styles.line} style={{ width: lineWidth(lineIndex, turn.lines) }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};
