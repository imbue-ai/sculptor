# Sculptor Frontend Review Rules

Review rules for Sculptor-specific frontend conventions: backend-data hooks (WS-pushed atoms and HTTP-pulled TanStack queries), Jotai atom usage, and component-level invariants. These complement the generic React rules in [`react.md`](react.md).

For each issue found, note the issue type, file/line, and a brief description of what is wrong and how to fix it.

---

## `use_ws_hooks_for_pushed_data`

**Question:** Is this data already arriving over the unified WebSocket stream — and if so, is the component reading it via the existing atom-backed hook?

The dominant data-flow in this codebase is WS push → Jotai atom → `useX` hook. The backend pushes full payloads over the unified stream (`useUnifiedStream`); incoming frames update Jotai atoms (`workspaceAtomFamily`, `projectAtomFamily`, `workspaceIdsAtom`, `projectsArrayAtom`, …); components read those atoms through generic hooks (`useWorkspace`, `useProject`, `useProjects`, `useIsWorkspaceDeleted`, …). Nothing fetches — the data is kept fresh by the stream. Reach for this path first.

TanStack Query ([`use_tanstack_for_pulled_data`](#use_tanstack_for_pulled_data)) covers the cases where this doesn't apply: data that isn't pushed over the WS, or is too large to ship every frame (the workspace diff, commit history, file content at a ref, per-commit diffs, …). Those endpoints are pulled on demand and cached by TanStack instead.

**What to look for:**
- A `useEffect` + `useState` (or a bespoke TanStack hook) fetching data that's already on the WS — should be reading the existing atom instead
- A new atom defined in a component for data the WS already delivers
- A new hook that takes `workspaceId` and re-fetches workspace metadata that `useWorkspace` already exposes
- A component subscribed to `workspaceAtomFamily(id)` directly instead of using `useWorkspace(id)` — bypasses the canonical accessor

**Fix:** Use the existing atom-backed hook. If the data is on the WS but no hook exposes it yet, add one in `sculptor/frontend/src/common/state/hooks/` modeled on `useWorkspace.ts` / `useProjects.ts` — a thin `useAtomValue` wrapper around the relevant atom (or `atomFamily`). Only reach for TanStack if the endpoint genuinely isn't pushed.

**When TanStack is the right call instead:**
- The endpoint isn't streamed over the WS at all (`getWorkspaceDiff`, `getWorkspaceCommits`, `workspaceReadFile`, …).
- The data could be streamed but is too large/expensive to push every frame (the full unified diff, file blobs).
- The data is project-scoped or pre-workspace and not part of the workspace stream.

When in doubt, grep the atom files (`sculptor/frontend/src/common/state/atoms/`) and check what `useUnifiedStream` writes to. If the data shows up there, use the atom hook.

---

## `use_tanstack_for_pulled_data`

**Question:** For data that isn't WS-pushed (or is too big to push), is this component (or hook) fetching, caching, or polling outside of TanStack Query?

Every HTTP-pulled read from the backend — `useWorkspaceDiff`, `useWorkspaceCommits`, `useWorkspaceFileContent`, `useWorkspaceCommitDiff`, `useWorkspaceFiles` — goes through `@tanstack/react-query`. The shared `queryClient` in `sculptor/frontend/src/common/queryClient.ts` is configured for our model: `staleTime: Infinity`, no window-focus or reconnect refetches, freshness driven by explicit invalidation (the unified WebSocket cascade for workspace data; a short per-hook `staleTime` for sources without a push signal). New HTTP reads should plug into this rather than spinning up a parallel cache. For the WS-pushed case, see [`use_ws_hooks_for_pushed_data`](#use_ws_hooks_for_pushed_data).

The only carve-out is the unified WebSocket stream itself (`useUnifiedStream`), which drives the invalidation cascade. Everything downstream of it that isn't a direct atom read is a TanStack query.

**What to look for:**
- A `useEffect` that calls a generated API function (anything imported from `../../api`) and stores the result in `useState`
- A bespoke `useState({ data, loading, error })` triple maintained by hand for an HTTP-pulled endpoint
- A new hook that takes a `workspaceId` / `projectId`, calls an HTTP endpoint, and doesn't use `useQuery`
- An imperative call site (Jotai action, runtime callback) that fetches an HTTP endpoint directly and writes to an atom instead of going through `queryClient.fetchQuery`
- An atom whose only purpose is to cache an HTTP response (legitimate atoms hold WS-pushed payloads or client state — see [`no_bespoke_fetch_caching`](#no_bespoke_fetch_caching))
- A `setInterval`-based polling loop fetching an HTTP endpoint — use `useQuery` with `refetchInterval` instead (single-flight per query key); or, if there's a WS event signaling "the data changed," trigger invalidation from that frame and drop the loop entirely. See also the generic [`no_concurrent_requests_in_polling_loop`](react.md#no_concurrent_requests_in_polling_loop).

**Fix:** Add a hook in `sculptor/frontend/src/common/state/hooks/` modeled on `useWorkspaceDiff` (workspace-scoped, rides the WS invalidation cascade) or a project-scoped equivalent with a short `staleTime` when no push signal exists. The hook handles request cancellation, shared caching across observers, and unmount safety. Prefer subscribing via the hook over imperative cache reads — components should observe the data, not pull it on demand.

**Debugging:** The shared client is exposed as `window.__TANSTACK_QUERY_CLIENT__`, so the cache is inspectable from the browser console — `__TANSTACK_QUERY_CLIENT__.getQueryCache().getAll()` lists every cache entry, `.invalidateQueries({ queryKey: ["sculptor", "workspace", id, "git"] })` forces a refresh. The standalone React Query DevTools panel also auto-discovers it.

---

## `no_bespoke_fetch_caching`

**Question:** Is an HTTP-fetched response being stored in a Jotai atom or `useState`?

HTTP-pulled data — anything `fetch`-ed from the backend via the generated API client — lives in the TanStack cache, keyed by its query key. Mirroring it into an atom creates two sources of truth: the atom can drift from the cache after an invalidation, observers don't share fetches, and there's no abort-on-unmount. The rule covers HTTP-fetched responses only; atoms that hold WebSocket-pushed payloads are the codebase default and belong in atoms — see [`use_ws_hooks_for_pushed_data`](#use_ws_hooks_for_pushed_data).

**What to look for:**
- `atom<DiffArtifact | null>(null)` or similar with a setter that runs after an HTTP API call
- A `useEffect` that calls `setX(data)` to copy a `fetch` result into local state
- A "results cache" Map kept in module scope or an atom mirroring an HTTP endpoint — TanStack's cache already does this, keyed properly

**Fix:** Drop the atom/state, return the data from a `useQuery`-backed hook. If multiple components need it, they all subscribe to the same hook — the cache dedupes the underlying fetch.

**Exceptions:**
- WS-pushed payloads belong in atoms. The streaming-data pipeline writes to atoms; this rule is not about those.
- Client state (form drafts, optimistic UI, "currently selected item" identifiers) belongs in atoms — that's what they're for. The data behind a selected ID still belongs in TanStack if it's HTTP-pulled, or in the WS-pushed atom if it's streamed.
- Mutations follow a separate pattern: optimistically update the atom that backs the WS-pushed payload, fire-and-forget the HTTP write, and let the WS deliver the server-authoritative value to reconcile. `useMarkRead` is one example — it sets `lastReadAt` on the task atom, calls `markWorkspaceAgentRead`, and lets the WS frame settle the truth. Don't introduce `useMutation` or write-through-TanStack patterns.

---

## `use_sculptor_query_key_prefix`

**Question:** Does this TanStack query (or mutation) key start with the reserved `SCULPTOR_QUERY_KEY_PREFIX` (`"sculptor"`) as its first element?

The shared `queryClient` is handed to runtime-loaded frontend plugins through an import map, so the cache key space is partitioned by namespace: host-owned queries live under `["sculptor", …]`, while each plugin keys its queries under its own plugin id. A host key that omits the prefix sits in the unreserved root of the cache, where a plugin keyed on the same first element could read it, invalidate it, or evict it out from under the host (and vice versa). Reserving `"sculptor"` as the first element keeps the two cleanly isolated no matter what a plugin does. Every host query and mutation key — including the partial-key filters passed to `invalidateQueries` / `removeQueries` / `getQueryData` / `setQueryData` / `fetchQuery` — must start with this prefix.

Reference the exported `SCULPTOR_QUERY_KEY_PREFIX` constant from `queryClient.ts` rather than a bare `"sculptor"` literal, so the namespace has a single source of truth, and build keys through the per-query `…QueryKey` helper (see [`use_tanstack_querykey_bundle`](#use_tanstack_querykey_bundle)) so producers and the filters that target them can't drift apart.

**What to look for:**
- A `queryKey` / `mutationKey` array whose first element is a domain word (`["workspace", …]`, `["project", …]`, `["telemetry"]`) instead of the reserved prefix
- A `queryClient.invalidateQueries` / `removeQueries` / `getQueryData` / `setQueryData` / `fetchQuery` key filter that omits the prefix — a partial-key filter missing the first element silently stops matching its now-prefixed producer
- A new `…QueryKey` helper that hardcodes the prefix as a `"sculptor"` string literal instead of referencing `SCULPTOR_QUERY_KEY_PREFIX`

**Fix:** Prepend `SCULPTOR_QUERY_KEY_PREFIX` as the first element of the key, leaving the rest unchanged, and update every consumer of that key (the `useQuery` and the `invalidateQueries`/`removeQueries` that target it) in the same change.

```ts
// Bad: lands in the unreserved cache root — a plugin keyed on "telemetry" collides
key: ["telemetry", workspaceId] as const,

// Good: under the host's reserved namespace
key: [SCULPTOR_QUERY_KEY_PREFIX, "telemetry", workspaceId] as const,
```

**Exceptions:** Plugin-authored queries are keyed under the plugin's own id, not `"sculptor"` — this rule governs host-owned keys only.

---

## `wire_invalidation_into_existing_cascade`

**Question:** Does this new workspace-scoped query hook into the existing invalidation cascade, or does it sit outside it?

Workspace-scoped query keys follow the shape `["sculptor", "workspace", workspaceId, "git", …]` so the `invalidateWorkspaceGitQueries` call — triggered when the unified WS stream reports `diffUpdatedAt` advanced — invalidates every git-derived cache in one shot. Workspace-close cleanup follows the same pattern: `removeWorkspaceQueriesCache` targets the whole `["sculptor", "workspace", workspaceId]` prefix. A new hook with a custom-shaped key (e.g. `["sculptor", "myDiff", workspaceId, …]`) won't be invalidated by the cascade, and won't be evicted on workspace close. (The leading `"sculptor"` is the host's reserved namespace — see [`use_sculptor_query_key_prefix`](#use_sculptor_query_key_prefix).)

Immutable data is the deliberate exception: `useWorkspaceCommitDiff` keys under `["sculptor", "workspace", workspaceId, "commitDiff", commitHash]` — a sibling of `"git"`, not inside it — because the diff for a given commit hash is byte-identical forever, and a WS-triggered refetch would just refetch identical bytes. The whole-workspace prefix still picks it up on close.

**What to look for:**
- A new workspace-scoped query key that doesn't start with `["sculptor", "workspace", workspaceId, "git", …]` but represents mutable git-derived data
- A new query key that doesn't sit under `["sculptor", "workspace", workspaceId, …]` at all — won't be evicted when the workspace tab closes
- A new WS-stream side effect that calls `setQueryData` or a bespoke setter instead of `invalidateQueries`

**Fix:** Use the documented key shape — see the `queryClient.ts` docstring for the full hierarchy. If the data is mutable and workspace-scoped, key it under `"git"` so the cascade picks it up. If it's immutable (commit-hash-keyed, ref-pinned), key it as a sibling of `"git"` with a comment explaining why.

**Exceptions:** Project-scoped or globally-scoped queries don't ride the workspace cascade — give them their own prefix (`["sculptor", "project", projectId, …]`) and either their own invalidation trigger or a short `staleTime` if there's no push signal.

**Cascade-blind backstops:** Even when a workspace-scoped query rides the cascade, a short per-hook `staleTime` (e.g. 2 seconds) is sometimes the right backstop for cases the cascade can't catch:

- Out-of-band on-disk edits — the backend has no FS watcher, so user edits made in another editor don't bump `diffUpdatedAt`.
- Initialization-window misprimes — endpoints that silently fall back to the project repo while the workspace is still spinning up can cache the wrong data under the workspace key; the eventual cascade invalidation arrives, but observers that don't remount (e.g. a popover left open) keep serving the stale entry.

A backstop is a departure from the "trust the cascade" default, so document the specific scenario in a comment on the `staleTime` when adding one — otherwise the value looks arbitrary in review.

---

## `use_tanstack_querykey_bundle`

**Question:** Does the TanStack queryKey helper bundle the key with its validity check (`BackendQueryKeyResult`)?

TanStack queryKeys are computed every render regardless of `enabled`, so they can't contain `!` type-lies or `?? ""` fallbacks. Our convention: the queryKey helper returns `{ key, isValid }`, and the hook feeds `isValid` into `enabled`. Co-locating the two means a new required input to the key forces an `isValid` update in the same place.

**What to look for:**
- A queryKey helper that returns a bare `QueryKey` array
- `workspaceId ?? ""` or `workspaceId!` inside the queryKey
- A hook deriving `enabled` from a hand-rolled null-check chain that duplicates the queryKey's own inputs

**Fix:**

```ts
const myQueryKey = (
  workspaceId: string | null,
  filePath: string | null,
): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git", "myThing", filePath] as const,
  isValid: workspaceId !== null && filePath !== null,
});

const { key, isValid } = myQueryKey(workspaceId, filePath);
const query = useQuery({
  queryKey: key,
  queryFn: ({ signal }) => fetchMyThing(workspaceId!, filePath!, signal),
  enabled: isValid,
});
```

Extra hook-specific gates compose with `isValid`: `enabled: isValid && workspace !== null && isReady`.

---

## `use_tanstack_result_bundle`

**Question:** Does this TanStack-backed hook return `BackendQueryResult<T>` with the standard shape?

Every `useQuery`-backed hook returns `{ data, isPending, isFetching, isError, error, refetch }: BackendQueryResult<T>`. Consumers know what shape to expect regardless of which hook they're consuming. `isPending` is the right "should I render a loading state?" signal — true whenever the hook has nothing to show, covering both "gated, no fetch attempted yet" and "first fetch in flight". Components needing to distinguish "waiting to even start" from "fetch in progress" pair `isPending` with `isFetching`.

`isLoading` is a TanStack v5 field that is false while the query is disabled — using it as the loading signal hides the "gated" state and is the wrong default in our codebase. We standardize on `isPending`.

**What to look for:**
- A hook that returns the raw `useQuery` result (leaks every TanStack field, including `isLoading`)
- A hook that returns a custom shape that omits `isFetching` or `error`
- A consumer that reads `query.isLoading` instead of `query.isPending`
- A hook with extra derived state (e.g. `isGenerating` on `useWorkspaceDiff`) that returns a bare object instead of intersecting `BackendQueryResult<T>` with the extension
- A local `useState` storing `isLoading` / `isError` / `error` derived from a `useQuery` result — `BackendQueryResult<T>` already exposes those; a `useEffect` mirroring `query.isPending` into local state is redundant (a specific case of the generic [`no_redundant_state`](react.md#no_redundant_state))

**Fix:** Return the bundle (and intersect for extensions):

```ts
type UseMyThingResult = BackendQueryResult<MyData | undefined> & {
  isGenerating: boolean;
};

return {
  data: query.data,
  isPending: query.isPending,
  isFetching: query.isFetching,
  isGenerating,
  isError: query.isError,
  error: query.error,
  refetch: query.refetch,
};
```

---

## `reuse_existing_data_hooks`

**Question:** Is there already a hook (TanStack-backed or atom-backed) for this data?

Both data paths benefit from a single canonical accessor. For atom-backed hooks: every consumer subscribes to the same atom and re-renders coherently when the WS frame lands. For TanStack hooks: two components calling the same hook share one cached entry and one network fetch — a second hook that hits the same endpoint with its own query key defeats this (two fetches, two cache entries, only one refreshes on cascade invalidation).

Two consumers calling the same hook is not duplication — atom subscriptions are free, and TanStack hooks dedupe to one cache entry. Parent fetching and passing down via prop, or child reading the hook independently — pick whichever matches the surrounding component structure. What's banned is a child fetching data and pushing it up through a callback, which sidesteps the canonical accessor entirely (the generic version of this is [`no_effect_for_passing_data_to_parent`](react.md#no_effect_for_passing_data_to_parent)).

Before adding a new hook, check `sculptor/frontend/src/common/state/hooks/` for existing coverage.

**Atom-backed (WS-pushed) — read these directly, don't re-fetch:**
- Workspace metadata for one ID → `useWorkspace`
- Whether a workspace was deleted → `useIsWorkspaceDeleted`
- Project metadata → `useProject`
- List of projects → `useProjects`

**TanStack-backed (HTTP-pulled):**
- Reading a file at a ref → `useWorkspaceFileContent` (text) or `useWorkspaceFilePayload` (text + binary)
- Reading a commit's unified diff → `useWorkspaceCommitDiff`
- Reading the workspace-vs-target-branch diff → `useWorkspaceDiff`
- Listing commits ahead of the target branch → `useWorkspaceCommits`
- Listing files changed → `useWorkspaceFiles`

**What to look for:**
- A new hook whose body re-fetches data the WS already streams (should be an atom read)
- A new hook whose body calls the same generated API function as an existing TanStack hook
- A new TanStack hook with a query key that's structurally similar but not identical to an existing one (e.g. extra normalization in the args that would have been a no-op)
- An imperative `queryClient.fetchQuery` call that builds its own key by hand instead of importing the existing keying helper

**Fix:** Use the existing hook, or — if the existing TanStack hook is close but not quite right — extend it (add a new `select`-based variant that reuses the same cache key) rather than spawning a parallel cache entry.

---

## `use_derived_atoms`

**Question:** Is a component subscribing to a large atom when it only needs a small slice of that data?

Subscribing to an entire atom (e.g., `userAtom`) when you only need one field (e.g., `userId`) causes the component to re-render on *any* change to that atom — even fields the component doesn't use. Create a derived read-only atom that selects only the data needed.

**What to look for:**
- `useAtomValue(largeAtom)` followed by accessing a single property
- A component that re-renders when unrelated fields in a shared atom change

```tsx
// Bad: re-renders when any user field changes (name, email, avatar, etc.)
const user = useAtomValue(userAtom);
const userId = user?.id;

// Good: only re-renders when userId specifically changes
const userIdAtom = atom((get) => get(userAtom)?.id);
const userId = useAtomValue(userIdAtom);
```

---

## `use_narrow_atom_accessors`

**Question:** Is the component using `useAtom` when it only reads or only writes?

Use `useAtomValue` for read-only access and `useSetAtom` for write-only access. `useAtom` returns both the value and setter — if you only write, the component still subscribes to value changes and re-renders unnecessarily.

**What to look for:**
- `const [value, setValue] = useAtom(...)` where only `value` is used (use `useAtomValue`)
- `const [value, setValue] = useAtom(...)` where only `setValue` is used (use `useSetAtom`)

---

## `no_unnecessary_atoms`

**Question:** Is this state used only within a single component? If so, does it need to be an atom?

Use `useState` for component-local state. Atoms add indirection — only promote to a Jotai atom when the state is shared across components or needs to persist beyond the component lifecycle.

**What to look for:**
- An atom whose only reader and writer is a single component
- An atom created inside a component (should likely be `useState`)

**Exceptions:**
- When a component uses most fields of an atom, subscribing to the whole atom is simpler and the re-render cost is negligible.

---

## `chat_scroll_listeners_respect_programmatic_flag`

**Question:** Does this `scroll` listener on the alpha chat container distinguish user-initiated scrolls from programmatic ones?

The alpha chat scroll container has multiple `scroll` listeners that react to user intent (engage/disengage auto-scroll, save scroll position, dismiss open popovers). The container also fires `scroll` events for programmatic scrolls: virtualizer measurement corrections, `scrollToIndex` from auto-scroll, viewport-stability compensation, scroll-position restore on task switch. These events look identical to user scrolls at the DOM level. To tell them apart, `useAlphaAutoScroll` exposes a shared `isProgrammaticScrollRef` — every callsite that scrolls programmatically sets it `true` before the scroll, and `useAlphaAutoScroll.handleScroll` clears it after consuming. Any new `scroll` listener on the same container that wants to act on user intent must read this flag, or it will treat the codebase's own scrolls as user input.

**What to look for:**
- A new `addEventListener("scroll", ...)` (or equivalent) on the alpha chat scroll container that doesn't reference `isProgrammaticScrollRef`
- A new hook that triggers `scrollTo` / `scrollTop = ...` / `virtualizer.scrollToIndex(...)` without setting `isProgrammaticScrollRef.current = true` first
- Any new "dismiss popover / collapse panel on scroll" pattern that doesn't consult the flag

**Fix:** Plumb the existing `isProgrammaticScrollRef` from `useAlphaAutoScroll` into the new listener / hook. Read the flag (but do not clear it — `useAlphaAutoScroll.handleScroll` owns the clear). Read order is preserved by React's child-effect-before-parent rule: provider-level listeners registered in a child component fire before listeners registered by hooks in the parent.

```tsx
// Bad: closes popovers on virtualizer corrections too
const onScroll = (): void => {
  for (const cb of subscribers) cb();
};
el.addEventListener("scroll", onScroll, { passive: true });

// Good: skip programmatic scrolls; flag is cleared elsewhere
const onScroll = (): void => {
  if (isProgrammaticScrollRef?.current) return;
  for (const cb of subscribers) cb();
};
el.addEventListener("scroll", onScroll, { passive: true });
```

```tsx
// Bad: programmatic scroll looks like user intent to other listeners
virtualizer.scrollToIndex(messageCount - 1, { align: "end" });

// Good: mark the scroll before triggering it
isProgrammaticScrollRef.current = true;
virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
```

---

## `radix_portal_keeps_theme_scope`

**Question:** Does this overlay that portals its content (a Radix `Popover`/`DropdownMenu`/`Dialog`/`Tooltip`/`HoverCard`/`Select`, or a hand-rolled `createPortal`) render that content inside the app's `.radix-themes` scope rather than on `document.body`?

Radix Themes defines every design token — the accent scale, surface/panel backgrounds, scrollbar colors, the `--gray-a*` ramp — on the `.radix-themes` root that `<Theme>` renders. A portal that targets `document.body` lands *outside* that root, so the portaled node resolves all `var(--*)` tokens to their empty/initial values: backgrounds paint transparent, text loses its color scale, and the surface is unreadable or invisible. The trap is that the component looks correct in isolation — Storybook wraps everything in a single `<Theme>` — and only breaks in the full app, where the portal escapes the token scope. `VerticalOverlayScrollbar` is the in-repo exemplar: it portals into the theme root specifically because a `<body>` portal resolves no color and paints the thumb transparent.

**What to look for:**
- A Radix overlay primitive (or its `*.Portal`) whose content has no explicit `container` — these default to `document.body`
- A manual `createPortal(node, document.body)` for themed UI
- An overlay that renders with a transparent or unstyled background only when mounted in the real app, not in Storybook

**Fix:** Portal into the nearest themed ancestor instead of `document.body` — pass a `container` resolved from the trigger via `triggerRef.current?.closest(".radix-themes")` (the shared `THEME_ROOT_SELECTOR` constant). The content then inherits the token scope and paints correctly in the full app. The theme root still sits outside the host's `overflow` clip, so this does not reintroduce clipping.

---

## `use_select_for_flat_option_lists`

**Question:** Is this a flat list of mutually-exclusive options that should be a Radix `Select`, rather than a `DropdownMenu`?

Radix `Select` is the right primitive for picking one value from a flat list of options (a model picker, a branch picker, an enum setting). `DropdownMenu` is for command/action menus — especially true *nested* cascades with submenus. Reaching for `DropdownMenu` to render a flat option list is not just a semantic mismatch: `DropdownMenu`'s open/close lifecycle reopen-flakes in the full app (the menu intermittently fails to reopen after a close), which surfaces as a flaky interaction in integration tests. `Select` does not have this failure mode for flat lists.

**What to look for:**
- A `DropdownMenu` whose items are all single-value choices with no submenus — a flat option list wearing a menu's clothing
- A picker built from `DropdownMenu` that an integration test has to retry or that flakes on reopen
- A new single-select control where `Select` would express the intent directly

**Fix:** Use Radix `Select` for flat, mutually-exclusive option lists. Reserve `DropdownMenu` for action menus and genuine nested cascades (submenus). If you need custom-rendered options beyond what `Select` supports, prefer a `Popover` with an explicit listbox over a `DropdownMenu` pressed into single-select duty.
