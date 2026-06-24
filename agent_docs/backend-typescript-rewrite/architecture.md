# Backend TypeScript Rewrite — Architecture

## Executive Summary

Sculptor's Python backend (FastAPI HTTP/WebSocket server, services layer,
agent orchestration/harnesses, and the execution-environment layer) is
rewritten from scratch in TypeScript. The contract held fixed is the
`docs/specs/` corpus (`SPEC.md` + `requirements.md` + `scenarios.md`), the
HTTP/WebSocket API, and the `sculpt` CLI; user data is carried forward by a
one-time big-bang migration. The explicit design goal is **eliminating
unnecessary architectural complexity** — the new backend's shape is driven
by what the frontend and `sculpt` actually consume, not by inherited
abstractions (the `Task` primitive, versioned task-input/state
serialization, the immutable-snapshot-plus-trigger store).

**Before:** Python + FastAPI + uvicorn, SQLite with append-only snapshot
tables and a materialized-view trigger layer, a services collection wired
through a DI/lifecycle container, agent harnesses subprocessing the Claude
and Pi CLIs, and a server-side projection (`web/derived.py`,
`message_conversion.py`) that converts persisted agent messages into the
streaming-update protocol.

**After:** Node.js + **Fastify** (Zod route schemas → a first-class OpenAPI doc
that regenerates both existing clients), a **plain current-state SQLite schema**
(WAL) with the snapshot/trigger/materialized-view machinery and the versioned
task-serialization gone, a **single concrete local execution environment** (git
via the CLI, terminals via `node-pty`) instead of a pluggable interface with one
implementation, **async agent supervisors** on the event loop instead of a
thread-per-task service collection, a **cleanly rewritten streaming projection**
behind the unchanged `streaming_update` wire protocol, and the vestigial `Task`
primitive replaced by a first-class **`Agent`**. User data crosses over via a
**standalone one-time migration tool**; in-flight agents resume by relaunching
the CLI session (no live-process handoff). The new backend lives in a new
`sculptor/backend` package and ships as a Node sidecar replacing the PyInstaller
one.

## Current Architecture

```
                         Electron main  /  Docker(OpenHost)  /  sculpt CLI
                                 │ launches + serves bundled UI
                                 ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  FastAPI app (web/app.py, ~80 routes under /api/v1) + uvicorn         │
   │  HTTP REST  +  WS /stream/ws (streaming_update)  +  terminal WS        │
   └───────────────┬───────────────────────────────────┬──────────────────┘
                   │ reads/writes via transactions      │ subscribes to message queues
                   ▼                                     ▼
   ┌────────────────────────────────┐    ┌──────────────────────────────────────┐
   │  Streaming projection           │    │  Service collection (DI container)    │
   │  streams.py  → builds            │    │  run in dependency order:             │
   │  streaming_update snapshot+delta │    │   data_model · dependency_mgmt ·      │
   │  derived.py  → CodingAgentTaskView│   │   project · workspace · git_repo ·    │
   │  message_conversion.py →          │    │   task · pr_polling · ci_babysitter · │
   │   SavedAgentMessage→ChatMessage   │    │   btw                                 │
   └────────────────────────────────┘    └───────────────┬──────────────────────┘
                                                          │
              ┌───────────────────────────────────────────┼───────────────────────────┐
              ▼                       ▼                     ▼                           ▼
   ┌──────────────────┐   ┌────────────────────┐  ┌─────────────────────┐  ┌────────────────────┐
   │ DataModelService │   │ TaskService         │  │ WorkspaceService     │  │ Pr/CI/Btw services │
   │ SQLite (WAL)      │   │ runs Tasks(=agents) │  │ EnvironmentManager   │  │ gh/glab polling     │
   │ immutable snapshot│   │ thread per task     │  │ → LocalEnvironment    │  │ pools (4 / 1.5s)    │
   │ + <e>_latest view │   │ pub/sub Message     │  │   (git worktree/clone │  └────────────────────┘
   │ via DB triggers   │   │ queues              │  │    + PTY processes)   │
   └──────────────────┘   └─────────┬──────────┘  └─────────────────────┘
                                     │ spawns subprocess per agent
                                     ▼
              ┌──────────────────────────────────────────────────────────┐
              │ Agent harnesses (agents/)                                 │
              │  default/claude_code_sdk → `claude` CLI, stream-json/JSONL │
              │  pi_agent → `pi --mode rpc`, multiplexed JSONL             │
              │  resume via CLI session continuation (--resume <id>)       │
              └──────────────────────────────────────────────────────────┘
```

**Key facts established by codebase analysis (drive the rewrite):**

- **Data model is small.** Six persisted entities (REQ-DATA-004):
  `UserSettings`, `Project` (=repo), `Workspace`, `Task` (=Agent — the
  vestigial primitive), `SavedAgentMessage` (the conversation log), and
  `Notification`. The CLI's mental model (`repo → workspaces → agents`) maps
  to `Project → Workspace → Task`.
- **The store mechanism is heavy and droppable (RW-DATA-7).** **Four of the six
  entities** (`UserSettings`, `Project`, `Workspace`, `Task`) are dual-table:
  an append-only immutable snapshot table plus a materialized `<entity>_latest`
  table kept in sync by `BEFORE/AFTER INSERT` triggers (`database/core.py`,
  `automanaged.py`; registered with `is_dual_table=True` in
  `data_model_service/sql_implementation.py`). The remaining two —
  `SavedAgentMessage` and `Notification` — are registered `is_dual_table=False`:
  **plain single append-only tables with no `_latest` view and no triggers**. So
  the "snapshot+view+trigger" machinery is real but applies to four entities,
  not all six. Only the *observable* guarantees must survive: history where the
  product exposes it, cheap current-state reads, durable on-disk layout, WAL
  durability (REQ-NFR-031).
