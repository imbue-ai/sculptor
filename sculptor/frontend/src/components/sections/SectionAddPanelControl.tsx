// The section-header "+" control. Unlike the empty-state AddPanelDropdown (plain
// click-to-open), this one is hover-driven:
//
//   - EVERY section: hovering the "+" opens the add-panel menu instantly (transient —
//     it closes shortly after the pointer leaves the button and the menu, unless pinned).
//   - CENTER section: a plain CLICK quick-adds a new agent of the last-used type (the
//     same action as the menu's "New {recent} agent" row) instead of toggling the menu.
//     A tooltip naming that action fades in after a ~1s dwell, alongside the open menu.
//   - NON-CENTER sections (left / right / bottom): a click PINS the menu open (it
//     survives the pointer leaving) until the "+" is clicked again. There is no
//     click-to-quick-add here: the one-click shortcut is reserved for the center (the
//     primary place to spin up agents). The side menus still create agents/panels the
//     normal way — by picking from the menu, which targets the requesting section.
//
// The menu contents themselves are the shared AddPanelMenuContent (identical to the
// empty-state dropdown). Radix's own click/keyboard toggle on the trigger is
// suppressed so this component fully owns the open state.

import { DropdownMenu, IconButton, Tooltip } from "@radix-ui/themes";
import { Plus } from "lucide-react";
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, ReactElement } from "react";
import { useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";

import { AddPanelMenuContent } from "./AddPanelDropdown.tsx";
import type { SubSectionId } from "./sectionTypes.ts";
import { toSection } from "./sectionTypes.ts";
import { useAddPanelActions } from "./useAddPanelActions.ts";

// Grace period after the pointer leaves the "+"/menu before a transient (unpinned) menu
// closes — long enough to cross the gap from the button to the menu without it snapping
// shut, short enough that it doesn't linger.
const MENU_CLOSE_DELAY_MS = 150;
// The center quick-add tooltip is a slower hint than the instant menu, so it only
// surfaces on a deliberate dwell rather than a cursor sweep across the header.
const QUICK_ADD_TOOLTIP_DELAY_MS = 1000;

const CENTER_TOOLTIP = "Click to quick-add an agent";
const DEFAULT_TOOLTIP = "Add panel";

export const SectionAddPanelControl = ({
  subSection,
  className,
}: {
  subSection: SubSectionId;
  className?: string;
}): ReactElement => {
  const isCenter = toSection(subSection) === "center";
  const actions = useAddPanelActions();

  const [isOpen, setIsOpen] = useState(false);
  const [isTooltipOpen, setIsTooltipOpen] = useState(false);
  // Pinned lives in a ref (not state) because the deferred close callback reads it
  // after the click that set it; it drives no rendering of its own.
  const pinnedRef = useRef(false);
  // Set on a trigger pointer-down so the Radix-driven open-toggle it produces is ignored
  // in handleOpenChange — a pointer click is handled by `activate`, not Radix's toggle.
  const suppressToggleRef = useRef(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const tooltipTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clearCloseTimer = (): void => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = undefined;
    }
  };

  const clearTooltipTimer = (): void => {
    if (tooltipTimer.current) {
      clearTimeout(tooltipTimer.current);
      tooltipTimer.current = undefined;
    }
  };

  const scheduleClose = (): void => {
    if (pinnedRef.current) {
      return; // a pinned menu stays open until it is explicitly toggled off
    }
    clearCloseTimer();
    closeTimer.current = setTimeout(() => setIsOpen(false), MENU_CLOSE_DELAY_MS);
  };

  const handleEnter = (): void => {
    clearCloseTimer();
    setIsOpen(true); // instant
    if (isCenter) {
      clearTooltipTimer();
      tooltipTimer.current = setTimeout(() => setIsTooltipOpen(true), QUICK_ADD_TOOLTIP_DELAY_MS);
    }
  };

  const handleLeave = (): void => {
    // Clear a stray suppress flag if a press dragged off the button without a click.
    suppressToggleRef.current = false;
    clearTooltipTimer();
    setIsTooltipOpen(false);
    scheduleClose();
  };

  // The trigger's primary action: quick-add in the center, pin-toggle elsewhere.
  const activate = (): void => {
    clearTooltipTimer();
    setIsTooltipOpen(false);
    if (isCenter) {
      clearCloseTimer();
      pinnedRef.current = false;
      setIsOpen(false);
      actions.createRecentAgent(subSection);
      return;
    }
    const isNextPinned = !pinnedRef.current;
    pinnedRef.current = isNextPinned;
    clearCloseTimer();
    setIsOpen(isNextPinned);
  };

  // A real pointer click (detail >= 1) runs `activate`; a keyboard-synthesized click
  // (detail === 0) is left to Radix's own keyboard handling (Enter / ArrowDown open the
  // menu), so the keyboard path stays standard and accessible.
  const handleClick = (event: ReactMouseEvent): void => {
    suppressToggleRef.current = false; // defensive: never let the flag outlive its click
    if (event.detail === 0) {
      return;
    }
    activate();
  };

  const handleOpenChange = (nextOpen: boolean): void => {
    // A pointer click on the trigger makes Radix fire its own open-toggle here; we handle
    // that click through `activate`, so drop the flagged toggle. Do NOT clear the flag here
    // — one trigger click can fire onOpenChange more than once (the dismissable layer's
    // outside-detection AND the trigger toggle), and every one of them must be dropped; the
    // flag is cleared by the click handler / pointer-leave instead. Genuine Radix-driven
    // changes — Escape, outside-click, item-select, keyboard — fall through and are honoured.
    if (suppressToggleRef.current) {
      return;
    }

    if (nextOpen) {
      // A Radix-driven open (e.g. keyboard, right after a hover-out) must cancel any close
      // the hover-out scheduled — otherwise that timer fires and closes the just-opened menu.
      clearCloseTimer();
    } else {
      pinnedRef.current = false;
      clearTooltipTimer();
      setIsTooltipOpen(false);
    }
    setIsOpen(nextOpen);
  };

  // A section header unmounts on collapse / workspace switch / the center quick-add's own
  // navigation; clear any pending timer so its callback can't setState after unmount.
  useEffect((): (() => void) => {
    return (): void => {
      if (closeTimer.current) {
        clearTimeout(closeTimer.current);
      }

      if (tooltipTimer.current) {
        clearTimeout(tooltipTimer.current);
      }
    };
  }, []);

  return (
    <DropdownMenu.Root modal={false} open={isOpen} onOpenChange={handleOpenChange}>
      <Tooltip content={isCenter ? CENTER_TOOLTIP : DEFAULT_TOOLTIP} open={isCenter ? isTooltipOpen : undefined}>
        <DropdownMenu.Trigger>
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            className={className}
            // Keyboard / assistive tech open the menu (this is a menu trigger); a pointer
            // click quick-adds. Name it for the menu it opens, not just the pointer action.
            aria-label={isCenter ? "Add agent or panel" : "Add panel"}
            data-testid={`${ElementIds.SECTION_ADD_PANEL_BUTTON}-${subSection}`}
            onPointerEnter={handleEnter}
            onPointerLeave={handleLeave}
            // Flag the pointer-down (capture phase, so the flag is set before Radix's
            // bubble-phase toggle fires onOpenChange) so handleOpenChange drops Radix's
            // pointer toggle. `activate` is the sole authority for a pointer click. Only a
            // primary press arms it (mirroring Radix's own `button === 0` guard), so a
            // right/middle-click can't leave the flag stuck and swallow a later change.
            onPointerDownCapture={(event: ReactPointerEvent) => {
              if (event.button === 0) {
                suppressToggleRef.current = true;
              }
            }}
            onClick={handleClick}
          >
            <Plus size={14} />
          </IconButton>
        </DropdownMenu.Trigger>
      </Tooltip>
      <AddPanelMenuContent subSection={subSection} onPointerEnter={clearCloseTimer} onPointerLeave={handleLeave} />
    </DropdownMenu.Root>
  );
};
