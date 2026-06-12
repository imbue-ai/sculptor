import { useVirtualizer } from "@tanstack/react-virtual";
import type { SuggestionProps } from "@tiptap/suggestion";
import classnames from "classnames";
import type { ReactElement, ReactNode } from "react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { ElementIds } from "~/api";

import styles from "./SuggestionList.module.scss";

export type SuggestionListRef = {
  onKeyDown: (props: { event: KeyboardEvent }) => boolean;
};

/**
 * Which action the user took to trigger the command handler.
 * - "select": Enter, Tab on a non-folder, or click — commit the item.
 * - "drillIn": Tab on a folder — narrow the search to that folder's contents.
 *
 * Attached transiently to the item object passed to `props.command` so that
 * suggestion configs (e.g. `createFileSuggestion`) can branch on it.
 */
export type SuggestionAction = "select" | "drillIn";

type SuggestionItemShape = {
  id: string;
  label: string;
  isSectionHeader?: boolean;
  isFirstInList?: boolean;
  [key: string]: unknown;
};

type SuggestionListContainerProps = {
  props: SuggestionProps;
  rowHeight: number;
  /**
   * Optional height for rows where `item.isSectionHeader` is true. When a list
   * interleaves non-selectable section headers with regular items, these rows
   * typically want slightly more vertical space than a plain item. Defaults
   * to `rowHeight` if not provided.
   */
  sectionHeaderHeight?: number;
  /**
   * Optional tighter height for the very first section header
   * (`item.isFirstInList`). The first header sits right at the popover's top
   * edge and doesn't need the extra top gap that separates later headers
   * from the preceding section's last item. Defaults to `sectionHeaderHeight`.
   */
  firstSectionHeaderHeight?: number;
  className?: string;
  emptyState: ReactNode;
  renderItem: (item: { id: string; label: string; [key: string]: unknown }) => ReactNode;
  itemTestId?: string;
  beforeList?: ReactNode;
  /** Optional element rendered below the scroll area (never overlaps items). */
  footer?: ReactNode;
  /**
   * "Step back one level" handler fired by Shift+Tab. Return `true` to
   * claim the event (one level was popped — keep the popover open); return
   * `false` to let the event fall through.
   *
   * This is the single entry point for hierarchical back navigation across
   * every picker (file path-mode up, entity type-drill back, plus-prefilter
   * category back). Nested pickers chain inner → outer by trying their own
   * step-back first and only invoking an outer `onExitToParent` when
   * internally at the root. Escape always closes the popover via TipTap's
   * default handling — it is *not* an alias for step-back.
   */
  onStepBack?: () => boolean;
  /**
   * When true, hovering a row sets the selected index — so mouse and
   * keyboard drive the same "active" state. Used by the skill picker to
   * keep its detail pane in sync with whichever row the user is focused
   * on, whether via arrow keys or mouse.
   */
  followHover?: boolean;
  /**
   * Predicate deciding whether a *mouse click* on a row drills into it
   * (action `"drillIn"`) instead of committing it (action `"select"`). The
   * keyboard exposes both gestures — Tab/ArrowRight drills, Enter commits —
   * but a click is a single gesture, so without this hint the mouse can only
   * ever commit and hierarchical rows (workspaces, folders) are unreachable
   * by mouse (SCU-1296). Return `true` for rows that carry a drill-in
   * affordance (e.g. a chevron). Defaults to treating every row as a leaf, so
   * a click commits.
   */
  isRowDrillable?: (item: SuggestionItemShape) => boolean;
  /**
   * Optional render prop for a right-hand pane next to the scroll area.
   * Invoked with the currently active item (or `undefined` if the list is
   * empty). Using a render prop means consumers don't need to track active
   * state separately — the container already owns `selectedIndex`, so
   * reading `items[selectedIndex]` here is the single source of truth.
   */
  sideContent?: (activeItem: SuggestionItemShape | undefined) => ReactNode;
};

const isSectionHeaderItem = (item: SuggestionItemShape | undefined): boolean => Boolean(item?.isSectionHeader);

/**
 * Walks from `start` in `direction` until landing on a selectable (non-header)
 * item. Returns the original index if every item is a header — shouldn't
 * happen in practice but keeps the caller from spinning.
 */
const findSelectableIndex = (items: ReadonlyArray<SuggestionItemShape>, start: number, direction: 1 | -1): number => {
  const n = items.length;
  if (n === 0) return 0;
  let i = ((start % n) + n) % n;
  for (let step = 0; step < n; step++) {
    if (!isSectionHeaderItem(items[i])) return i;
    i = (i + direction + n) % n;
  }
  return start;
};