- **Versioned task serialization is vestigial.** `TaskInputs`/`TaskState`
  carry `object_type`-discriminated version unions (`AgentTaskInputsV2`,
  `AgentTaskStateV2`) and a frozen-Pydantic-schema guard (REQ-DATA-013).
  RW-SIMP-3 explicitly permits dropping this once the store is clean-slate.
- **There is exactly ONE execution environment.** `LocalEnvironment` is the
  only `Environment` subclass in the entire repo. The "container/remote
  backend" (SPEC §7.12) is **not** a second environment — it is the *custom
  backend command*, an escape hatch that relocates the **whole backend**
  off-host and connects over a printed URL (RW-DEPLOY-1, REQ-NFR-040). The
  abstract `Environment` interface (file/process ops, terminal, git) thus has
  a single implementation that does git worktree/clone + local PTY
  subprocesses.
- **Agent harnesses are language-agnostic at the edge.** Both `claude` and
  `pi` are long-lived subprocesses speaking JSON (stream-json/JSONL, rpc).
  Resume is the CLI's own session continuation (`--resume <session_id>`,
  reading `~/.claude/projects/.../<id>.jsonl`, tolerating a corrupt tail) —
  REQ-NFR-022, REQ-INT-021/022. No in-process agent state to port.
- **No Python-only blocker in the dependency surface.** Every production
  dependency has a clean TS equivalent (FastAPI→Fastify, Pydantic→Zod,
  Alembic→a TS migration runner such as `drizzle-kit`, SQLAlchemy→Drizzle/Kysely
  on `better-sqlite3`, `typeid-python`→`typeid-js` — both confirmed in use,
  `primitives/ids.py` and `frontend/package.json`). The git-layer decision
  resolves to the `git` CLI (`pygit2` is test-only; see above). `boto3` is
  **confirmed** to appear only in `upload_diagnostics.py` (unsigned S3 upload) —
  no longer a loose end.
- **The streaming projection is the intricate core.** `streams.py` turns
  TaskService `Message` queues into the `streaming_update` wire protocol
  (full snapshot on connect, then deltas — REQ-NFR-001);
  `message_conversion.py` folds the persisted `SavedAgentMessage` log into
  the frontend's `ChatMessage` shape (partial-chunk folding, tool-use/result
  pairing, error/warning blocks). This is the prime simplification target but
  the wire protocol is fixed contract.

## Proposed Architecture

**Foundational stack (decided in Q&A round 1):**

- **Runtime + framework:** Node.js + **Fastify**, using
  **`fastify-type-provider-zod`** (the Fastify Zod type provider) so route
  schemas are Zod, plus **`@fastify/swagger`** to emit the OpenAPI document
  first-class from those schemas. (These are two distinct packages — the type
  provider validates/serializes against Zod and feeds `@fastify/swagger`, which
  produces the spec; `zod-openapi` is a *different* standalone library and is
  not what's meant here.) WebSockets via **`@fastify/websocket`** (the `ws`
  integration). This satisfies RW-API-1/2 (same REST + WS surface) and is the
  spine for RW-API-4 (one OpenAPI doc regenerates both the frontend client
  and the `sculpt` client). Zod replaces Pydantic as the single source of
  request/response/runtime-validation truth.
- **Persistence:** **plain relational, current-state rows** on SQLite (WAL,
  busy-timeout — REQ-NFR-031) via **`better-sqlite3`** (synchronous, native)
  behind a thin TS query/schema layer (**Drizzle** recommended; Kysely a viable
  alternative). The choice of the synchronous driver, its event-loop
  implications, and the migration runner that replaces Alembic are covered in
  *Persistence engine & SQLite library choice* below. The append-only
  immutable-snapshot tables, the `<entity>_latest` materialized views, and
  the DB-trigger machinery are **dropped** (RW-DATA-7, RW-SIMP-1). The
  conversation log (`agent_message`) stays append-only — it is the **primary**
  place the product exposes full history (the `notification` table is also a
  single append-only table today; the other four entities are the dual-table
  ones being collapsed). Versioned `TaskInputs`/`TaskState`
  unions and the frozen-Pydantic-schema guard are dropped (RW-SIMP-3); the
  new schema is clean-slate behind the migration.
- **Git:** **shell out to the system `git` CLI** (git is already required —
  REQ-COMPAT-021; the current backend already shells out for essentially all
  git operations through `git_repo_service/git_commands.py`). No native libgit2
  binding — and note `pygit2` is **only** used in Python *test fixtures*
  (`foundation/fixtures.py`), not in production paths, so dropping it is
  trivial. Caveat: REQ-COMPAT-021 leaves the **minimum git version unpinned**
  (OPEN-6); since the default workspace strategy relies on `git worktree`, the
  plan should note the implicit floor (worktree support) even though the
  product does not currently assert one.

