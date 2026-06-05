import { useAtom, useAtomValue } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ResizeHandle } from "~/components/panels/ResizeHandle.tsx";

import { secondChatAgentIdAtomFamily } from "./centerAtoms.ts";
import styles from "./CenterPanes.module.scss";
import { diffPanelOpenAtom, diffPanelSplitRatioAtom } from "./diffPanel/atoms.ts";
import { DiffPanel } from "./diffPanel/DiffPanel.tsx";
import { SecondaryChatPane } from "./SecondaryChatPane.tsx";

// The chat pane never shrinks below this; when space is tight, pane B gives way
// (REQ-PERSIST-3). pane B has its own smaller floor.
const CHAT_MIN_PX = 385;
const PANE_B_MIN_PX = 300;
const HANDLE_PX = 1;

type CenterPanesProps = {
  workspaceId: string;
  chatContent: ReactNode;
};

/**
 * The Center: pane A is always a chat; pane B is EITHER the single-file diff
 * viewer OR a second agent's chat — mutually exclusive, 2 panes maximum
 * (REQ-CENTER-1/2/3). The chat pane stays mounted across open/close so its
 * scroll position and draft survive; pane B mounts/unmounts.
 */
export const CenterPanes = ({ workspaceId, chatContent }: CenterPanesProps): ReactElement => {
  const isDiffOpen = useAtomValue(diffPanelOpenAtom);
  const [secondChatAgentId, setSecondChatAgentId] = useAtom(secondChatAgentIdAtomFamily(workspaceId));
  const [splitRatio, setSplitRatio] = useAtom(diffPanelSplitRatioAtom);

  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  // Diff wins over a chat split: opening a file while two chats are shown swaps
  // the second chat pane for the diff (REQ-CENTER-3).
  useEffect(() => {
    if (isDiffOpen && secondChatAgentId !== null) {
      setSecondChatAgentId(null);
    }
  }, [isDiffOpen, secondChatAgentId, setSecondChatAgentId]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setContainerWidth(rect.width);
    });
    observer.observe(el);
    return (): void => observer.disconnect();
  }, []);

  const shouldShowSecondChat = secondChatAgentId !== null && !isDiffOpen;
  const isSplit = isDiffOpen || shouldShowSecondChat;

  // pane B target width from the persisted % of the container, clamped so the
  // chat keeps at least CHAT_MIN_PX and pane B keeps PANE_B_MIN_PX.
  const maxPaneB = Math.max(PANE_B_MIN_PX, containerWidth - CHAT_MIN_PX - HANDLE_PX);
  const desiredPaneB = containerWidth > 0 ? Math.round((splitRatio / 100) * containerWidth) : 0;
  const paneBWidth = Math.min(Math.max(desiredPaneB, PANE_B_MIN_PX), maxPaneB);

  const getPaneBSize = useCallback(() => paneBWidth, [paneBWidth]);
  const onResizePaneB = useCallback(
    (nextPx: number): void => {
      if (containerWidth <= 0) return;
      const clamped = Math.min(
        Math.max(nextPx, PANE_B_MIN_PX),
        Math.max(PANE_B_MIN_PX, containerWidth - CHAT_MIN_PX - HANDLE_PX),
      );
      setSplitRatio((clamped / containerWidth) * 100);
    },
    [containerWidth, setSplitRatio],
  );

  return (
    <div ref={containerRef} className={styles.row}>
      <div className={styles.chatPane}>{chatContent}</div>
      {isSplit && (
        <>
          <ResizeHandle
            axis="x"
            getSize={getPaneBSize}
            onResize={onResizePaneB}
            direction={-1}
            ariaLabel="Resize center split"
          />
          <div className={styles.paneB} style={{ width: paneBWidth }}>
            {isDiffOpen ? (
              <DiffPanel workspaceId={workspaceId} singleFile />
            ) : secondChatAgentId !== null ? (
              <SecondaryChatPane agentId={secondChatAgentId} />
            ) : null}
          </div>
        </>
      )}
    </div>
  );
};
