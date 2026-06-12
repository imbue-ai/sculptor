# React Review Rules

Generic React review rules: effects, state, refs, render purity, performance, props, and lists. The goal is to ensure components are correct, performant, and readable. These checks complement our [frontend style guide](../style/frontend.md). For Sculptor-specific conventions (backend data hooks, Jotai atoms, component-level invariants), see [`sculptor.md`](sculptor.md).

For each issue found, note the issue type, file/line, and a brief description of what is wrong and how to fix it.

---

## `no_effect_for_derived_values`

**Question:** Is this effect computing a value that could be calculated directly during rendering?

Effects are escape hatches for synchronizing with external systems — they should not be the default tool for derived state, event responses, or data transformations ([You Might Not Need an Effect](https://react.dev/learn/you-might-not-need-an-effect)). If a value can be derived from existing props or state, compute it inline. An effect that sets state based on other state/props introduces an unnecessary render cycle — React renders with the stale value first, then immediately re-renders with the derived value.

**What to look for:**
- `useEffect` + `setState` where the new state is a pure function of props or other state
- A `useState` whose only setter is inside a `useEffect`

```tsx
// Bad: unnecessary render cycle
const [fullName, setFullName] = useState("");
useEffect(() => {
  setFullName(`${firstName} ${lastName}`);
}, [firstName, lastName]);

// Good: derive during render
const fullName = `${firstName} ${lastName}`;
```

---

## `no_effect_for_expensive_computations`

**Question:** Is this effect only there because the computation is expensive, not because it's a side effect?

Use `useMemo` for expensive pure computations. `useEffect` + `setState` forces two renders; `useMemo` computes the value in the same render pass.

**What to look for:**
- `useEffect` that filters, sorts, maps, or transforms data and then calls `setState`
- No actual side effect (no network request, no DOM mutation, no subscription)

```tsx
// Bad: two render passes
const [filtered, setFiltered] = useState<ReadonlyArray<Item>>([]);
useEffect(() => {
  setFiltered(items.filter(expensivePredicate));
}, [items]);

// Good: one render pass
const filtered = useMemo(() => items.filter(expensivePredicate), [items]);
```

---

## `no_effect_for_state_reset`

**Question:** Is this effect resetting state when a prop changes?

Use a `key` prop on the component instead. When the key changes, React unmounts and remounts with fresh state — no effect needed, no flash of stale state.

**What to look for:**
- `useEffect` that calls one or more `setState(initialValue)` with a prop in the dependency array
- The effect body only resets state — it performs no side effects

```tsx
// Bad: stale comment visible for one frame
useEffect(() => {
  setComment("");
}, [postId]);

// Good: parent renders <CommentForm key={postId} />
```

---

## `no_effect_for_state_adjustment`

**Question:** Is this effect partially adjusting state (not fully resetting) when props change?

Prefer computing the value during render. If you must store it in state (rare), update state directly during render with a comparison to the previous value — React will re-render immediately without the stale intermediate render.

**What to look for:**
- `useEffect` that reads a prop and conditionally updates state based on it
- The state depends on the prop but isn't an exact copy of it

---

## `no_effect_for_event_handling`

**Question:** Does this effect run logic that should be in an event handler instead?

If something happens in response to a specific user interaction (click, submit, navigation), put it in the event handler. An effect that watches for state changes caused by an interaction obscures what triggered the logic and introduces unnecessary indirection.

**What to look for:**
- A boolean flag state (e.g., `submitted`, `shouldFetch`) set in an event handler, with an effect watching that flag
- `useEffect` whose dependency is a state variable that only changes in response to user action

```tsx
// Bad: effect watches for state change caused by submit
useEffect(() => {
  if (submitted) {
    postData(formData);
  }
}, [submitted, formData]);

// Good: handle in the event handler directly
const handleSubmit = (): void => {
  postData(formData);
};
```

---

## `no_effect_chains`

**Question:** Are multiple effects chaining together, each triggering the next by setting state?

Effect chains (A sets state -> effect B fires -> sets state -> effect C fires) cause cascading re-renders and are extremely hard to trace through. Consolidate the logic into a single event handler or a single effect.

**What to look for:**
- Three or more `useEffect` calls where each one's `setState` triggers the next one's dependency
- Render count much higher than expected for a single user interaction

---

## `no_effect_for_notifying_parent`

**Question:** Is this effect calling a parent callback (e.g., `onChange`, `onUpdate`) after setting local state?

Call both `setState` and the parent callback together in the event handler. An effect that fires `onChange` after every state change makes the component unpredictable — the parent can't distinguish user-initiated changes from programmatic ones.

**What to look for:**
- `useEffect` with a parent callback in the body and local state in the dependency array
- The parent callback is only meaningful when the user does something, not on every re-render

```tsx
// Bad: fires onChange on every state change including programmatic resets
useEffect(() => {
  onChange(value);
}, [value]);

// Good: notify in the event handler alongside the state update
const handleChange = (newValue: string): void => {
  setValue(newValue);
  onChange(newValue);
};
```

---

## `no_effect_for_passing_data_to_parent`

**Question:** Is a child component fetching data in an effect and then sending it up to the parent via a callback?

Data should flow top-down. If the parent needs the data, the parent should fetch it and pass it down as props. A child that fetches and pushes data upward inverts the data flow, making dependencies harder to trace and creating potential infinite loops.

**What to look for:**
- `useEffect` in a child that calls `fetch` or similar, then calls a parent-provided callback with the result
- The parent uses the result to render other children at the same level

---

## `no_effect_for_global_initialization`

**Question:** Is this effect initializing something that only needs to happen once for the entire app (not per-component mount)?

Move it to module scope or app initialization. An effect that runs "once" still runs on every mount in StrictMode, and re-executes if the component remounts for any reason.

**What to look for:**
- `useEffect(() => { ... }, [])` that initializes a global, configures a library, or sets up a singleton

---

## `no_effect_for_data_fetching_without_cleanup`

**Question:** Is this effect fetching data without handling race conditions?

Effects that fetch data must handle the case where the component unmounts or dependencies change before the fetch completes. Without cleanup, a slow response from a previous fetch can overwrite the result of a newer one.

**What to look for:**
- `useEffect` with `fetch` or an async call, no `return () => { ... }` cleanup
- No boolean `ignore` flag or `AbortController` to cancel stale requests

```tsx
// Bad: race condition if userId changes quickly
useEffect(() => {
  fetchUser(userId).then((user) => setUser(user));
}, [userId]);

// Good: cleanup prevents stale writes
useEffect(() => {
  let isIgnored = false;
  fetchUser(userId).then((user) => {
    if (!isIgnored) { setUser(user); }
  });
  return (): void => { isIgnored = true; };
}, [userId]);
```

---

## `extract_helper_functions`

**Question:** Does this effect contain logic that could be a standalone pure function?

Pure transformations, data formatting, validation, or computation inside an effect should be extracted into helper functions defined *outside* the component (or in a utils file). This makes the logic independently testable and keeps the effect body focused on the side effect itself.

**What to look for:**
- Data transformations or filtering inside the effect body
- Multi-step computations that don't depend on React APIs (refs, setState)
- String/array/object manipulation that could be a pure function

**Fix:** Extract the logic into a named function outside the component. The effect should call the function, not contain the implementation.

```tsx
// Bad: pure logic buried in effect
useEffect(() => {
  const conn = connectToRoom(roomId);
  const mapped = items.map(transformItem);
  const sorted = mapped.sort(compareByDate);
  conn.send(sorted);
  return (): void => conn.disconnect();
}, [roomId, items]);

// Good: helper is testable in isolation
const processItems = (items: ReadonlyArray<Item>): ReadonlyArray<Item> =>
  items.map(transformItem).sort(compareByDate);

useEffect(() => {
  const conn = connectToRoom(roomId);
  conn.send(processItems(items));
  return (): void => conn.disconnect();
}, [roomId, items]);
```

---

## `extract_hook`

**Question:** Does this effect (plus its associated state) represent reusable logic that appears in multiple components, or logic complex enough to deserve its own unit tests?

**What to look for:**
- The same effect + state pattern duplicated across components
- An effect that manages a complex lifecycle (subscriptions, polling, websocket connections)
- An effect whose behavior you'd want to test independently from rendering

**Fix:** Extract into a custom hook. The hook should return an object with named properties (per our style guide). Name it `use<Description>`.

**Exceptions:** Only extract when the pattern is duplicated in 2+ components or the lifecycle is complex enough to warrant isolated testing. Premature extraction adds indirection without benefit.

---

## `simplify_effect_logic`

**Question:** Can the logic inside this effect be restructured to be more linear and readable?

**What to look for:**
- Deeply nested conditionals inside an effect
- Multiple unrelated side effects in a single `useEffect` — split into separate effects
- Complex boolean logic that could be simplified with early returns or guard clauses
- Effects that do both "setup" and "ongoing" work — split into separate effects

**Fix:** Flatten conditionals with early returns. Split multi-concern effects. Use descriptive variable names for intermediate values.

---

## `no_mixed_lifecycles`

**Question:** Would changing one dependency unintentionally tear down an unrelated resource?

When a single effect manages multiple resources, any dependency change tears down all of them. This is only a problem when the resources are truly independent — if they should share a lifetime, or must be set up and torn down atomically, keeping them together is correct.

**What to look for:**
- A single effect managing two or more resources (connections, subscriptions, timers, observers, widgets) where each is only relevant to a subset of the dependencies
- A dependency change that would destroy something unrelated — e.g., a theme change closing a network connection

**Fix:** Split the effect so each resource re-runs only when its own dependencies change. If one resource needs to reference another across effects, use a ref — but make sure the reading effect handles the case where the ref is null, since effect ordering is implicit.

---

## `effect_has_comment`

**Question:** Does this complex effect have a comment explaining *what* it does and *why* it exists?

Effects with complex state transitions or non-obvious dependencies are hard to reason about. A one-line comment above these effects explaining their purpose dramatically improves readability.

**What to look for:**
- A `useEffect` with complex state transitions or multiple dependencies that lacks a comment
- Comments that describe *how* (implementation) instead of *what/why* (intent)

**Fix:** Add a comment like: `// Sync scroll position when the active item changes`

**Exceptions:** Simple, self-evident effects (e.g., a 3-line effect that obviously fetches user data) don't need comments. Reserve for effects where the *why* isn't clear from the code.

---

## `effect_has_correct_dependencies`

**Question:** Does this effect's dependency array accurately reflect all reactive values used inside it?

Missing dependencies cause stale closures — the effect reads an old value and produces incorrect behavior. Extra dependencies cause unnecessary re-runs — the effect tears down and re-establishes for no reason.

**What to look for:**
- Suppressed `eslint-disable-next-line react-hooks/exhaustive-deps` comments — each one is a potential stale closure bug
- Values used inside the effect body that are not listed in the dependency array
- Dependencies that change on every render (objects, arrays, functions) causing the effect to re-run constantly

---

## `effect_has_cleanup`

**Question:** Does this effect set up something that needs to be torn down?

Effects that create subscriptions, event listeners, timers, or observers *must* return a cleanup function. Missing cleanup causes memory leaks and bugs when the component unmounts or dependencies change — the old subscription keeps firing after the new one starts.

**What to look for:**
- `addEventListener` without a corresponding `removeEventListener` in the cleanup
- `setInterval` or `setTimeout` without `clearInterval` / `clearTimeout`
- `.subscribe()` without `.unsubscribe()` in the cleanup
- `new IntersectionObserver` without `.disconnect()`

```tsx
// Bad: no cleanup — event listener persists after unmount
useEffect(() => {
  window.addEventListener("resize", handleResize);
}, []);

// Good: cleanup prevents leaks
useEffect(() => {
  window.addEventListener("resize", handleResize);
  return (): void => window.removeEventListener("resize", handleResize);
}, []);
```

---

## `no_state_updates_on_unmounted`

**Question:** Can this effect call `setState` after the component unmounts?

Async operations (fetches, timeouts) that call `setState` in their callback must be cancelled or guarded in the cleanup. This is a specific case of `effect_has_cleanup`, but common enough to call out — it produces the "Can't perform a React state update on an unmounted component" warning.

**What to look for:**
- `useEffect` with an `async` function or `.then()` that calls `setState`, and no cleanup
- `setTimeout` that calls `setState` without being cleared on unmount

---

## `group_related_state`

**Question:** Are there multiple `useState` calls whose values always change together?

If two or more state variables always update at the same time, merge them into a single state object. This prevents impossible intermediate states where one is updated but not the other (React batches setState calls in event handlers, but not always in async code). See [Principles for Structuring State](https://react.dev/learn/choosing-the-state-structure).

**What to look for:**
- Two or more `setState` calls always appearing together in every handler
- State variables that are meaningless without each other (e.g., `x` and `y` for a position)

```tsx
// Bad: always updated together, can desync in async code
const [x, setX] = useState(0);
const [y, setY] = useState(0);

// Good: single state object guarantees consistency
const [position, setPosition] = useState({ x: 0, y: 0 });
```

---

## `no_contradictory_state`

**Question:** Is it possible for the state to represent an "impossible" combination?

If two state variables can contradict each other (e.g., `isEditing` true while `isSubmitted` is also true), restructure as a discriminated union or a single status variable. Impossible states lead to impossible bugs.

**What to look for:**
- Multiple boolean flags that are flipped independently but only some combinations are valid
- Conditional logic that checks combinations of flags (`if (isEditing && !isSubmitted && draft)`)

```tsx
// Bad: can be in impossible states (isEditing=true, isSubmitted=true, draft="old text")
const [isEditing, setIsEditing] = useState(false);
const [isSubmitted, setIsSubmitted] = useState(false);
const [draft, setDraft] = useState<string | undefined>(undefined);

// Good: impossible states are unrepresentable
type FormState =
  | { status: "idle" }
  | { status: "editing"; draft: string }
  | { status: "submitted"; result: SubmitResult };
```

---

## `no_redundant_state`

**Question:** Can any state variable be computed from other state or props?

If yes, it's not state — it's a derived value. Remove it and compute inline. Every piece of redundant state is a potential source of desync bugs — you have to remember to update it everywhere the source changes.

**What to look for:**
- A `useState` whose value is always derived from other state or props
- State that is "kept in sync" with another value via a `useEffect`

---

## `no_duplicate_state`

**Question:** Is the same data stored in multiple state variables or in both state and props?

A common case is copying a prop into state. Unless you intentionally want to "snapshot" the initial value and diverge from the prop going forward, don't do this — you now have two sources of truth that can drift apart.

**What to look for:**
- `const [value, setValue] = useState(props.value)` — this only captures the initial prop
- Two state variables that hold the same object or overlapping data

---

## `non_idempotent_component`

**Question:** Given the same props and state, does this component always produce the same output?

Components should be pure functions of their inputs. Side effects belong in effects or event handlers, never in the render body.

**What to look for:**
- Reading from mutable globals or `window` properties during render (not in effects)
- Mutating variables outside the component during render
- `Math.random()` or `Date.now()` in the render path (move to effects or event handlers)
- Direct DOM reads (`getBoundingClientRect()`) during render instead of in effects

**Exceptions:** Some non-determinism during render is intentional (e.g., feature flags read from a stable store). The rule should catch *accidental* impurity.

---

## `monolithic_component`

**Question:** Is this component handling too many concerns, making it difficult to read, review, and modify safely?

A monolithic component typically suffers from one or both of these problems: (1) business logic mixed with visual rendering, or (2) a JSX return that handles multiple distinct UI sections inline.

**What to look for:**
- A component that both fetches/computes data AND renders a UI tree — business logic interleaved with JSX
- Multiple distinct UI sections (header, body, footer, dialogs, overlays) rendered inline in a single return
- `.map()` calls that render non-trivial JSX (more than a few lines) inline rather than extracting the item into its own component
- Deeply nested conditional rendering (`{condition && (<...>)}`) repeated at different levels
- Inline context menus, dialogs, or modals defined directly in the parent's return rather than as separate components
- Sections separated by comments like `{/* Actions */}` — the comment is a sign it should be a component

**Fix:** Split the component along one or both axes:
- **Logic vs. view:** Extract a presentational component that receives data via props. The container handles data fetching, state management, and business logic, then passes data down. Presentational components are easier to test, reuse, and reason about.
- **UI sections:** Extract distinct sections into well-named sub-components — even if they're only used once — to make the structure self-documenting.

**Exceptions:**
- Leaf-level components that simply have many props/attributes on a single element (e.g., a complex SVG or a form input with many aria attributes).
- Thin layout wrappers that compose multiple children in a flat list without logic — these are inherently simple despite line count.
- Trivial `.map()` calls that render a single simple element.
- Don't over-extract: if a sub-component would require passing many props that are only used in one place, consider a clearly named local variable (`const header = (...)`) instead.

---

## `should_memoize_component`

**Question:** Does this component re-render frequently with the same props due to parent re-renders?

Wrap with `React.memo` when the component is expensive to render (large JSX tree, many children) and the parent re-renders often but this component's props rarely change.

**What to look for:**
- A component with a large JSX subtree whose parent re-renders frequently (e.g., parent subscribes to a fast-changing store)
- React DevTools Profiler shows this component as a re-render hotspot with unchanged props

**Do NOT memoize when:** the component is cheap to render, props change on every render anyway, or you haven't measured a problem.

---

## `should_memoize_values_or_callbacks`

**Question:** Are expensive computations or callback references being recreated on every render, causing downstream re-renders?

Use `useMemo` for expensive derived values and `useCallback` for callbacks passed to memoized children. But only when there's a measurable benefit.

**What to look for:**
- A callback passed as a prop to a `React.memo` child that is recreated on every render
- A computation that takes >1ms and runs on every render (check with React DevTools Profiler)

---

## `stable_references_in_dependencies`

**Question:** Are effect/memo dependencies creating new references on every render?

Objects, arrays, and functions created inline during render are new references each time, causing effects and memos to re-run on every render regardless of whether the *logical* value changed.

**What to look for:**
- Object or array literals created in the component body and passed to a `useEffect` or `useMemo` dependency array
- A `useEffect` that runs on every render despite having a dependency array — check if a dependency is a new reference each time
- True constants that could be hoisted to module scope instead of wrapped in `useMemo`

```tsx
// Bad: new object on every render triggers effect every time
const options = { threshold: 0.5 };
useEffect(() => {
  observe(element, options);
}, [options]); // always a new reference!

// Best for true constants: hoist to module scope for a stable reference with no hook overhead
const OPTIONS = { threshold: 0.5 };

const MyComponent = (): ReactElement => {
  useEffect(() => {
    observe(element, OPTIONS);
  }, [OPTIONS]);
};

// Good for values that depend on props/state: useMemo for a stable reference
const options = useMemo(() => ({ threshold, minSize }), [threshold, minSize]);
useEffect(() => {
  observe(element, options);
}, [options]);
```

---

## `no_raf_as_timing_hack`

**Question:** Is `requestAnimationFrame` being used to "wait for the DOM to be ready" rather than to batch visual updates or measure post-layout geometry?

`requestAnimationFrame` schedules a callback before the next paint — it does not guarantee that a specific DOM element, shadow root, or layout calculation will be available. Using it as a one-frame delay to work around render timing issues creates race conditions: if the thing you're waiting for takes longer than one frame, the callback runs too early; if it's already available, the delay is unnecessary. Inside effects that re-run frequently, each invocation schedules a new rAF callback that may fire after the effect has already cleaned up, leading to stale reads or writes.

**What to look for:**
- `requestAnimationFrame` inside a `useEffect` used to defer a DOM query or `setState` until "after the component paints"
- `requestAnimationFrame` as the first line of an effect body, wrapping the entire effect logic
- `requestAnimationFrame(() => setState(...))` — deferring a state update by one frame to avoid a "flash" of stale UI
- `requestAnimationFrame` inside observer callbacks (`ResizeObserver`, `MutationObserver`) where the observer already fires at the right time

**Fix:** Identify *what* you're actually waiting for and use the appropriate mechanism:
- If waiting for an element to exist in the DOM → use `MutationObserver` or a callback ref
- If waiting for layout to settle after a resize → `ResizeObserver` already fires post-layout, no rAF needed
- If deferring a state update to avoid a visual flash → derive the value during render instead of setting state in an effect
- If you genuinely need to measure geometry after React commits → `requestAnimationFrame` is correct, but document *why* the measurement can't happen synchronously in the effect

**Exceptions:** `requestAnimationFrame` is appropriate when you need to (1) measure DOM geometry that is only valid after the browser has performed layout (e.g., `getBoundingClientRect` on a newly mounted element whose dimensions depend on CSS), or (2) coalesce multiple rapid updates into a single visual frame (e.g., throttling a scroll or drag handler). In both cases, the intent should be clear from a comment.

---

## `no_inline_object_props`

**Question:** Are object/array literals or anonymous functions passed as props to memoized children?

This defeats `React.memo` since the prop is a new reference every render, causing the memoized child to re-render anyway.

**What to look for:**
- `<MemoizedChild style={{ color: "red" }} />` — new object each render
- `<MemoizedChild onClick={() => doThing()} />` — new function each render
- `<MemoizedChild items={data.filter(predicate)} />` — new array each render

---

## `unstable_list_keys`

**Question:** Are list items rendered with stable, unique keys?

Using array index as a key causes bugs when items are reordered, inserted, or deleted — React reuses DOM nodes based on key position, leading to stale state in child components.

**What to look for:**
- `items.map((item, index) => <Item key={index} ... />)`
- Keys that are not unique within the list (e.g., duplicate IDs)

---

## `ref_read_during_render`

**Question:** Is `ref.current` read or written during the render body?

This makes component behavior unpredictable — React may render the component multiple times (StrictMode) or skip renders (concurrent features), and the ref value during render is not guaranteed. Read/write refs only in event handlers, effects, or callbacks. See [Referencing Values with Refs](https://react.dev/learn/referencing-values-with-refs).

**What to look for:**
- `ref.current` appearing in JSX or in calculations that determine JSX output
- `ref.current = ...` assignments outside of `useEffect` or event handlers

```tsx
// Bad: reading ref during render — stale, no re-render on change
const countRef = useRef(0);
return <div>{countRef.current}</div>;

// Good: use state for rendered values
const [count, setCount] = useState(0);
return <div>{count}</div>;
```

**Exceptions:**
- Lazy initialization (`if (!ref.current) { ref.current = new Thing(); }`) during render is acceptable — it runs once and is effectively side-effect-free.
- Syncing a ref with state or props (`ref.current = value`) during render to give event handlers or callbacks access to the latest value is the standard "latest ref" pattern. Do not wrap this in a `useEffect` — the effect runs after commit, creating a window where the ref is stale. The direct assignment is synchronous and always up-to-date.

---

## `ref_for_rendered_value`

**Question:** Does a ref store a value that determines what JSX to render?

If the value affects output, it should be state. Refs update immediately but silently — the UI will be stale until something else triggers a re-render.

**What to look for:**
- `useRef` for a value that appears in JSX or influences conditional rendering
- A ref that is updated and then the component expects the UI to reflect the change

---

## `destructive_dom_mutation`

**Question:** Is a ref used to mutate DOM that React manages?

Adding children, removing nodes, or changing the structure of elements React renders causes crashes or visual inconsistencies when React tries to update nodes that no longer match its virtual DOM. See [Manipulating the DOM with Refs](https://react.dev/learn/manipulating-the-dom-with-refs).

**What to look for:**
- `ref.current?.remove()`, `ref.current?.appendChild(...)`, `ref.current!.innerHTML = ...` on elements that React renders children into
- DOM manipulation that changes the *structure* (not just styling) of React-managed elements

```tsx
// Bad: crashes React on next state update
const divRef = useRef<HTMLDivElement>(null);
const handleClick = (): void => {
  divRef.current?.remove();
};
return <div ref={divRef}>Content</div>;

// Good: use conditional rendering
const [isVisible, setIsVisible] = useState(true);
return isVisible ? <div>Content</div> : undefined;
```

**Exceptions:** Modifying DOM inside an element that is always empty in JSX (`<div ref={containerRef} />`) is safe — React has no children to reconcile.

---

## `ref_resource_cleanup`

**Question:** Does an effect or event handler create a resource stored in a ref but never clean it up?

Refs that hold resource handles (timeout IDs, interval IDs, observers, controllers) must be cleaned up on unmount.

**What to look for:**
- `timerRef.current = setInterval(...)` without a corresponding `clearInterval(timerRef.current)` in a cleanup function
- `observerRef.current = new IntersectionObserver(...)` without `.disconnect()` on unmount

---

## `duplicate_state_across_siblings`

**Question:** Do two sibling components each maintain their own copy of the same state, causing them to fall out of sync?

Identify the single source of truth — lift the state to the closest common parent, or use a shared state container (Context, a shared store, etc.). See [Sharing State Between Components](https://react.dev/learn/sharing-state-between-components).

**What to look for:**
- Two components at the same level each calling `useState` for logically the same value
- State that should be coordinated (e.g., "only one panel active at a time") but each component tracks it independently

```tsx
// Bad: siblings own duplicate state, can't coordinate
const PanelA = (): ReactElement => {
  const [isActive, setIsActive] = useState(false);
  return <section>{isActive ? <Content /> : <Button onClick={() => setIsActive(true)} />}</section>;
};
const PanelB = (): ReactElement => {
  const [isActive, setIsActive] = useState(false);
  return <section>{isActive ? <Content /> : <Button onClick={() => setIsActive(true)} />}</section>;
};

// Good: parent owns the single source of truth
const Accordion = (): ReactElement => {
  const [activeIndex, setActiveIndex] = useState(0);
  return (
    <>
      <Panel isActive={activeIndex === 0} onShow={() => setActiveIndex(0)} />
      <Panel isActive={activeIndex === 1} onShow={() => setActiveIndex(1)} />
    </>
  );
};
```

---

## `prop_copied_into_state`

**Question:** Does a component copy a prop into local state and try to keep them in sync?

This creates a duplicate source of truth. Either make the component controlled (driven entirely by props + callbacks) or uncontrolled (fully owns its own state with an optional `defaultValue`), not a hybrid.

**What to look for:**
- `const [value, setValue] = useState(props.value)` — only captures the initial prop, drifts after
- A `useEffect` that syncs `setValue(props.value)` whenever the prop changes — sign of a hybrid controlled/uncontrolled component

---

## `prop_drilling`

**Question:** Is state passed down through multiple layers when a child could access it directly?

Prop drilling through 3+ levels is a signal that intermediate components shouldn't be managing that data. Have the leaf component read the data from a shared source (Context, a state container, or a hook) directly. This avoids coupling intermediate components to data they don't need and prevents unnecessary re-renders of those intermediaries.

**What to look for:**
- Props passed through components that don't use them (just forward them)
- "Middleman" components whose only purpose is to thread data downward
- A prop that appears in a component's type but is never read — only forwarded
- A chain of 3+ components each accepting and forwarding the same prop

**Fix:** Have the leaf component read from the shared source directly. This also improves performance since intermediate components no longer re-render when that data changes.

---

## `controlled_vs_uncontrolled_mismatch`

**Question:** Is a component that should be controlled managing its own internal state instead, or is a naturally uncontrolled component forced to be controlled unnecessarily?

A component that needs to coordinate with siblings or be driven by a parent should be controlled (receives value + onChange from parent). A simple, self-contained component used in many places should be uncontrolled (owns its state, optionally accepts `defaultValue`).

**What to look for:**
- A component that manages `useState` internally but the parent needs to read or set that value — should be controlled
- A simple input-like component that every parent must manage state for, even when the parent doesn't care about the intermediate value — should be uncontrolled with `defaultValue`

**Exceptions:**
- Prop drilling through 1-2 levels is normal and often clearer than introducing a shared store for a small piece of state.
- Some components are intentionally uncontrolled for simplicity (e.g., a text input that only reports on submit). Don't force controlled patterns where they add complexity without benefit.

---

## `no_concurrent_requests_in_polling_loop`

**Question:** Does this polling or refresh loop guard against multiple concurrent in-flight requests?

When a `setInterval` fires an async request every N seconds, a slow response (taking longer than N seconds) means the next interval fires before the previous request completes. This stacks up concurrent requests, wasting bandwidth and potentially applying responses out of order. The fix is to ensure only one request is in-flight at a time — either by using a polling utility that handles single-flight for you, or by tracking an in-flight flag with a ref.

**What to look for:**
- `setInterval` callback that calls `fetch`, an API function, or any async operation without checking whether the previous call has completed
- Polling loops that use state (not a ref) to track in-flight status — state updates may not be visible to the next interval tick due to closures
- Recursive `setTimeout` patterns that don't `await` the async work before scheduling the next timeout

**Fix:** Use a polling utility that guarantees single-flight per request and cleans up on unmount. If using raw `setInterval`, track an in-flight boolean in a `useRef` and early-return when it's already running (state-based flags can't be read accurately by the next tick due to closure capture).

```tsx
// Bad: if getDeps() takes >3s, requests pile up
useEffect(() => {
  const id = setInterval(async () => {
    const { data } = await getDeps();
    setDeps(data);
  }, 3_000);
  return () => clearInterval(id);
}, []);

// Good: in-flight flag in a ref, visible to subsequent ticks
const isFetchingRef = useRef(false);
useEffect(() => {
  const id = setInterval(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const { data } = await getDeps();
      setDeps(data);
    } finally {
      isFetchingRef.current = false;
    }
  }, 3_000);
  return () => clearInterval(id);
}, []);
```

---

## `no_silently_gated_handlers`

**Question:** Does this interaction handler refuse the interaction with an internal early-return while the element still renders as fully actionable?

A control that gates its own handler — `onClick`, `onKeyDown`, `onPointerDown` — with an early-return on a readiness or loading condition (`if (!canExpand) return;`, `if (isLoading) return;`) must also reflect that gate in the DOM. If it does not, the element renders as a fully actionable node — a `<div onClick>` with no other signal, or a `<button>` with no `disabled` attribute — while internally refusing the interaction. The interaction is silently dropped: no error, no event, no DOM change. A real user gets no feedback, and the test framework's actionability auto-wait — which would otherwise hold the interaction until the control is genuinely ready — is defeated, because the element reports itself as enabled. The lost interaction surfaces much later as an opaque downstream timeout rather than at the actual mistake.

Reflect the gate through an attribute the rendering and test frameworks already understand: `disabled` on native form controls (`<button>`, `<input>`, `<textarea>`, `<select>`), or `aria-disabled` on non-native interactive elements (a `<div>`/`<span>`, or a Radix `Flex`/`Box`/`Text` carrying an `onClick`). Keep the handler's early-return as defense-in-depth — `aria-disabled` is advisory and does not block a real pointer event — but it must not be the *only* expression of the gate.

**What to look for:**
- An `onClick`/`onKeyDown`/`onPointerDown` handler whose body early-returns on a readiness, loading, or "can/should/is-ready" condition
- The element carrying that handler has no `disabled` or `aria-disabled` bound to the same condition
- A non-native element (`div`, `span`, Radix `Flex`/`Box`/`Text`) with an `onClick` that is conditionally inert
- A control that signals non-interactivity only through a CSS class (e.g. cursor styling), with no matching `disabled`/`aria-disabled`
- One element rendered under the same testid across states — interactive in some, an inert plain element in others

**Fix:** Bind `disabled` (native controls) or `aria-disabled` (non-native elements) to the exact condition the handler early-returns on, so the element is honest about its readiness in the DOM.

**Exceptions:** Handlers that early-return on a transient event detail (`if (event.key !== "Enter") return;`), a null ref, or any guard unrelated to the control's interactive readiness are not gating actionability and do not need a `disabled` attribute.
