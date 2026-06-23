import { Checkbox, Flex, Popover, Text } from "@radix-ui/themes";
import classnames from "classnames";
import { useAtomValue, useSetAtom } from "jotai";
import { ChevronDown, ChevronRight, ListFilter, Search, SquareSlash } from "lucide-react";
import type { ReactElement } from "react";
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useImbueParams, useWorkspacePageParams } from "~/common/NavigateUtils";
import { chatActionsAtom } from "~/common/state/atoms/chatActions";
import type { SkillEntry } from "~/common/state/hooks/useSkills";
import { useSkills } from "~/common/state/hooks/useSkills";
import { useTaskSupportsSkills } from "~/common/state/hooks/useTaskHelpers";
import { PanelHeader } from "~/components/panels/PanelHeader";
import type { SkillType } from "~/components/skillBadge";
import { SkillChip } from "~/components/skills/SkillChip";
import { SkillHoverContent } from "~/components/skills/SkillHoverContent";
import { TooltipIconButton } from "~/components/TooltipIconButton";
import { openFileViewTabAtom } from "~/pages/workspace/components/diffPanel/atoms";

import styles from "./SkillsPanel.module.scss";
import { SkillsSearch } from "./SkillsSearch";

const SKILL_TYPE_LABELS: Record<SkillType, string> = {
  builtin: "Built-in",
  sculptor: "Sculptor",
  custom: "Custom Skills",
};

const FILTERABLE_TYPES: ReadonlyArray<SkillType> = ["builtin", "sculptor", "custom"];

// Order skills are grouped in the panel: user's own work first, framework
// defaults last. The same order drives keyboard selection, so ArrowDown
// from the bottom of "Custom" lands on the first "Sculptor" chip.
const TYPE_ORDER: Record<SkillType, number> = { custom: 0, sculptor: 1, builtin: 2 };

// Popover hover timing — mirrors AlphaPromptNavigator so the dot-rail and the
// skills panel feel consistent. A deliberate cold-open delay so a quick skim
// down the list doesn't fan popovers out, a snappy close, and zero-delay
// hand-off when the popover is already visible (cumulative-hover semantics
// across rows).
const OPEN_DELAY_MS = 420;
const CLOSE_DELAY_MS = 80;
const REOPEN_GRACE_PERIOD_MS = 300;
// While the list is scrolling, mouseenter events fire continuously as chips
// race under the cursor. Suppress popover open/swap until the user has been
// stationary for this long, so a quick scroll doesn't fan popovers out.
const SCROLL_END_DELAY_MS = 150;
// Minimum gap between the popover and the viewport top/bottom edges. Chips
// near the edge get clamped so the popover doesn't slide off-screen.
const VIEWPORT_EDGE_MARGIN_PX = 8;

type PopoverPosition = { x: number; y: number };

