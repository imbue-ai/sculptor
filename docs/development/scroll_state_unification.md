# Unifying alpha-chat scroll behavior into an explicit state machine

Status: **reference** — the migration described here has landed. Audience:
Sculptor frontend maintainers.

This document explains *why* the alpha chat's scroll behavior is being reworked
into a single explicit state machine, *what* that machine is, and *how* the
migration is staged. If you are touching anything under
`sculptor/frontend/src/pages/workspace/components/chat-alpha/hooks/`, read this
first.

---

## Motivating prompt

The maintainer who initiated this work framed the problem as follows:

> Please look at the underlying issue holistically. Look at it more than just the
> one case, but the entire cluster.
>
> Consider the software principle: Make incorrect states impossible to represent.
>
> Consider also the software principle: use the type system to express
> sequences/state machines.
>
> Given both these requirements, while still respecting the major architectural
> constraints of sculptor, is there a broader fix that we can make that will
> solve this problem more holistically, and make representation of scroll
> behavior a simple, deterministic and clean abstraction? I am asking for an
> explicit, in-the-code, not a comment but actual semantic spelling out of the
> states and transitions of the system in question.
>
> If there are only a few features or current requirements that stand in the way
> of this implementation, please flag those requirements to me.
>
> Additional context to keep in the background: agents often invent/complicate
> systems by writing extremely defensive code at a local level, without
> realizing that at a macro level the underlying problem has a much simpler,
> elegant solution. I am asking you to take a step back on this class of flakes
> and find that elegant solution.

---

## The problem: an implicit state machine smeared across five files

A whole cluster of CI flakes (tracked under SCU-1566) shares one signature —
`Page.wait_for_function: Timeout 30000ms` — across the alpha-chat scroll tests
(`test_alpha_scroll_task_switch`, `test_alpha_scroll_behaviors`,
`test_alpha_scroll_padding_agent_switch`, `test_alpha_scroll_auto_scroll`,
`test_alpha_scroll_prompt_nav`, …).

They are not separate bugs. The alpha chat already *has* a scroll state machine;
it is simply implicit, distributed across ~11 boolean refs in five files, and
mutated from event handlers, `requestAnimationFrame` callbacks, `ResizeObserver`
callbacks, and layout effects — sequenced only by prose comments such as "this
hook's layout effect runs before that one's by call order."

| Flag | Owner | Form |
| --- | --- | --- |
| `isRestoringRef` | `useAlphaScrollPersistence` | ref |
| `isSettlingRef` + `settleGeneration` | `useAlphaVirtualizer` | ref + state |
| `isEngagedRef` / `isEngaged` | `useAlphaAutoScroll` | ref **and** state |
| `isAtBottomRef` / `isAtBottom` | `useAlphaAutoScroll` | ref **and** state |
| `isFillingRef` + `fillingAnchorIndexRef` | `useAlphaAutoScroll` | ref |
| `isSuppressedRef` / `isSuppressed` | `useAlphaAutoScroll` | ref + state |
| `isUserScrollingRef` | `useAlphaAutoScroll` | ref |
| `isProgrammaticScrollRef` | `AlphaChatInterface` (shared) | ref |
| `isNavigatingRef` | `AlphaChatInterface` (shared) | ref |

That is on the order of 2¹¹ representable combinations, of which only a handful
are legal. Every flake in the cluster has the same shape: **two of these flags
disagree about who owns `scrollTop`, across an animation-frame boundary** — and
because no single value names the combined state, a test cannot *await* the
system being ready. It can only poll geometry (`scrollTop` stability, exact
`scrollHeight` equality, message offsets) and hope the dust has settled, which
under CI load it sometimes never does within the budget.

Symptom-by-symptom, the same root cause:

| Flaky test | Surface symptom | Underlying illegal/unobservable state |
| --- | --- | --- |
| `test_scroll_position_restored_on_task_switch` | `scrollTop < 10` never holds | the deferred restore re-assert fires *after* the user/test already scrolled — "restoring" and "user is in control" are both true |
| `test_scroll_height_settles_after_agent_switch` | `scrollHeight === before` never holds | virtualizer measurement settle has **no observable "done"** |
| `test_first_message_visible_after_agent_switch`, `test_dynamic_padding_survives_agent_switch` | message offset never lands | same settle, different assertion |
| `test_arrow_up_*` (prompt nav) | highlight/scroll never lands | `isNavigating` + the 500 ms scroll-spy freeze racing an async `scrollToIndex` and user input |
| `test_auto_scroll_and_jump_to_bottom` | jump-to-bottom attribute wrong | `isEngaged` × `isAtBottom` × `isFilling` combination is internally inconsistent for a frame |

A local fix for any one of these (e.g. adding *another* flag/attribute, or a
test-side "wait until scrollTop is stable for N frames" helper) is exactly the
defensive-local-patch trap: it treats a symptom and leaves the 2¹¹-state space
intact for the next collision to find.

