import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ImperativePanelHandle } from "react-resizable-panels";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { fileBrowserSplitRatioAtom } from "~/common/state/atoms/userConfig.ts";
import { expandedPanelIdAtom } from "~/components/panels/atoms.ts";

import {
  closeDiffPanelAtom,
  diffPanelOpenAtom,
  diffPanelSplitRatioAtom,
  fileBrowserDockSideAtom,
} from "./diffPanel/atoms.ts";
import { DiffPanel } from "./diffPanel/DiffPanel.tsx";
import styles from "./DiffSplitContainer.module.scss";

const LAYOUT_PERSIST_DEBOUNCE_MS = 200;
const COLLAPSE_THRESHOLD = 5;
const CHAT_MIN_WIDTH_PX = 385;
const CHAT_MIN_FALLBACK_PERCENT = 25;
// Below this width the DiffTabBar's left/right control clusters overlap the tabs.
const DIFF_MIN_WIDTH_PX = 300;
const DIFF_MIN_FALLBACK_PERCENT = 25;

type DiffSplitContainerProps = {
  workspaceId: string;
  chatContent: ReactNode;
};

export const DiffSplitContainer = ({ workspaceId, chatContent }: DiffSplitContainerProps): ReactElement => {
  const isOpen = useAtomValue(diffPanelOpenAtom);
  const [splitRatio, setSplitRatio] = useAtom(diffPanelSplitRatioAtom);
  const defaultSplitRatio = useAtomValue(fileBrowserSplitRatioAtom);
  const closeDiffPanel = useSetAtom(closeDiffPanelAtom);
  // The diff viewer always docks on the same side as the file browser panel.
  const splitPosition = useAtomValue(fileBrowserDockSideAtom);

  const layoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<ImperativePanelHandle>(null);
  const diffPanelRef = useRef<ImperativePanelHandle>(null);
  const [containerSize, setContainerSize] = useState(0);

  const expandedPanelId = useAtomValue(expandedPanelIdAtom);
  const isInExpandMode = expandedPanelId != null;

  // Clean up pending layout timer on unmount
  useEffect(() => {
    return (): void => {
      if (layoutTimerRef.current) clearTimeout(layoutTimerRef.current);
    };
  }, []);

  const isDiffFirst = splitPosition === "left";

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setContainerSize(rect.width);
    });
    observer.observe(el);
    return (): void => {
      observer.disconnect();
    };
  }, []);

  const chatMinPercent =
    containerSize > 0 ? Math.ceil((CHAT_MIN_WIDTH_PX / containerSize) * 100) : CHAT_MIN_FALLBACK_PERCENT;

  const rawDiffMinPercent =
    containerSize > 0 ? Math.ceil((DIFF_MIN_WIDTH_PX / containerSize) * 100) : DIFF_MIN_FALLBACK_PERCENT;
  // Cap so chatMinPercent + diffMinPercent never exceeds 100 (would make the layout unsatisfiable).
  const diffMinPercent = Math.min(rawDiffMinPercent, Math.max(0, 100 - chatMinPercent));

  const effectiveSplitRatio = splitRatio > 0 ? splitRatio : defaultSplitRatio;
  const chatSize = Math.max(100 - effectiveSplitRatio, chatMinPercent);
  const diffSize = 100 - chatSize;

  // Imperatively collapse/expand the diff panel when isOpen changes.
  // Using useLayoutEffect ensures the resize happens before the browser
  // paints, so the user never sees the intermediate state.
  const prevIsOpenRef = useRef(isOpen);
  useLayoutEffect(() => {
    const panel = diffPanelRef.current;
    if (!panel || prevIsOpenRef.current === isOpen) return;
    prevIsOpenRef.current = isOpen;

    if (isOpen) {
      panel.expand();
      panel.resize(effectiveSplitRatio);
    } else {
      panel.collapse();
    }
  }, [isOpen, effectiveSplitRatio]);

  // Collapse/expand chat panel when entering/exiting expand mode so that the
  // DiffPanel instance stays mounted (no remount = preserved hunk expansion,
  // scroll position, collapsed sections, etc.).
  useEffect(() => {
    if (!isOpen) return;
    if (isInExpandMode) {
      chatPanelRef.current?.collapse();
    } else {
      chatPanelRef.current?.expand();
    }
  }, [isInExpandMode, isOpen]);

  // Keep layout-relevant values in refs so handleLayout stays stable across
  // isInExpandMode / isDiffFirst changes, avoiding PanelGroup callback churn.
  const isInExpandModeRef = useRef(isInExpandMode);
  isInExpandModeRef.current = isInExpandMode;
  const isDiffFirstRef = useRef(isDiffFirst);
  isDiffFirstRef.current = isDiffFirst;

  const handleLayout = useCallback(
    (sizes: Array<number>): void => {
      // Skip layout persistence when the diff panel is closed — the collapse
      // triggers an onLayout with size 0 which would otherwise fire
      // closeDiffPanel redundantly or persist a zero split ratio.
      if (!isOpen) return;

      if (layoutTimerRef.current) {
        clearTimeout(layoutTimerRef.current);
      }
      layoutTimerRef.current = setTimeout(() => {
        // Don't persist sizes while the chat panel is collapsed for expand mode.
        if (isInExpandModeRef.current) return;

        const diffPanelSize = isDiffFirstRef.current ? sizes[0] : sizes[1];

        if (diffPanelSize <= COLLAPSE_THRESHOLD) {
          closeDiffPanel();
          return;
        }

        setSplitRatio(diffPanelSize);
      }, LAYOUT_PERSIST_DEBOUNCE_MS);
    },
    [isOpen, closeDiffPanel, setSplitRatio],
  );

  const chatPanel = (
    <Panel
      ref={chatPanelRef}
      id="diff-split-chat"
      defaultSize={isOpen ? chatSize : 100}
      minSize={chatMinPercent}
      collapsible
      collapsedSize={0}
      order={isDiffFirst ? 2 : 1}
    >
      {chatContent}
    </Panel>
  );

  const diffPanel = (
    <Panel
      ref={diffPanelRef}
      id="diff-split-diff"
      defaultSize={isOpen ? diffSize : 0}
      minSize={diffMinPercent}
      collapsible
      collapsedSize={0}
      order={isDiffFirst ? 1 : 2}
    >
      {isOpen && <DiffPanel workspaceId={workspaceId} />}
    </Panel>
  );

  const isResizeDisabled = !isOpen || isInExpandMode;
  const resizeHandle = (
    <PanelResizeHandle
      disabled={isResizeDisabled}
      className={`${styles.horizontalResizeHandle} ${isResizeDisabled ? styles.hidden : ""}`}
    />
  );

  return (
    <div ref={containerRef} className={styles.splitWrapper}>
      <PanelGroup key={splitPosition} direction="horizontal" onLayout={handleLayout}>
        {isDiffFirst ? (
          <>
            {diffPanel}
            {resizeHandle}
            {chatPanel}
          </>
        ) : (
          <>
            {chatPanel}
            {resizeHandle}
            {diffPanel}
          </>
        )}
      </PanelGroup>
    </div>
  );
};