export const SuggestionListContainer = forwardRef<SuggestionListRef, SuggestionListContainerProps>(
  (
    {
      props,
      rowHeight,
      sectionHeaderHeight,
      firstSectionHeaderHeight,
      className,
      emptyState,
      renderItem,
      itemTestId,
      beforeList,
      footer,
      onStepBack,
      followHover,
      isRowDrillable,
      sideContent,
    },
    ref,
  ): ReactElement => {
    const items = props.items as ReadonlyArray<SuggestionItemShape>;
    const [selectedIndex, setSelectedIndex] = useState(() => findSelectableIndex(items, 0, 1));
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    // When `items` changes identity, reset selection to the first selectable
    // row during render (the React-recommended pattern for "adjust state when
    // a prop changes" — avoids the stale intermediate render that a useEffect
    // would produce). See https://react.dev/learn/you-might-not-need-an-effect
    //
    // Track `prevItems` with `useState`, NOT `useRef`. Production wraps the
    // editor in `<StrictMode>`, which double-invokes function components in
    // dev. A ref mutation in the first run would persist into the second
    // run, making `prev === current` falsely true and silently dropping the
    // queued setSelectedIndex from the first run — selection then sticks on
    // the stale row even though items changed. `useState` is StrictMode-safe
    // because state updates are queued, not applied synchronously.
    const [prevItems, setPrevItems] = useState(items);
    if (prevItems !== items) {
      setPrevItems(items);
      const next = findSelectableIndex(items, 0, 1);
      if (next !== selectedIndex) setSelectedIndex(next);
    }

    const virtualizer = useVirtualizer({
      count: items.length,
      getScrollElement: () => scrollContainerRef.current,
      estimateSize: (index: number) => {
        const item = items[index];
        if (!isSectionHeaderItem(item)) return rowHeight;
        if (item?.isFirstInList) {
          return firstSectionHeaderHeight ?? sectionHeaderHeight ?? rowHeight;
        }
        return sectionHeaderHeight ?? rowHeight;
      },
      overscan: 5,
    });

    // Keep the selected item visible when navigating with keyboard. Skipped on
    // mount so the popover starts scrolled to the top — without this,
    // react-virtual sometimes shifts scroll to align the initially-selected
    // row, pushing a leading section header partway out of view.
    const didMountRef = useRef(false);
    useEffect(() => {
      if (!didMountRef.current) {
        didMountRef.current = true;
        return;
      }
      virtualizer.scrollToIndex(selectedIndex, { align: "auto" });
    }, [selectedIndex, virtualizer]);

    const selectItem = (index: number, action: SuggestionAction = "select"): void => {
      const item = items[index];
      if (!item || isSectionHeaderItem(item)) return;
      // Attach the action so the `command` handler can distinguish Tab
      // (drill into folder) from Enter/click (select). Suggestion configs
      // that don't care about this field simply ignore it.
      props.command({ ...item, action });
    };

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }): boolean => {
        if (event.key === "ArrowUp") {
          setSelectedIndex((prev) => findSelectableIndex(items, prev - 1, -1));
          return true;
        }

        if (event.key === "ArrowDown") {
          setSelectedIndex((prev) => findSelectableIndex(items, prev + 1, 1));
          return true;
        }

        if (event.key === "Enter") {
          if (props.items.length === 0) {
            return false;
          }
          selectItem(selectedIndex, "select");
          return true;
        }

        // Shift+Tab and ArrowLeft both pop one hierarchy level — keyboards
        // without a comfortable Tab reach (and users who prefer the cursor
        // pad) get the same step-back affordance. At the root with no
        // further level to pop, we swallow the event so the editor doesn't
        // steal focus, but keep the popover open — the user can press
        // Escape to close.
        if ((event.key === "Tab" && event.shiftKey) || event.key === "ArrowLeft") {
          onStepBack?.();
          return true;
        }

        // Tab and ArrowRight both drill into the active row (folder, type,
        // or workspace). For files / skills / commands without a deeper
        // level, the suggestion config falls through to a plain commit, so
        // the same key resolves an unambiguous action either way.
        if (event.key === "Tab" || event.key === "ArrowRight") {
          if (props.items.length === 0) {
            return false;
          }
          selectItem(selectedIndex, "drillIn");
          return true;
        }

        return false;
      },
    }));

    const sideContentNode = sideContent?.(items[selectedIndex]);
    const containerClass = classnames(styles.suggestionList, sideContentNode && styles.suggestionListSplit, className);
    const virtualItems = virtualizer.getVirtualItems();
    const totalSize = virtualizer.getTotalSize();

    if (props.items.length === 0) {
      return (
        <div className={containerClass} data-testid={ElementIds.MENTION_LIST}>
          {beforeList}
          {emptyState}
          {footer && <div className={styles.footer}>{footer}</div>}
        </div>
      );
    }

    const scrollArea = (
      <div ref={scrollContainerRef} className={styles.scrollArea}>
        {beforeList}
        <div style={{ height: totalSize, position: "relative" }}>
          {virtualItems.map((virtualRow) => {
            const item = items[virtualRow.index];
            const positionStyle = {
              position: "absolute" as const,
              top: 0,
              left: 0,
              width: "100%",
              height: virtualRow.size,
              transform: `translateY(${virtualRow.start}px)`,
            };
            if (isSectionHeaderItem(item)) {
              return (
                <div
                  key={item.id}
                  className={classnames(styles.sectionHeaderRow, item.isFirstInList && styles.sectionHeaderFirstRow)}
                  style={positionStyle}
                  aria-hidden
                >
                  {renderItem(item)}
                </div>
              );
            }
            return (
              <button
                type="button"
                key={item.id}
                className={classnames(styles.item, virtualRow.index === selectedIndex && styles.selected)}
                onClick={() => selectItem(virtualRow.index, isRowDrillable?.(item) ? "drillIn" : "select")}
                onMouseEnter={followHover ? (): void => setSelectedIndex(virtualRow.index) : undefined}
                data-testid={itemTestId}
                style={positionStyle}
              >
                {renderItem(item)}
              </button>
            );
          })}
        </div>
      </div>
    );

    return (
      <div className={containerClass} data-testid={ElementIds.MENTION_LIST}>
        {sideContentNode ? (
          <div className={styles.twoPane}>
            <div className={styles.leftPane}>{scrollArea}</div>
            <div className={styles.rightPane}>{sideContentNode}</div>
          </div>
        ) : (
          scrollArea
        )}
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    );
  },
);
