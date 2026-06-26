# Backend TypeScript Rewrite — Review

> **Status: all findings resolved.** Every HIGH, MEDIUM, and actionable LOW
> below was fixed and committed on `saeed/rewrite/full-parity`. `just format`,
> `just check` (lint, typecheck, ratchets, hygiene), and `just test-unit` (Python
> backend, TS backend, frontend, foundation, sculpt) are all green after the
> fixes; the previously-failing PTY unit test did not recur. Fix commits:
>
> | Area | Commit |
> |------|--------|
> | Stream/terminal WS + auth (bus isolation, send guards, PTY listener leak, index validation, token-in-URL redaction) | `06e5c932fc` |
> | Migration fail-loud (FK precheck, enum/JSON validation, swap window, `__dirname` guard) | `95c96af400` |
> | Supervisor lifecycle (map-eviction leak, idempotent finalize, stop-path flush, narrowed persist catch, dead concurrency limiter removed) | `4786f5f010` |
> | Subprocess/harness/git (spawn error listener, pipe drain, process timeout, malformed-RPC tolerance, unmatched tool-call unblock, upload containment, git-diff arg-array, ref `--`, stale-PID identity, terminal registry unify, auth-path detail redaction) | `4f47f03a71` |
> | Telemetry + polling (consent gate requires explicit decision, value-based trace masking, shutdown flush, post-stop poll guard, bounded-pool cap robustness) | `1e2ffdf5a7` |
> | Sidecar Node checksum + stale-test rename | `92511a60f4` |
>
> The repo-wide comment scrub (stripping `Task N.N` / `REQ-*` / `RW-*` /
> `SCU-####` / Python-line pointers) was applied across every touched
> subsystem as part of these commits. The original findings are preserved
> below as the record of what was reviewed and fixed.

## Summary

- **The rewrite meets its spec.** The entire Python backend is gone and reborn as
  a Fastify/Node TypeScript backend under `sculptor/backend/` (156 source +
  65 test files). Every `RW-*` requirement traces to a concrete module and a
  targeted test, and every numeric/contractual bar in `req_trace.md`
  (pool of 4 + 1.5 s spacing, WAL + 15 s busy timeout, 20 MB upload cap, 3 s
  repo poll, babysitter off-by-default + cap 3, version windows, literal
  placeholder substitution, consent-gated masking) is asserted in code **and**
  pinned by a unit test. The strongest parity proof: the generated frontend
  API client is **byte-identical to `origin/main`** despite the OpenAPI source
  moving Python→TS.
- **Top things to address before merging (none are blockers, but two are worth
  a fix):** (1) a backend-crash path — `spawnBackgroundProcess` registers no
  `'error'` listener, so a spawn failure becomes an uncaught exception; (2) a
  pi-harness path where a malformed RPC frame throws a `TypeError` that escapes
  the stdout handler and hangs the turn. Both are HIGH. A `/stream/ws` send that
  isn't isolated from the event bus, and a supervisor map that leaks one entry
  per agent run, round out the HIGH list.
- **One repo-wide hygiene issue, flagged independently by every reviewer:**
  comments throughout the new backend embed internal planning pointers
  (`Task N.N`, `REQ-*`, `RW-*`, `Phase N`, `SCU-####`) and verbatim Python
  source line citations (`web/app.py:476`) that the project's own comment policy
  forbids and that will rot the moment the Python tree is deleted.
- **Tests are green at the unit level** (`just check` clean; Python backend,
  frontend, foundation, and `sculpt` suites pass; TS backend 440/441 with the
  one failure a known load-induced PTY-timing flake that passes 5/5 in
  isolation). The full integration/scenario suite (RW-VERIFY-1) is the hours-long
  electron + real-Claude CI oracle; it was driven green under the
  `SCULPTOR_BACKEND=ts` env gate in build phases 9.5/99.1 and runs in CI — it was
  **not** re-run inside this review pass (see Test Coverage).

## Requirements Coverage