export const SkillsPanel = (): ReactElement => {
  const { skills: rawSkills, isLoading, error } = useSkills();
  const chatActions = useAtomValue(chatActionsAtom);
  const { workspaceID } = useWorkspacePageParams();
  const { taskID } = useImbueParams();
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  // A harness that doesn't support skills collapses the panel to an empty
  // state so the user sees a clear signal instead of stale skill content.
  // `?? true` keeps the panel populated before the task's capabilities have
  // loaded.
  const canRenderSkills = useTaskSupportsSkills(taskID ?? "") ?? true;
  const skills = useMemo(() => (canRenderSkills ? rawSkills : []), [canRenderSkills, rawSkills]);

  const [search, setSearch] = useState("");
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [activeFilters, setActiveFilters] = useState<ReadonlySet<SkillType>>(() => new Set());
  // Type-sections start expanded. Clicking a header toggles its membership
  // in this set; chips of types in the set are hidden but the header stays.
  const [collapsedGroups, setCollapsedGroups] = useState<ReadonlySet<SkillType>>(() => new Set());
  // Index of the currently keyboard-selected chip while the search input has
  // focus. Reset to 0 whenever the search opens or the visible list shifts so
  // the user always lands on the top match without re-pressing ArrowDown.
  const [selectedIndex, setSelectedIndex] = useState(0);

  const availableTypes = useMemo(() => new Set(skills.map((s) => s.type)), [skills]);

  // Single shared popover state. While the popover is visible, hovering a
  // different chip swaps content and animates position; while it's hidden,
  // hovering schedules an open after OPEN_DELAY_MS (or instantly if a sibling
  // popover closed within the grace period).
  const [popoverSkill, setPopoverSkill] = useState<SkillEntry | null>(null);
  const [popoverPosition, setPopoverPosition] = useState<PopoverPosition>({ x: 0, y: 0 });
  const [isPopoverVisible, setIsPopoverVisible] = useState(false);
  const [hasAnimated, setHasAnimated] = useState(false);

  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isOverChipRef = useRef(false);
  const isOverPopoverRef = useRef(false);
  const isPopoverVisibleRef = useRef(false);
  const lastClosedAtRef = useRef(0);
  const activeSkillRef = useRef<SkillEntry | null>(null);
  const activeChipElementRef = useRef<HTMLElement | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  // Measured rendered height of the popover, used to clamp its y so it
  // doesn't overflow the viewport top/bottom edges.
  const popoverContentRef = useRef<HTMLDivElement | null>(null);
  const [popoverHeight, setPopoverHeight] = useState(0);
  // Scroll-suppression state. While `isScrollingRef` is true, mouseenter on a
  // chip records its target into the `pending*` refs without touching the
  // active refs (which the visible-popover re-anchor reads). When the
  // scroll-end timer fires, pending → active and we resume normal hover.
  const isScrollingRef = useRef(false);
  const scrollEndTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSkillRef = useRef<SkillEntry | null>(null);
  const pendingChipElementRef = useRef<HTMLElement | null>(null);

  const clearOpenTimer = useCallback((): void => {
    if (openTimerRef.current !== null) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
  }, []);

  const clearCloseTimer = useCallback((): void => {
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const dismissPopover = useCallback((): void => {
    clearOpenTimer();
    clearCloseTimer();
    isPopoverVisibleRef.current = false;
    lastClosedAtRef.current = Date.now();
    setIsPopoverVisible(false);
    setPopoverSkill(null);
    setHasAnimated(false);
    activeSkillRef.current = null;
    activeChipElementRef.current = null;
  }, [clearOpenTimer, clearCloseTimer]);

  // Schedule a close that only commits if the mouse hasn't returned to a chip
  // or the popover by the time the timer fires.
  const schedulePopoverClose = useCallback((): void => {
    clearCloseTimer();
    closeTimerRef.current = setTimeout(() => {
      if (!isOverChipRef.current && !isOverPopoverRef.current) {
        clearOpenTimer();
        dismissPopover();
      }
    }, CLOSE_DELAY_MS);
  }, [clearCloseTimer, clearOpenTimer, dismissPopover]);

  const scheduleOpenForActiveChip = useCallback((): void => {
    if (openTimerRef.current !== null) return;
    const timeSinceClose = Date.now() - lastClosedAtRef.current;
    const delay = timeSinceClose < REOPEN_GRACE_PERIOD_MS ? 0 : OPEN_DELAY_MS;
    openTimerRef.current = setTimeout(() => {
      openTimerRef.current = null;
      const target = activeSkillRef.current;
      if (target === null || !isOverChipRef.current) return;
      setPopoverSkill(target);
      isPopoverVisibleRef.current = true;
      setIsPopoverVisible(true);
      // Enable the position transition only after the popover has been
      // committed at its initial anchor, so the first appearance lands in
      // place instead of sliding in, while later chip-to-chip swaps animate.
      requestAnimationFrame(() => setHasAnimated(true));
    }, delay);
  }, []);

  const handleChipMouseEnter = useCallback(
    (skill: SkillEntry, chipElement: HTMLElement): void => {
      isOverChipRef.current = true;
      clearCloseTimer();

      // While scrolling, just remember the latest hovered chip in pending
      // refs — don't open, swap, or move the active anchor. The scroll-end
      // handler promotes pending → active and resumes hover behavior once
      // the list is stationary.
      if (isScrollingRef.current) {
        pendingSkillRef.current = skill;
        pendingChipElementRef.current = chipElement;
        return;
      }

      activeChipElementRef.current = chipElement;
      const rect = chipElement.getBoundingClientRect();
      const nextPosition = { x: rect.left, y: rect.top + rect.height / 2 };

      if (isPopoverVisibleRef.current && activeSkillRef.current?.name !== skill.name) {
        // Already visible — instantly switch content, animate position to the new chip.
        activeSkillRef.current = skill;
        setPopoverSkill(skill);
        setPopoverPosition(nextPosition);
      } else if (!isPopoverVisibleRef.current) {
        // Retarget the pending open to this chip. If a timer is already running
        // from a previous chip, let it finish — it reads activeSkillRef when it
        // fires, so cumulative hover across rows opens for whichever chip the
        // mouse is on at that moment.
        activeSkillRef.current = skill;
        setPopoverPosition(nextPosition);
        scheduleOpenForActiveChip();
      }
    },
    [clearCloseTimer, scheduleOpenForActiveChip],
  );

  // Re-anchor the popover to the active chip when the panel scrolls, or
  // dismiss if the chip is now outside the visible scroll region. Also marks
  // the list as scrolling and schedules a scroll-end commit that resumes
  // popover hover behavior once the user has been stationary.
  const handleScrollAreaScroll = useCallback((): void => {
    const chipElement = activeChipElementRef.current;
    const scrollArea = scrollAreaRef.current;
    if (chipElement !== null && scrollArea !== null) {
      const chipRect = chipElement.getBoundingClientRect();
      const areaRect = scrollArea.getBoundingClientRect();
      if (chipRect.bottom < areaRect.top || chipRect.top > areaRect.bottom) {
        dismissPopover();
      } else {
        setPopoverPosition({ x: chipRect.left, y: chipRect.top + chipRect.height / 2 });
      }
    }

    isScrollingRef.current = true;
    // Cancel any pending open from before scroll started — we don't want a
    // popover to appear mid-scroll because a 420ms timer happened to fire.
    clearOpenTimer();
    if (scrollEndTimerRef.current !== null) {
      clearTimeout(scrollEndTimerRef.current);
    }
    scrollEndTimerRef.current = setTimeout(() => {
      scrollEndTimerRef.current = null;
      isScrollingRef.current = false;
      // If a chip was hovered during scroll, promote it to active now and
      // either swap the visible popover's content or schedule a fresh open.
      if (pendingSkillRef.current !== null && pendingChipElementRef.current !== null) {
        activeSkillRef.current = pendingSkillRef.current;
        activeChipElementRef.current = pendingChipElementRef.current;
        pendingSkillRef.current = null;
        pendingChipElementRef.current = null;
      }
      if (!isOverChipRef.current || activeSkillRef.current === null) return;
      const el = activeChipElementRef.current;
      if (el !== null) {
        const r = el.getBoundingClientRect();
        setPopoverPosition({ x: r.left, y: r.top + r.height / 2 });
      }

      if (isPopoverVisibleRef.current) {
        setPopoverSkill(activeSkillRef.current);
      } else {
        scheduleOpenForActiveChip();
      }
    }, SCROLL_END_DELAY_MS);
  }, [dismissPopover, clearOpenTimer, scheduleOpenForActiveChip]);

  const handleChipMouseLeave = useCallback((): void => {
    isOverChipRef.current = false;
    schedulePopoverClose();
  }, [schedulePopoverClose]);

  const handlePopoverMouseEnter = useCallback((): void => {
    isOverPopoverRef.current = true;
    clearOpenTimer();
    clearCloseTimer();
  }, [clearOpenTimer, clearCloseTimer]);

  const handlePopoverMouseLeave = useCallback((): void => {
    isOverPopoverRef.current = false;
    schedulePopoverClose();
  }, [schedulePopoverClose]);

  // Cleanup timers on unmount.
  useEffect(() => {
    return (): void => {
      clearOpenTimer();
      clearCloseTimer();
      if (scrollEndTimerRef.current !== null) {
        clearTimeout(scrollEndTimerRef.current);
      }
    };
  }, [clearOpenTimer, clearCloseTimer]);

  const handleClick = (skill: SkillEntry): void => {
    chatActions.insertSkill?.({ name: skill.name, description: skill.description, type: skill.type });
  };

  // For non-builtin skills the API always provides filePath, so the handler
  // is only wired up when filePath is defined.
  const handleOpenInSculptor = (skill: SkillEntry): void => {
    if (skill.filePath === null) return;
    openFileViewTab({ workspaceId: workspaceID, filePath: skill.filePath });
  };

  const handleSearchOpen = (): void => {
    setIsSearchOpen(true);
  };

  const handleSearchClose = (): void => {
    setIsSearchOpen(false);
    setSearch("");
  };

  const toggleFilter = (type: SkillType): void => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  const filteredSkills = useMemo(() => {
    const q = search.toLowerCase();
    const matches = skills.filter((s) => {
      if (activeFilters.size > 0 && !activeFilters.has(s.type)) return false;
      return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
    });
    // Group-then-alphabetize so the rendered order matches the section
    // headers below. visibleSkills (filtered through collapsed groups)
    // is what keyboard selection actually walks.
    return [...matches].sort((a, b) => {
      if (a.type !== b.type) return TYPE_ORDER[a.type] - TYPE_ORDER[b.type];
      return a.name.localeCompare(b.name);
    });
  }, [skills, search, activeFilters]);

  // Skills that are actually rendered as chips: filteredSkills minus any
  // chip whose type is in a collapsed group. selectedIndex / Enter / scroll
  // are all keyed off this array so the keyboard cursor only walks rows
  // the user can see.
  const visibleSkills = useMemo(
    () => filteredSkills.filter((s) => !collapsedGroups.has(s.type)),
    [filteredSkills, collapsedGroups],
  );

  const toggleGroup = useCallback((type: SkillType): void => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  // Dismiss the popover whenever the visible list shifts — search input,
  // filter toggle, group collapse, or upstream skill refetch. The chip the
  // popover anchors to may have moved or unmounted, leaving
  // `activeChipElementRef` pointing at a detached node and the popover
  // stranded at the wrong position. We key off `visibleSkills` alone and
  // read the active skill via ref: depending on `activeSkillRef`'s value
  // would re-fire on every chip hover and immediately dismiss the popover
  // we just opened.
  useEffect(() => {
    if (activeSkillRef.current !== null) {
      dismissPopover();
    }
  }, [visibleSkills, dismissPopover]);

  // Reset the keyboard selection to the top of the list whenever the visible
  // list shifts (typing, filter toggle, group collapse, refetch) or the
  // user opens search.
  useEffect(() => {
    setSelectedIndex(0);
  }, [visibleSkills, isSearchOpen]);

  const moveSelection = useCallback((delta: number): void => {
    setSelectedIndex((prev) => {
      const next = prev + delta;
      // Stop at the boundaries — wrapping would feel surprising in a long
      // skill list and ArrowDown-to-end / ArrowUp-to-top is a stronger
      // signal than the same key cycling.
      return Math.max(0, next);
    });
  }, []);

  // Clamp the bottom boundary against the current list length so ArrowDown
  // past the end stays put. Reading `visibleSkills.length` inside the
  // setter would race with the reset effect; doing it here in render is
  // simpler and accurate.
  const effectiveSelectedIndex = Math.min(selectedIndex, Math.max(0, visibleSkills.length - 1));

  const handleSearchEnter = useCallback((): void => {
    // Use the clamped index, not raw selectedIndex — moveSelection lets
    // selectedIndex grow past the end of the list, and the visual
    // selection lives on whatever effectiveSelectedIndex points at.
    const skill = visibleSkills[effectiveSelectedIndex];
    if (skill !== undefined && !chatActions.isDisabled) {
      chatActions.insertSkill?.({ name: skill.name, description: skill.description, type: skill.type });
    }
  }, [visibleSkills, effectiveSelectedIndex, chatActions]);

  // Map skill name → its position in `visibleSkills`. Chips in collapsed
  // groups aren't in this map, so they render with `selected={false}` and
  // are skipped by the keyboard navigator.
  const visibleIndexBySkillName = useMemo(() => {
    const map = new Map<string, number>();
    visibleSkills.forEach((skill, idx) => map.set(skill.name, idx));
    return map;
  }, [visibleSkills]);

  // Scroll the selected chip into view when the keyboard moves the
  // selection. block: "nearest" avoids jumping the list when the chip is
  // already visible. The function-presence guard keeps jsdom-based unit
  // tests from crashing — there's no scrollIntoView on Node DOM.
  useEffect(() => {
    if (!isSearchOpen) return;
    const scrollArea = scrollAreaRef.current;
    if (scrollArea === null) return;
    const chip = scrollArea.querySelector<HTMLElement>(
      `[data-testid="${ElementIds.SKILL_CHIP}"][data-selected="true"]`,
    );
    if (chip !== null && typeof chip.scrollIntoView === "function") {
      chip.scrollIntoView({ block: "nearest" });
    }
  }, [effectiveSelectedIndex, isSearchOpen]);

  // Measure the popover's rendered height so we can clamp its y inside the
  // viewport. Re-runs whenever the visible content or visibility changes;
  // window-resize is rare during a hover and other interactions close the
  // popover anyway.
  useLayoutEffect(() => {
    if (!isPopoverVisible || popoverContentRef.current === null) return;
    setPopoverHeight(popoverContentRef.current.offsetHeight);
  }, [isPopoverVisible, popoverSkill]);

  // Clamp the popover's vertical anchor so it stays inside the viewport. If
  // the popover is taller than the available space (extreme content + tiny
  // viewport), pin it to the top edge so the start of the description stays
  // visible. We read window.innerHeight directly — `position: fixed` makes
  // that the right reference frame.
  const clampedPopoverY =
    popoverHeight === 0
      ? popoverPosition.y
      : ((): number => {
          const half = popoverHeight / 2;
          const minY = VIEWPORT_EDGE_MARGIN_PX + half;
          const maxY = window.innerHeight - VIEWPORT_EDGE_MARGIN_PX - half;
          if (minY > maxY) return minY;
          return Math.max(minY, Math.min(popoverPosition.y, maxY));
        })();

  const isDisabled = chatActions.isDisabled;
  const isEmpty = filteredSkills.length === 0 && !isLoading;
  const hasActiveFilters = activeFilters.size > 0;

  return (
    <Flex direction="column" className={styles.panel} height="100%" data-testid={ElementIds.SKILLS_PANEL}>
      {isSearchOpen ? (
        <SkillsSearch
          query={search}
          onQueryChange={setSearch}
          onClose={handleSearchClose}
          onArrowDown={(): void => moveSelection(1)}
          onArrowUp={(): void => moveSelection(-1)}
          onEnter={handleSearchEnter}
        />
      ) : (
        <PanelHeader
          title="Skills"
          actions={
            <>
              <Popover.Root>
                <Popover.Trigger>
                  <TooltipIconButton
                    tooltipText="Filter by type"
                    aria-label="Filter by type"
                    className={hasActiveFilters ? styles.filterActive : undefined}
                  >
                    <ListFilter size={14} />
                  </TooltipIconButton>
                </Popover.Trigger>
                <Popover.Content side="bottom" align="end" sideOffset={4}>
                  <Flex direction="column" gap="2">
                    <Text size="2" weight="medium">
                      Filter by type
                    </Text>
                    {FILTERABLE_TYPES.map((type) =>
                      availableTypes.has(type) ? (
                        <Text as="label" size="2" key={type}>
                          <Flex align="center" gap="2">
                            <Checkbox
                              size="1"
                              checked={activeFilters.has(type)}
                              onCheckedChange={() => toggleFilter(type)}
                            />
                            {SKILL_TYPE_LABELS[type]}
                          </Flex>
                        </Text>
                      ) : null,
                    )}
                  </Flex>
                </Popover.Content>
              </Popover.Root>
              <TooltipIconButton
                tooltipText="Search skills"
                aria-label="Search skills"
                data-testid={ElementIds.SKILLS_PANEL_SEARCH_TOGGLE}
                onClick={handleSearchOpen}
              >
                <Search size={14} />
              </TooltipIconButton>
            </>
          }
        />
      )}

      <div ref={scrollAreaRef} className={styles.scrollArea} onScroll={handleScrollAreaScroll}>
        <Flex direction="column" px="1" py="2" gap="1">
          {isLoading ? (
            <Text size="2" color="gray">
              Loading…
            </Text>
          ) : error !== null ? (
            <Text size="2" color="red">
              {error}
            </Text>
          ) : isEmpty ? (
            <Flex direction="column" align="center" justify="center" className={styles.emptyState} py="2" gap="3">
              <SquareSlash size={48} strokeWidth={1.5} color="var(--gray-9)" />
              <Text size="3" weight="medium" color="gray">
                {!canRenderSkills ? "Skills unavailable" : search ? "No matching skills" : "No skills found"}
              </Text>
              {!search && canRenderSkills && (
                <Text size="2" color="gray" align="center" className={styles.emptyStateHint}>
                  Add custom skills in <code>.claude/skills/</code>
                </Text>
              )}
              {!canRenderSkills && (
                <Text size="2" color="gray" align="center" className={styles.emptyStateHint}>
                  This harness does not support skills.
                </Text>
              )}
            </Flex>
          ) : (
            <Flex direction="column" gap="0">
              {filteredSkills.map((skill, index) => {
                // Render a section header above the first chip of each
                // type. The skills are pre-sorted by [type, name], so a
                // type change between adjacent skills marks a boundary.
                const isFirstOfType = index === 0 || filteredSkills[index - 1].type !== skill.type;
                const isCollapsed = collapsedGroups.has(skill.type);
                const visibleIndex = visibleIndexBySkillName.get(skill.name);
                return (
                  <Fragment key={skill.name}>
                    {isFirstOfType && (
                      <div
                        className={styles.groupHeader}
                        role="button"
                        tabIndex={0}
                        aria-expanded={!isCollapsed}
                        onClick={(): void => toggleGroup(skill.type)}
                        onKeyDown={(e): void => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleGroup(skill.type);
                          }
                        }}
                      >
                        {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                        <span>{SKILL_TYPE_LABELS[skill.type]}</span>
                      </div>
                    )}
                    {!isCollapsed && (
                      <SkillChip
                        skill={skill}
                        onClick={(): void => handleClick(skill)}
                        onMouseEnter={(e): void => handleChipMouseEnter(skill, e.currentTarget)}
                        onMouseLeave={handleChipMouseLeave}
                        onOpenInSculptor={
                          skill.type !== "builtin" ? (): void => handleOpenInSculptor(skill) : undefined
                        }
                        disabled={isDisabled}
                        selected={isSearchOpen && visibleIndex === effectiveSelectedIndex}
                      />
                    )}
                  </Fragment>
                );
              })}
            </Flex>
          )}
        </Flex>
      </div>

      {isPopoverVisible && popoverSkill !== null && (
        <div
          className={classnames(styles.popoverHitArea, { [styles.popoverAnimated]: hasAnimated })}
          style={{ transform: `translate(${popoverPosition.x}px, ${clampedPopoverY}px)` }}
          onMouseEnter={handlePopoverMouseEnter}
          onMouseLeave={handlePopoverMouseLeave}
        >
          <div ref={popoverContentRef} className={styles.popover}>
            <SkillHoverContent
              id={`/${popoverSkill.name}`}
              skillDescription={popoverSkill.description}
              skillType={popoverSkill.type}
            />
          </div>
        </div>
      )}
    </Flex>
  );
};
