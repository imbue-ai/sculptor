import type { DragEndEvent, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import { closestCenter, DndContext, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToHorizontalAxis, restrictToParentElement } from "@dnd-kit/modifiers";
import { arrayMove, horizontalListSortingStrategy, SortableContext } from "@dnd-kit/sortable";
import { Box } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { OverlayScrollbar } from "~/components/tabs/OverlayScrollbar";
import { SortableTab } from "~/components/tabs/SortableTab";
import type { DropIndicator, TabBarProps, TabDefinition } from "~/components/tabs/types";

import styles from "./TabBar.module.scss";

const DEFAULT_TAB_WIDTH = 200;
const MIN_TAB_WIDTH = 100;

export const TabBar = ({
  tabs,
  openTabIds,
  activeTabId,
  maxTabWidth = DEFAULT_TAB_WIDTH,
  onActivate,
  onClose,
  onReorder,
  children,
  rightContent,
  className,
  tabBarClassName,
  onDoubleClick,
  alwaysCloseable = false,
  variant = "default",
  contextMenuContent,
  scrollTrigger,
  closeReplacesIcon = false,
  dndMode = "owned",
  externalDragActive = false,
}: TabBarProps): ReactElement => {
  const isCompact = variant === "compact";
  // In "shared" mode an ancestor DndContext (PanelDndProvider) owns the drag, so
  // this TabBar renders only the SortableContext — no local DndContext, no local
  // drag state, no local drop indicators.
  const isShared = dndMode === "shared";

  const [dragState, setDragState] = useState<{ activeId: string | null; overId: string | null }>({
    activeId: null,
    overId: null,
  });
  const [containerWidth, setContainerWidth] = useState<number>(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const childrenRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  // ResizeObserver for responsive tab widths (default variant only)
  useEffect((): (() => void) | void => {
    if (isCompact) return;

    const element = containerRef.current;
    if (!element) return;

    let rafId: number | undefined;
    const observer = new ResizeObserver((): void => {
      if (rafId !== undefined) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame((): void => {
        setContainerWidth(element.clientWidth);
      });
    });

    observer.observe(element);
    return (): void => {
      observer.disconnect();
      if (rafId !== undefined) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [isCompact]);

  // Auto-scroll active tab into view
  useEffect((): void => {
    if (!scrollContainerRef.current) return;

    const activeElement = scrollContainerRef.current.querySelector(`[data-tab-id="${activeTabId}"]`);
    if (activeElement) {
      activeElement.scrollIntoView?.({ behavior: "smooth", block: "nearest", inline: "nearest" });
    }
  }, [activeTabId, scrollTrigger]);

  // Convert vertical wheel to horizontal scroll (default variant)
  useEffect((): (() => void) | void => {
    if (isCompact) return;

    const el = scrollContainerRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent): void => {
      if (e.deltaX !== 0) return;
      if (e.deltaY === 0) return;

      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return (): void => {
      el.removeEventListener("wheel", handleWheel);
    };
  }, [isCompact]);

  const tabMap = useMemo((): Map<string, TabDefinition> => {
    return new Map<string, TabDefinition>(tabs.map((t) => [t.id, t]));
  }, [tabs]);

  const openTabs = useMemo((): Array<TabDefinition> => {
    return openTabIds.flatMap((id) => {
      const tab = tabMap.get(id);
      return tab ? [tab] : [];
    });
  }, [tabMap, openTabIds]);

  const activeTab = useMemo((): TabDefinition | undefined => {
    return openTabs.find((t) => t.id === activeTabId);
  }, [openTabs, activeTabId]);

  const tabWidth = useMemo((): number | undefined => {
    // Compact variant: no width management
    if (isCompact) return undefined;

    if (containerWidth === 0) return maxTabWidth;

    const childrenWidth = childrenRef.current?.offsetWidth ?? 0;
    const availableWidth = containerWidth - childrenWidth;
    const naturalWidth = Math.min(availableWidth / openTabIds.length, maxTabWidth);

    return Math.max(MIN_TAB_WIDTH, naturalWidth);
  }, [containerWidth, openTabIds.length, maxTabWidth, isCompact]);

  const isCloseable = alwaysCloseable || openTabIds.length > 1;
  const isDragActive = dragState.activeId !== null || externalDragActive;

  const getDropIndicator = useCallback(
    (tabId: string): DropIndicator | undefined => {
      if (!dragState.activeId || !dragState.overId) return undefined;
      if (tabId !== dragState.overId) return undefined;

      const activeIndex = openTabIds.indexOf(dragState.activeId);
      const overIndex = openTabIds.indexOf(dragState.overId);
      if (activeIndex === -1 || overIndex === -1) return undefined;

      return activeIndex <= overIndex ? "right" : "left";
    },
    [dragState.activeId, dragState.overId, openTabIds],
  );

  const handleDragStart = (event: DragStartEvent): void => {
    setDragState({ activeId: event.active.id as string, overId: null });
  };

  const handleDragMove = (event: DragMoveEvent): void => {
    const overId = event.over?.id as string | undefined;
    setDragState((prev) => ({ ...prev, overId: overId ?? null }));
  };

  const handleDragEnd = (event: DragEndEvent): void => {
    setDragState({ activeId: null, overId: null });
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = openTabIds.indexOf(active.id as string);
      const newIndex = openTabIds.indexOf(over.id as string);
      onReorder?.(arrayMove(openTabIds, oldIndex, newIndex));
    }
  };

  const handleDragCancel = (): void => {
    setDragState({ activeId: null, overId: null });
  };

  const hasContent = tabs.some((t) => t.content !== undefined);

  const tabBarClass = isCompact
    ? `${styles.tabBarCompact} ${tabBarClassName ?? ""}`
    : `${styles.tabBar} ${tabBarClassName ?? ""}`;

  const rowContent = (
    <div ref={containerRef} className={tabBarClass} role="tablist">
      {isCompact ? (
        <>
          <div
            ref={scrollContainerRef}
            className={`${styles.compactScroll} ${rightContent ? styles.compactScrollFill : ""}`}
          >
            <SortableContext items={openTabIds} strategy={horizontalListSortingStrategy}>
              {openTabs.map((tab) => (
                <SortableTab
                  key={tab.id}
                  tab={tab}
                  isActive={tab.id === activeTabId}
                  isCloseable={isCloseable}
                  isDragActive={isDragActive}
                  dropIndicator={getDropIndicator(tab.id)}
                  onActivate={onActivate}
                  onClose={onClose}
                  onDoubleClick={onDoubleClick}
                  variant={variant}
                  contextMenuContent={contextMenuContent}
                  closeReplacesIcon={closeReplacesIcon}
                  ghostWhenDragging={isShared}
                />
              ))}
            </SortableContext>
          </div>
          {rightContent ? (
            <div className={styles.compactRightContent}>
              {children}
              {rightContent}
            </div>
          ) : (
            children
          )}
        </>
      ) : (
        <>
          <div className={styles.defaultScrollWrapper}>
            <div ref={scrollContainerRef} className={styles.defaultScroll}>
              <SortableContext items={openTabIds} strategy={horizontalListSortingStrategy}>
                {openTabs.map((tab) => (
                  <SortableTab
                    key={tab.id}
                    tab={tab}
                    isActive={tab.id === activeTabId}
                    isCloseable={isCloseable}
                    isDragActive={isDragActive}
                    width={tabWidth}
                    dropIndicator={getDropIndicator(tab.id)}
                    onActivate={onActivate}
                    onClose={onClose}
                    onDoubleClick={onDoubleClick}
                    contextMenuContent={contextMenuContent}
                    closeReplacesIcon={closeReplacesIcon}
                    ghostWhenDragging={isShared}
                  />
                ))}
              </SortableContext>
            </div>
            <OverlayScrollbar scrollRef={scrollContainerRef} className={styles.overlayScrollTrack} />
          </div>
          {children && (
            <Box ref={childrenRef} className={styles.controls} pl="2">
              {children}
            </Box>
          )}
        </>
      )}
    </div>
  );

  // "owned" mode wraps the row in its own DndContext for within-strip reorder;
  // "shared" mode relies on the ancestor PanelDndProvider's context instead.
  const tabBarRow = isShared ? (
    rowContent
  ) : (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[restrictToHorizontalAxis, restrictToParentElement]}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      {rowContent}
    </DndContext>
  );

  if (!hasContent) {
    return tabBarRow;
  }

  return (
    <div className={`${styles.container} ${className ?? ""}`}>
      {tabBarRow}
      <div role="tabpanel" data-testid="tab-content" className={styles.contentArea}>
        {activeTab?.content}
      </div>
    </div>
  );
};