`RW-*` IDs are defined in `spec.md`; `REQ-*` belong to `docs/specs/requirements.md`.
All modules and tests below were confirmed to exist in the diff; the numeric
bars were confirmed asserted in their tests.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| RW-PARITY-1 (all `docs/specs/` behavior holds) | Covered | Integration/scenario suite is the oracle; driven green under env gate (Task 9.5/99.1), runs in CI |
| RW-PARITY-2 (~446 scenarios pass) | Covered* | Same suite; *re-verified in CI/build, not in this pass |
| RW-PARITY-3 (NFR bars) | Covered | pool `services/pr_polling/pool.ts:10-11`; WAL/timeout `db/connection.ts:18-20`; snapshot/delta `projection/`; recovery `runner/runner.ts` re-supervise |
| RW-PARITY-4 (integration contracts + taxonomies) | Covered | `services/pr_polling/cli_status.ts` (5 distinct categories); harnesses `harness/claude`, `harness/pi`; registry `services/terminal_agent_registry`; `.env` `services/env_injection/env.ts` |
| RW-PARITY-5 (security/telemetry) | Covered | `telemetry/posthog.ts` consent re-check + `maskProperties`; env names-only `services/env_injection/env.ts:52` (see MEDIUM caveats below) |
| RW-PARITY-6 (platform/dependency windows) | Covered | `services/dependencies.ts:47-58` (claude 2.1.170/blocked 2.1.101, pi 0.78.0) |
| RW-API-1 (REST surface) | Covered | `routes/*` (~80 endpoints), OpenAPI emit `openapi.ts` |
| RW-API-2 (WS endpoints) | Covered | `routes/stream_ws.ts`, `routes/terminal_ws.ts` |
| RW-API-3 (frontend unchanged) | Covered | `git diff` of `frontend/src/api/` is **empty**; `projection/to_wire.ts` camelizer + tests |
| RW-API-4 (one OpenAPI → both clients) | Covered | `openapi_overlay.json`; frontend client byte-identical; sculpt client byte-identical (commit `aa51211`) |
| RW-API-5 (`sculpt` unchanged) | Covered | `auth/session_token.ts`, `config/port.ts`; gated by `test_sculpt_cli.py` |
| RW-DATA-1..5,7 (data preservation + migration) | Covered | `migrate/{read_old_db,transform,run,index}.ts`; all six entities, IDs verbatim, on-disk layout untouched; `migrate.seed_verify.test.ts` |
| RW-DATA-6 (in-flight resume) | Covered | `runner/runner.ts` re-supervise on startup; session ids read from on-disk state by `harness/claude/validated_session_state.ts`; resume case in seed→verify test |
| RW-DATA-8 (forward-only, fail-loud, seed→migrate→verify) | Covered | `migrate/read_old_db.ts:42-61` + `index.ts:32-36` guards; `migrate.seed_verify.test.ts` |
| RW-SIMP-1/2/3 (simplicity, drop vestigial) | Covered | Plain current-state schema (no snapshot/trigger); one local environment; no `Task`-model serialization; Python backend deleted |
| RW-DEPLOY-1/2/3 (delivery vehicles) | Covered | `scripts/build-sidecar.sh` (esbuild + pinned Node, codesign), `frontend/src/electron/main.ts` (Node sidecar, readiness preserved), `openhost.Dockerfile`, `static.ts` |
| RW-VERIFY-1 (integration suite passes) | Covered* | *Oracle suite; green under env gate in CI, not re-run here |
| RW-VERIFY-2 (suite kept in Python) | Covered | Only the launch seam repointed (`testing/server_utils.py`, `resources.py`); test logic unchanged; `sculpt` CLI kept |
| RW-VERIFY-3 (unit coverage) | Covered | 65 TS test files, 441 tests |

\* "Covered*" = realized in code and verified by the integration suite in CI /
build phase, but that suite was not re-executed inside this review pass.

## User Scenarios

- **Existing user upgrades (migration).** Delivered. The standalone migration
  tool (`migrate/`) moves all six entities with IDs preserved verbatim and the
  on-disk layout untouched (so git worktrees and Claude session-file paths stay
  valid), guards forward-only, and backs up before swapping. Covered by
  `migrate.seed_verify.test.ts`. One robustness gap (FK-on single transaction
  aborts the whole upgrade on a single orphan row) is noted below — data-safe
  but opaque.

- **User notices no difference.** Delivered. The frontend talks to the same
  REST + WS contract; the regenerated frontend client is byte-identical to main,
  the camelCase wire boundary is tested, and the streaming snapshot-then-delta
  protocol is preserved (and the classic snapshot/subscribe race is correctly
  avoided — snapshot build and subscribe share one synchronous block). End-to-end
  proof rests on the integration suite (the oracle).

- **Both clients build unchanged.** Delivered and strongly evidenced: empty diff
  for the generated frontend client, byte-identical sculpt client.

- **Power user drives `sculpt`.** Delivered. Session-token auth, port discovery,
  dual-prefix/short IDs implemented; gated behaviorally by `test_sculpt_cli.py`.

- **Non-functional behavior preserved.** Delivered with two telemetry caveats
  (consent gate leans on the token gate rather than the consent flag
  pre-onboarding; masking is key-name-based) — see MEDIUM findings. Polling
  pools, spacing, durability, and errored-agent restore are implemented and unit-tested.

