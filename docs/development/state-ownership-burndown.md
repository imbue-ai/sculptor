# State-ownership burndown

Operational plan for driving the frontend's state-ownership violations to
zero. The principle being enforced is stated in
[`style/frontend.md` → State management](style/frontend.md#state-management);
the reviewer-facing rules live in
[`review/sculptor.md`](review/sculptor.md#no_dual_store_writes); the
mechanical floor is held by three ratchets (`no-fire-and-forget-api-catch`,
`no-scattered-setquerydata`, `no-noop-queryfn`). This doc is the process
that connects them: how to enumerate the remaining debt, how to judge each
site, and what "done" means.

Counts are deliberately **not** duplicated here — `ratchet-counts.toml` is
the source of truth and its git history is the burndown chart. Run
`just ratchets` for current numbers.

## Violation taxonomy

| Class | Definition | Detected by |
| -- | -- | -- |
| V1 dual-store writes | One server fact written into two stores at call sites | `no-scattered-setquerydata` ratchet + review (`no_dual_store_writes`) |
| V2 optimism without a failure path | Optimistic local write + swallowed rejection; "the WS will heal it" claimed for a *failure* (delta streams only re-send on change) | `no-fire-and-forget-api-catch` ratchet + review (`optimistic_write_without_failure_path`) |
| V3 unsound rollback | Rollback that clobbers interleaved authoritative writes, or restores only part of what `onMutate` wrote | review only (`unsound_optimistic_rollback`) |
| V4 fetch semantics on push-fed keys | No-op queryFns, unpinned `gcTime` on WS-fed key families | `no-noop-queryfn` ratchet + review (`push_fed_query_with_fetch_semantics`) |
| V5 duplicate operation paths | Two implementations of one operation with divergent consistency behavior | review only (`no_duplicate_operation_paths`) |

## Enumerating candidates

From `sculptor/frontend/src`:

```bash
# V2 candidates — swallowed rejections (judge each: was there a local write first?)
grep -rn "\.catch(() => {" . --include="*.ts" --include="*.tsx" | grep -v "\.test\."

# V1 candidates — cache writes outside queryClient.ts / mutations/
grep -rn "\.setQueryData(" . --include="*.ts" --include="*.tsx" \
  | grep -v "\.test\.\|common/queryClient.ts\|state/mutations/"

# V1/V2 candidates — optimistic atom writes on server facts near API calls
grep -rn "useSetAtom(.*AtomFamily" . --include="*.ts" | grep -v "\.test\."

# Healing-assumption comments to audit (each must be true for its path)
grep -rni "arrive.*via WebSocket\|fire-and-forget" . --include="*.ts" --include="*.tsx"
```

## Judging a candidate

A swallowed rejection is a violation **only if** (a) an optimistic local
write (cache or atom) preceded the call, **and** (b) the healing channel does
not re-send on failure. Concretely:

- Telemetry, analytics, and reply-POSTs (plugin-command results) with no
  local write: **exempt** — nothing to heal.
- Optimistic write + failure leaves the server unchanged: **violation** —
  the delta stream will never correct it. This is the class that shipped
  real bugs (stale read-state after a failed persist).

Exempt sites stay inside the frozen ratchet count. When a count must go up,
the bump needs written justification in the PR (the `ratchet-counts.toml`
header states the convention).

## Fix recipe (per surface)

The task migration (`SCU-1120`) is the template. For each surface
(workspace open/close state, workspace delete, path autocomplete, repo
segment, …):

1. Decide the fact's canonical store. If legacy readers need a second
   store, feed it from one mirror (see `useTaskQueryMirror.ts`), never from
   call sites.
2. Move the mutation to a `useMutation` hook using the shared helpers in
   `src/common/state/mutations/` — snapshot + sync-version in `onMutate`,
   version-checked symmetric rollback in `onError`, nothing in `onSuccess`.
3. Port the surface's tests (don't delete behavioral coverage; the old
   override-lifecycle tests moving onto `useMarkUnreadMutation` is the
   example).
4. Tighten the relevant `ratchet-counts.toml` entries in the same PR.

One surface per PR. Order by user-visible risk: failure paths that leave
permanently stale UI first, hygiene (duplicate paths, dead options) last.

## Known burn-down items

- `useOptimisticTaskDelete.ts` — the two `setQueryData` rollback/tombstone
  writes should move behind a delete mutation in `state/mutations/`
  (accounts for the entire `no-scattered-setquerydata` budget).
- The workspace open/close writes in `state/atoms/workspaces.ts` and
  `useOptimisticWorkspaceDelete.ts` — same optimistic-write shape as the
  old task code; classify against V1/V2 and migrate on the same recipe.
- The Jotai task atoms + `useTaskQueryMirror` — delete both once the last
  Jotai reader (`tasksArrayAtom` consumers, the per-field selector
  families) migrates to `useTask`/`useTaskIds`. This is the terminal item.

## Exit criteria

- All three ratchet budgets at `0` (then they are de-facto hard bans).
- No `unsound_optimistic_rollback` / `no_duplicate_operation_paths`
  findings across N consecutive weeks of reviews.
- The mirror and the legacy task atoms deleted.

When all three hold, delete this doc.
