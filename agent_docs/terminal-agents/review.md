# Terminal Agents — Review

Final review pass over `origin/main...HEAD` (29 commits, 98 files, +6,879/−471)
against `spec.md`, `architecture.md`, and the plan. This pass re-verified every
requirement in code, re-ran the unit suites, ran the feature's Playwright
integration suite (which the earlier in-branch review pass had not executed),
and re-ran the `/code-review-checklist` skill on the current tip.

## Summary

- **The implementation meets the spec.** All 24 `REQ-*` requirements are
  Covered (one with a benign, functionally-equivalent deviation — see
  REQ-SIG-2). Every architecture decision is reflected in the diff: dedicated
  task handler owning an agent-scoped PTY, run-scoped ephemeral signal
  messages, capability-gated panel switch, TOML registration directory,
  session-id validation + shell-quoting, stale-shell reaping, and the
  server-side automated-prompt reverse channel.
- **All test suites pass.** `just format` (no-op), `just check` (lint,
  typecheck, ratchets), `just test-unit` (backend, frontend, imbue-core,
  sculpt) all exit 0. The feature's Playwright suite: **13/13 passed**
  (90.8s). The pi/conformance integration files this diff modified: **29/29
  passed** (103.4s). The only thing not executed is the token-burning
  `@real_claude` e2e (see Test Coverage).
- **An earlier review pass on this branch already ran and was addressed.**
  Its findings (comment scrub, TanStack migration, `BEGIN IMMEDIATE`
  read-then-write hardening, dead-code removal, status reset on
  environment-release) landed as commits `4ef9e9fc2e`, `27703313ca`,
  `695bad31c3`, `295c0dfd4e`, `371ef2caa1`, `d2560dc99c`, `3ebcd95722`. This
  pass verified each fix is in place.
- **No blockers.** The remaining findings are LOW: five leftover
  `timeout=15_000` assertions the timeout-cleanup commit missed, a registrations
  hook that returns a custom shape instead of the standard `BackendQueryResult`
  bundle, and some residual direct `get_by_test_id` use in test bodies.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-TYPE-1 (per-agent type) | Covered | `interfaces/agents/agent.py:490-506` new config variants in `AgentConfigTypes`; `web/app.py:1592` `_agent_config_for_request` stamps per-agent at creation |