## The principle: make illegal states unrepresentable; use types for the sequence

Collapse the boolean soup into **one explicit, typed state value** with a single
writer, and model scroll as a finite state machine whose transitions are total
functions. Then:

- Illegal combinations (`restoring` *and* `following`, `filling` *and*
  `at bottom`) cannot be constructed — they are not in the type.
- "A real user input always wins" is expressed **once**, not re-derived in four
  hooks.
- "Settled" stops being a geometry heuristic and becomes a value the DOM
  advertises, so tests `await` a state instead of polling pixels.

## The design

Scroll behavior decomposes into three concerns. Two are small finite state
machines; one is a derived observation. Keeping them separate (rather than one
giant union) is deliberate — they are genuinely orthogonal, and conflating them
is what produced the soup.

### 1. `ScrollAuthority` — who is moving `scrollTop`, and why

Exactly one actor owns `scrollTop` at any instant. Programmatic phases are
transient and always resolve back to `userControlled`. A genuine user input
preempts any of them.

```ts
// scrollAuthority.ts
export type ScrollAuthority =
  | { kind: "userControlled" }                          // settled; the user owns scrollTop
  | { kind: "restoring"; taskId: string }               // applying saved position after a switch
  | { kind: "anchoringTurn"; anchorIndex: number }      // new user message animating/placing at top
  | { kind: "following" }                               // pinned to bottom, following the stream
  | { kind: "navigating"; promptIndex: number };        // keyboard prompt navigation

// Events are named by *cause*, never by effect — the reducer is the single place
// that decides the effect.
export type ScrollEvent =
  | { kind: "taskSwitched"; taskId: string }
  | { kind: "restoreSettled" }
  | { kind: "userScrolled" }                            // hardware wheel/touch/key — always wins
  | { kind: "newUserTurn"; index: number }
  | { kind: "turnAnchored" }
  | { kind: "reachedBottom" }                           // user scrolled to the very bottom mid-stream
  | { kind: "streamingStopped" }
  | { kind: "navStarted"; promptIndex: number }
  | { kind: "navMoved"; promptIndex: number }
  | { kind: "navEnded" };

export const nextAuthority = (s: ScrollAuthority, e: ScrollEvent): ScrollAuthority => {
  if (e.kind === "userScrolled") return { kind: "userControlled" };   // the one global invariant
  if (e.kind === "taskSwitched") return { kind: "restoring", taskId: e.taskId };

  switch (s.kind) {
    case "userControlled":
      if (e.kind === "newUserTurn")   return { kind: "anchoringTurn", anchorIndex: e.index };
      if (e.kind === "reachedBottom") return { kind: "following" };
      if (e.kind === "navStarted")    return { kind: "navigating", promptIndex: e.promptIndex };
      return s;
    case "restoring":
      if (e.kind === "restoreSettled") return { kind: "userControlled" };
      return s;
    case "anchoringTurn":
      if (e.kind === "turnAnchored")  return { kind: "following" };
      return s;
    case "following":
      if (e.kind === "streamingStopped") return { kind: "userControlled" };
      if (e.kind === "newUserTurn")      return { kind: "anchoringTurn", anchorIndex: e.index };
      return s;
    case "navigating":
      if (e.kind === "navMoved") return { kind: "navigating", promptIndex: e.promptIndex };
      if (e.kind === "navEnded") return { kind: "userControlled" };
      return s;
  }
};
```

The reducer is **pure, total, and exhaustively typed** (the `switch` is
checked for exhaustiveness by the compiler). It is the entire spec of the
sequence, in one place, testable without a DOM.

### 2. `LayoutPhase` — the virtualizer's measurement lifecycle

Independent of who owns the scroll: after a task switch the virtualizer
invalidates measurements and the dynamic `paddingEnd` reconverges over a couple
of frames. That convergence is what `test_scroll_height_settles` was trying to
observe.

```ts
// layoutSettle.ts
export type LayoutPhase =
  | { kind: "stable" }
  | { kind: "measuring"; sinceTaskId: string };   // remeasuring; paddingEnd not yet converged

export const nextLayout = (
  s: LayoutPhase,
  e: { kind: "invalidated"; taskId: string } | { kind: "converged" },
): LayoutPhase => (e.kind === "invalidated" ? { kind: "measuring", sinceTaskId: e.taskId } : { kind: "stable" });
```

### 3. At-bottom-ness is a derived *observation*, not a state

Whether the viewport is at the bottom drives only the jump-to-bottom button. It
is a function of geometry (`scrollHeight - scrollTop - clientHeight <=
THRESHOLD`), so it is **computed**, never stored as a mode. Storing it was the
source of "the button says one thing while the scroll says another."

### 4. Search suppression is a top-level guard