- **Self-hosted + desktop deployments.** Delivered. Electron launcher is a
  faithful rename preserving readiness/auto-restart; Docker/OpenHost image
  serves static UI; sidecar packaging codesigns node + native addons.

- **Maintainer extends the backend.** Delivered. Routes/services are thin, flat
  modules over the substrate; far less indirection than the Python layering.

## Test Coverage

- **Tests added:** 65 TS unit test files (441 tests) across `routes/`, `db/`,
  `migrate/`, `projection/`, `runner/`, `harness/`, `services/`, `telemetry/`,
  `git/`, `terminal/`; golden message-conversion fixtures; a
  seed→migrate→verify migration test including in-flight resume. The Python
  integration/scenario suite is **kept as-is** (RW-VERIFY-2) with only the
  launch seam repointed.

- **`just check`:** PASS — lint, typecheck (tsc + pyrefly), ratchets, file
  hygiene, yaml, shellcheck, uv-lock all OK.

- **`just test-unit`:** Python backend PASS; frontend PASS; foundation PASS;
  sculpt PASS. **TS backend: 440/441.** The single failure is
  `src/terminal/terminal.test.ts:66` (`expect(exitCode).toBe(0)` after a fixed
  300 ms delay) — a **load-induced PTY-timing flake**, not a product regression:
  it passed 5/5 tests on 3 consecutive isolated runs. It is the same brittle
  fixed-delay pattern called out for the Python PTY tests. **Recommendation:**
  replace the fixed `delay(300)` with a wait-for-exit-event (e.g. await the
  `onExit` promise) so the assertion is event-driven rather than time-driven.

- **Integration tests (RW-VERIFY-1):** **Not re-run in this review pass.** The
  parity oracle is the full Python integration/scenario suite (electron +
  real-Claude, multi-hour); it was driven green under `SCULPTOR_BACKEND=ts` in
  build phases 9.5/99.1 and runs in CI. Known-flaky jobs (`browser_panel`
  electron, PTY under `-n 8`, offload base-image cache-miss) pass on retry.
  Because this suite is the primary parity bar, **CI must be green on this branch
  before merge** — that is the gate this review defers to, not a substitute
  verification.

- **Skipped / xfail / pending:** None observed in the new TS suite. The one TS
  failure above is a flake, not a skip.

## Code Review Findings

Configured skill `/code-review-checklist` was applied across the new backend,
fanned out over six subsystem slices. Findings consolidated below by severity.
No CRITICAL issues found.

### HIGH

**`environment/process.ts:57-61` — backend-crash on spawn failure.**
`spawnBackgroundProcess` registers no `'error'` listener on the child; the only
in-tree caller adds just `'close'`. A spawn failure (ENOENT/EACCES) emits
`'error'` with no listener → uncaught exception that crashes the whole Node
backend. Add an `'error'` handler.

**`harness/pi/rpc.ts:18-29` + `harness/pi/harness.ts:537-543` — turn hang on
malformed RPC frame.** `asAgentMessage` checks `Array.isArray(content)` but not
element shape; a frame with a `null` content element makes
`extractAssistantText`/`buildInterleavedContent` throw `TypeError`. `routeLine`
catches only `PiCrashError` and rethrows, so the `TypeError` escapes the stdout
`data` handler uncaught and the turn promise never resolves — defeating the
file's stated "tolerate malformed payloads" intent.

**`runner/runner.ts:40-79,136` — supervisor map leak.** Supervisors are removed
from `AgentRunner.supervisors` only in `stopAgent`. On natural termination
(`handleExit → finalize`) the supervisor stays in the map forever; one dead
`AgentSupervisor` (holding the agent row + writer) accumulates per agent ever
run on a long-lived server. Wire an `onFinalize` callback to evict.

**`routes/stream_ws.ts:91,110` (+ `events/bus.ts:18-24`) — one bad WS connection
can break fan-out for all clients.** Per-connection `socket.send(...)` runs
inside an `eventBus.subscribe` handler, and `EventBus.publish` invokes handlers
with no `try/catch`. If a send throws (socket mid-close, or a projection chokes
on an unexpected event), the exception aborts delivery to every *other*
`/stream/ws` client for that event and propagates back into the producer (repo
poller, agent runner). `terminal_ws.ts` guards every send with
`readyState === OPEN`; `stream_ws.ts` does not. Guard the sends or isolate
handlers in the bus.

### MEDIUM