```
        Electron main  /  Docker(OpenHost)  /  sculpt CLI   (unchanged clients)
                 │ launch backend (custom command MAY change, RW-DEPLOY-3)
                 │ + connect over printed URL; backend serves bundled UI assets
                 ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Fastify app  (~80 routes /api/v1, Zod schemas → OpenAPI doc)          │
   │  REST  +  WS /stream/ws  +  terminal WS    [serves static UI]          │
   └──────────┬───────────────────────────────────────────┬───────────────┘
              │ Zod-validated handlers                     │ WS connection = 1 subscriber
              ▼                                            ▼
   ┌────────────────────────────┐         ┌──────────────────────────────────────┐
   │ Streaming projection        │◀────────│ In-process event bus (typed emitter)  │
   │ snapshot-on-connect + deltas │ deltas  │ replaces per-task Queue fan-out        │
   │ (preserves streaming_update) │         └───────────────┬──────────────────────┘
   └────────────────────────────┘                          │ publish Message events
              ▲ current-state reads                         │
              │                                             ▼
   ┌──────────┴───────────────┐   ┌──────────────────────────────────────────────┐
   │ Persistence (SQLite/WAL) │   │ Agent runner (replaces TaskService)            │
   │ plain relational tables: │   │  one async supervisor per running agent        │
   │  user_settings, repo,    │◀──│  spawns + manages the CLI subprocess           │
   │  workspace, agent,       │   │  persists messages, emits events               │
   │  agent_message, notif.   │   │  on startup: re-supervise non-terminal agents  │
   └──────────────────────────┘   └───────────────┬────────────────────────────────┘
                                                   │ subprocess (stream-json / rpc)
                                                   ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ Execution: ONE concrete local environment (no pluggable interface)      │
   │  git worktree/clone via `git` CLI  +  PTY subprocesses (node-pty)        │
   │  agent harnesses: claude (stream-json/JSONL), pi (rpc)                   │
   │  resume = CLI session continuation (--resume <session_id>)              │
   └────────────────────────────────────────────────────────────────────────┘
```

**Shape-driving simplifications (RW-SIMP-1/2/3):**

- **Collapse the `Environment` abstraction to one concrete local
  implementation.** Only `LocalEnvironment` exists (the sole concrete subclass
  of the abstract `Environment` in `interfaces/environments/base.py`); the
  "remote backend" is whole-backend relocation, not a per-workspace
  environment. Note this is **more than one interface** to collapse: alongside
  `Environment` there are sibling abstractions with a single local
  implementation each — the `AgentExecutionEnvironment` protocol (→
  `LocalAgentExecutionEnvironment`) and the testing-only `ComputingEnvironment`
  protocol. The abstract interfaces, capability flags, and registry indirection
  all go away; the simplification is larger than a single class swap.
- **Replace the `Task` primitive with a first-class `Agent`.** The DB row, the
  service, and the API speak "agent" directly; "Task" disappears as a concept.
- **Replace the DI service-collection + ConcurrencyGroup thread management**
  with plain module wiring and Node's async model (one async supervisor per
  agent; subprocesses for the CLIs and PTYs). The bounded PR/CI worker pool
  (4 + 1.5 s spacing, REQ-NFR-011) is preserved as an explicit concurrency
  limiter, not a thread pool.

## Component Deep Dives

### HTTP/WS API layer (Fastify)
Serves the **~80** `/api/v1` routes (the FastAPI app also exposes a handful of
internal, non-`/api/v1` schema routes — `/_ws_types/...`, `/_types/...`,
`/_element_tags` — for ~83 total; only the `/api/v1` surface is client-facing
contract), the `/stream/ws` streaming channel, the two
terminal WS channels (`/api/v1/workspaces/{id}/terminal/{index}/ws` and
`/api/v1/agents/{id}/terminal/ws`), and the bundled static UI (RW-DEPLOY-2). Route
schemas are Zod; the OpenAPI document is generated from them and is the single
artifact both client generators consume (RW-API-4). Auth is the existing
session-token contract: `GET /session-token` issues it, `x-session-token`
guards the rest; `sculpt` and the frontend authenticate identically
(REQ-INT-040, RW-API-5). Compatibility is behavioral — response shapes MAY
differ where no client reads them (RW-API-3, RW-SIMP-3).

### Persistence engine & SQLite library choice

SQLite itself is fixed by the contract: the store is `internal/database.db`
(REQ-DATA-002), it must run **WAL with a ~15 s busy timeout** (REQ-NFR-031),
survive in-place upgrade (REQ-DATA-010), and remain a single local file other
processes can open (the migration tool; ad-hoc read-only debugging of a live DB).
What's open is the **Node SQLite library** and how it interacts with Node's
single-threaded event loop. This is the load-bearing runtime decision, so it gets
its own treatment.

**Decision: `better-sqlite3` (synchronous, in-process), one writer connection.**

*Why synchronous is the right default here, not a liability.* The current Python
backend gets concurrency from **thread-per-task**, and SQLite — a single-writer
engine — serializes those threads' writes, which is exactly why it needs the 15 s
**busy timeout** to absorb `SQLITE_BUSY` while one thread waits for another's
write lock. The TS design runs everything on **one event loop**, so DB access is
**naturally serialized through a single connection**: there is only ever one
writer, `SQLITE_BUSY` from self-contention disappears, and the busy-timeout's job
shrinks to covering *other processes* (the migration tool, external readers).
That is a genuine simplification — the synchronous, single-connection model
removes a whole class of lock-contention/retry logic, it doesn't add one.

*The real cost — event-loop blocking — and why it's acceptable.* A synchronous
query blocks the event loop for its duration. For the workload here that is
almost always fine, because the queries are small and indexed against a local
file:

- With `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL`, commits append to
  the `-wal` file and **do not `fsync` per commit** (fsync happens at checkpoint),
  so a typical row write is tens of microseconds — far below any frame budget.
- `better-sqlite3` uses **prepared, cached statements** and is the fastest of the
  Node SQLite options for exactly this small-query profile.

The two places that *could* block long enough to matter, and the mitigations:

1. **High-frequency partial-message writes.** Smooth streaming emits many partial
   chunks per assistant message. Writing one row per token would be a lot of tiny
   synchronous writes. *Mitigation:* **coalesce** — persist partial chunks at a
   bounded cadence (the frontend already throttles render; REQ-NFR-003) and write
   the finalized message once, rather than a row per token. The append-only
   `agent_message` log keeps `is_partial` so the projection still folds partials,
   but we control the write rate.