When in-chat search is open, auto-scroll behaviors are suspended. Rather than add
a `searching` member to the authority union (which would multiply every phase by
"is search open"), suppression is a **single top-level boolean on the store that
gates dispatch**: while suppressed, only the auto-scroll *initiation* events
(`newUserTurn`, `reachedBottom`) are dropped, so a search session never starts
pinning or anchoring. Completion events (`turnAnchored`, `streamingStopped`,
`restoreSettled`, `navEnded`) and the globals (`userScrolled`, `taskSwitched`)
still apply, so the machine can always reach a settled state. This keeps the
union strictly about *authority*.

### The store: one writer, ref-backed, selectively reactive

A `useReducer`/`useState` machine is **not** viable here: the `following` phase
re-pins every animation frame during streaming, and the existing code uses refs
precisely to avoid re-rendering the virtualized list (and tearing down the
`ResizeObserver`) on every such tick. So the machine lives in a **ref-backed
external store** that:

- holds `{ authority, layout, isSuppressed }`,
- exposes `dispatch(event)`, `getState()`, and `subscribe(listener)`,
- mirrors the authority kind onto the scroll container as `data-scroll-phase`
  and a derived `data-scroll-settled` on every transition,
- is read by React components that genuinely must re-render (e.g. the
  jump-to-bottom button) via `useSyncExternalStore` with a selector, so
  high-frequency `following` ticks do not re-render anything that didn't select
  them.

```ts
// data-scroll-settled := authority is quiescent AND layout has converged.
const isSettled = (a: ScrollAuthority, l: LayoutPhase): boolean =>
  (a.kind === "userControlled" || a.kind === "following") && l.kind === "stable";
```

### The deterministic test signal

Every heuristic in the cluster collapses to one of two awaits:

```python
# "the chat has fully settled after whatever I just did"
expect(view).to_have_attribute("data-scroll-settled", "true")

# or, when a test cares about a specific phase:
expect(view).to_have_attribute("data-scroll-phase", "userControlled")
```

No frame-stability polling, no exact-`scrollHeight` equality, no per-test fixed
sleeps. `wait_for_alpha_scroll_idle` and friends are deleted.

> Note (relaxation, see decisions below): `data-scroll-settled` reflects *our*
> control flow becoming quiescent, not a guarantee that TanStack Virtual's
> internal `scrollToIndex` correction has painted its final sub-pixel. That is an
> accepted limitation — observable authority is the bar.

## Resolved design decisions

These were settled during design review:

1. **At-bottom is derived geometry, kept orthogonal to the authority union.**
   It never becomes a stored mode.
2. **Sub-pixel-exact settle is *not* required.** Observable authority quiescence
   is the contract. We do not patch or instrument TanStack Virtual's internal
   async scroll corrections; `restoreSettled` / `converged` are emitted from our
   own rAF / measurement callbacks.
3. **Search suppression is a top-level guard**, not a state in the union.
4. **The scroll-to-top animation and the dynamic `paddingEnd` feature are
   kept.** They are the reason the `anchoringTurn` authority phase and the
   `measuring` layout phase exist.
5. **The migration is incremental** — every commit stays green — **but the
   entire migration is completed by the final commit.**

## What this buys us

- The 2¹¹-combination space becomes ~5 authority states × 2 layout states × a
  guard, with illegal combinations unrepresentable.
- "User input wins" lives in one line.
- Cross-hook ordering stops depending on hook *call order*; hooks emit events
  into one store and read one state.
- Tests await a state instead of polling geometry — the entire flake cluster's
  failure mode (`wait_for_function` timeout) disappears at the source.

## Migration plan (one green commit each)

1. **Design doc** (this file).
2. **Core, unwired:** `scrollAuthority.ts`, `layoutSettle.ts`, the ref-backed
   store hook, and exhaustive unit tests. Purely additive.
3. **Persistence:** `useAlphaScrollPersistence` dispatches
   `taskSwitched` / `restoreSettled` / `userScrolled`; the store owns
   `restoring`; drive `data-scroll-phase`. Behavior identical.
4. **Virtualizer settle:** replace `isSettlingRef` + `settleGeneration` with the
   `LayoutPhase` machine.
5. **Auto-scroll:** replace `isEngagedRef` / `isFillingRef` / `isAtBottomRef`
   with `following` / `anchoringTurn` + derived at-bottom; emit `userScrolled`.
   (Largest step.)
6. **Prompt nav + suppression:** replace `isNavigatingRef` and the 500 ms freeze
   with the `navigating` phase; model search suppression as the top-level guard.
7. **Tests + cleanup:** migrate integration tests to await `data-scroll-phase` /
   `data-scroll-settled`; delete `wait_for_alpha_scroll_idle` and every dead
   ref/flag. Full `just check` + scroll integration suite.

## How to extend this later

- Need a new scroll behavior? Add a member to `ScrollAuthority` (or an event),
  and the compiler will force you to handle it in `nextAuthority` and anywhere
  that switches on the phase. That is the point: the type system makes the
  sequence explicit and the gaps loud.
- Resist adding a new boolean ref. If you find yourself reaching for one, it is
  almost certainly a transition or a derived value that belongs in the machine
  or is computed from geometry.
