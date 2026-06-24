# Backend TypeScript Rewrite

## Overview

Rewrite Sculptor's backend from scratch in TypeScript, with the
explicit goal of **eliminating all unnecessary architectural
complexity**. The current backend carries significant debt from prior
designs that have since changed, and is over-engineered relative to
what the frontend actually needs.

The rewrite should produce the **simplest possible architecture** that
preserves current behavior. "Current behavior" is **not** something this
spec re-derives — it is already pinned, exhaustively and citably, by
Sculptor's existing product specification set in `docs/specs/`:

- **`SPEC.md`** — the narrative product spec: what Sculptor is and how
  every feature behaves.
- **`requirements.md`** — the measurable/contractual facts: the
  non-functional bars (`REQ-NFR-*`), platform/dependency compat
  (`REQ-COMPAT-*`), persistence & migration guarantees (`REQ-DATA-*`),
  external integration contracts (`REQ-INT-*`), and security/privacy/
  telemetry (`REQ-SEC-*`).
- **`scenarios.md`** (~446 Given/When/Then) + **`scenario_coverage.md`**
  — the UI-level acceptance corpus and its mapping to integration tests.

**That corpus is the contract the rewrite must preserve in full** —
functional *and* non-functional behavior, including telemetry,
durability, integration failure modes, and the measurable targets. The
rewrite changes only the backend's internal architecture; everything the
spec set guarantees stays true.

The bulk of the design work (the *how*) will happen in the architecting
step. This spec captures the **goals and requirements** that constrain
that design — what "simplest architecture preserving behavior" means,
what's in and out of scope, and how we'll know the rewrite succeeded.

### Scope, success bar, and cutover

- **Scope — everything in TypeScript.** The entire Python backend is
  rewritten: the FastAPI HTTP/WebSocket server, the services layer, the
  agent orchestration/harnesses, *and* the execution-environment layer
  (local PTY processes, git worktrees, and the pluggable Docker/remote
  environment interface). No Python backend component remains after the
  rewrite.

- **Success bar — behavioral parity against the spec corpus.**
  "Preserves current behavior" means every guarantee in `docs/specs/`
  (`SPEC.md` + `requirements.md` + `scenarios.md`) still holds. Concretely
  verified by: the **existing frontend works unchanged** against the new
  backend, the **`sculpt` CLI works unchanged**, and the **existing
  integration/scenario test suite passes** (it boots the backend and
  drives the real frontend, so it is the executable form of the corpus).
  Compatibility is behavioral, not byte-for-byte — where no client
  depends on an exact response shape, the new backend is free to differ.

- **Cutover — big-bang replacement.** The TypeScript backend fully
  replaces the Python backend in a single release. A **one-time data
  migration** (a standalone tool the user runs once at upgrade) moves existing
  users' data into the new schema. There is no period of Python/TS coexistence.

_(This Overview is a rough starting point — we'll sharpen it through
Q&A.)_

## User Scenarios

These scenarios are written from the perspective of an **existing
Sculptor user upgrading to the rewritten backend**, plus the
**maintainers** who own the codebase. The frontend is unchanged in all
of them.

### Existing user upgrades to the new backend
A user running the current (Python-backend) Sculptor upgrades to the
release containing the TypeScript backend. They run the one-time migration
tool, which moves their existing `~/.sculptor` data store into the new schema
(`RW-DATA-1`, `RW-DATA-2`). After
migration, all of their projects, workspaces, past agents, and
conversation history are present exactly as before (`RW-DATA-3`). They
resume work without re-onboarding (`RW-DATA-4`).

### User uses the app and notices no difference
The user opens a workspace, starts an agent, watches streaming updates,
opens a terminal, views diffs/commits, answers an agent question, and
interrupts a run. Every one of these flows behaves as it did on the
Python backend, because the frontend talks to the same HTTP + WebSocket
API contract (`RW-API-1`, `RW-API-2`, `RW-API-3`). The user cannot
tell the backend was rewritten. If an agent was mid-run when they
upgraded, it resumed and kept going (`RW-DATA-6`).

### Both generated clients build against the new backend unchanged
A maintainer regenerates the frontend's API client *and* the `sculpt`
CLI client from the new backend's OpenAPI schema. Both generated clients
are compatible and compile/run unchanged (`RW-API-4`).

### A power user keeps driving Sculptor from the `sculpt` CLI
A user who scripts Sculptor through the `sculpt` CLI — creating
workspaces and agents, listing/streaming, using env-var ID defaults and
short-prefix IDs — finds every command works exactly as before, and the
workspaces/agents they create still appear in the GUI and vice versa
(`RW-API-5`, `requirements.md` REQ-FUNC-101).