2. **Snapshot-on-connect.** Each `/stream/ws` connect builds a full snapshot.
   Current-state reads are indexed and cheap; the expensive part is **folding the
   whole `agent_message` log → `ChatMessage`** for active agents. *Mitigation:*
   keep a warm **in-memory per-agent projection cache** that the runner updates as
   messages arrive, so connect serves from memory instead of re-folding history
   synchronously; bound/paginate history if a single agent's log is very large.

*Escalation path (only if measured).* If profiling under many concurrent agents
shows event-loop stalls, move the DB onto a **dedicated `worker_thread`** running
`better-sqlite3`, with the main loop talking to it over a `MessagePort`
request/response channel. This preserves the synchronous-inside-the-worker
simplicity while taking blocking off the main loop. **Do not build this
pre-emptively** — it reintroduces serialization boundaries (the very thing the
async-supervisor model avoids) and async transaction plumbing; add it only if a
real benchmark demands it.

**Why not the alternatives:**

- **`node:sqlite` (Node's built-in).** Synchronous, no native-addon packaging
  burden — attractive — but it landed in **Node 22.5** and is still
  *experimental*. The project pins **Node 20.13.1** (REQ-COMPAT-011), and the
  sidecar is to ship a pinned Node 20 runtime, so `node:sqlite` is **not
  available** without a runtime bump. Worth revisiting if/when the backend's Node
  is bumped, precisely because it would remove a native addon.
- **`node-sqlite3` (async, callback/libuv-threadpool).** Avoids event-loop
  blocking by dispatching to the libuv thread pool, but: (a) it pays per-call
  thread-pool hop overhead that, for sub-millisecond local queries, **costs more
  than it saves**; (b) it has **no synchronous transactions**, which makes the
  projection's read-modify-write and the migration's bulk insert markedly more
  awkward; (c) it is less actively maintained. Net negative for a local
  single-file DB.
- **`@libsql/client` (libsql, a SQLite fork).** Offers an embedded local file +
  async API, but it's a heavier dependency and a *fork* of SQLite — extra
  compatibility surface for no benefit we need (no remote/replica requirement
  here). Overkill.

**Query/schema layer: Drizzle (recommended), Kysely acceptable.** Both run
synchronously on `better-sqlite3` and satisfy "thin TS query layer." **Drizzle**
is recommended because it also gives schema-as-TypeScript with `drizzle-kit`
**migrations**, which is the natural replacement for Alembic's role — ongoing
forward-only schema evolution with a per-migration **seed→migrate→verify** test
(preserving the REQ-DATA-011/012 process guarantees for the *new* backend).
**Kysely** is a leaner query builder with its own migration runner and is a fine
alternative if the team prefers hand-written SQL migrations. Note these
**ongoing** schema migrations are distinct from the **one-time** big-bang data
migration tool (separate code path; see Migration Strategy).

### Streaming projection (clean TS rewrite, golden-test guided)
A single typed in-process event bus replaces the per-task `Queue` fan-out and
the multiple subscription indices (`by_user`/`by_project`/`by_workspace`/
`by_task`). Each `/stream/ws` connection is one subscriber that, on connect,
receives a full snapshot built from current-state reads, then receives deltas
as agents emit messages (REQ-NFR-001). The message-log → `ChatMessage` folding
(partial-chunk merge, tool-use/result pairing, error/warning/context blocks)
is rewritten idiomatically and pinned by golden fixtures ported from
`message_conversion_test.py` (input log → expected `streaming_update`). The
`streaming_update` wire shape stays fixed; how the backend derives it is free
to change.

### Agent runner (replaces TaskService) + harnesses
One async supervisor per running agent on the event loop (no thread-per-task,
no `ConcurrencyGroup`). The supervisor spawns and manages the agent CLI
subprocess, persists each emitted message to the append-only `agent_message`
log, and publishes events to the bus. On startup it re-supervises every
non-terminal agent (the restart-style resume above).

The harnesses are subprocess adapters — language-agnostic at the wire (`claude`
over stream-json/JSONL on stdin/stdout, `pi` over `--mode rpc` with multiplexed
JSONL channels), resumed via the CLI's own session continuation (REQ-INT-021/022,
REQ-NFR-022). But "thin" understates them: each is responsible for a non-trivial
launch contract that the plan must budget for, not just stdin/stdout plumbing:

- **Claude launch wiring (REQ-INT-021):** `--verbose`, **hook-event** wiring,
  **MCP server config**, and disabling `AskUserQuestion`/`ExitPlanMode` (so
  Sculptor renders those itself). Flags track the upstream CLI compatibility
  window (REQ-COMPAT-020) — the *contract*, not the exact flags, is fixed.
- **Session validation + corrupt-tail tolerance (REQ-NFR-022):** the session
  file at `~/.claude/projects/-code/<session_id>.jsonl` is validated (≥1
  user/assistant message with a matching `sessionId`) and resumed from the
  valid prefix when the tail is corrupt — logic to port carefully (it has a
  Python unit test, `process_manager_utils.py`).
- **Pi launch wiring (REQ-INT-022):** `--session-dir`/`--session-id`,
  the `response` / `extension_ui_request` / `AgentSessionEvent` channels, and
  **API keys injected from named env vars at startup and never persisted**
  (REQ-SEC-002).
- **Missing-binary errors (REQ-INT-023):** surface specific
  `ClaudeBinaryNotFoundError` / `PiBinaryNotFoundError` equivalents, not a
  generic failure.

### Execution environment (one concrete local implementation)
No pluggable `Environment` interface — a single concrete local module does:
git worktree / clone / in-place setup via the `git` CLI, file/process
operations, and PTY terminals via **node-pty**. node-pty (libuv forkpty/winpty)
also retires the elaborate posix_spawn-vs-fork lock dance the Python PTY code
carries to survive forking from a multi-threaded process — a real complexity
deletion. The terminal WS channels stream node-pty I/O. The "remote backend"
remains the custom-launcher escape hatch (whole backend off-host), not a second
environment (SPEC §7.12, RW-DEPLOY-1).