**`runner/supervisor.ts:122-128` — interrupt drops the last partial.** `stop()`
finalizes (CANCELLED) but never calls `writer.flush()`, and sets
`finalized=true` first so the later `onExit → handleExit` short-circuits before
it can flush. A cold re-fold or reconnect-after-evict shows a truncated final
message for a cancelled turn.

**`runner/concurrency.ts` (via `runner/runner.ts:101-122`) — limiter doesn't
limit.** `limiter.run(async () => …)` releases the slot as soon as the
subprocess is *launched* (the body is synchronous to spawn), so all N harnesses
still spawn in one burst. The "startup thundering herd" the comment claims to
bound is not bounded — either gate on readiness/exit or remove the dead
complexity.

**`runner/message_writer.ts:79-86` — silent durability loss.** `persist()` wraps
`appendAgentMessage` in a bare `catch {}` that swallows *every* error with no
logging. A transient DB failure (busy/locked/disk) silently drops the row while
the warm cache already folded it — violating the cache-equals-durable-log
invariant the cache file itself flags as critical. Narrow the catch or log.

**`migrate/run.ts:40-66` (+ `db/connection.ts:21`) — one orphan row blocks an
upgrade opaquely.** All inserts run in one transaction with `foreign_keys = ON`;
any dangling reference in real historical data (e.g. an `agent.workspace_id` or
`notification.task_id` pointing at a row absent from the `*_latest` snapshot)
aborts the whole migration with a bare `FOREIGN KEY constraint failed` and no
row identification. Data-safe (fail-loud, no partial write) but brittle.
Consider an up-front integrity check with a row-identifying error.