| REQ-TYPE-2 (`+` menu lists all types) | Covered | `AgentTabs.tsx:507-566` menu (Claude/pi/Terminal/registrations); `web/app.py:3162` registrations listing route; `test_agent_type_menu.py` |
| REQ-TYPE-3 (replace `Workspace.harness`) | Covered | Column dropped (`database/models.py`, migration `b3f1a9c2d6e5` + version test); `HarnessName`, `_agent_config_for_workspace`, request/response fields all deleted |
| REQ-TYPE-4 (pi gated by `ENABLE_MULTI_HARNESS`) | Covered | `AgentTabs.tsx:541` and `AddWorkspacePage.tsx:442` render the pi entry conditionally; gating asserted in `test_agent_type_menu.py:65`, `test_add_workspace_agent_type.py:37` |
| REQ-TYPE-5 (new-workspace flow choice) | Covered | `AddWorkspacePage.tsx:412-466` agent-type select replaces the harness picker; first agent still created with no prompt; `test_add_workspace_agent_type.py` |
| REQ-TYPE-6 (split button, last-used type) | Covered | `AgentTabs.tsx:497-565` split `+`/chevron; `agentTabs.ts:33` `lastUsedAgentTypeAtom` (client-side, `registered:<id>` encoding); one-click flow asserted in `test_agent_type_menu.py:22` |
| REQ-REG-1 (user-scope declarative config) | Covered | `services/terminal_agent_registry/registry.py` loads `<sculptor folder>/terminal_agents/*.toml`; no repo scope, no settings UI |
| REQ-REG-2 (name + launch cmd; resume template) | Covered | `TerminalAgentRegistration` (registry.py:30) requires display_name + launch_command; optional `resume_command_template` (validated: `{session_id}` only, at most once) + `accepts_automated_prompts` |
| REQ-REG-3 (re-read without restart) | Covered | Listing route re-reads the directory per request (`app.py:3162`); both pickers refetch on menu open; proven live in `test_registered_terminal_agent_appears_in_menu_and_creates` |
| REQ-SIG-1 (local HTTP event API) | Covered | `POST /api/v1/agents/{agent_id}/signal` (`web/app.py:3188`); `terminal_signal_test.py` |
| REQ-SIG-2 (inject env vars) | Covered (deviation) | `run_terminal_agent/v1.py:196-203` injects `SCULPT_API_PORT`/`SCULPT_AGENT_ID`/etc. via PTY `extra_env`. The auth token is **not** injected; the `sculpt` CLI self-fetches it from the auth-exempt loopback session-token endpoint. Same security posture (any loopback process can mint it), hooks need no credentials in env — functionally satisfies the requirement, deviates from architecture §4's "inject the token" letter. |
| REQ-SIG-3 (`sculpt signal` subcommands) | Covered | `tools/sculpt/sculpt/commands/signal.py` (busy/idle/waiting/files-changed/session-id; `waiting` maps to wire `waiting-on-input`); `tools/sculpt/tests/unit/test_signal.py` |
| REQ-SIG-4 (closed v1 vocab, ignore unknown) | Covered | `_TERMINAL_SIGNAL_STATUS_BY_EVENT` (`app.py:3173`); unknown events logged + 204; `SignalEventRequest.event` is a plain string so additive evolution validates |
| REQ-SIG-5 (drive tab indicators) | Covered | `derived.py:468-481` busy→RUNNING (spinner), waiting→WAITING (attention dot); unread dot deliberately not driven (spec amendment per architecture §5); `derived_task_status_test.py`, `test_terminal_agent_signals.py` |
| REQ-SIG-6 (files-changed → diff refresh) | Covered | `app.py` files-changed → `maybe_refresh_workspace_diff` (outside the transaction); `test_files_changed_refreshes_workspace_diff` + integration |
| REQ-TERM-1 (terminal panel = shell in code dir) | Covered | `run_terminal_agent/v1.py` handler + `AgentTerminalPanel.tsx`; no chat UI, no parsing; `test_terminal_agent_basic.py` |
| REQ-TERM-2 (neutral status w/o signals) | Covered | `scan_terminal_signal_state` (`derived.py:98`) → READY with no signals; broken-integration degradation asserted in `test_no_signals_this_run_is_rejected` + neutral-dot integration assertions |
| REQ-TERM-3 (periodic diff refresh, swappable) | Covered | `diff_refresh.py` `PeriodicDiffRefresher` (3s interval, `git status`+HEAD fingerprint pre-check per plan Q&A, encapsulated class); `diff_refresh_test.py` |
| REQ-LIFE-1 (PTY survives tab/window close) | Covered | PTY owned by the backend task, not the WS; reconnect-with-scrollback asserted in `test_terminal_agent_basic.py:80-85`; `agent_terminal_ws_test.py` |
| REQ-LIFE-2 (terminate on archive/teardown) | Covered | Handler `finally` → `stop_agent_terminal` (`v1.py:263`); manager registered under the workspace environment id so `stop_terminals_for_environment` is the backstop (`test_stop_terminals_for_environment_stops_agent_terminal`) |
| REQ-LIFE-3 (resume after restart via session id) | Covered | `launch_command_for_start` (`v1.py:67`) renders the resume template when session id + template exist; `render_resume_command` validates+quotes; restart leg of `test_registered_terminal_agent_resumes_after_restart` |
| REQ-LIFE-4 (plain terminal → fresh shell) | Covered | Plain config returns no launch command; `test_plain_terminal_agent_gets_fresh_shell_after_restart` asserts fresh shell and no stale scrollback |
| REQ-LIFE-5 (program runs in shell; exit → prompt) | Covered | `write_launch_command` types the command into the login shell as a job; no auto-relaunch on exit (WS respawn is a bare shell); `test_registered_terminal_agent_launches_program` exit-to-prompt leg |
| REQ-UI-1 (terminal occupies chat space) | Covered | `ChatPanelContent.tsx:34-56` switches on `useTaskSupportsChatInterface`; no chat input/model picker for terminal agents |
| REQ-UI-2 (capability-gate, not ad-hoc) | Covered | `supports_chat_interface` on `HarnessCapabilities` (`harness.py:76`, no default — every harness forced to declare); FE reads via capability atom/hook; no config-type conditionals in the frontend |
| REQ-UI-3 (tab behaves like any other) | Covered | Rename/archive/delete agnostic to type (`test_terminal_agent_tab_rename_and_delete`); dots from the same `data-dot-status` path |
| REQ-CLAUDE-1 (bundled Claude Code example) | Covered | `samples/terminal_agents/claude-code/` (TOML + hooks JSON + README), copyable, absent from the menu until installed; loader round-trip test pins the sample to the schema; `real_claude/test_claude_code_terminal_agent.py` |