### Supporting services (plain modules)
PR/CI polling (`gh`/`glab` subprocess calls, the failure taxonomy
`cli_missing`/`not_authenticated`/`rate_limited`/`network_error` — REQ-INT-003)
keeps its bounded concurrency (4 workers + 1.5 s spacing, REQ-NFR-011) as an
async limiter; repo polling at 3 s (REQ-NFR-061); CI babysitter (off, retry
cap 3 — REQ-NFR-062); `/btw` read-only side-questions; terminal-agent registry
(TOML files re-read on demand, params stamped at agent creation —
REQ-INT-030/031); `.env` injection with per-repo-over-global precedence
(REQ-INT-050); consent-gated PostHog telemetry that masks private content
(REQ-SEC-010, via the PostHog Node SDK). Diagnostics upload (`boto3`→
`@aws-sdk/client-s3` **with anonymous/unsigned credentials**, or a plain
unauthenticated `PUT` — the current code uses botocore `UNSIGNED`
(`signature_version=UNSIGNED`) to `put_object` into a public report bucket, so the
TS replacement must reproduce the *unsigned* access pattern, **not** a signed
request. This is the only `boto3` use in the repo — `upload_diagnostics.py`).

## Data Model Changes

Six entities persist (REQ-DATA-004), now plain current-state tables on SQLite
(WAL + busy timeout, REQ-NFR-031), under the corrected names (see *Naming &
domain-model cleanup* below). The vestigial multi-tenancy columns
`organization_reference` / `user_reference` are dropped from every entity
(local-first single-user, REQ-SEC-002):

- `user_settings` — account/email, telemetry consent flags, agent defaults
  (model = MRU, effort = xhigh, fast = off — REQ-NFR-070). Settings also live
  in `internal/config.toml` as today (REQ-DATA-002); legacy-field tolerance on
  load is preserved (REQ-DATA-022).
- `repo` (was `Project`), `workspace` — the `Repo → Workspace → Agent`
  hierarchy matches the `sculpt` mental model and the GUI (REQ-FUNC-101
  cross-surface visibility).
- `agent` (was `Task`) — the agent run: its config, starting git hash,
  `run_state` (was `outcome`: the run lifecycle), selected model, error, read
  state, and the per-agent session/resume pointers (Claude/Pi session id,
  terminal session id + shell pid). The `object_type`-versioned
  `TaskInputs`/`TaskState` unions and the frozen-Pydantic-schema guard are gone
  (RW-SIMP-3); fields are flat columns / typed JSON.
- `agent_message` (was `SavedAgentMessage`) — the append-only conversation log
  the product exposes as history (RW-DATA-7). Keyed by message id, FK to
  agent, carries the message payload + source + is_partial. **Already a single
  append-only table today** (`is_dual_table=False`), so the new schema keeps it
  as-is — there is no snapshot/view machinery to strip here.
- `notification` — also **already single-table** (`is_dual_table=False`); carried
  over with the names/columns aligned to the rest of the schema.

History elsewhere (the four dual-table entities' snapshot tables, their
`<entity>_latest` views, and the triggers) is dropped — nothing in the contract
exposes per-entity history beyond the message log. On-disk folder layout
(`internal/database.db`, `internal/config.toml`, `internal/logs/`,
`internal/uploads/`, `internal/artifacts/`, `workspaces/`), the `.format_version`
marker, and durability guarantees survive (REQ-DATA-001/002/010).

**On-disk state stays associated (RW-DATA-5).** Beyond the DB rows, the migration
must keep each record correctly bound to the on-disk state it references — the
git clones/worktrees backing each workspace, agent working directories, and the
uploaded files / cached artifacts under `internal/uploads/` and
`internal/artifacts/`. Because the migration **preserves the on-disk layout and
all existing IDs** (see Migration Strategy), these references remain valid by
construction; the migration test asserts it explicitly.

### Naming & domain-model cleanup (internal only)

The rewrite is a clean slate behind the API (RW-SIMP-3), so internal names are
corrected to match what things actually are. **Hard rule:** anything the
frontend reads on the wire keeps its current name (RW-API-3) — the rename is in
the DB schema and backend code; the API serialization maps internal→external
where they differ. Confirmed wire-locked names: **`project_id`** (214 refs in
`frontend/src`), **`workspace_id`**, and the derived UI **`status`** field. The
external API stays `projects`/`project_id` until a future, separately-scoped UI
change aligns the wire.

Renames adopted (see Q&A):

- **`Project` → `Repo`.** It is a git repo with one working tree per workspace;
  `sculpt` already calls it `repo`. Internal table `repo`, type `Repo`,
  variables `repo_id`. Wire keeps `project_id`.
- **`Task` → `Agent`.** The vestigial primitive becomes the first-class concept
  (table `agent`, type `Agent`). **Agent IDs:** existing `tsk_…` IDs are kept
  as-is by the migration (the prefix is opaque to clients and appears in URLs,
  short-prefix lookup, on-disk paths, and `SCULPT_AGENT_ID`); **new agents mint
  `agt_…`**. ID parsing, validation, and the `/agents/by-prefix` lookup must
  therefore accept **both** prefixes indefinitely.
- **`SavedAgentMessage` → `AgentMessage`** (table `agent_message`).
- **Drop `organization_reference` / `user_reference`** from the entities. These
  are multi-tenancy vestiges; the product is local-first single-user
  (REQ-SEC-002) and they are not wire-exposed. `UserSettings` keeps the single
  local user's identity.