**Session token in WS query param is logged.** `auth/guard.ts:41`,
`routes/stream_ws.ts:38`, `routes/terminal_ws.ts:77` accept the token as a query
param (legitimate — browsers can't set WS headers), but it then rides in
`req.url`, which Fastify request logging writes to the app log. Scrub the token
from logged URLs.

**`environment/process.ts:35-52` — no timeout / unbounded buffers on git calls.**
`runProcessToCompletion` (every git call routes through it) has no timeout and
accumulates stdout/stderr into unbounded strings; a wedged child (lock
contention, credential helper, hook) never resolves. Background children
(`:57-61`) open pipes nothing drains — a process writing >~64 KB blocks forever.

**`terminal/manager.ts:7-13` — reapStalePid may kill a recycled pid.**
`reapStalePid` SIGKILLs a pid persisted from a prior backend run with no
start-time/identity check; the OS may have recycled that pid.

**Two terminal registries.** `environment/local_environment.ts:140-148` (per-env
`TerminalManager`) vs `terminal/index.ts:9-14` (process-wide singleton).
`LocalEnvironment.close()` tears down only its own; terminals created via the
singleton aren't reaped on environment teardown (orphan risk). Confirm which the
routes use.

**`harness/claude/mcp.ts:408-411` — early `tools/call` dropped → turn hang.** A
`tools/call` arriving before its `tool_use` id is registered (and no cached
text) is dropped with no `control_response`; the CLI blocks on that call until
the process is killed.

**`harness/pi/prompt_assembly.ts:32-34,53-71` — upload path escape.**
`resolveUploadPath` does `path.join(uploadsDir(), entry)` with no containment, so
a `files` entry like `../../etc/passwd` (or an absolute path) escapes the uploads
dir. Bounded (runs in the user's own environment) but the upload id should be
constrained.

**`git/diff.ts:57-63,116` — git failure looks like a clean tree.** `diffAgainst`
builds a `bash -c "git … ; …"` shell string (inputs controlled today, so not
injectable, but prefer an arg array) and returns only `stdout`, never inspecting
exit code/stderr; `commitDiff` maps `exitCode>1` to `""`. A failing diff (bad
ref, corrupt repo) surfaces as "no changes" rather than an actionable error.

**Telemetry consent caveats (`telemetry/posthog.ts:28-46`).** `consentGranted()`
keys solely on `is_product_analytics_enabled`, which the pre-onboarding default
config sets `true` while `is_privacy_policy_consented` is still `false` — so the
gate doesn't strictly require explicit consent before onboarding; it leans on the
token gate (no backend token → inert) instead. Separately, `maskProperties`
redacts by key name only, so private content under a non-matching key (e.g. the
trace batch forwarded wholesale by `routes/trace.ts:24`) passes unmasked.
Faithful to Python parity and inert in practice, but not a strict "mask all
content" guarantee.

**`routes/terminal_ws.ts:106-113` — onExit listener leak.** Each socket
reconnect calls `pty.onExit(...)`, and `pty.onExit` only adds with no removal; a
long-lived reused terminal accumulates one exit listener per reconnect.

### LOW

Representative items (full list in subagent notes): non-constant-time token
compare (`auth/session_token.ts:59-64`); `NaN`-keyed terminal on non-numeric
`:index` (`routes/terminal_ws.ts:181`); enum columns written via raw casts in
`migrate/transform.ts` without Zod validation; `parseJson` errors lack
entity/object-id context; `migrate/index.ts:46-48` removes the live DB before the
atomic rename (widens crash window); `git` refs passed without a `--` separator
(`git/git.ts`, `git/history.ts`); pi failure `Details:` may echo provider text on
the auth branch; PATH prepend trailing-delimiter; `shutdownTelemetry()` has no
caller (client never flushed on exit); Node runtime tarball in
`scripts/build-sidecar.sh:360-367` is curl'd without checksum/signature
verification (native addons *are* sha256-verified); stale test name
`test_regression_task_list_after_sync_dir_wiped.py` no longer wipes a sync dir.

### MEDIUM — Comments (repo-wide, flagged by every reviewer)

Comments throughout the new backend embed internal planning pointers the
project's comment policy explicitly forbids: requirement/work IDs (`REQ-NFR-*`,
`REQ-DATA-*`, `RW-DATA-*`, `RW-SIMP-*`, `REQ-SEC-*`), plan task/phase tags
(`Task 1.7`, `Task 8.1`, `Phase 6`), ticket IDs in code comments (`SCU-1291`,
`scu-1429`), and verbatim Python source line citations (`web/app.py:476`,
`streams.py L…`) that will rot when the Python tree is deleted. Examples span
`db/connection.ts`, `db/migrate.ts`, `migrate/index.ts`, `events/bus.ts`,
`runner/*`, `projection/*`, `git/*`, `harness/*`, `services/*`,
`telemetry/posthog.ts`. The conceptual "why" and the `ported from <symbol>`
provenance notes are worth keeping; the bare planning tags and line-number
pointers should be scrubbed. This is the single most consistent finding and is a
good candidate for one mechanical cleanup pass.

### Verified clean

`services/terminal_agent_registry/*` (re-read on demand; genuinely literal
substitution via `split().join()` — values containing `{}`/`$`/`%` pass through;
unknown placeholders rejected). `services/dependencies.ts` (version windows
correct; SHA-256 verified before install; staged-then-atomic-rename).
`services/ci_babysitter/*` (off-by-default, cap enforced, dedup). Failure
taxonomy stays distinct (`cli_status.ts`). Env surface is names-only, values
never logged. Migration mapping cross-checked against the real old Python schema
(all six entities, all prefixes, `TaskState`→`RunState` values match). Generated
frontend client byte-identical to main; sculpt client byte-identical. All commit
messages and the committed `agent_docs` markdown are world-safe — no secrets,
PII, internal hostnames, or private ticket contents. The Claude `bash -c`
launch string correctly `shlex.quote`s every interpolated value.

## Overall Assessment

**This is a high-quality, mergeable rewrite.** The spec's contract is met:
behavioral parity is preserved through an unchanged frontend client and an
unchanged Python integration suite, the architecture is genuinely simpler (plain
current-state schema, one execution environment, no vestigial `Task`
serialization), and the contractual/numeric bars are each backed by a test. The
byte-identical client regeneration is unusually strong evidence that the wire
contract didn't drift.

**Biggest risk:** the parity guarantee ultimately rests on the multi-hour
integration/scenario suite (RW-VERIFY-1), which this review did **not** re-run.
Merge should be gated on that suite being green in CI on this branch — treat that
as the real acceptance test, with the unit-level green here as the fast signal.

**Recommended before merge (none strictly blocking):**
1. Fix the two HIGH crash/hang paths: missing `'error'` listener on
   `spawnBackgroundProcess`, and the uncaught `TypeError` escaping the pi stdout
   handler.
2. Fix the `/stream/ws` unguarded-send fan-out break and the supervisor-map leak
   (both HIGH; both small, localized fixes).
3. Make the failing PTY unit test event-driven (kills the only red unit signal).
4. One mechanical comment-scrub pass to strip `Task N.N` / `REQ-*` / `RW-*` /
   `SCU-####` / Python-line-number pointers from shipped source.

**Follow-up (non-blocking):** the migration's FK-on single-transaction
brittleness, the silent persist `catch {}`, the concurrency limiter that doesn't
limit, the telemetry consent-flag-vs-token-gate nuance, and the build-script
Node-tarball checksum are all worth tickets but don't block the cutover.