Architecture decisions verified in the diff: dedicated handler instead of the
chat loop (`tasks/api.py:40` dispatch); no `TerminalAgent`/`create_agent_for_run`
extension (comment documents why at `harness_registry.py:98`); agent-scoped PTY
key `agent:<task_id>` registered under the environment id; ephemeral
`TerminalAgentSignalRunnerMessage` with `EnvironmentAcquiredRunnerMessage` as the
run-start anchor (plus reset on `EnvironmentReleased`, an improvement found in
the earlier pass); shell-self-exit keeps the task RUNNING with on-demand respawn;
shell pid persisted and reaped with session-leader/age guards; CI babysitter
inherits config type from the most recent chat agent (plan Q&A decision 2,
`coordinator.py:355`); first-agent intro message skipped for terminal agents
(`app.py:1763`). The one mechanism deviation from the architecture's §9 file
list: Commit/PR/custom-action **consumers are untouched** — routing lives in
which hook registers `chatActionsAtom` (`useChatData` for chat agents,
`useTerminalChatActions` for opted-in terminal agents, nothing → disabled).
This is cleaner than editing each consumer and delivers the same behavior.

## User Scenarios

- **Plain terminal in place of chat** — Delivered. Terminal agent opens a login
  shell in the workspace code dir; neutral dot; file changes reach the Changes
  panel via periodic refresh; PTY survives tab switches. Covered end-to-end by
  `test_terminal_agent_basic.py` (passed).
- **Claude Code TUI as a registered terminal agent** — Delivered. The bundled
  sample's hooks report busy/idle/waiting/files-changed/session-id through
  `sculpt signal`; dots driven accordingly. Covered deterministically by the
  fake-program tests (passed) and by the real-TUI `@real_claude` e2e (not run
  this pass — see Test Coverage).
- **Resume after Sculptor restart** — Delivered. Session id persisted on
  `AgentTaskStateV2.terminal_session_id` (validated charset), relaunch renders
  the resume template (shell-quoted), surviving prior shell reaped first.
  Covered by `test_registered_terminal_agent_resumes_after_restart` (passed).
- **Quitting the TUI drops to a shell** — Delivered. The program runs as a
  shell job; exit lands at a usable prompt, status returns to neutral, no
  relaunch. Covered by `test_registered_terminal_agent_launches_program` (passed).
- **Mixed workspace** — Delivered. Agent type is per-task config; diffs,
  branch info, and the commit bar stay workspace-shared. Exercised implicitly
  by every feature test (chat agent + terminal agents side by side).
- **Registered agent without working hooks** — Delivered. No signals → neutral
  status, periodic refresh still works; the terminal-input endpoint refuses
  writes in that state (`test_no_signals_this_run_is_rejected`).

## Test Coverage

- **Tests added:** ~110 new test functions. Backend unit: `v1_test.py` (6),
  `terminal_session_test.py` (11), `diff_refresh_test.py` (4),
  `terminal_signal_test.py` (6), `terminal_input_test.py` (12),
  `derived_task_status_test.py` (17), `agent_terminal_ws_test.py` (5),
  `registry_test.py` (7), `terminal_agent/harness_test.py` (5),
  `coordinator_test.py` (+4), `app_basic_test.py` (+10), migration version
  test, `tools/sculpt/tests/unit/test_signal.py` (6). Integration
  (Playwright): `test_terminal_agent_basic.py`, `test_terminal_agent_signals.py`,
  `test_registered_terminal_agent.py`, `test_terminal_agent_automated_prompts.py`,
  `test_agent_type_menu.py`, `test_add_workspace_agent_type.py`. Real-Claude
  e2e: `real_claude/test_claude_code_terminal_agent.py`. Coverage maps 1:1 onto
  the architecture's Testing Strategy section, including the restart-reset
  status case, pre-environment BUILDING, session-id charset rejection, and the
  bundled-sample loader round-trip.
- **Test suite status:** `just format` no-op; `just check` **pass** (lint,
  typecheck, ratchets); `just test-unit` **pass** (all four suites). Exit 0.
- **Integration tests run (this pass, via the integration-test harness):**
  the six feature files — **13 passed in 90.8s**; the four pre-existing files
  this diff modified (`test_minimum_interface_conformance.py`,
  `test_pi_basic.py`, `test_pi_capability_gating.py`,
  `test_pi_managed_install.py`) — **29 passed in 103.4s**. Zero failures.
- **Not run:** `real_claude/test_claude_code_terminal_agent.py` (`@real_claude`,
  600s timeout). It burns real tokens and is excluded from the default CI runs
  by design; the deterministic fake-program tests cover the same plumbing. Run
  it once before release if the bundled sample is part of the release story.
- **Skipped / xfail:** none introduced. The two `pytestmark = skipif(win32)`
  guards on PTY test modules are correct (PTYs are POSIX-only).