### Non-functional behavior is preserved, not just features
The user's telemetry consent choice is still honored and still masks
private content; PR/CI status still polls within the same bounded
worker pool and spacing; an errored agent still surfaces visibly with a
restore path; the data store still survives an in-place upgrade. None of
these are user-requested features, but all are part of the contract the
rewrite preserves (`RW-PARITY-3`, `RW-PARITY-5`).

### Self-hosted and desktop deployments keep working
The app continues to ship and run through its existing delivery
vehicles — the desktop (Electron) app and the self-hosted
(Docker/OpenHost) deployment — launched the same way users launch it
today (`RW-DEPLOY-1`, `RW-DEPLOY-2`).

### A maintainer extends the backend
A maintainer adds a new endpoint or service. Because the rewritten
architecture is dramatically simpler — fewer layers, less indirection,
no vestigial abstractions — they can locate the relevant code and make
the change with far less ceremony than the Python backend required
(`RW-SIMP-1`, `RW-SIMP-2`, `RW-SIMP-3`).

## Requirements

> **Anchoring note.** The product's behavior is already specified in
> `docs/specs/`. To avoid duplication and drift, the requirements below
> are *meta-requirements about the rewrite* — they say "preserve what
> `docs/specs/` already pins" and reference those documents' stable
> `REQ-*` IDs, rather than re-deriving behavior.
>
> **ID convention (two namespaces, kept disjoint on purpose).** This
> rewrite spec's own requirements use the **`RW-`** prefix
> (`RW-PARITY-*`, `RW-API-*`, `RW-DATA-*`, `RW-SIMP-*`, `RW-DEPLOY-*`,
> `RW-VERIFY-*`). The product specification set in `docs/specs/`
> (`requirements.md` in particular) uses **`REQ-`** (`REQ-FUNC-*`,
> `REQ-NFR-*`, `REQ-COMPAT-*`, `REQ-DATA-*`, `REQ-INT-*`, `REQ-SEC-*`).
> So in this spec and the architecture/plan documents downstream of it,
> **any `RW-*` ID is defined here; any `REQ-*` ID belongs to
> `docs/specs/`.** The two `…-DATA-*` areas previously collided (both
> started `REQ-DATA-`); the `RW-` prefix removes that ambiguity, and
> `docs/specs/requirements.md` zero-pads its IDs (`REQ-DATA-003`),
> which further distinguishes them at a glance.

### Behavioral contract preservation (RW-PARITY)
- **RW-PARITY-1 (MUST):** Every behavior specified in `docs/specs/`
  (`SPEC.md`, `requirements.md`, `scenarios.md`) MUST hold against the
  new backend. The corpus is the exhaustive contract; this spec does not
  re-enumerate it.
- **RW-PARITY-2 (MUST):** All ~446 scenarios in `scenarios.md` MUST
  continue to pass, demonstrated through `scenario_coverage.md`'s mapped
  integration tests (see REQ-VERIFY).
- **RW-PARITY-3 (MUST):** Non-functional guarantees in `requirements.md`
  §2 that are realized in the backend MUST be preserved — e.g. live
  update stream semantics (full snapshot on connect, then deltas;
  `REQ-NFR-001`), crash recovery & agent reattachment (`REQ-NFR-020/021/022`),
  local persistence & upgrade survival (`REQ-NFR-030`), and backend
  polling/concurrency defaults (PR/CI pool of 4 + 1.5 s spacing,
  `REQ-NFR-011`; repo polling 3 s, `REQ-NFR-061`; WAL + busy-timeout
  durability behavior, `REQ-NFR-031`).
- **RW-PARITY-4 (MUST):** External integration contracts in
  `requirements.md` §5 MUST be preserved, **including their failure
  taxonomies** — git host providers via `gh`/`glab` (`REQ-INT-001..003`),
  the agent model CLIs (Claude stream-json/`--resume`, Pi rpc;
  `REQ-INT-021..023`), terminal-agent registration (`REQ-INT-030/031`),
  the `sculpt`↔backend session-token contract (`REQ-INT-040/041`), and
  `.env` injection precedence (`REQ-INT-050`).
- **RW-PARITY-5 (MUST):** Security, privacy & telemetry guarantees in
  `requirements.md` §6 MUST be preserved — the agent trust boundary
  (`REQ-SEC-001`), local-first/single-user and never-persist-secrets
  (`REQ-SEC-002`), and **consent-gated telemetry** (PostHog product
  analytics gated on the persisted consent flags, masking private
  content; `REQ-SEC-010`). Note Sentry error reporting is frontend-only
  and thus unaffected by the backend rewrite.
