/**
 * Scroll authority: the explicit answer to "who is moving the chat's
 * scrollTop right now, and why".
 *
 * Exactly one actor owns scrollTop at any instant. Programmatic phases are
 * transient and always resolve back to `userControlled`; a genuine user input
 * preempts any of them. Modelling this as a single discriminated union (instead
 * of a handful of independent boolean refs) makes illegal combinations such as
 * "restoring AND following" unrepresentable, and puts the whole sequence in one
 * pure, exhaustively-typed reducer.
 *
 * See docs/development/scroll_state_unification.md for the rationale.
 */

export type ScrollAuthority =
  // Settled: the user owns scrollTop and nothing programmatic is in flight.
  | { kind: "userControlled" }
  // An agent switch is restoring the saved scroll position.
  | { kind: "restoring"; agentId: string }
  // A new user message is being animated/placed at the top of the viewport.
  | { kind: "anchoringTurn"; anchorIndex: number }
  // Pinned to the bottom, following streaming output.
  | { kind: "following" }
  // Keyboard prompt navigation is driving the scroll.
  | { kind: "navigating"; promptIndex: number };

/**
 * Inputs to the authority machine, named by *cause* rather than effect — the
 * reducer is the single place that decides what each cause does in each state.
 */
export type ScrollEvent =
  | { kind: "agentSwitched"; agentId: string }
  | { kind: "restoreSettled" }
  | { kind: "userScrolled" }
  | { kind: "newUserTurn"; index: number }
  | { kind: "turnAnchored" }
  | { kind: "reachedBottom" }
  | { kind: "streamingStopped" }
  | { kind: "navStarted"; promptIndex: number }
  | { kind: "navMoved"; promptIndex: number }
  | { kind: "navEnded" };

export const initialAuthority: ScrollAuthority = { kind: "userControlled" };

/** Compile-time exhaustiveness guard: adding a `ScrollAuthority` kind without a
 *  matching case below becomes a type error here rather than a silent fallthrough. */
const assertNever = (value: never): never => {
  throw new Error(`Unhandled scroll authority state: ${JSON.stringify(value)}`);
};

/**
 * The complete specification of the scroll-authority sequence: a pure, total
 * transition function. Returns the same reference on a no-op so callers can
 * detect "nothing changed" by identity.
 */
export const nextAuthority = (state: ScrollAuthority, event: ScrollEvent): ScrollAuthority => {
  // Two transitions are global, valid from every state:
  //  - a genuine user scroll always returns control to the user;
  //  - an agent switch always begins restoring the incoming agent.
  if (event.kind === "userScrolled") {
    return state.kind === "userControlled" ? state : { kind: "userControlled" };
  }

  if (event.kind === "agentSwitched") {
    return { kind: "restoring", agentId: event.agentId };
  }

  switch (state.kind) {
    case "userControlled":
      if (event.kind === "newUserTurn") return { kind: "anchoringTurn", anchorIndex: event.index };
      if (event.kind === "reachedBottom") return { kind: "following" };
      if (event.kind === "navStarted") return { kind: "navigating", promptIndex: event.promptIndex };
      return state;
    case "restoring":
      if (event.kind === "restoreSettled") return { kind: "userControlled" };
      // Genuine user intent during the restore window preempts the restore
      // (mirrors the `userControlled` arms).
      if (event.kind === "newUserTurn") return { kind: "anchoringTurn", anchorIndex: event.index };
      if (event.kind === "reachedBottom") return { kind: "following" };
      if (event.kind === "navStarted") return { kind: "navigating", promptIndex: event.promptIndex };
      return state;
    case "anchoringTurn":
      // The anchored turn becomes the thing we follow once its response
      // overflows the viewport...
      if (event.kind === "turnAnchored") return { kind: "following" };
      // ...or the moment the viewport reaches the bottom (e.g. jump-to-bottom).
      if (event.kind === "reachedBottom") return { kind: "following" };
      // A short response that finishes before it ever overflows ends the turn
      // without entering follow.
      if (event.kind === "streamingStopped") return { kind: "userControlled" };
      // A newer turn re-anchors to it.
      if (event.kind === "newUserTurn") return { kind: "anchoringTurn", anchorIndex: event.index };
      return state;
    case "following":
      if (event.kind === "streamingStopped") return { kind: "userControlled" };
      if (event.kind === "newUserTurn") return { kind: "anchoringTurn", anchorIndex: event.index };
      if (event.kind === "navStarted") return { kind: "navigating", promptIndex: event.promptIndex };
      return state;
    case "navigating":
      if (event.kind === "navMoved") return { kind: "navigating", promptIndex: event.promptIndex };
      if (event.kind === "navEnded") return { kind: "userControlled" };
      return state;
    default:
      return assertNever(state);
  }
};
