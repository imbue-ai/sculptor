import { Anchor as PopoverAnchor } from "@radix-ui/react-popover";
import type { Measurable } from "@radix-ui/rect";
import { Popover } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { type CSSProperties, type KeyboardEvent, type ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import { useWorkspaceCodePath } from "~/pages/workspace/hooks/useWorkspaceCodePath.ts";

import { AlphaCommandPopover } from "./AlphaCommandPopover.tsx";
import { AlphaExpandedToolRow } from "./AlphaExpandedToolRow.tsx";
import { AlphaToolPill } from "./AlphaToolPill.tsx";
import styles from "./AlphaToolPillRow.module.scss";
import { AlphaToolPopover } from "./AlphaToolPopover.tsx";
import { chatToolDensityAtom } from "./atoms.ts";
import { useCloseOnChatScroll } from "./hooks/useChatScroll.tsx";
import { usePillHoverDelay } from "./hooks/usePillHoverDelay.ts";
import { usePluginToolVisualization } from "./pluginToolViz.ts";
import { useToolNavigation } from "./ToolNavigationContext.tsx";
import type { PillData } from "./toolPill.types.ts";
import { buildPillData } from "./toolPillUtils.ts";

const POPOVER_STYLE: CSSProperties = { padding: 0, width: 560, maxHeight: 400 };

type AlphaToolPillRowProps = {
  blocks: ReadonlyArray<ToolUseBlock | ToolResultBlock>;
  toolResultMap: Map<string, ToolResultBlock>;
  inProgressMessageId: string | null;
  rowIndex?: number;
};

export const AlphaToolPillRow = ({
  blocks,
  toolResultMap,
  inProgressMessageId,
  rowIndex,
}: AlphaToolPillRowProps): ReactElement | null => {
  const workspaceCodePath = useWorkspaceCodePath();
  const nav = useToolNavigation();
  const density = useAtomValue(chatToolDensityAtom);
  const isExpanded = density === "expanded";

  // Local state — used only when no ToolNavigationProvider wraps this row.
  // The setter is wrapped below to keep localIsPinnedRef in lock-step with the
  // open id; the pair-naming lint rule does not fit this case.
  // eslint-disable-next-line react/hook-use-state
  const [localOpenPillId, setLocalOpenPillIdState] = useState<string | null>(null);
  const localIsPinnedRef = useRef(false);
  const setLocalOpenPillId = useCallback((id: string | null, pinned: boolean = true): void => {
    localIsPinnedRef.current = id !== null && pinned;
    setLocalOpenPillIdState(id);
  }, []);
  const openPillId = nav ? nav.openItemId : localOpenPillId;
  const setOpenPillId = nav ? nav.setOpenItemId : setLocalOpenPillId;
  const isPinnedRef = nav ? nav.isPinnedRef : localIsPinnedRef;

  const [rawFocusedIndex, setRawFocusedIndex] = useState(0);
  const pillRefs = useRef<Array<HTMLElement | null>>([]);
  const rowRef = useRef<HTMLDivElement>(null);
  const popoverContentRef = useRef<HTMLDivElement | null>(null);

  const {
    handlePillMouseEnter,
    handlePillMouseLeave,
    handlePopoverMouseEnter,
    handlePopoverMouseLeave,
    notifyPinnedToggle,
  } = usePillHoverDelay({ openPillId, setOpenPillId, isPinnedRef, popoverElRef: popoverContentRef });

  const pillDataList = useMemo(
    () => buildPillData(blocks, toolResultMap, inProgressMessageId),
    [blocks, toolResultMap, inProgressMessageId],
  );

  // Register this row's pills with the shared nav context.
  useEffect(() => {
    if (!nav || rowIndex === undefined) return;
    const pillIds = pillDataList.map((p) => p.id);
    nav.registerRow(rowIndex, pillIds);
    return (): void => {
      nav.unregisterRow(rowIndex);
    };
  }, [nav, rowIndex, pillDataList]);

  const focusedIndex = pillDataList.length > 0 ? Math.min(rawFocusedIndex, pillDataList.length - 1) : 0;

  const openPill = openPillId ? pillDataList.find((p) => p.id === openPillId) : undefined;
  const isPopoverOpen = openPill !== undefined;

  const handleToggle = useCallback(
    (pillId: string, open: boolean): void => {
      setOpenPillId(open ? pillId : null, true);
      notifyPinnedToggle(open);
    },
    [setOpenPillId, notifyPinnedToggle],
  );

  // Chat scroll dismisses the popover — both the visual anchor and the
  // user's attention have moved, leaving a stale floating panel.
  const handleCloseOnScroll = useCallback((): void => {
    setOpenPillId(null, false);
    notifyPinnedToggle(false);
  }, [setOpenPillId, notifyPinnedToggle]);
  useCloseOnChatScroll(handleCloseOnScroll, isPopoverOpen);

  const handleNavigate = useCallback(
    (direction: "prev" | "next" | "up" | "down"): void => {
      if (nav) {
        nav.navigate(direction);
        return;
      }

      // Fallback: navigate within this row only. Vertical nav has no
      // sibling row to jump to, so it's a no-op outside the shared context.
      if (direction === "up" || direction === "down") return;

      const currentIndex = openPillId ? pillDataList.findIndex((p) => p.id === openPillId) : focusedIndex;
      const targetIndex =
        direction === "prev" ? Math.max(currentIndex - 1, 0) : Math.min(currentIndex + 1, pillDataList.length - 1);
      if (targetIndex === currentIndex) return;
      const targetPill = pillDataList[targetIndex];
      if (!targetPill) return;
      setOpenPillId(targetPill.id);
      setRawFocusedIndex(targetIndex);
      pillRefs.current[targetIndex]?.scrollIntoView({ block: "nearest", inline: "nearest" });
    },
    [nav, openPillId, pillDataList, focusedIndex, setOpenPillId],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      // In default density the row is horizontal — Left/Right step within
      // the row, Up/Down jump across rows once a popover is open. In
      // expanded density rows are vertical, so the axes are swapped:
      // Up/Down step within the row, Left/Right cross rows.
      const intraPrev = isExpanded ? "ArrowUp" : "ArrowLeft";
      const intraNext = isExpanded ? "ArrowDown" : "ArrowRight";
      const crossPrev = isExpanded ? "ArrowLeft" : "ArrowUp";
      const crossNext = isExpanded ? "ArrowRight" : "ArrowDown";

      if (e.key === intraPrev || e.key === intraNext) {
        const direction = e.key === intraNext ? "next" : "prev";
        if (isPopoverOpen) {
          e.preventDefault();
          handleNavigate(direction);
          return;
        }
        // No popover open. Try to move focus within the row group; if we're
        // already at the boundary, let the event propagate so chat-level
        // arrow nav (between messages / prompts) still works. This matters
        // most in expanded density, where the intra-row axis (Up/Down) is
        // the same axis the chat uses for message navigation.
        const target =
          direction === "next" ? Math.min(focusedIndex + 1, pillDataList.length - 1) : Math.max(focusedIndex - 1, 0);
        if (target === focusedIndex) return;
        e.preventDefault();
        setRawFocusedIndex(target);
        pillRefs.current[target]?.focus();
        return;
      }

      if (e.key === crossPrev || e.key === crossNext) {
        // Only intercept while a popover is open. stopPropagation prevents
        // the window-level prompt-nav listener from also handling the key
        // (which would scroll chat or move between messages).
        if (!isPopoverOpen) return;
        e.preventDefault();
        e.stopPropagation();
        handleNavigate(e.key === crossNext ? "down" : "up");
        return;
      }

      if (e.key === "Escape") {
        e.preventDefault();
        setOpenPillId(null);
        pillRefs.current[focusedIndex]?.focus();
      }
    },
    [focusedIndex, pillDataList.length, isPopoverOpen, isExpanded, handleNavigate, setOpenPillId],
  );

  // Density flips swap the row layout from a single horizontal pill row to a
  // stack of full-width rows. Wiring the popover anchor as a DOM wrapper —
  // PopoverAnchor in default, conditional PopoverAnchor on the active row in
  // expanded — meant the anchor's position in the React tree changed across
  // modes, forcing React to unmount/mount the entire row subtree (and the
  // virtualizer to re-measure async on the next frame, which produces the
  // visible flicker the user sees during the toggle).
  //
  // Instead, we pin a single PopoverAnchor with a `virtualRef` that just
  // returns a bounding rect. The DOM stays identical across density flips —
  // the rect closure adapts: anchor on the active row in expanded mode,
  // anchor on the row container in default mode.
  const openPillIdRef = useRef(openPillId);
  const isExpandedRef = useRef(isExpanded);
  const pillDataListRef = useRef(pillDataList);
  // Mirror the latest values into refs so the virtualRef measurable callback
  // and per-pill click handlers (both invoked outside render) read current
  // state without re-subscribing.
  useEffect(() => {
    openPillIdRef.current = openPillId;
    isExpandedRef.current = isExpanded;
    pillDataListRef.current = pillDataList;
  });

  const anchorMeasurableRef = useRef<Measurable>({
    getBoundingClientRect: (): DOMRect => {
      // In expanded mode with an active pill, anchor on that row so the
      // popover opens directly below it. Otherwise (or as a fallback if the
      // active row's element isn't ready), anchor on the row container.
      if (isExpandedRef.current && openPillIdRef.current !== null) {
        const idx = pillDataListRef.current.findIndex((p) => p.id === openPillIdRef.current);
        const el = idx >= 0 ? pillRefs.current[idx] : null;
        if (el) return el.getBoundingClientRect();
      }
      return rowRef.current?.getBoundingClientRect() ?? new DOMRect();
    },
  });

  // Per-pill stable callbacks. Memoized so AlphaExpandedToolRow (wrapped in
  // memo) can skip re-rendering rows whose data didn't change when one row's
  // open state changes.
  const handleItemRef = useMemo(
    () =>
      pillDataList.map((pill, index) => (el: HTMLElement | null): void => {
        pillRefs.current[index] = el;
        nav?.setItemRef(pill.id, el);
      }),
    [pillDataList, nav],
  );

  const handleItemToggle = useMemo(
    () =>
      pillDataList.map((pill) => (): void => {
        // Click closes only when this pill is already pinned-open;
        // otherwise click pins it (or opens + pins it).
        const shouldClose = openPillIdRef.current === pill.id && isPinnedRef.current;
        handleToggle(pill.id, !shouldClose);
      }),
    [pillDataList, handleToggle, isPinnedRef],
  );

  const handleItemFocus = useMemo(
    () => pillDataList.map((_pill, index) => (): void => setRawFocusedIndex(index)),
    [pillDataList],
  );

  const handleItemMouseEnter = useMemo(
    () => pillDataList.map((pill) => (): void => handlePillMouseEnter(pill.id)),
    [pillDataList, handlePillMouseEnter],
  );

  if (pillDataList.length === 0) return null;

  return (
    <Popover.Root
      open={isPopoverOpen}
      onOpenChange={(open) => {
        if (!open) setOpenPillId(null);
      }}
    >
      <PopoverAnchor virtualRef={anchorMeasurableRef} />
      <div
        ref={rowRef}
        className={isExpanded ? styles.expandedRowList : styles.pillRow}
        role="toolbar"
        aria-label="Tool calls"
        onKeyDown={handleKeyDown}
        data-testid={ElementIds.ALPHA_CHAT_TOOL_PILL_ROW}
      >
        {pillDataList.map((pill, index) => {
          const isOpen = openPillId === pill.id;
          if (isExpanded) {
            // Expanded rows open the popover on click only — no hover open.
            // The row already shows the popover-header content inline, so
            // the popover is mostly for the body output; there's no value
            // in opening it incidentally as the user sweeps the cursor.
            return (
              <div key={pill.id} className={styles.expandedHoverZone}>
                <AlphaExpandedToolRow
                  ref={handleItemRef[index]}
                  pillData={pill}
                  workspaceCodePath={workspaceCodePath}
                  isOpen={isOpen}
                  onToggle={handleItemToggle[index]!}
                  onFocus={handleItemFocus[index]}
                  tabIndex={index === focusedIndex ? 0 : -1}
                />
              </div>
            );
          }
          const isLast = index === pillDataList.length - 1;
          return (
            // Hover zone wraps each pill (and its trailing comma) so the
            // hit-area extends past the visible button. Adjacent zones
            // touch, so sliding across the row keeps the popover open.
            <span
              key={pill.id}
              className={styles.pillHoverZone}
              onMouseEnter={handleItemMouseEnter[index]}
              onMouseLeave={(e) => handlePillMouseLeave(e)}
            >
              <AlphaToolPill
                ref={handleItemRef[index]}
                pillData={pill}
                isOpen={isOpen}
                onToggle={handleItemToggle[index]!}
                onFocus={handleItemFocus[index]}
                tabIndex={index === focusedIndex ? 0 : -1}
              />
              {!isLast && <span className={styles.commaSeparator}>,</span>}
            </span>
          );
        })}
      </div>
      <Popover.Content
        side="bottom"
        sideOffset={4}
        align="start"
        collisionPadding={16}
        className={styles.popoverContent}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onFocusOutside={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => {
          if (rowRef.current?.contains(e.target as Node)) e.preventDefault();
        }}
        style={POPOVER_STYLE}
      >
        {openPill && (
          <div
            ref={popoverContentRef}
            data-alpha-tool-popover
            data-testid={ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER}
            onMouseEnter={handlePopoverMouseEnter}
            onMouseLeave={handlePopoverMouseLeave}
          >
            <PillPopoverContent pill={openPill} workspaceCodePath={workspaceCodePath} />
          </div>
        )}
      </Popover.Content>
    </Popover.Root>
  );
};

/**
 * The popover body for one pill in default density. Consults the plugin
 * tool-visualization registry first so a matching plugin overrides even the
 * dedicated Bash/Monitor command popover (which otherwise bypasses the shared
 * per-entry dispatch). With no plugin match, single-call Bash/Monitor pills use
 * the command popover; everything else falls to the shared multi-entry tool
 * popover — whose per-entry `ToolEntryContent` runs the same registry check, so
 * a plugin hit renders through it there too.
 */
const PillPopoverContent = ({
  pill,
  workspaceCodePath,
}: {
  pill: PillData;
  workspaceCodePath: string | null;
}): ReactElement => {
  const block = pill.blocks[0] ?? null;
  const result = pill.results[0] ?? null;
  const { visualization } = usePluginToolVisualization({ block, result, pillState: pill.state });

  if (visualization === null && (pill.label === "Bash" || pill.label === "Monitor")) {
    return (
      <AlphaCommandPopover
        toolName={pill.label}
        block={block ?? undefined}
        result={result ?? undefined}
        isExecuting={pill.state === "initializing"}
      />
    );
  }
  return <AlphaToolPopover pillData={pill} workspaceCodePath={workspaceCodePath} />;
};
