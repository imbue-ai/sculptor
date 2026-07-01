# GitHub PR-Status Polling — Rate-Limit Redesign

## Executive Summary

Sculptor maintains its knowledge of every workspace's PR status by
**polling** GitHub (via `gh api graphql`). The
poller is **per-workspace**: each workspace issues its own GraphQL query on an
interval. GitHub's GraphQL primary rate limit is **5,000 points/hour per user
token**, so cost scales as `O(workspaces / interval)`. At ~20 open workspaces on
the default 30s interval this saturates the budget, polling stalls, and PR
status goes stale across the whole app.

**Root cause (measured, not estimated):** each per-workspace query costs **2
points**, and 20 workspaces × 120 polls/hr × 2 = **~4,800 points/hr — ~96% of
the 5,000 budget.** This exactly reproduces the reported "breaks around 20
workspaces" symptom.

**Chosen solution:** replace the per-workspace query with a **single
`search`-based GraphQL query per user token per poll round** that fetches *all*
of the user's open PRs across all repos in one request, plus two supporting
changes (a terminal-state follow-up fetch and a proactive rate-budget governor).
Measured cost of the search query for 20 PRs is **7 points** with
`reviewThreads first:30` → ~840 points/hr (17% of budget); the **shipped** query
trims that to `first:10` (Change 1b) for **~3 points → ~360 points/hr (~7%)**.
Either way it is a **~6×-or-better reduction** that turns the cost model from
`O(workspaces)` into roughly `O(distinct open PRs ÷ page size)`. Because each
round is so cheap, the freshness knob stays the polling **interval** (kept short
for everyone) rather than any local event trigger — see "Freshness" below.

**Before:** N workspaces ⇒ N GraphQL queries per round ⇒ ~2N points/round.
20 workspaces saturates the hourly budget.

**After:** N workspaces ⇒ 1 GraphQL query per round (paginated only beyond 100
open PRs) ⇒ ~3 points/round for 20 PRs (shipped `threads:10`; ~7 at the
`threads:30` upper bound). The same token comfortably supports 50–100
workspaces, and degrades gracefully (auto-lengthening interval) rather than
hitting a wall.

---

## Problem Statement

### Current behavior

- **Service:** `sculptor/web/pr_polling_service.py` — an app-level
  `PrPollingService` with a fixed pool of 4 worker threads pulling per-workspace
  `_PollJob`s off a priority queue.
- **Query:** `sculptor/web/pr_status.py::_GRAPHQL_PR_QUERY` — one
  `repository(...).pullRequests(headRefName, first: 5)` query per workspace,
  pulling check rollup, reviews, and unresolved review threads.
- **Cadence:** `UserConfig.pr_poll_interval_seconds` (default **30s**) for open
  workspaces; `× pr_poll_closed_multiplier` (default 6) for closed workspaces;
  `× _TERMINAL_STATE_MULTIPLIER` (10) for merged/closed PRs; floor
  `_MIN_POLL_INTERVAL_SECONDS` (10s).
- **Existing rate defenses:** global 1.5s spacing between poll starts
  (`_GLOBAL_MIN_POLL_SPACING_SECONDS`), and a reactive 60s cooldown on rate-limit
  errors (`_RATE_LIMIT_COOLDOWN_SECONDS`) over one global budget. These shape
  *bursts* but do **not** lower steady-state hourly spend.
- **Auth:** the user's own `gh` credentials (per-user token, no shared app
  token). The rate limit is therefore **per user**, shared across all of that
  user's workspaces.
- **Fan-out to UI:** an observer pattern (`add_observer`) pushes
  `PrStatusInfo` (`sculptor/web/data_types.py`) updates into the per-connection
  `stream_everything` generator (`sculptor/web/streams.py`) and into the CI
  babysitter (`services/ci_babysitter_service/coordinator.py`).

### Why it fails

GitHub GraphQL **primary** limit = 5,000 points/hour/user. Cost is
`O(workspaces / interval)`:

| Workspaces | Queries/hr (30s) | Cost/query | Points/hr | % of 5,000 |
|-----------:|-----------------:|-----------:|----------:|-----------:|
| 10 | 1,200 | 2 | 2,400 | 48% |
| **20** | **2,400** | **2** | **4,800** | **96%** ← saturates |
| 50 | 6,000 | 2 | 12,000 | 240% (broken) |

The reactive cooldown then kicks in repeatedly, so updates arrive late or not at
all. The user observes "PR status stops updating once I have ~20+ workspaces."

---

## The Cost Model (measured)

GitHub computes a query's cost as: *number of connection-fetches, assuming every
`first`/`last` reaches its limit, summed, ÷ 100, rounded, **minimum 1 point**.*
Nested connections multiply by parent cardinality.

All numbers below were measured live against `imbue-ai/sculptor` by adding
`rateLimit { cost }` to each query shape (see Appendix A for the raw runs).

### Where the current 2 points/query goes

For the current query (`pullRequests first:5`, `reviewThreads first:30`,
`comments first:1`):

| connection | fetched | count |
|---|---|---:|
| `pullRequests(first:5)` | once | 1 |
| `commits(last:1)` | per PR | 5 |
| `latestReviews(first:20)` | per PR | 5 |
| `reviewThreads(first:30)` | per PR | 5 |
| `comments(first:1)` under each thread | per PR × per thread | **150** |
| **total** | | **166 → ÷100 → cost 2** |

