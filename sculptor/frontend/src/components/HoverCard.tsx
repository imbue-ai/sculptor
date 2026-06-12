import { HoverCard as RadixHoverCard } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import styles from "./HoverCard.module.scss";

// Shared hover-group coordination. When `group` is set, each HoverCard reports
// its open/close to a module-level store keyed by the group id. Any card in an
// "active" group (something currently open, or closed within the last
// REOPEN_GRACE_PERIOD_MS) opens with zero delay — so sliding the mouse from
// one chip to the next feels seamless. The group also tracks the most recent
// opener id; when it changes, sibling cards that are still open force-close
// themselves so only one popover in the group is ever visible. Ported from
// AlphaPromptNavigator.
const REOPEN_GRACE_PERIOD_MS = 300;

type GroupState = {
  openCount: number;
  lastClosedAt: number;
  activeOpenerId: symbol | null;
  listeners: Set<() => void>;
};

const groupStates = new Map<string, GroupState>();

const getGroupState = (groupId: string): GroupState => {
  let state = groupStates.get(groupId);
  if (!state) {
    state = { openCount: 0, lastClosedAt: 0, activeOpenerId: null, listeners: new Set() };
    groupStates.set(groupId, state);
  }
  return state;
};

const notifyGroup = (groupId: string): void => {
  getGroupState(groupId).listeners.forEach((listener) => listener());
};

const subscribeToGroup = (groupId: string, listener: () => void): (() => void) => {
  const state = getGroupState(groupId);
  state.listeners.add(listener);
  return (): void => {
    state.listeners.delete(listener);
  };
};

const isGroupActive = (groupId: string): boolean => {
  const state = getGroupState(groupId);
  if (state.openCount > 0) return true;
  return Date.now() - state.lastClosedAt < REOPEN_GRACE_PERIOD_MS;
};

const getActiveOpenerId = (groupId: string): symbol | null => getGroupState(groupId).activeOpenerId;

const registerGroupOpen = (groupId: string, openerId: symbol): void => {
  const state = getGroupState(groupId);
  state.openCount += 1;
  state.activeOpenerId = openerId;
  notifyGroup(groupId);
};

const registerGroupClose = (groupId: string, openerId: symbol): void => {
  const state = getGroupState(groupId);
  state.openCount = Math.max(0, state.openCount - 1);
  state.lastClosedAt = Date.now();
  if (state.activeOpenerId === openerId) {
    state.activeOpenerId = null;
  }
  notifyGroup(groupId);
  // Re-notify once the grace period expires so subscribers recompute
  // `isGroupActive` and drop back to the default open delay. This timer
  // intentionally has no cancellation — it only reads module-level state
  // and is a no-op if no listeners remain.
  setTimeout(() => notifyGroup(groupId), REOPEN_GRACE_PERIOD_MS + 10);
};

const noopSubscribe = (): (() => void) => (): void => {};
const falseSnapshot = (): boolean => false;
const nullOpenerSnapshot = (): symbol | null => null;

const useIsGroupActive = (group: string | undefined): boolean => {
  // Memoize on `group` so useSyncExternalStore doesn't unsubscribe and
  // re-subscribe on every parent render. Without this, passing inline
  // arrows would churn the group's listener Set each render.
  const subscribe = useMemo(
    () => (group ? (listener: () => void): (() => void) => subscribeToGroup(group, listener) : noopSubscribe),
    [group],
  );
  const getSnapshot = useMemo(() => (group ? (): boolean => isGroupActive(group) : falseSnapshot), [group]);
  return useSyncExternalStore(subscribe, getSnapshot, falseSnapshot);
};

const useActiveOpenerId = (group: string | undefined): symbol | null => {
  const subscribe = useMemo(
    () => (group ? (listener: () => void): (() => void) => subscribeToGroup(group, listener) : noopSubscribe),
    [group],
  );
  const getSnapshot = useMemo(
    () => (group ? (): symbol | null => getActiveOpenerId(group) : nullOpenerSnapshot),
    [group],
  );
  return useSyncExternalStore(subscribe, getSnapshot, nullOpenerSnapshot);
};

type HoverCardProps = {
  trigger: ReactNode;
  content: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  sideOffset?: number;
  alignOffset?: number;
  openDelay?: number;
  closeDelay?: number;
  /**
   * Optional hover-group id. Cards sharing a group open instantly once any
   * sibling is open (or was open within the last 300ms), so moving the mouse
   * between adjacent chips doesn't re-trigger the full open delay.
   */
  group?: string;
  /**
   * When true, pins the card open regardless of hover/focus state. Hover
   * state is still tracked in the background so the card stays open if the
   * user hovers while pinned and remains on-hover behavior if `forceOpen`
   * flips back to false.
   */
  forceOpen?: boolean;
  /**
   * When true, hovering the trigger no longer opens the card. `forceOpen`
   * still opens it (so a node-selected chip remains pinned), but ambient
   * hover is suppressed — used by the mention chips in a Tiptap editor
   * while the user has a range selection active, to keep popovers from
   * fanning out across the selection.
   */
  suppressHover?: boolean;
};