- **`Task.outcome: TaskState` → `Agent.run_state`** (the run lifecycle —
  `QUEUED`/`RUNNING`/`SUCCEEDED`/`FAILED`/`CANCELLED`/`DELETED`). The misleading
  name "outcome" (it holds `RUNNING`) is dropped; the distinct UI-facing
  `status` (`WAITING`/`ERROR`/…) computed in the projection keeps its wire name.

## Migration Strategy

**In-flight agent resume across the big-bang cutover (RW-DATA-6) — draft,
confirming in Q&A.** Codebase analysis shows the current backend never hands
off a live process across a restart. On startup
(`concurrent_implementation._clean_previously_running_tasks`) every task left
`RUNNING` is reset to `QUEUED`; the scheduler then re-runs it, and the agent
harness *relaunches the CLI subprocess* and continues the model session via
the CLI's own session continuation (`claude --resume <session_id>`, reading
`~/.claude/projects/.../<session_id>.jsonl`, tolerating a corrupt tail —
REQ-NFR-022, REQ-INT-021). The OS subprocess is disposable.

This means the cutover is **just a restart with a schema migration in front of
it**: there is no Python↔TS live-process handoff to engineer. For resume to keep
working, two things must hold:

1. **Each non-terminal agent's persisted session id carries forward** — the
   Claude/Pi session id the harness resumes with, and
   `AgentTaskStateV2.terminal_session_id` for terminal agents. These are columns
   the migration copies into the new `agent` row.
2. **The CLI's session file stays where the CLI re-derives its path.** Claude
   derives the session-file path from the working directory (e.g.
   `~/.claude/projects/-code/<session_id>.jsonl`). As long as the working
   directory is unchanged, the file is already in the right place.

**Crucially, this migration preserves the on-disk layout and keeps every
existing ID** (including `tsk_…` agent IDs, which appear in on-disk paths — see
Naming cleanup). So workspace working directories do **not** move, and the
Claude/Pi session files therefore stay valid **in place, with no relocation
step**. The session-folder *relocation* logic only matters when a working
directory actually changes — which this migration deliberately avoids.