## Code Review Findings

`/code-review-checklist` run against `origin/main...HEAD` with the spec as the
stated goal. An earlier in-branch review pass's findings were all addressed
(commit map in the Summary); findings below are what remains on the current tip.

### Correctness

No issues found. Verified specifically: the two read-evolve-write
`current_state` paths now open `BEGIN IMMEDIATE` transactions
(`v1.py:85-97`, `app.py:3196`); `scan_terminal_signal_state` resets on both
run-start and environment-released anchors so an ended run's signals are never
revived (`derived.py:98-121`); `create_agent_terminal` registers the manager
only after `start()` succeeds and stops the loser on a registration race;
`write_launch_command` removes its output callback in a `finally`; the handler's
`finally` always stops + unregisters the PTY, with environment-scoped teardown
as the backstop.

**LOW (informational)** — `terminal_session.py:166` (`reap_stale_shell`). The
`create_time() >= backend.create_time()` guard rejects recycled pids but also
skips a genuinely stale shell spawned by the *current* backend process (a
re-run without a restart). Deliberate trade-off favoring pid-reuse safety;
the docstring documents the guard order.

### Consistency with stated goal

**LOW (deviation, documented)** — REQ-SIG-2: the architecture said to inject
the session token into the PTY env; the implementation injects identity/port
and lets `sculpt` mint the token from the auth-exempt loopback endpoint.
Functionally equivalent (the endpoint already hands the token to any loopback
caller), and hooks carry no credentials in env. Worth one line in the
architecture doc if it is kept current; not a code change.

Otherwise the diff matches the spec with no unrequested scope creep. The §9
consumer-file edits were superseded by a cleaner seam (routing decided by which
hook registers `chatActionsAtom`) with the same user-visible result.

### Test coverage

**LOW — RESOLVED (`2f52ea0505`)** — `test_terminal_agent_signals.py:52,55,58,66`
and `test_terminal_agent_basic.py:71` passed `timeout=15_000` to assertions
that gate on a real PTY→HTTP→WS→React round-trip; the timeout-cleanup commit
(`371ef2caa1`) had missed these five. All five now use the 30s default; both
files re-run green (3 passed).

**LOW (informational)** — fixed `page.wait_for_timeout(3_000)` PTY-readiness
waits before typing (`test_terminal_agent_basic.py:39`,
`test_terminal_agent_signals.py:46`, `test_registered_terminal_agent.py:146,163`).
Sleep-then-*type* (not sleep-then-assert): the keystroke target has no
observable ready signal, and every subsequent wait is a retrying
`wait_for_xterm_substring`. Acceptable as written; a shell-ready sentinel would
shave ~3s/test if it ever matters.

### Proof of work completeness

N/A — the stated goal is a spec, not an autonomous-workflow MR body.

### Dead code & leftover artifacts

No issues found. The earlier pass's findings (unused
`PeriodicDiffRefresher.force()`, unreachable `AGENT_TYPE_LABELS.registered`)
are fixed on the tip; the `Workspace.harness` removal left no stragglers
(grep-clean for `HarnessName`, old ElementIDs, SQL column).

### Comments

No issues found. The earlier pass's 69 `REQ-*`/`architecture §N`/`phase N`
comment references were scrubbed in `4ef9e9fc2e`; a fresh grep over the diff
finds none in source. No real-people names; no narration comments.

### Error handling

No issues found. `_compute_fingerprint` catches `(OSError, ProcessError)` with
5s git timeouts and degrades to "skip this tick"; `reap_stale_shell` catches
precise process exceptions; the registration loader skips+logs per-file errors
so one bad TOML cannot break the menu; CLI subcommands exit 1 with the status
on stderr. (Pre-existing broad `except Exception` in
`coordinator.py:340` was refactored but not introduced by this diff.)

### Security & secrets

No issues found. The two injection vectors are double-guarded: **session-id**
is charset/length-validated at the route (`[A-Za-z0-9._-]{1,128}`) *and*
`shlex.quote`d at resume-template rendering (which uses `str.replace`, never
`.format`); **terminal input** requires opt-in registration + live-run
IDLE/WAITING signal + live PTY, is bracketed-paste wrapped, and the prompt text
is never logged (only its length). Chat-agent task ids return 404 (not 403) so
the route doesn't leak task type. The agent terminal WS route is
unauthenticated, matching the existing workspace terminal WS on the
loopback-only server.

### Type safety

No issues found. New public functions and pydantic models are annotated; the
discriminated union extended correctly; `HarnessCapabilities` has no defaults so
the new bool forced every constructor site (all five harnesses + mocks/stories
updated). TS types and ElementIds regenerated (`just check` runs
`generate-api`/`generate-sculpt-client`; tree clean afterward).

