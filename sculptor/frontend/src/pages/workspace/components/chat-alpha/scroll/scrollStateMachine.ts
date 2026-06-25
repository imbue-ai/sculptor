/**
 * The single owner of alpha-chat scroll state.
 *
 * Wraps the two pure reducers (`scrollAuthority`, `layoutSettle`) plus a
 * top-level search-suppression guard in one ref-backed store. The scroll hooks
 * dispatch events into it and read its state; nothing else owns scroll booleans.
 *
 * Why a hand-rolled store rather than `useReducer`: the `following` phase
 * re-pins every animation frame during streaming. Turning those ticks into
 * React state updates would re-render the virtualized list (and tear down its
 * ResizeObserver) every frame — the exact reason the legacy code used refs. This
 * store keeps state in a closure, mirrors it to the DOM, and notifies only the
 * subscribers that opt in (via `useSyncExternalStore`), so high-frequency
 * transitions cost nothing for components that didn't select them.
 *
 * See docs/development/scroll_state_unification.md.
 */
import type { LayoutEvent, LayoutPhase } from "./layoutSettle.ts";
import { initialLayout, nextLayout } from "./layoutSettle.ts";
import type { ScrollAuthority, ScrollEvent } from "./scrollAuthority.ts";
import { initialAuthority, nextAuthority } from "./scrollAuthority.ts";

/** Reflected onto the scroll container so tests can await a phase deterministically. */
export const SCROLL_PHASE_ATTR = "data-scroll-phase";
/** "true" once authority is quiescent AND layout has converged. */
export const SCROLL_SETTLED_ATTR = "data-scroll-settled";

export type ScrollMachineState = {
  authority: ScrollAuthority;
  layout: LayoutPhase;
  isSuppressed: boolean;
  /**
   * The most recent sampled answer to "is the viewport within the at-bottom
   * threshold of the content bottom", written by the scroll/resize observers.
   * It is a captured observation of external geometry (like scrollTop itself),
   * not a mode — `projectAtBottom` only consults it for the phases where being
   * at the bottom is not already implied by the authority.
   */
  geometryAtBottom: boolean;
};

/**
 * Events that *enter* an auto-scroll mode. While search suppresses auto-scroll
 * these are dropped, so a search session never starts pinning/anchoring.
 * Completion events (turnAnchored, streamingStopped, restoreSettled, navEnded)
 * and the global ones (userScrolled, taskSwitched) always apply, so the machine
 * can always reach a settled state.
 */
const SUPPRESSIBLE_EVENTS: ReadonlySet<ScrollEvent["kind"]> = new Set(["newUserTurn", "reachedBottom"]);

/** The single definition of "everything has settled" — what the DOM signal and
 *  the tests key on. `following` counts as settled: it is a stable steady mode,
 *  not a transient one-shot scroll. */
export const isScrollSettled = (state: ScrollMachineState): boolean =>
  (state.authority.kind === "userControlled" || state.authority.kind === "following") && state.layout.kind === "stable";

/**
 * Whether the viewport is at the bottom, as the jump-to-bottom button and the
 * pin-to-bottom logic see it. Derived, never stored as its own flag: `following`
 * is at the bottom by definition (we are pinning there), `anchoringTurn` never is
 * (a new turn sits at the top while its response fills in below), and every other
 * phase defers to the last sampled geometry. Keeping the phase override here is
 * what stops the button from ever disagreeing with the scroll mode.
 */
export const projectAtBottom = (state: ScrollMachineState): boolean => {
  if (state.authority.kind === "following") return true;
  if (state.authority.kind === "anchoringTurn") return false;
  return state.geometryAtBottom;
};

export type ScrollStateMachine = {
  getState: () => ScrollMachineState;
  dispatch: (event: ScrollEvent) => void;
  dispatchLayout: (event: LayoutEvent) => void;
  setSuppressed: (suppressed: boolean) => void;
  /** Record the latest sampled at-bottness (from the scroll/resize observers). */
  setGeometryAtBottom: (atBottom: boolean) => void;
  subscribe: (listener: () => void) => () => void;
  /** Point the machine at the scroll container so it can reflect state to the DOM. */
  attach: (element: HTMLElement | null) => void;
};

export const createScrollStateMachine = (): ScrollStateMachine => {
  let state: ScrollMachineState = {
    authority: initialAuthority,
    layout: initialLayout,
    isSuppressed: false,
    geometryAtBottom: true,
  };
  let element: HTMLElement | null = null;
  const listeners = new Set<() => void>();

  const reflect = (): void => {
    if (element === null) return;
    element.setAttribute(SCROLL_PHASE_ATTR, state.authority.kind);
    element.setAttribute(SCROLL_SETTLED_ATTR, isScrollSettled(state) ? "true" : "false");
  };

  const commit = (next: ScrollMachineState): void => {
    state = next;
    reflect();
    for (const listener of listeners) listener();
  };

  return {
    getState: (): ScrollMachineState => state,
    dispatch: (event): void => {
      if (state.isSuppressed && SUPPRESSIBLE_EVENTS.has(event.kind)) return;
      const authority = nextAuthority(state.authority, event);
      if (authority === state.authority) return;
      commit({ ...state, authority });
    },
    dispatchLayout: (event): void => {
      const layout = nextLayout(state.layout, event);
      if (layout === state.layout) return;
      commit({ ...state, layout });
    },
    setSuppressed: (isSuppressed): void => {
      if (isSuppressed === state.isSuppressed) return;
      commit({ ...state, isSuppressed });
    },
    setGeometryAtBottom: (geometryAtBottom): void => {
      if (geometryAtBottom === state.geometryAtBottom) return;
      commit({ ...state, geometryAtBottom });
    },
    subscribe: (listener): (() => void) => {
      listeners.add(listener);
      return (): void => {
        listeners.delete(listener);
      };
    },
    attach: (nextElement): void => {
      element = nextElement;
      reflect();
    },
  };
};