> **Correction (important for the plan):** earlier drafts said the migration
> would "reuse the existing folder-migration helper's path-rewrite +
> Claude-session-folder relocation (REQ-DATA-021)." That helper —
> `scripts/migrate_sculptor_folder.py` (`sculptor_migrate`) — **has been removed
> from the repo** (commit `18134f05e7`, "Remove the data-folder migration
> script"); it was the one-shot pre-0.22 `~/.sculptor_data` (flat) → `~/.sculptor`
> relocation, retired at v0.37 once the upgrade window passed. It is *not*
> available to reuse, and `docs/specs/requirements.md` **REQ-DATA-021 is now
> stale** (it still cites the deleted file). The TS migration does not need it:
> because paths are preserved, no path-rewrite/session-relocation is required.
> If a future decision *does* move any directory, the (small) rewrite logic must
> be **reconstructed** from git history, not "reused."

On first launch the TS backend re-supervises every non-terminal agent exactly as
crash-recovery does today. If a session file is missing or unreadable, the agent
surfaces as errored with a restore path (REQ-NFR-021) rather than being silently
lost.

**Schema migration mechanics — standalone one-time tool (decided in Q&A round
3).** The migration is a **standalone tool the user runs once**, not an
automatic startup step. It reads current state from the old DB — the
`<entity>_latest` tables for the four dual-table entities (`user_settings_latest`,
`project_latest`, `workspace_latest`, `task_latest`) and directly from the two
single-table logs (`saved_agent_message`, `notification`, which have no `_latest`
view) — writes a fresh new-schema SQLite file (the old DB is backed up and left
untouched), and swaps it in. It is forward-only, fails loud on a
newer/incompatible store (RW-DATA-8, mirroring REQ-DATA-011), and is covered by a
seed→migrate→verify test (mirroring REQ-DATA-012). Because the migration
**preserves the on-disk layout and all existing IDs**, the Claude/Pi session
files and workspace working trees stay valid in place with **no path rewrite**
(see the resume discussion and correction above). Because the old DB is retained,
rollback is trivial.

> **Spec reconciled:** the spec's **RW-DATA-2** has been updated to allow a
> standalone one-time migration tool the user runs (automatic on-upgrade no
> longer required), along with the dependent Overview / upgrade-scenario /
> RW-DATA-8 phrasings. The architecture and spec now agree.

### Packaging & deployment (RW-DEPLOY-1/2/3)
The TS backend is a **new top-level package `sculptor/backend`** (sibling to
`sculptor/frontend` and `sculptor/sculptor`), built with the same Node 20 / TS
toolchain as the frontend. For distribution it is **bundled to JS (esbuild) and
shipped alongside a pinned Node 20 runtime** in the sidecar directory that
replaces today's PyInstaller `sculptor_backend`; Electron and the Docker/OpenHost
image launch `node backend.js`. Native addons (`node-pty`, `better-sqlite3`)
sit next to the bundle. The Electron `main.ts` launcher and the Docker image
are updated to start the Node sidecar instead of the Python one and to wait on
the printed-URL / `/api/v1/health` readiness signal (REQ-NFR-040). The
packaged-application launch experience is unchanged (RW-DEPLOY-1); only the
internal launch command changes (RW-DEPLOY-3). The backend keeps serving the
bundled frontend assets (RW-DEPLOY-2). macOS-arm64 + linux-x64 only
(REQ-COMPAT-001/002); the macOS artifact stays signed/notarized (REQ-SEC-003).

## Files to Modify / Create / Delete

**Create (new `sculptor/backend/` TS package):**
- `sculptor/backend/` — Fastify app, Zod route schemas + OpenAPI emit, the
  streaming projection + event bus, the agent runner + supervisors, the
  claude/pi harness adapters, the concrete local execution environment
  (git-CLI + node-pty), the supporting services (PR/CI polling, repo polling,
  CI babysitter, btw, terminal-agent registry, `.env` injection, telemetry),
  the SQLite persistence layer (plain schema + queries), and Vitest unit tests.
- `sculptor/backend/migrate/` — the standalone one-time migration tool (reads
  the four `<entity>_latest` tables + the two single-table logs → new schema;
  **preserves on-disk layout and IDs, so no path rewrite / session relocation is
  needed**) and its seed→migrate→verify test (including an in-flight-resume
  case). Note the old `scripts/migrate_sculptor_folder.py` helper is **gone**
  (see Migration Strategy correction) — nothing to reuse.
- Golden fixtures ported from `web/message_conversion_test.py`.

**Modify:**
- `sculptor/frontend/src/electron/main.ts` — launch the Node sidecar; keep the
  readiness/auto-restart behavior (REQ-NFR-040).
- Build/packaging: `sculptor/builder/*` (replace `build-sidecar.sh`'s
  PyInstaller step with the esbuild-bundle + bundled-Node packaging), the
  Docker/OpenHost image, and CI workflows (`.github/workflows/*`).
- `sculptor/tests/integration` harness: repoint the backend-launch seam
  (`testing/server_utils.py` / `SculptorFactory`) at the TS backend; FakeClaude
  stub install path unchanged.
- Client generation config (`generate-api`, `generate-sculpt-client`) to source
  the TS backend's OpenAPI doc.

**Delete (at cutover):**
- The entire Python backend `sculptor/sculptor/{web,services,agents,database,
  tasks,state,service_collections,foundation,interfaces,...}` and its
  PyInstaller sidecar build. The Python `sculpt` CLI and the Python integration
  test suite are **kept** (RW-VERIFY-2; `sculpt` is a client, out of scope to
  rewrite).

## Alternatives Considered

- **Framework: Hono / NestJS instead of Fastify.** Hono is lighter but less
  battle-tested for long-lived subprocess/PTY servers; NestJS's DI-heavy,
  decorator-driven style cuts against RW-SIMP. Fastify +
  `fastify-type-provider-zod` + `@fastify/swagger` gives first-class OpenAPI
  without the ceremony.
- **Persistence: port the event-sourced snapshot/trigger store to TS, or add
  per-entity history tables.** Both carry forward (or expand) complexity that
  RW-DATA-7 explicitly lets us drop; nothing in the contract exposes
  per-entity history beyond the message log. Rejected for plain current-state
  rows.
- **SQLite library: `node:sqlite`, `node-sqlite3` (async), or `@libsql/client`
  instead of `better-sqlite3`.** Rejected respectively because `node:sqlite`
  needs Node ≥22.5 (we pin Node 20), the async driver trades sub-ms blocking for
  worse thread-pool overhead and loses synchronous transactions, and libsql is a
  heavier SQLite fork we have no remote/replica need for. See *Persistence engine
  & SQLite library choice* for the full analysis.
- **Git: nodegit (libgit2) or isomorphic-git.** nodegit adds native-build pain;
  isomorphic-git has weak `git worktree` support (the default workspace
  strategy). Shelling out to the already-required `git` binary — which the
  current backend already does for most operations — is simplest.
- **Resume: live process/PTY handoff across cutover.** Cross-language and
  fragile, and unnecessary: the current design already disposes and relaunches
  agent processes on restart, continuing via the CLI's own session.
- **Streaming: mechanical transliteration, or push projection to the client.**
  Transliteration preserves complexity the spec names as a simplification
  target; pushing projection to the client breaks RW-API-3 (frontend
  unchanged, expects `ChatMessage`/`streaming_update`). Clean TS rewrite pinned
  by golden tests instead.
- **Concurrency: Node worker_threads per agent.** Unnecessary serialization
  boundaries for subprocess-bound work; async supervisors on the event loop
  suffice.
- **Packaging: Node SEA or pkg single binary.** Both still wrestle with native
  addons (`node-pty`, `better-sqlite3`); shipping a bundle + pinned Node mirrors
  the current `--onedir` layout and is the most debuggable.
- **Migration: automatic-on-startup, or in-place DB transform.** The user
  relaxed the automatic requirement (see Migration Strategy / Open Questions);
  in-place transform is harder to make atomic/resumable than writing a fresh DB
  and swapping.

## Risks and Mitigations

- **Streaming-projection parity drift.** The projection is the subtlest part of
  the contract. *Mitigation:* port `message_conversion_test.py` cases as golden
  fixtures; the integration/scenario suite (RW-VERIFY-1) is the end-to-end
  backstop, driving the real frontend against the new projection.
- **Resume depends on out-of-DB session files whose path derives from the
  working directory.** A path that changed during migration would silently break
  `--resume`. *Mitigation:* the migration **preserves the on-disk layout and all
  existing IDs**, so working directories and session-file paths are unchanged and
  no relocation is needed (the old relocation helper has been removed anyway —
  see Migration Strategy). On an unreadable session, surface
  errored-with-restore (REQ-NFR-021) rather than failing opaquely; cover with a
  migrate-then-resume test. *Residual risk is small but non-zero:* verify nothing
  in the new schema changes a value embedded in a workspace path
  (`workspace.environment_id`) or a Claude session-folder name.
- **`sculpt`-client compatibility is not gated in CI** (behavioral-only
  decision). The `@fastify/swagger`-generated OpenAPI may differ subtly from
  FastAPI's (operationIds, `$ref`s, nullable encoding) and the frontend suite doesn't
  exercise the `sculpt` client. *Mitigation:* keep `sculpt` command-level checks
  against the running backend; treat clean regeneration of both clients as a
  developer-time expectation; revisit if drift appears.
- **Behavioral parity gaps the scenario suite doesn't cover.** ~446 scenarios
  are broad but not exhaustive of every non-functional bar (telemetry masking,
  polling spacing, durability). *Mitigation:* trace each `requirements.md`
  numeric/contractual bar (REQ-NFR/INT/SEC) to a specific module + targeted
  unit test in the new backend.
- **Native addons across two platforms.** `node-pty` / `better-sqlite3` must
  build/load on macOS-arm64 + linux-x64 inside the packaged sidecar.
  *Mitigation:* prebuilt binaries pinned per platform, smoke-tested in the
  packaged-backend integration path that already exists.
- **Synchronous SQLite blocking the event loop under load.** `better-sqlite3` is
  synchronous, so heavy reads (snapshot-on-connect history folding) or a flood of
  tiny writes (per-token partial messages) across many concurrent agents could
  stall the single event loop and hurt the live-update bars (REQ-NFR-001/010).
  *Mitigation:* coalesce partial-message writes to a bounded cadence; serve
  snapshot-on-connect from a warm in-memory per-agent projection cache rather than
  re-folding history; WAL + `synchronous=NORMAL` to keep writes sub-millisecond.
  Escalation only if measured: move the DB to a dedicated `worker_thread`. Full
  reasoning in *Persistence engine & SQLite library choice*.
- **Big-bang cutover has no Python/TS fallback.** *Mitigation:* the migration
  retains the old DB (trivial rollback to the prior app version); the migration
  tool is standalone and fail-loud, so a bad store is detected before the new
  backend runs against it.
- **Scope is very large (~110k LOC of Python replaced).** *Mitigation:* the
  contract is fixed and executable (the suite), so the rewrite can proceed
  subsystem-by-subsystem against a green parity bar rather than big-bang in
  development; cutover is big-bang only at release.

## Testing Strategy

The primary parity bar is the **existing Python integration/scenario suite**
run unchanged against the TS backend (RW-VERIFY-1/2). The suite **never runs
the backend in-process** — every test launches the backend as a *subprocess*
(`SculptorInstance` holds "the backend server process"; the launch argv flows
through `testing/server_utils.py` / `SculptorFactory`, with SIGTERM→SIGKILL
teardown) and drives the real application through Playwright. The only
adaptation is therefore **repointing that one subprocess-launch seam** at the
TS backend binary/dev command — no cross-language embedding, no test-logic
changes. **FakeClaude keeps working unchanged**: it is a fake `claude` binary
installed on `PATH` (`dependency_stubs.install_default_claude_stub`), and the TS
backend invokes it by the same stream-json-over-stdio contract — determinism is
preserved.

A TS unit layer (Vitest) covers backend internals to roughly the depth the
Python unit tests do (RW-VERIFY-3), but the cross-stack guarantee rests on the
integration suite.

Additional targeted gates:
- **Projection golden tests** — `message_conversion_test.py` cases ported as TS
  golden fixtures, asserting `streaming_update` parity at the unit level.
- **Migration test** — seed an old-schema `~/.sculptor` → run the migration tool
  → verify all six entities + on-disk state, including an in-flight agent
  resuming after cutover (RW-DATA-6).
- **Client compatibility is behavioral (decided in Q&A round 3).** No dedicated
  client-regeneration CI gate. The integration suite drives the real frontend,
  which uses the generated frontend client, so RW-API-3 is covered
  behaviorally; the `sculpt` client is validated by its own command behavior
  against the running backend (RW-API-5). RW-API-4's "regenerates both
  clients with no manual adaptation" is treated as a developer-time
  expectation, not a CI bar — see Open Questions for the residual `sculpt`-client
  coverage note.

## Open Questions

- **RW-DATA-2 (migration automation) — resolved.** The spec was updated to
  allow a standalone one-time migration tool the user runs; automatic-on-upgrade
  is no longer required. Architecture and spec agree; no open action.
- **`docs/specs/requirements.md` REQ-DATA-021 is stale — fix in the global spec.**
  It still cites `scripts/migrate_sculptor_folder.py`, which was removed in commit
  `18134f05e7`. The rewrite no longer depends on that helper (paths are
  preserved), but the product requirements doc should be corrected (either drop
  REQ-DATA-021 or restate it as historical), since the rewrite's parity bar
  references that corpus. Small, out-of-band edit to the global spec — flagged here
  so the plan phase doesn't carry the dead reference forward.
- **`sculpt`-client regeneration coverage.** With client compatibility verified
  behaviorally (no CI regeneration gate), the `sculpt` Python client — generated
  from the backend OpenAPI and not exercised by the frontend suite — has thinner
  parity coverage. The plan should decide which `sculpt` command-level checks
  stand in for RW-API-4/RW-API-5 on that surface.
- **Inherited product-spec gaps (`requirements.md` §7, OPEN-1..8).** Latency
  budgets, concurrency caps, back-compat horizon, telemetry default-state
  discrepancy, etc. remain open at the product level. Per Non-Goals the rewrite
  preserves current de-facto behavior for each and does not resolve them; it
  must not regress them.
- **`boto3`→AWS-SDK behavioral equivalence for diagnostics upload.** Confirmed
  the single `boto3` use is the **unsigned** S3 `put_object` in
  `upload_diagnostics.py` (`from botocore import UNSIGNED`, `signature_version=UNSIGNED`).
  It maps to `@aws-sdk/client-s3` configured with an anonymous/no-op credential
  provider, or simply a plain unauthenticated HTTPS `PUT` to the public bucket
  URL. The plan should pick one and verify the anonymous upload still succeeds
  (the alternative of a *signed* request is wrong — there are no credentials).
- **Per-subsystem requirement trace.** A full REQ-by-REQ trace
  (`requirements.md` numeric bars → new backend module + test) is a Plan-phase
  deliverable; this architecture covers the load-bearing ones inline but does
  not enumerate all ~80 endpoints / all NFR constants.