### Backwards compatibility

No issues found. Migration `b3f1a9c2d6e5` symmetrically drops `harness` from
`workspace`/`workspace_latest` with a downgrade re-adding it
(`server_default="claude"`) and a row-survival version test. Existing tasks need
no migration (config already per-task). Frontend↔backend contract shipped
together (FE sends `agentType`/`registrationId`; `harness` fields removed both
sides in the same commit).

### Frontend issues

**LOW** — `useTerminalAgentRegistrations.ts:27-41` returns
`{ registrations, refresh }` instead of the standard `BackendQueryResult<T>`
bundle (`use_tanstack_result_bundle`). The menus render fine from an empty
default and arguably don't need pending/error states, but the convention exists
so consumers never guess hook shapes; returning the bundle (plus the derived
`registrations`) is a five-line change.

Everything else checks out: TanStack hook under the `["sculptor", …]` key
prefix with `staleTime: 0` and explicit refetch-on-open (the documented pattern
for non-pushed, non-workspace-scoped data); split-button `Flex` uses `gap="2"`
per CLAUDE.md; `ChatPanelContent` renders `null` while capabilities are unknown
(deliberate, commented — avoids registering chat actions for a terminal agent);
`useTerminalChatActions` mirrors `useChatData`'s register/teardown contract,
keeps the send closure stable across status flips, and surfaces 409s as a
toast; `useTerminal`'s `terminalPath` generalization keeps the path in the WS
effect deps; list keys use stable `registrationId`; the storage-teardown guard
in `atomWithDebouncedStorage` is a justified best-effort catch.

### Integration test issues

**MEDIUM→LOW (residual)** — `use_pom_hierarchy`: the earlier pass's POM finding
was partially addressed (shared `get_agent_terminal_panel` /
`get_agent_terminal_textarea` helpers, `open_agent_type_menu` with
Radix-teardown retry). Test bodies still reach for
`page.get_by_test_id(ElementIDs.CHAT_INPUT)` (4×) and `ElementIDs.AGENT_TAB`
(1×, `test_add_workspace_agent_type.py:78`); a `chat input absent` helper
would finish the job. Low impact — the IDs are stable and the assertions are
one-liners.

**LOW** — the five remaining `timeout=15_000` assertions (see Test coverage).

No `use_expect_not_assert` violations (the bare `assert`s read non-DOM state:
SQLite, xterm buffer snapshots after a retrying wait); no `no_sleep_then_assert`
violations; `_FAKE_TUI_COMMAND`'s `sleep 8` is latched (busy asserted before
the sleep window matters) and commented; launch-mode markers correct
(`@real_claude` alone on the token-burning test; everything else unmarked
browser-mode).

### Style guide & ratchets

No issues found. Named constants for every timeout/interval; imports at top;
early-exit style; `just ratchets` passes (runs inside `just check`).

### Git hygiene

No issues found. 26 implementation commits, one per plan task plus review-fix
commits, each message explaining the why. The `Task N.N:` subjects and
`REQ-*`/`§N` references in some bodies resolve against the spec/architecture
committed in-repo under `agent_docs/terminal-agents/`, so they remain readable
to an outside reader.

### Public-facing text (commit messages & PR/MR description)

No issues found. No secrets, PII, internal hostnames, customer data, or candid
internal commentary in any commit message in range. No MR body exists yet — when
one is written, the same scrub rules apply.

## Overall Assessment

**Ready to merge.** The feature is faithfully implemented to spec and
architecture, the structural decisions all landed as designed, the earlier
review pass's findings were fixed and verified, and every suite that can run
deterministically is green (unit, lint/types/ratchets, 42 Playwright tests
across feature + regression files).

Remaining items, all LOW and none blocking:

1. ~~Restore default timeouts on the five remaining `timeout=15_000` assertions~~
   — resolved in `2f52ea0505`.
2. Return the standard `BackendQueryResult` bundle from
   `useTerminalAgentRegistrations`.
3. Optional: a POM helper for the repeated `CHAT_INPUT`-absent assertion.
4. Consider one `@real_claude` run of `test_claude_code_terminal_agent.py`
   before a release that advertises the bundled Claude Code sample.

Biggest residual risk: the bundled Claude Code hooks JSON is pinned to the
hook-event names and CLI flags of Claude Code 2.x (the README documents this);
a future CLI rename degrades gracefully to plain-terminal behavior by design,
but the sample would silently lose its rich integration — the real-claude e2e
is the canary for that.