- **RW-PARITY-6 (MUST):** Platform/dependency contracts in
  `requirements.md` §3 MUST be honored — the same external binaries and
  compatibility windows (Claude CLI window, `gh`/`glab`, git, Pi;
  `REQ-COMPAT-020..023`) on the same target platforms
  (`REQ-COMPAT-001/002`).

### API compatibility (RW-API)
- **RW-API-1 (MUST):** The new backend MUST serve the same HTTP REST
  API the current backend serves — same paths, methods, and the
  request/response behavior clients depend on (the ~80 endpoints under
  `/api/v1/...`).
- **RW-API-2 (MUST):** The new backend MUST serve the same WebSocket
  endpoints clients depend on: the streaming-update channel
  (`/api/v1/stream/ws`) and the terminal channels
  (`/api/v1/workspaces/{id}/terminal/{index}/ws`,
  `/api/v1/agents/{id}/terminal/ws`), preserving their message
  protocols.
- **RW-API-3 (MUST):** The existing frontend MUST work against the new
  backend **with no frontend code changes**. Compatibility is
  behavioral; exact response shapes MAY differ where no client depends
  on them.
- **RW-API-4 (SHOULD):** The new backend SHOULD emit an OpenAPI schema
  that regenerates **both** generated clients — the frontend client
  (`generate-api`, `@hey-api/openapi-ts`) and the `sculpt` CLI client
  (`generate-sculpt-client`) — with no manual adaptation
  (`requirements.md` REQ-INT-041, REQ-COMPAT-014).
- **RW-API-5 (MUST):** The `sculpt` CLI MUST work unchanged against the
  new backend, including its session-token auth, env-var ID defaults,
  short-prefix IDs, and cross-surface visibility with the GUI
  (`requirements.md` REQ-FUNC-101, REQ-INT-040). Like the frontend,
  `sculpt` is a client of the backend and is out of scope to rewrite,
  but in scope to keep working.

### Data preservation & migration (RW-DATA)
- **RW-DATA-1 (MUST):** Existing users' data MUST survive the upgrade.
  The new backend MAY define a different database schema, but a
  migration path from the current schema MUST exist.
- **RW-DATA-2 (MUST):** A one-time migration MUST move existing users' data
  into the new schema. It MAY be a **standalone tool the user runs once**
  rather than an automatic on-upgrade step — automatic execution is **not**
  required. It MUST be a single, self-contained operation (no multi-step manual
  data wrangling).
- **RW-DATA-3 (MUST):** After migration, all user-visible state the
  current backend persists (projects, workspaces, agents/their runs,
  conversation history, notifications, user settings) MUST be present
  and correct.
- **RW-DATA-4 (MUST):** A migrated user MUST NOT have to re-onboard or
  reconfigure (account/email, telemetry choice, project setup, etc.).
- **RW-DATA-5 (MUST):** On-disk state MUST be preserved and remain
  correctly associated with its migrated records — specifically the
  git clones/worktrees backing each workspace, and the agent working
  directories, uploaded files, and cached artifacts referenced by the
  database.
- **RW-DATA-6 (MUST):** Agents that are **in-flight at upgrade time**
  MUST survive the migration and resume under the new backend, rather
  than being lost or silently killed. This is the rewrite-boundary
  instance of the existing crash-recovery guarantee
  (`requirements.md` REQ-NFR-020); the reattachment mechanism is for the
  architecture step.
- **RW-DATA-7 (MUST):** The current storage *mechanism* — an
  append-only immutable snapshot table per entity plus a materialized
  `<entity>_latest` view maintained by DB triggers
  (`requirements.md` REQ-DATA-003) — is implementation, not contract,
  and MAY be replaced with something simpler. Only its
  externally-observable guarantees MUST hold: full history is retained
  where the product exposes it, current state is cheap to read, and the
  on-disk Sculptor folder layout / durability guarantees
  (`requirements.md` REQ-DATA-001/002/010) survive upgrade.
- **RW-DATA-8 (SHOULD):** The new migration SHOULD uphold the same
  safety bar the current one does — forward-only,
  failing loudly on an incompatible/newer store rather than corrupting
  data (`requirements.md` REQ-DATA-011), and covered by a seed →
  migrate → verify test (`requirements.md` REQ-DATA-012).

### Architectural simplicity (RW-SIMP)
- **RW-SIMP-1 (MUST):** The rewrite MUST produce the simplest
  architecture that satisfies the other requirements. Layers,
  indirection, and abstractions that exist only to serve obsolete prior
  designs MUST NOT be carried forward.
- **RW-SIMP-2 (SHOULD):** The architecture SHOULD be organized so the
  frontend's actual needs drive the backend's shape, rather than the
  backend imposing concepts the frontend never models.