> **How to read this table.** GitHub charges "requests needed to fulfill each
> connection" = the connection's *parent cardinality*; a connection's own `first`
> only multiplies cost for connections nested *beneath* it. So `comments` (nested
> under `reviewThreads`, under the PRs) costs 5×30=150, whereas `latestReviews` —
> which has nothing nested under it — costs just 5 (one per PR), and its own
> `first:20` is **cost-free**. Every row here matches the live `rateLimit.cost`
> measurements in Appendix A (e.g. varying `latestReviews` from `first:1` to
> `first:100` leaves the round at `cost 2`, confirming it is not a multiplier).
> The measured `cost` remains the final authority — re-measure the exact
> production query (Risk #4) before the governor relies on any projection.

**~90% of the cost is the `comments`-under-`reviewThreads` fan-out.** The
`pullRequests(first: 5)` multiplies that dominant term by 5, and the
`reviewThreads(first: 30)` is the other multiplier. Both are larger than needed:

- `pullRequests first:N` — `1→3` cost **1**, `5` cost **2**, `10` cost **3**.
- `reviewThreads first:M` (at PRs=5) — `1→10` cost **1**, `30` cost **2**,
  `50` cost **3**.

So today every poll pays **2** where **1** would do — a flat ~2× overpay, in
every workspace, every round.

### Why batching by `search` wins (and aliasing does not)

Measured, identical field selection, 4 PRs:

| Approach | cost |
|---|---:|
| 4 separate per-workspace queries | 2+2+2+2 = **8** |
| 1 query, 4 PRs via `repository` **aliases** | **7** (near-wash) |
| 1 **`search`** query, 4 PRs | **1** |

Naive aliasing is a near-wash — it just sums the same per-branch connection
costs — which is the intuitively-correct "points are conserved" result.
`search` wins because it changes the *shape*: it fetches **exactly the PRs
needed** through a single top-level connection (no 5×-per-branch over-fetch),
so the per-PR cost amortizes to ~0.33 instead of 2.

Collapsing N requests/round into one also relieves GitHub's **secondary** rate
limits (per-minute points and concurrent-request caps), which the primary-budget
math above doesn't capture and which `_GLOBAL_MIN_POLL_SPACING_SECONDS` exists
today to dodge — a bonus the REST-with-ETag alternative (below) does *not* get,
since 304s aren't documented to exempt the secondary limits.

### Search scaling (measured)

| Open PRs | 1 `search` query | N separate queries (~2 ea) | ratio |
|---------:|-----------------:|---------------------------:|------:|
| 1 | 1 | 2 | 2× |
| 4 | 1 | 8 | 8× |
| 10 | 3 | 20 | 6.7× |
| **20** | **7** | **40** | **5.7×** |
| 50 | 17 | 100 | 5.9× |
| 100 | 33 | 200 | 6× |

Steady state ≈ **0.33 points/PR** vs **2 points/query** today — a durable ~6×.

---

## Goals & Non-Goals

### Goals
1. PR status stays timely for users with 50+ workspaces on a single token.
2. Cost model becomes `O(distinct open PRs ÷ page size)`, not `O(workspaces)`.
3. Degrade **gracefully** (auto-lengthen interval) instead of hitting a wall.
4. No regression in surfaced data: state, check rollup, reviews/approvals,
   unresolved threads, base-branch mismatch detection, merged/closed transitions.
5. No new hosted infrastructure; keep using the user's own `gh` token.

### Non-Goals
1. Webhooks / push-based delivery (requires hosted ingress — see Rejected).
2. Sub-second freshness. Status remains poll-based; the target is "timely,"
   not "instant."
3. Changing the UI contract (`PrStatusInfo`) or the observer/stream fan-out.
4. Surfacing PRs **not authored by the token owner.** Every PR a Sculptor
   workspace opens is created by the agent running `gh` with the user's own
   credentials (the "Create PR" prompt — `user_config.py:208` — instructs the
   agent to "create a pull request using the GitHub CLI"), so it is authored by
   `@me`. Sculptor is a **single-user desktop app**, so the PR-creating agent and
   the polling host share that one user's `gh` identity — the search's
   `author:@me`, evaluated with the same identity, always matches the workspace's
   own PRs. The current query surfaces a *teammate's* PR on a tracked branch only
   incidentally (it doesn't filter by author); that was never a designed
   feature, and `author:@me` intentionally drops it. This keeps the cost model
   from being shaped by an out-of-scope case (see Change 2).

---

## Chosen Design

Three changes, in priority order. **Change 1 is the core fix**; 2–3 harden it.

### Change 1 — One `search` query per token per round (core)

Replace per-workspace `_GRAPHQL_PR_QUERY` with a single per-token query:

```graphql
query($q: String!, $prCount: Int!, $after: String) {
  search(query: $q, type: ISSUE, first: $prCount, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number title url state baseRefName
        repository { nameWithOwner }
        headRefName
        mergeable                       # REQUIRED — drives has_conflicts → MERGE_CONFLICT (see note)
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
        latestReviews(first: 20) { nodes { state author { login } } }  # left at 20: cost-free (no nested connection)
        reviewThreads(first: 10) {      # trimmed 30 → 10 (see Change 1b)
          totalCount                    # ALL threads (resolved+unresolved); not an unresolved count — see Change 1b caveat
          nodes { isResolved comments(first: 1) { nodes { author { login } path line body } } }
        }
      }
    }
  }
  rateLimit { cost remaining limit resetAt }
}
```

with `$q = "is:pr state:open author:@me archived:false sort:updated"`.

> **`sort:updated` is required, not cosmetic.** `_first_matching_target`
> (`pr_status.py:112`) returns the *first* PR matching a base branch and relies
> on the query ordering PRs most-recently-updated first (today's per-branch
> query sets `orderBy: {field: UPDATED_AT, direction: DESC}` —
> `pr_status.py:166`). `search` defaults to *best-match* relevance order, so
> without `sort:updated` the "most recently touched PR wins" tie-break breaks
> when one branch carries two open PRs against the same base. Adding it to `$q`
> preserves today's semantics.

> **`mergeable` is not optional.** The current per-workspace query fetches it
> (`pr_status.py::_GRAPHQL_PR_QUERY`) and `_parse_conflict_status` maps it to the
> tri-state `has_conflicts`, which `classify_transitions`
> (`ci_babysitter_service/transitions.py`) reads *directly* to fire
> `Transition.MERGE_CONFLICT`. It is a scalar (no connection), so it adds ~zero
> point cost. Omitting it would make `has_conflicts` permanently `None` and
> silently kill the babysitter's merge-conflict prompt for open PRs — a Goal-#4
> regression. It must ride on every open-PR node in the hot search query: a PR
> that the search *matches* never triggers Change 2's unmatched-branch fetch, so
> its conflict signal has nowhere else to come from.

> **`latestReviews(first: 20)` is left at 20 — do *not* trim it.** It looks like
> a fan-out term but is not: it has no nested connection, so (measured) its
> `first` value has **zero** effect on cost — `first:1` and `first:100` both leave
> the round at the same `cost`. Only `reviewThreads` (which nests `comments`) is
> worth trimming. Keeping 20 preserves every reviewer's latest state at no cost.

> **`rateLimit { ... limit ... }`** is selected so Change 3's governor can target
> a fraction of the *actual* limit rather than hardcoding 5,000 (GitHub App
> tokens, were Sculptor ever to use one, get a higher limit).

**Key properties:**
- **One query spans all repos.** `author:@me` is not repo-scoped, so a single
  request covers every workspace's PR across every repo the token can see — no
  repo enumeration needed. (See the `author:@me` trade-off below, and Risk #1.)
  Note this drops the `{owner}/{repo}` cwd-expansion the current query relies on
  (`gh` fills those from the working dir's `origin` — `pr_status.py:207`): the
  token-global search runs from no specific repo, so the fan-out must derive each
  workspace's `nameWithOwner` by **parsing its `origin` URL** (today the poller
  only calls `_is_github_url(origin_url)` and never parses owner/repo — this is
  new, small, work).
- **Mapping — index for fan-out, but cache per workspace.** Build a transient
  index `(repository.nameWithOwner, headRefName) -> list[PrNode]` from the round
  (a *list*, because one source branch can carry several PRs targeting different
  bases). The **persisted cache stays keyed by `WorkspaceID`**
  (`_cache: dict[WorkspaceID, PrStatusInfo]`, unchanged from today) — *not* by
  `(repo, branch)`. This matters because `PrStatusInfo` is **workspace-relative**:
  it carries `workspace_id` and the `mismatched_pr_*` fields, which are computed
  by comparing each PR's `baseRefName` to *that workspace's* `target_branch`. Two
  workspaces can share the same `(repo, headRefName)` but have different targets,
  so the *same* PR node yields a "match" `PrStatusInfo` for one and a "mismatch"
  one for the other. For each tracked workspace, look up its `(repo, branch)` in
  the index, pick the open PR whose `baseRefName` matches its target (the
  existing `_first_matching_target` logic), derive a per-workspace `PrStatusInfo`,
  diff it against the cached one for that `WorkspaceID`, and emit only changes
  through the existing observer pattern.
- **`author:@me` is correct for the goal, with one intentional behavior change.**
  The current query does *not* filter by author
  (`pullRequests(headRefName: $branch)` returns PRs on the branch regardless of
  who opened them). Because every PR a workspace opens is authored by the token
  owner (Non-Goal #4), `author:@me` matches all of them — it is the right filter.
  The only thing it drops is the *incidental* surfacing of a **teammate's** PR on
  a tracked branch, which is an explicit non-goal; it is not preserved and does
  not drive any fallback. The unmatched-branch fetch in Change 2 exists for a
  different reason: the user's *own* PR can leave `state:open` (merged/closed),
  be absent at cold-start, or transiently drop out of the search index. See
  Change 2 and Risk #1.
- **Pagination.** `first: 100`; follow `pageInfo` only when a user genuinely has
  >100 open PRs (rare). `log()` if pagination ever triggers so silent truncation
  can't masquerade as "all covered." Note the cost is `O(all the user's open
  PRs)`, *including PRs in repos with no Sculptor workspace* — see the cost
  caveat below.
- **Self-throttling input.** `rateLimit { cost remaining limit resetAt }` rides
  in the same response, feeding Change 3 with zero extra calls.

> **Cost scope caveat.** Because `author:@me` is token-global, the search pays for
> *every* open PR the user has across *every* repo — not just the ones backing a
> Sculptor workspace. A user with 150 unrelated open PRs pays the paginated cost
> (~33 pts/round at 100, more beyond) even with two workspaces open. Scoping the
> query with explicit `repo:` qualifiers would bound this to workspace repos, but
> reintroduces the repo enumeration this design deliberately avoids and risks
> overrunning the search query-length limit; left out by choice. Revisit if a
> user's unrelated-PR volume proves to dominate the budget in practice.

**Change 1b — trim the `reviewThreads` page size.** Independently of search,
`reviewThreads(first: 30 → 10)` halves the dominant cost term (measured: at
PRs=5 it takes cost 2→1; in the search shape, at 20 PRs, it takes the round from
cost 7 → ~3). `reviewThreads` is the *only* page size worth trimming — it nests
`comments`, so its `first` multiplies the cost; `latestReviews` nests nothing and
its `first` is cost-free, so leave it at 20 (see the note in Change 1). Ten
threads is ample for the UI in practice.

> **Caveat on the "+N more" affordance.** `reviewThreads.totalCount` counts
> **all** review threads (resolved *and* unresolved), but the UI surfaces only
> *unresolved* ones (`_parse_review_comments` filters on `isResolved` —
> `pr_status.py:294`), and the `reviewThreads` connection has **no server-side
> `isResolved` filter**, so there is no cheap way to get an exact unresolved
> count beyond the page we fetch. So `totalCount` is *not* an unresolved count
> and "+N more unresolved" computed from it would over-count. Options: (a) label
> the affordance as total review threads, not unresolved; (b) only show "+N
> more" when the fetched page is full (`len(unresolved) == first` after
> filtering), accepting that we can't give an exact remainder; or (c) drop the
> count and show a generic "more threads on GitHub →" link. Pick one in
> implementation; do not present `totalCount` as the unresolved remainder.

This is a one-line query change and should land first as an interim mitigation
even before the search refactor (see Rollout Phase 0).

### Change 2 — Per-workspace fallback for any branch the search doesn't match

`state:open author:@me` returns only the user's currently-open PRs. It can never
*affirmatively* report "this branch has no PR" — a branch with no open authored
PR is simply absent from the results, indistinguishable from one that didn't
match. So a workspace is **"unmatched"** whenever no node in the round's
`(repo, branch) -> list[PrNode]` index satisfies its target, and that spans two
very different populations:

- **Transient / terminal** (the cases the search *should* have covered): the
  user's own PR merged/closed (left `state:open`), was already terminal at cold
  start, or transiently dropped out of the search index for one round.
- **Steady-state no-open-PR** (common, and *not* a transition): a feature branch
  with no PR opened yet, or a workspace sitting on its target/base branch (no PR
  is possible). A teammate-only PR also lands here — it is a non-goal (Non-Goal
  #4), so it just resolves to `none`; we do not chase it.

**First, skip what cannot have a PR** — preserve today's short-circuits *before* a
branch enters the unmatched set. A workspace with no branch info / not yet ready,
or whose `current_branch == strip_remote_prefix(target_branch)`
(`pr_polling_service.py:699`), resolves to `none` with **no fetch at all**.

**For the rest, fall back to per-workspace polling — at the workspace's own
cadence, *not* once per search round.** Each unmatched workspace issues one
targeted, author-agnostic, all-states fetch via the existing
`_fetch_prs_with_details` query (`repository(owner,name){ pullRequests(headRefName,
first:5, ...) }`, all states, includes `mergeable`) — *exactly today's
per-workspace poll*. Its next fetch is scheduled by `_compute_poll_delay` (base
interval, with the closed/terminal multipliers), **independent of the
search-round interval**. This decoupling is load-bearing: the search round may be
shortened (the batch is cheap), but the fallback fetches must keep their own
cadence — otherwise shortening the round would multiply per-workspace cost for
every no-open-PR branch. Outcomes:

- **Terminal PR** (`MERGED`/`CLOSED`) → emit terminal `PrStatusInfo`; the
  `_TERMINAL_STATE_MULTIPLIER` backoff puts it on the slow terminal cadence.
- **Open PR** (a search-index drop-out that is actually still open) → full open
  `PrStatusInfo`, as today.
- **No PR** (no-PR-yet, base-branch already filtered above, or teammate-only) →
  `pr_state="none"`, re-checked at the base cadence. If a prior round showed it
  open and this is a one-round index blip, the empty result is a **no-op** —
  never emit a spurious terminal transition; the next round resolves it.

Route these fallback fetches through the **same `_HostThrottle`** as the search
(global spacing + rate-limit cooldown) and reuse the per-workspace
`first_failure` / cooldown handling that already wraps `fetch_pr_status`.

**Cost, stated honestly.** The redesign is *cheap for workspaces with a
currently-open authored PR* — they ride the one batched search for free.
Workspaces *without* one (no-PR-yet, terminal, base-branch) still cost one
per-workspace `gh` call at their normal cadence — **the same as today**. So the
saving scales with the fraction of tracked workspaces that have an open PR; in
the 20+-active-workspace scenario that motivated this, that fraction is high, so
the batch absorbs most of the spend. What the design removes is the
*per-open-PR-per-round* blow-up that saturates the budget; what it does **not**
remove is baseline per-workspace polling for branches with no open PR. The
governor (Change 3) sees the combined spend via `remaining` regardless. One
transient remains: a **cold-start burst** — on the first round every
already-terminal / no-PR workspace is unmatched and fetched once before settling
onto its (slow or base) cadence; bounded, one-time, `log()` the count.

This preserves the merged-conflict / merged-success transitions and the open-PR
`mergeable`/`has_conflicts` signal the CI babysitter
(`ci_babysitter_service/coordinator.py`, `transitions.py`) depends on.

### Change 3 — Proactive rate-budget governor

Today the only defense is a *reactive* 60s cooldown after a 403. Add a
**proactive** governor driven by the `rateLimit` block returned in every search
response:

- Maintain a target ceiling at `pr_poll_budget_fraction` of the `limit` reported
  in the response (default **80%** → ~4,000 points/hr on a 5,000 token). Reading
  `limit` from the response rather than hardcoding 5,000 keeps this correct if
  the token's budget ever differs (e.g. a GitHub App token).
- After each round, compute the projected hourly spend and, if it would exceed
  the ceiling, **lengthen the interval** (multiplicative back-off) until
  projected spend fits, recovering toward the configured interval when headroom
  returns.
- **Drive the projection off `remaining`, not just the search query's `cost`.**
  The search response's `cost` covers only the one batched query; the Change 2
  unmatched-branch fetches each spend separately (their own `gh` calls, with
  their own `rateLimit` blocks) and are *not* in the search response's `cost`.
  `remaining` (and `resetAt`), by contrast, reflect the token's **global**
  GraphQL budget across every query that hour, so basing back-off on the
  observed *rate of decline of `remaining`* — or on `(limit - remaining)`
  extrapolated to the hour — captures search **and** unmatched-fetch spend
  together. Use the per-round `cost` only as a lower-bound sanity check.
- If `remaining` is already low, defer the next round until `resetAt`.

Result: the system *never* hits the wall; it trades freshness for budget
smoothly and visibly (surface "PR updates throttled to respect GitHub rate
limits" in the UI rather than failing silently).

### Freshness — the interval is the only reliable knob

We deliberately do **not** try to trigger polls on a local push (to justify a
longer interval by catching the user's own changes via an event), for two
reasons:

- **A local push is not reliably observable.** There is no push event and no
  HEAD-sha in the stream — `WorkspaceBranchInfo` carries only `current_branch`
  (`data_types.py:51`), and `on_branch_changed` fires on a branch *switch*
  (`streams.py:749`: `prev != current_branch`), not on new commits to the same
  branch. And a user can push from anywhere — another machine, the GitHub web
  UI, a rebase in a different checkout — none of which Sculptor's single managed
  working dir can see.
- **A local push is the wrong signal anyway.** It is a *minority* of what
  changes PR status: reviews, approvals, comments, someone else merging, the
  base branch moving, and **CI completing** are all *remote* events with no
  local correlate. CI is also *asynchronous* — checks go pending on push and
  resolve minutes later — so even a perfectly-detected push fires too early to
  observe the outcome you care about; interval polling has to catch it regardless.

For a local-first app with no webhook ingress, **PR-status freshness is
fundamentally bounded by the polling interval** — the authoritative state lives
on GitHub and changes for reasons we cannot observe locally. The redesign does
not fight this; it makes the *batched* round *cheap*. Because a batched round is
~3–7 points (20 open PRs, `threads:10`–`30`) vs ~4,800 points/hr today, there is
no need to lengthen the interval — the default 30s sits at ~7–17% of budget, and
the governor (Change 3) only stretches it under genuine pressure. One caveat if
you *shorten* it below 30s: the batch stays cheap, but Change 2's per-workspace
fallback fetches (for no-open-PR branches) are **not** batched, so they must keep
their own per-workspace cadence rather than firing once per (shortened) round —
see Change 2. Shortening the search round speeds up open-PR freshness without
multiplying fallback cost only if that decoupling holds.

The existing immediate re-poll on `on_branch_changed` / `on_workspace_ready`
(`streams.py:748–750`) is **retained** — it gives instant feedback on a
branch-switch or freshly-created PR, which is reliable and reuses code that
already exists. It is existing behavior, *not* a push trigger, and is not
relied on to relax the interval.

*Optional / future:* if sub-interval freshness on specific PRs is ever wanted,
the *reliable* lever is **foreground/visibility** — poll the workspace the user
is actively viewing more often — because focus is a local, observable signal,
unlike a push. That needs a focus signal from the frontend and is out of scope
here.

### Resulting cost (20 workspaces *that each have an open PR*, 30s interval)

| | Queries/hr | Points/hr | % of 5,000 |
|---|---:|---:|---:|
| Current (per-workspace) | 2,400 | ~4,800 | 96% |
| Change 1 alone (search, threads:10) | 120 | ~360 | 7% |
| Change 1, threads:30 | 120 | ~840 | 17% |
| + interim Phase 0 trim only (no search) | 2,400 | ~2,400 | 48% |

At 50 workspaces the search design is ~2,040 pts/hr (41%); at 100, ~3,960 (79%,
where Change 3 begins stretching the interval). The wall is gone.

> **These figures are the search-query cost for the open-PR population only.**
> Three things to keep in mind:
> (1) **They assume every counted workspace has an open authored PR**, so it
> rides the batch. Workspaces *without* one (no-PR-yet, terminal, base-branch)
> are **not** in these numbers — they still cost one per-workspace `gh` call at
> their own cadence (Change 2), i.e. ~today's cost for that subpopulation. Total
> spend ≈ (one batched search per round) + (per-workspace polling of the
> no-open-PR workspaces). The saving scales with the open-PR fraction.
> (2) The 50/100-workspace projections use the **`threads:30`** cost (17/33
> pts/round); the **shipped** query uses `threads:10` (Change 1b), ~2.3× cheaper,
> so the open-PR cost is well under these (100 open-PR workspaces ≈ ~1,560 pts/hr,
> ~31%). The table keeps `threads:30` as the pessimistic bound.
> (3) The governor (Change 3) sees the *combined* spend — batch + per-workspace
> fallbacks + cold-start burst — via `remaining`, not by summing these per-query
> costs, so it backs off correctly regardless of the open-PR fraction.

---

## Component-Level Changes

> Paths below are abbreviated `sculptor/web/...`; the real tree is nested
> `sculptor/sculptor/web/...` (and `PrStatusInfo` is defined in
> `sculptor/sculptor/web/data_types.py`, re-exported via `web/derived.py`).

- **`sculptor/web/pr_status.py`**
  - Add `fetch_open_prs_for_token(working_dir) -> list[PrNode]` issuing the
    search query (Change 1) and parsing nodes into the existing intermediate
    shape used by `_parse_reviews` / `_parse_review_comments`.
  - **Reuse `fetch_pr_status` / `_fetch_prs_with_details` verbatim for Change
    2's unmatched-branch fetch** — that existing path is already an
    author-agnostic, all-states, single-branch query that includes `mergeable`
    and builds the full open *or* terminal `PrStatusInfo`. No new
    `fetch_terminal_pr` is needed; the only addition is the new search-based
    `fetch_open_prs_for_token`.
  - Trim `reviewThreads` to `first: 10` (Change 1b); leave `latestReviews` at
    `first: 20` (cost-free, no nested connection). Keep `_PR_QUERY_LIMIT` for the
    unmatched-branch fetch path.
  - **Keep `mergeable` in the search query** (Change 1 note) so open-PR
    `has_conflicts` survives.
- **`sculptor/web/pr_polling_service.py`**
  - Re-architect the worker model from **per-workspace jobs** to **one
    per-token poll round** that builds a transient
    `(repo, branch) -> list[PrNode]` index and derives a **per-`WorkspaceID`**
    `PrStatusInfo` from it (see Change 1 "Mapping"), plus a small queue of
    unmatched-branch fetches (Change 2). The 4-thread pool collapses to a single
    periodic poller per distinct token (typically one), with a side-worker for
    the unmatched-branch fetches.
  - Keep the observer registry and the cache **keyed by `WorkspaceID`**
    (`_cache: dict[WorkspaceID, PrStatusInfo]`, unchanged) — the `(repo, branch)`
    index is transient and for fan-out only, *not* the cache key.
  - Implement Change 3 (governor) here, reading the `rateLimit` block.
  - Retain the immediate re-poll on `on_branch_changed` / `on_workspace_ready`
    (routed through the token-level poller); do **not** add a push trigger (see
    "Freshness").
  - Constants: `_GLOBAL_MIN_POLL_SPACING_SECONDS` is near-moot with one batched
    query per round (it still spaces Change 2's fallback fetches);
    `pr_poll_interval_seconds` can stay at its 30s default (batching removes the
    budget pressure to raise it). The `_HostThrottle` is a single global budget,
    so the governor slots in directly.
  - **Cadence knobs govern the per-workspace *fallback*, not the batch.**
    `pr_poll_closed_multiplier` and `_TERMINAL_STATE_MULTIPLIER` do not affect a
    workspace *with* an open PR — those ride the batch for free, open or closed.
    They are **load-bearing for Change 2's fallback fetches**: a closed or
    terminal workspace with no open authored PR still polls per-workspace, and
    these multipliers are what keep that fallback cheap (poll a closed/terminal
    no-PR workspace rarely). Keep and apply both in `_compute_poll_delay` for the
    fallback path.
- **`sculptor/web/streams.py`**
  - `_notify_pr_polling_service`: route branch/workspace events to the new
    token-level poller (the existing `on_workspace_created` / `on_workspace_ready`
    / `on_branch_changed` / `on_workspace_deleted` calls and the
    `PrStatusInfoCleared` injection are unchanged). No push trigger.
- **`sculptor/web/data_types.py`**
  - Optional cleanup: `error_provider: Literal["github"] | None` is single-valued
    (GitHub is the only provider) — drop it, or leave as a documented no-op. Not
    required by this change, but a natural tidy while here.
- **`sculptor/sculptor/config/user_config.py`**
  - Keep `pr_polling_enabled`, `pr_poll_interval_seconds`, and
    `pr_poll_closed_multiplier` (it sets the cadence of Change 2's per-workspace
    fallback for closed/no-PR workspaces; see the poller bullet above). Add
    `pr_poll_budget_fraction` (default 0.8) for Change 3. The default interval
    stays at 30s — batching removes any budget pressure to raise it.
- **Tests** — `pr_polling_service_test.py`, `pr_status_test.py`,
  `test_backend_pr_polling.py`: update for the search shape, add unmatched-branch
  fetch coverage (terminal / cold-start / index-blip no-op + terminal-cadence
  exclusion), `mergeable`→`has_conflicts`, governor back-off math, and the
  shared-branch / different-target fan-out. See **Testing Strategy** for the full
  list.

---

## Rejected / Deferred Alternatives

### Webhooks + hosted relay (deferred — the "real" long-term fix)
A GitHub App delivering `pull_request` / `pull_request_review` /
`check_suite` / `issue_comment` events to a **hosted Sculptor relay** that
pushes to the local client over the existing WebSocket would make cost `O(1)` in
workspace count and updates instant. **Deferred** because Sculptor is local-first
with **no public ingress**: this requires hosting infra, a GitHub App, user
installation, and org-policy handling — a model change well beyond this issue.
Revisit if/when Sculptor grows a hosted component.

### REST conditional requests (ETag / 304) (deferred — not the cheapest here)
`304 Not Modified` responses don't count against the **primary** limit, so
"most PRs don't change" sounds like a free win. Rejected as the primary lever
because: (a) the four signals we show live on **separate REST resources with
separate ETags**, turning one GraphQL call into ~4 REST calls per PR; (b) the
**secondary** per-minute/concurrency limits are **not** documented to exempt
304s, so request *volume* still bites at scale; (c) it does nothing about the
per-workspace structure and adds multi-resource ETag bookkeeping plus a drop
from `gh api graphql` to raw REST. `search` solves the same quota problem more
cheaply and with less code. Keep on the shelf if foreground-freshness ever needs
shaving.

### Naive GraphQL aliasing (rejected — near-wash)
Combining per-workspace queries via `repository` aliases measured **7 vs 8**
points for 4 PRs — essentially no benefit, because cost sums the same per-branch
connection-fetches. Only the `search` *shape* (exact `first:N`, single top
connection) delivers the reduction.

---

## Rollout Plan

- **Phase 0 (hours, interim):** ship Change 1b alone — `reviewThreads 30 → 10`.
  One line, halves current cost (96% → ~48% at 20 workspaces), buys headroom
  while the refactor lands. Caveat: this lowers the unresolved-comment cap from
  30 to 10 threads per PR, so a PR with >10 unresolved threads would surface
  fewer comments — ship the "+N more" affordance alongside it (see the
  `totalCount` caveat in Change 1b — it counts all threads, not unresolved
  ones), or accept the lower cap.
- **Phase 1 (core):** implement Change 1 (search poller + per-workspace fan-out
  mapping, **including `mergeable`**) and Change 2 (unmatched-branch fetch),
  **replacing** the per-workspace poll path outright — no feature flag. Before
  merging, validate the production query's real `cost` with `rateLimit { cost }`
  and confirm `has_conflicts` / MERGE_CONFLICT still fire (the existing
  integration suite, extended per Testing Strategy, is the gate).
- **Phase 2 (harden):** Change 3 (governor). Keep the interval short — batching
  removes any need to lengthen it (see "Freshness").

No feature flags: the search path replaces the per-workspace path directly, and
each phase stands alone (Phase 0 is a one-line query edit; Phase 2 only adds the
governor on top of Phase 1). The existing `pr_polling_enabled` kill switch is
retained — it is the user-facing on/off for polling, not a rollout flag. The
safety net is the test suite and a clean revert, not a runtime toggle.

---

## Risks & Open Questions

1. **`author:@me` scoping (resolved by design, not left open).** `author:@me
   state:open` is the *correct* filter, not a compromise: every PR a workspace
   opens is authored by the token owner (Non-Goal #4), so it matches all of
   them. The cases where a tracked branch's own PR is absent from the round — it
   merged/closed (including at cold start), or got dropped by a search-index
   blip — are **handled by default** via Change 2's targeted all-states fetch
   for unmatched branches. (A teammate-authored PR is intentionally *not*
   chased — see Non-Goal #4.) The residual question is *cost*, and it is **not**
   just the transition rate: the unmatched set also includes the steady-state
   **no-open-PR** population (feature branches with no PR yet — base-branch
   workspaces are short-circuited before fetching), which keeps polling
   per-workspace at the base cadence (≈ today's cost). Measure the open-PR
   fraction across real fleets: that fraction is what the batch saves, and the
   remainder sets the per-workspace residual the governor must absorb. The win is
   largest when most active workspaces have an open PR (the motivating scenario).
2. **Search-index lag.** GitHub's search index can trail live state by
   seconds–minutes, so the `search` round can briefly miss a just-changed PR.
   Two backstops already in the design: a still-open PR that transiently drops
   out is re-resolved by Change 2's unmatched-branch fetch (and an empty result
   is treated as a no-op, never a spurious terminal transition); and the next
   round catches anything the index was lagging on. If foreground freshness ever
   feels laggy, the targeted single-branch fetch (Change 2's query, author-
   agnostic and index-free) can be run directly for the viewed PR.
3. **`mergeable` UNKNOWN.** Computed async; may need a re-poll. Pre-existing
   behavior, not a regression, but the governor must not thrash on it.
4. **Measured `cost` is selection-dependent.** At 20 PRs the round costs ~7 with
   `reviewThreads first:30` and ~3 with `first:10`; **re-measure the exact
   production query** with `rateLimit { cost }` before committing the governor's
   projections.
5. **Multiple tokens *and* multiple hosts.** The single token-global search runs
   against one GitHub host with one identity. If a Sculptor instance ever spans
   multiple GitHub identities, run one poll round per distinct token (the
   per-token budget is independent). Note also that `_is_github_url`
   (`pr_polling_service.py:213`) matches *any* hostname containing "github",
   which includes **GitHub Enterprise** hosts — workspaces could point at
   `github.com` and a GHE instance simultaneously. A single search round can't
   cover both, so the poller must key its round (and its `gh` invocation's host
   resolution) by **(host, token)**, not assume one global GitHub. Common case
   today is a single (host, token); this is the generalization point.

---

## Testing Strategy

- **Unit (`pr_status_test.py`):** search-response parsing → `PrStatusInfo`,
  including check rollup, approvals, unresolved threads, base mismatch, **and
  `mergeable` → `has_conflicts`** (CONFLICTING/MERGEABLE/UNKNOWN/missing →
  True/False/None/None); unmatched-branch all-states fetch parsing (open,
  merged, closed).
- **Unit (`pr_polling_service_test.py`):**
  - (repo,branch)→workspace fan-out, **including two workspaces sharing one
    `(repo, headRefName)` with different `target_branch`** → one gets a match,
    the other a `mismatched_pr_*` `PrStatusInfo` (proves the cache is keyed by
    `WorkspaceID`, not `(repo, branch)`).
  - unmatched-branch fetch for each cause: merged/closed → terminal; cold start
    (no prior round) → resolved; and a one-round search-index drop-out → **no
    spurious terminal transition** (empty terminal result is a no-op).
  - **short-circuit before fetching**: a workspace whose `current_branch ==
    target` (or with no branch info / not ready) resolves to `none` with **zero
    `gh` calls** — assert no fallback fetch is issued.
  - **fallback cadence is decoupled from the search round**: a no-PR-yet feature
    branch is re-checked at the **base interval** (`_compute_poll_delay`), *not*
    once per search round — assert that halving the search-round interval does
    **not** change its fallback fetch frequency; and a closed/no-PR workspace
    polls at the `pr_poll_closed_multiplier` cadence.
  - **terminal-cadence exclusion**: a workspace resolved to merged/closed is
    *not* re-fetched on every subsequent search round (it moves to the terminal
    cadence) — assert the unmatched-fetch count tracks the transition rate +
    no-open-PR population at their cadences, not O(workspaces) per round.
  - governor back-off/recover math against the response's `limit`/`remaining`
    (including spend from Change 2 fetches, via `remaining` decline);
  - pagination trigger + `log` on >100 PRs; cold-start burst `log`.
- **Integration (`test_backend_pr_polling.py`):** end-to-end WebSocket — open →
  approved → **conflict (has_conflicts True, MERGE_CONFLICT fires)** → merged
  transition still surfaces; a branch switch (`on_branch_changed`) triggers an
  immediate re-poll.
- **Cost regression guard:** a test (or CI check) that asserts the production
  query's `rateLimit.cost` stays within an expected band, so a future field
  addition that balloons the fan-out is caught early.

---

## Appendix A — Raw Measurements

Measured live against `imbue-ai/sculptor` with an authenticated `gh` token
(GraphQL budget 5,000/hr), by appending `rateLimit { cost }` to each shape.

```
# Separate (current per-workspace shape), 4 real branches
  saeed/scu-1523                          -> cost 2
  maciek/scu-1522-disable-plugins         -> cost 2
  saeed/scu-1504                          -> cost 2
  bry/scu-1524-restack-stacked-branches   -> cost 2
  SUM = 8

# Combined, 4 PRs via repository aliases   -> cost 7   (near-wash)
# Search, 4 PRs                            -> cost 1

# pullRequests(first:N), single branch
  N=1 ->1   N=2 ->1   N=3 ->1   N=5 ->2   N=10 ->3

# reviewThreads(first:M) at pullRequests first:5
  M=1 ->1   M=5 ->1   M=10 ->1   M=30 ->2   M=50 ->3

# search(first:N), one query, threads first:30
  N=1 ->1   N=4 ->1   N=10 ->3   N=20 ->7   N=50 ->17   N=100 ->33
```

## Appendix B — Key References

- Poller: `sculptor/sculptor/web/pr_polling_service.py`
- GitHub query: `sculptor/sculptor/web/pr_status.py` (`_GRAPHQL_PR_QUERY`,
  `_PR_QUERY_LIMIT`, `_parse_conflict_status`)
- Data type: `sculptor/sculptor/web/data_types.py` (`PrStatusInfo`)
- Stream fan-out: `sculptor/sculptor/web/streams.py` (`stream_everything`,
  `_notify_pr_polling_service`)
- CI babysitter consumer:
  `sculptor/sculptor/services/ci_babysitter_service/coordinator.py`,
  `transitions.py`
- Config: `sculptor/sculptor/config/user_config.py` (`pr_polling_enabled`,
  `pr_poll_interval_seconds`, `pr_poll_closed_multiplier`)
- GitHub docs: [GraphQL rate & query limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api),
  [REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