export const HoverCard = ({
  trigger,
  content,
  side,
  align,
  sideOffset = 8,
  alignOffset,
  openDelay = 200,
  closeDelay = 150,
  group,
  forceOpen = false,
  suppressHover = false,
}: HoverCardProps): ReactElement => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const closeTimerRef = useRef<number>();
  // Tracks whether this card is currently counted in its group. Prevents
  // double-register and ensures cleanup on unmount-while-open.
  const registeredRef = useRef(false);
  // Stable per-instance id used to claim the "active opener" slot inside the
  // group, so siblings can detect that a different card opened and close
  // themselves. Lazy-init via a ref so we only allocate one Symbol per mount.
  const openerIdRef = useRef<symbol | null>(null);
  openerIdRef.current ??= Symbol("hover-card-opener");
  // Suppress the first hover-open when the trigger mounts under a stationary
  // mouse — e.g. a /- or @-mention chip that appears at the text cursor,
  // exactly where the user's pointer happens to be resting. Browsers fire
  // `pointerenter` on the new element even without a real user move, which
  // would otherwise pop the card open without a deliberate hover.
  const hasUserMovedSinceMountRef = useRef(false);

  useEffect(() => {
    const markMoved = (): void => {
      hasUserMovedSinceMountRef.current = true;
    };
    document.addEventListener("mousemove", markMoved, { once: true });
    return (): void => document.removeEventListener("mousemove", markMoved);
  }, []);

  const isGroupHoverActive = useIsGroupActive(group);
  const activeOpenerId = useActiveOpenerId(group);
  const isEffectiveOpenDelay = group && isGroupHoverActive ? 0 : openDelay;
  // Within a group, close immediately on leave. Otherwise Radix's default
  // close delay can leave card A open while the user has already moved to
  // chip B and B's open has registered — both popovers visible at once.
  // The activeOpenerId effect below force-closes siblings as a backstop, but
  // it runs a render after the open registers, which is too late to avoid the
  // visible double. Group popovers are informational, so the standard
  // trigger→content hover grace doesn't apply.
  const effectiveCloseDelay = group ? 0 : closeDelay;

  const cancelClose = (): void => clearTimeout(closeTimerRef.current);

  const scheduleClose = (): void => {
    closeTimerRef.current = window.setTimeout(() => setIsOpen(false), 0);
  };

  // Intercept Radix's hover callbacks through the timer so hover-close
  // doesn't bypass an active focus session inside the content.
  const handleOpenChange = (next: boolean): void => {
    if (next) {
      if (suppressHover) return;
      if (!hasUserMovedSinceMountRef.current) {
        // Suppress hover-opens until the user actually moves the mouse.
        // Focus-driven opens still fire via the onFocus handler below.
        return;
      }
      cancelClose();
      setIsOpen(true);
    } else {
      scheduleClose();
    }
  };

  // `isOpen` reflects hover/focus state and lags behind prop changes, so mask
  // it out while `suppressHover` is on. Without the mask, a popover that was
  // already open when a range selection started would stay visible.
  const isEffectiveOpen = forceOpen || (isOpen && !suppressHover);

  // Keep the shared group in sync with this card's effective open state so
  // pinned-open cards participate in the same zero-delay hand-off as
  // hover-opened ones.
  useEffect(() => {
    if (!group) return;
    const openerId = openerIdRef.current;
    if (openerId === null) return;
    if (isEffectiveOpen && !registeredRef.current) {
      registerGroupOpen(group, openerId);
      registeredRef.current = true;
    } else if (!isEffectiveOpen && registeredRef.current) {
      registerGroupClose(group, openerId);
      registeredRef.current = false;
    }
  }, [isEffectiveOpen, group]);

  // Enforce single-open semantics within a group: when a sibling claims the
  // active-opener slot, close ours. Without this, a hover-leave that races
  // with a hover-enter on the next chip can leave both popovers visible.
  // `forceOpen` cards (e.g. pinned mention chips) opt out — they stay open
  // regardless of sibling activity.
  useEffect(() => {
    if (!group || forceOpen) return;
    if (!isOpen) return;
    if (activeOpenerId === null) return;
    if (activeOpenerId === openerIdRef.current) return;
    setIsOpen(false);
  }, [activeOpenerId, group, forceOpen, isOpen]);

  useEffect(
    () => (): void => {
      clearTimeout(closeTimerRef.current);
      const openerId = openerIdRef.current;
      if (group && openerId !== null && registeredRef.current) {
        registerGroupClose(group, openerId);
        registeredRef.current = false;
      }
    },
    [group],
  );

  return (
    <RadixHoverCard.Root
      open={isEffectiveOpen}
      onOpenChange={handleOpenChange}
      openDelay={isEffectiveOpenDelay}
      closeDelay={effectiveCloseDelay}
    >
      <RadixHoverCard.Trigger
        onFocus={(): void => {
          if (suppressHover) return;
          cancelClose();
          setIsOpen(true);
        }}
        onBlur={scheduleClose}
      >
        {trigger}
      </RadixHoverCard.Trigger>
      <RadixHoverCard.Content
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
        className={styles.content}
        onFocusCapture={cancelClose}
        onBlurCapture={scheduleClose}
      >
        {content}
      </RadixHoverCard.Content>
    </RadixHoverCard.Root>
  );
};