- **RW-SIMP-3 (MUST):** The HTTP/WebSocket API and the frontend's
  observed behavior are the **sole contract**. Any backend behavior not
  reachable through that contract MAY be dropped freely — it is a clean
  slate behind the API. This explicitly includes vestigial internal
  abstractions (e.g. the `Task` model underlying agents, versioned
  task-input/state serialization) and any service machinery the
  contract does not require.

### Deployment & runtime (RW-DEPLOY)
- **RW-DEPLOY-1 (MUST):** The backend MUST continue to ship and run in
  its existing delivery vehicles: the desktop (Electron) app and the
  self-hosted (Docker/OpenHost) deployment. The user experience is
  unchanged: they launch the packaged application exactly as before.
- **RW-DEPLOY-2 (MUST):** The backend MUST keep serving the bundled
  frontend UI assets (the "serve static" behavior) so self-hosted
  deployments work as they do today.
- **RW-DEPLOY-3 (MAY):** *How* the backend process is launched (the
  `sculptor` CLI command, its subcommands/flags, the server runtime and
  ports) is an internal detail and MAY change freely — the Node runtime
  replaces Python+uvicorn, and the Electron/Docker wrappers are updated
  to match. Only the packaged-application launch experience is held
  fixed.

### Verification (RW-VERIFY)
- **RW-VERIFY-1 (MUST):** The existing integration/scenario test suite
  (the frontend-driven end-to-end tests, with FakeClaude determinism)
  MUST pass against the new backend, serving as the primary parity bar.
- **RW-VERIFY-2 (MUST):** The test suite itself is **kept as-is in
  Python** (pytest + FakeClaude); only the harness that boots the
  backend is adapted to launch the TypeScript backend. Test *logic* is
  not rewritten, so the corpus stays a trustworthy, unchanged oracle of
  prior behavior.
- **RW-VERIFY-3 (SHOULD):** Backend unit-level coverage equivalent to
  what the Python backend has SHOULD exist in the new backend, but the
  cross-stack parity guarantee rests on RW-VERIFY-1.

## Non-Goals

- **Not a behavior redesign.** This is not an opportunity to change what
  the product does or how it behaves. Everything in `docs/specs/` is
  held fixed; only the backend's internal architecture changes.
- **Not a frontend or `sculpt` CLI rewrite.** Both are clients of the
  backend, explicitly out of scope, and must not require changes to work
  against the new backend.
- **Not a coexistence project.** There is no goal of running the Python
  and TypeScript backends side by side; cutover is big-bang (see
  Overview).
- **No new features.** Adding capabilities is out of scope; the rewrite
  preserves the current feature set.
- **Not a resolution of the spec's pre-existing open questions.** The
  `requirements.md` §7 open questions (OPEN-1..8 — latency budgets,
  concurrency caps, back-compat horizon, telemetry default-state
  discrepancy, etc.) are pre-existing product gaps. The rewrite inherits
  the current *de facto* behavior for each and is not chartered to pin
  them down (though it must not regress whatever behavior exists today).
- **Not a change to the test corpus.** Per RW-VERIFY-2 the integration
  tests stay in Python; porting them to TS is explicitly out of scope.

## Open Questions

_(To be carried into the architecture step.)_

- **In-flight resume mechanism (`RW-DATA-6`):** How the new backend
  reattaches to agent processes started by the old backend across the
  big-bang cutover — and the failure mode if reattachment isn't possible
  for a given environment type (local PTY vs Docker/remote). The current
  resumption contract (`requirements.md` REQ-NFR-022: agent-CLI session
  continuation, corrupt-tail tolerance) sets the bar to meet.
- **Language boundary at the agent-CLI edge:** The agent CLIs (Claude,
  Pi) speak stream-json/rpc over a subprocess and are language-agnostic,
  so the harness is portable to TS. But the architect should confirm
  there is no Python-only dependency in the harness/environment layer
  (e.g. a library with no Node equivalent) that complicates the
  "everything in TypeScript" scope — and decide how to handle it if so.
- **WebSocket streaming-update projection:** The live-update stream
  (full snapshot on connect, then deltas) and its server-side derivation
  (`web/derived.py`, `message_conversion.py`) are the most intricate part
  of the frontend contract and a prime simplification target. The
  architect must preserve the observed stream protocol (`REQ-NFR-001`)
  while it is free to redesign how the backend computes it.
- **Inherited spec gaps:** `requirements.md` §7 (OPEN-1..8) remain open
  at the product level; the rewrite preserves current behavior for each
  but does not resolve them (see Non-Goals).
