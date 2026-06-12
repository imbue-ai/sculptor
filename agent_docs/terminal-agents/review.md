# Terminal Agents — Review

## Summary

- **The implementation meets the spec.** All 24 `REQ-*` requirements are
  covered in code with tests; every architectural decision (handler-owned PTY,
  run-scoped ephemeral status signals, agent-scoped PTY registered under the
  environment id, session-id validation + shell-quoting, stale-shell reaping,
  registration TOML loader, automated-prompt reverse channel) is reflected in
  the diff. `just check` and `just test-unit` both pass (exit 0).
- **Top thing to address before merging:** a pervasive comment-policy
  violation — **69** `REQ-*` / `architecture §N` / `phase N` references in code
  comments and test docstrings (CLAUDE.md forbids these; they're meaningless to
  an outside reader and several files are publicly visible). Mechanical to fix.
- **Two substantive (non-blocking) findings:** (1) the new terminal-agent
  registrations hook uses a hand-rolled `useState`+`fetch` instead of TanStack
  Query (violates `sculptor.md`, and has a stale-overwrite race); (2) two new
  `current_state` read-evolve-upsert write paths use deferred transactions whose
  "evolve only this field" comments overstate the concurrency safety — switch to
  `immediate=True` to match the repo's existing read-then-write pattern.
- **Nothing here is a hard blocker.** The substantive findings are robustness /
  convention issues, not crashes or data-loss. The Playwright integration suite
  for this feature was **not re-executed** in this pass (see Test Coverage).

## Resolution

All findings below were addressed on this branch after the review pass.
`just check` and `just test-unit` pass green after the fixes. Commit map:

- **Comments (HIGH)** — internal `REQ-*` / `architecture §N` references scrubbed
  from code comments and test docstrings (pre-existing pi/harness-abstraction
  refs left untouched): `4ef9e9fc2e`.
- **Frontend / TanStack (HIGH)** — `useTerminalAgentRegistrations` moved onto
  `useQuery`: `27703313ca`.
- **Concurrency (MEDIUM)** — the two `current_state` read-then-write paths now
  use `BEGIN IMMEDIATE` (and `on_exception` promoted to a shared helper):
  `695bad31c3`.
- **Dead code / consistency (MEDIUM)** — unreachable `AGENT_TYPE_LABELS.registered`
  removed and a shared registered-type encoding helper extracted: `295c0dfd4e`.
- **Integration tests (MEDIUM/LOW)** — shared `get_agent_terminal_panel` POM
  helper and restored default status-dot timeouts: `371ef2caa1`.
- **Status correctness (LOW)** — `scan_terminal_signal_state` now resets on the
  environment-released marker: `d2560dc99c`.
- **Dead code (LOW)** — unused `PeriodicDiffRefresher.force()` removed:
  `3ebcd95722`.

Deliberately left (judged correct as-is, noted in the per-category findings):
the `reap_stale_shell` same-backend guard (intentional pid-reuse safety); the
pre-existing CI-babysitter broad `except Exception`; the REQ-SIG-2 token
deviation (functionally correct — the CLI mints the token from the auth-exempt
loopback endpoint); and the fixed `wait_for_timeout` PTY-readiness waits in the
integration tests (replacing them risks introducing flakiness). The Playwright
suite still needs a run via `/run-integration-test` before merge.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-TYPE-1 (per-agent type) | Covered | `interfaces/agents/agent.py` new `TerminalAgentConfig`/`RegisteredTerminalAgentConfig` in `AgentConfigTypes`; `web/app.py` `_agent_config_for_request` factory |
| REQ-TYPE-2 (`+` menu choices) | Covered | `AgentTabs.tsx` dropdown lists Claude/pi/Terminal/registrations; `/api/v1/terminal-agent-registrations` listing route |
| REQ-TYPE-3 (replace `Workspace.harness`) | Covered | `database/models.py` column removed; migration `b3f1a9c2d6e5_drop_harness_from_workspace.py`; `_agent_config_for_workspace` deleted |
| REQ-TYPE-4 (pi gated by `ENABLE_MULTI_HARNESS`) | Covered | `AgentTabs.tsx` + `AddWorkspacePage.tsx` conditionally render the pi entry; `test_agent_type_menu.py`, `test_add_workspace_agent_type.py` assert gating |
| REQ-TYPE-5 (new-workspace flow choice) | Covered | `AddWorkspacePage.tsx` agent-type select replaces harness picker; `test_add_workspace_agent_type.py` |
| REQ-TYPE-6 (split button + last-used) | Covered | `AgentTabs.tsx` split button; `agentTabs.ts` `lastUsedAgentTypeAtom`; `test_agent_type_menu.py` |
| REQ-REG-1 (user-scope config) | Covered | `services/terminal_agent_registry/registry.py` loads `~/.sculptor/terminal_agents/*.toml`; no repo-scope, no UI |
| REQ-REG-2 (name + launch cmd, opt. resume) | Covered | `TerminalAgentRegistration` model + `RegisteredTerminalAgentConfig` (launch/resume template, `accepts_automated_prompts`) |
| REQ-REG-3 (re-read on menu open) | Covered | `registry.py` re-reads per request; `useTerminalAgentRegistrations.refresh()` on menu open; `registry_test.py` |
| REQ-SIG-1 (local HTTP event API) | Covered | `web/app.py` `POST /api/v1/agents/{agent_id}/signal`; `terminal_signal_test.py` |
| REQ-SIG-2 (inject env vars) | **Covered (deviation)** | `run_terminal_agent/v1.py:196-200` injects `SCULPT_API_PORT/WORKSPACE_ID/PROJECT_ID/AGENT_ID`. **Auth token is NOT injected**; the `sculpt` CLI instead fetches it on demand from the auth-exempt loopback `/api/v1/session-token` (`tools/sculpt/sculpt/auth.py` + `session.py`). Functionally satisfies the req; deviates from architecture §4's "inject the token into `extra_env`." |
| REQ-SIG-3 (`sculpt signal` subcommands) | Covered | `tools/sculpt/sculpt/commands/signal.py` (busy/idle/waiting/files-changed/session-id); `tools/sculpt/tests/unit/test_signal.py` |
| REQ-SIG-4 (closed vocab, ignore unknown) | Covered | `web/app.py` `_TERMINAL_SIGNAL_STATUS_BY_EVENT`; unknown events logged + ignored (204); `terminal_signal_test.py` |
| REQ-SIG-5 (drive tab indicators; not unread) | Covered | `web/derived.py` terminal status branch; ephemeral messages excluded from `updated_at`; `derived_task_status_test.py` |
| REQ-SIG-6 (files-changed → diff refresh) | Covered | `web/app.py` files-changed → `maybe_refresh_workspace_diff`; `terminal_signal_test.py` |
| REQ-TERM-1 (terminal panel = shell) | Covered | `run_terminal_agent/v1.py` handler; `terminal_agent/harness.py` all-false chat caps; `AgentTerminalPanel.tsx` |
| REQ-TERM-2 (neutral when no signal) | Covered | `derived.py` `scan_terminal_signal_state` → READY with no signal; `test_terminal_agent_basic.py` |
| REQ-TERM-3 (periodic diff refresh) | Covered | `run_terminal_agent/diff_refresh.py` `PeriodicDiffRefresher` (git status+HEAD fingerprint, 3s); `diff_refresh_test.py` |
| REQ-LIFE-1 (PTY survives tab/window close) | Covered | PTY owned by backend handler, not WS; `agent_terminal_ws_test.py`; `test_terminal_agent_basic.py` reconnect |
| REQ-LIFE-2 (terminate on archive/teardown) | Covered | `v1.py` `finally` → `stop_agent_terminal`; manager registered under env id → `stop_terminals_for_environment` backstop |
| REQ-LIFE-3 (resume after restart) | Covered | `v1.py` `launch_command_for_start` uses resume template when session id present; `terminal_session.py` `render_resume_command` |
| REQ-LIFE-4 (plain terminal = fresh shell) | Covered | `v1.py` returns no launch command for plain config; on-demand bare-shell respawn |
| REQ-LIFE-5 (program runs in shell; exit→prompt) | Covered | `terminal_session.py` writes launch command as a shell job; task stays RUNNING on program exit; no auto-relaunch |
| REQ-UI-1 (terminal occupies chat space) | Covered | `ChatPanelContent.tsx` switches on `useTaskSupportsChatInterface`; `AgentTerminalPanel.tsx` |
| REQ-UI-2 (capability-gate, not ad-hoc) | Covered | `interfaces/agents/harness.py` `supports_chat_interface` (no default); FE reads via capability hook; no ad-hoc config-type checks |
| REQ-UI-3 (tab behaves like any other) | Covered | `AgentTabs.tsx` rename/archive/delete agnostic to type; status dots from `derived.py` |
| REQ-CLAUDE-1 (bundled Claude Code example) | Covered | `samples/terminal_agents/claude-code/` TOML + hooks JSON calling `sculpt signal …`; not auto-installed; `real_claude/test_claude_code_terminal_agent.py` |

## User Scenarios

- **Plain terminal in place of chat** — Delivered. Creating a Terminal agent
  spawns a login shell in the workspace code dir, shows neutral status, refreshes
  the diff periodically, and survives window close / restart (fresh shell).
  Covered by `test_terminal_agent_basic.py`.
- **Claude Code TUI as registered terminal agent** — Delivered. The bundled
  sample registration + hooks drive busy/waiting/idle dots and diff refresh;
  the user interacts only via the terminal. Covered by the fake-program
  `test_registered_terminal_agent.py` and the real-Claude
  `test_claude_code_terminal_agent.py` (gated `@real_claude`).
- **Resume after restart** — Delivered. Reported session id persists on
  `AgentTaskStateV2.terminal_session_id`; restart relaunches via the resume
  template (validated + shell-quoted), reaping a surviving prior shell first.
  Covered by `v1_test.py` / `terminal_session_test.py` and the restart leg of
  `test_registered_terminal_agent.py`.
- **Quitting the TUI drops to a shell** — Delivered. The program runs as a shell
  job; on exit the user lands at the prompt, status returns to neutral, no
  auto-relaunch.
- **Mixed workspace** — Delivered. Agent type is per-task config; diffs/branch/
  commit bar are workspace-shared regardless of agent type.
- **Registered agent without working hooks** — Delivered. With no signals the
  agent degrades to plain-terminal behavior (neutral status, periodic refresh).

## Test Coverage

- **Tests added:** ~100 new test functions. Backend unit: `v1_test.py` (399),
  `terminal_session_test.py` (238), `diff_refresh_test.py` (74),
  `agent_terminal_ws_test.py` (153), `terminal_signal_test.py` (214),
  `terminal_input_test.py` (335), `derived_task_status_test.py` (108),
  `registry_test.py` (114), `coordinator_test.py` (+106), `app_basic_test.py`
  (+237), `tools/sculpt/tests/unit/test_signal.py` (104). Integration
  (Playwright): `test_terminal_agent_basic.py`, `test_terminal_agent_signals.py`,
  `test_registered_terminal_agent.py`, `test_terminal_agent_automated_prompts.py`,
  `test_agent_type_menu.py`, `test_add_workspace_agent_type.py`. Real-Claude e2e:
  `real_claude/test_claude_code_terminal_agent.py`.
- **Test suite status:** `just check` → **pass (exit 0)**; `just test-unit` →
  **pass (exit 0)**.
- **Integration tests run:** **NOT re-executed in this review pass.** The
  Playwright suite requires the `/run-integration-test` harness and is slow; the
  real-Claude test (`@real_claude`, `timeout=600`) is excluded from CI and burns
  tokens. The Build phase's task `99_01_verify_all_tests` is expected to have run
  them green. **Recommendation: run the feature's Playwright tests via
  `/run-integration-test` before merge.**
- **Skipped / xfail:** No new unconditional skips. The `@pytest.mark.skipif(...
  win32)` markers on PTY tests are correct (PTYs are POSIX-only). The one
  unconditional `@pytest.mark.skip` in `app_basic_test.py:562` is **pre-existing**
  (not introduced by this diff).
- **Coverage gap to confirm (LOW):** the deleted `test_workspace_harness_picker.py`
  asserted the harness badge persisted on the workspace row after creation; the
  replacement tests drop that post-creation persistence assertion. Confirm the
  badge surface was intentionally removed.

## Code Review Findings

The configured `/code-review-checklist` skill was run against `origin/main...HEAD`
(goal = the spec). Findings by category:

### Correctness

**MEDIUM** — `tasks/handlers/run_terminal_agent/v1.py:85-90` (`_persist_terminal_shell_pid`)
and `web/app.py:3236-3238` (session-id persist). Both do read → `evolve(one field)`
→ `upsert_task` on the full `current_state` blob inside a **deferred** transaction
(`open_task_transaction()` / the request transaction without `immediate=True`).
`evolve` rebuilds the whole state from the snapshot read *in that transaction*, so
two concurrent writers (the handler thread writing `terminal_shell_pid` while a
`session-id` signal — or a rename — writes another field) can last-writer-wins
clobber each other. The docstrings ("evolves only this field so concurrent state
writers are not clobbered") describe field-merge *within one snapshot*, which does
not prevent cross-transaction clobbering. The repo already uses `immediate=True`
for read-then-write paths (e.g. `app.py:991`); `sql_implementation.py` documents
that deferred BEGIN "leaves read-then-write paths exposed to stale-snapshot races."
This feature newly introduces a handler-thread writer racing request-thread
writers, so a real collision is more likely than the pre-existing rename path.
Recommend `immediate=True` on both new write paths (and softening the comments).

**LOW** — `web/derived.py:104-119` (`scan_terminal_signal_state`). The reverse scan
resets at `EnvironmentAcquiredRunnerMessage` but not at `EnvironmentReleasedRunnerMessage`,
so between a run releasing and the next run acquiring, a signal from the just-ended
run is still reported as live status (and would satisfy the terminal-input
IDLE/WAITING guard). Self-heals on the next acquire; low impact.

**LOW (informational)** — `tasks/handlers/run_terminal_agent/terminal_session.py`
(`reap_stale_shell`). The `create_time() >= this-backend.create_time()` guard
correctly rejects recycled pids but also skips a genuinely-stale shell spawned by
the *current* backend (no restart). Acceptable trade-off favoring pid-reuse safety.

Resource lifecycle is otherwise sound: `create_agent_terminal` registers the
manager only after `start()` succeeds and stops the loser on a registration race;
`write_launch_command` removes its output callback in `finally`; the handler's
`finally` always stops + unregisters.

### Consistency with stated goal

**MEDIUM** — `AgentTabs.tsx:48`. `AGENT_TYPE_LABELS` maps `registered: "Claude"`
with the comment "falls back to Claude until phase 4." Its only use site is the
`else` branch where `defaultAgentType` provably cannot be `"registered"` (the
registered case is handled separately). The entry exists only to satisfy
`Record<AgentTypeName, string>` exhaustiveness and is unreachable; the label is
dead/misleading. Narrow the map type or remove the entry.

Otherwise the diff matches the spec with no unrequested scope creep.

### Test coverage

**LOW** — `test_registered_terminal_agent.py:148,165`, `test_terminal_agent_basic.py:39`,
`test_terminal_agent_signals.py:46` use `page.wait_for_timeout(3_000)` as a fixed
PTY-readiness delay before typing. Documented and not snapshot-then-assert (the
following `wait_for_xterm_substring` is a real retrying wait), but it adds ~3s per
test and could wait on a shell-ready sentinel instead.

**LOW** — dropped harness-badge persistence coverage (see Test Coverage above).

### Proof of work completeness

N/A — the stated goal is a spec, not an autonomous-workflow MR body. Section skipped.

### Dead code & leftover artifacts

**MEDIUM** — `AgentTabs.tsx:48`, the unreachable `AGENT_TYPE_LABELS.registered`
entry (see Consistency).

**LOW** — `tasks/handlers/run_terminal_agent/diff_refresh.py:61-65`,
`PeriodicDiffRefresher.force()` is only called from tests; the handler loop uses
`tick()` only. Small deliberate API surface, but unwired in production.

The `Workspace.harness` removal is clean (no leftover `harness`/`HarnessName`
references; old `HARNESS_*` ElementIDs and SQL select removed). No debug prints /
commented-out code / unused imports in new files.

### Comments

**HIGH (pervasive)** — **69** code comments / test docstrings reference internal
`REQ-*` ids, `architecture §N`, or `phase N` (43 in source, 26 in tests). CLAUDE.md
("Comments") and the checklist forbid "pointers to throwaway docs, tickets, or plan
phases — `agent_docs/...` paths, `REQ-*` ids, or implementation-plan phase
references." Examples: `terminal_session.py:7,151,199`; `v1.py:13,67,133,222,229`;
`registry.py:1,68`; `interfaces/agents/agent.py:209,225`; `web/derived.py:412,464-466`;
`web/app.py:1598,3169,3175,3194,3262`; `agentTabs.ts:12`; `AgentTerminalPanel.tsx:15`;
`ChatPanelContent.tsx:25,32`; `useTerminalChatActions.ts:17,19`; and most new test
docstrings. Rewrite each to state the *why* without the internal reference. No
real-people names found.

### Error handling

No bare `except:`. `_compute_fingerprint` catches `(OSError, ProcessError)` and
checks return codes/timeouts; `reap_stale_shell` catches precise
`(ProcessLookupError, psutil.NoSuchProcess, PermissionError)`; git calls carry a
5s timeout.

**LOW** — `services/ci_babysitter_service/coordinator.py:340-342` keeps an
unconditional `except Exception` (logs at debug, falls back to `()`). Pre-existing
code that this diff refactored; it does carry context.

### Security & secrets

No secrets. The two injection vectors are well-guarded: **session-id** is validated
by `re.fullmatch(r"[A-Za-z0-9._-]{1,128}")` at the route *and* `shlex.quote`'d before
interpolation into the resume command (two layers; `render_resume_command` uses
`str.replace`, not `.format`); **terminal/input** bytes are gated by three guards
(opt-in registration, run-started + IDLE/WAITING signal, live PTY) and wrapped in
bracketed-paste markers, and the prompt text is never logged (only its length). New
POST routes require `get_user_session`; the agent terminal WS route is unauthenticated,
matching the existing `workspace_terminal_websocket` (loopback-only server). 404 (not
403) is returned for chat-agent task ids to avoid leaking task type.

Note (informational): REQ-SIG-2's auth token is reachable by any process in the
terminal via the auth-exempt loopback `/api/v1/session-token` endpoint — the same
posture the architecture's "inject the token" decision would have produced, since
that endpoint already hands the token to any loopback caller.

### Type safety

New public functions/pydantic models are annotated; the discriminated
`AgentConfigTypes` union is extended correctly. `Any` appears only in the handler
return type (mirrors the sibling chat handler) and one `cast(EnvironmentTypes, …)`,
both justified. ElementIDs were regenerated (new `AGENT_TYPE_*`,
`ADD_AGENT_CHEVRON_BUTTON`, `AGENT_TERMINAL_PANEL`, `ADD_WORKSPACE_AGENT_TYPE_SELECT`
present; stale harness ids removed). No unjustified `any`.

### Backwards compatibility

Migration `b3f1a9c2d6e5` is a clean symmetric drop of `harness` from
`workspace`/`workspace_latest` with a downgrade that re-adds it
(`server_default="claude"`); it is the new head and the migration test confirms row
survival. Reading an older DB (column still present) silently ignores it
(forward-read-safe). Frontend↔backend contract shipped together (FE sends
`agentType`/`registrationId`, no longer `harness`; regenerated types + mocks updated
in lockstep). **LOW (inherent):** running an *older* backend after this migration
(or against tasks carrying the two new config variants) would fail — standard
downgrade-incompat, the alembic downgrade path exists.

### Frontend issues

**HIGH** — `common/state/hooks/useTerminalAgentRegistrations.ts:19-29` violates
`sculptor.md` `use_tanstack_for_pulled_data` / `no_bespoke_fetch_caching`: an
HTTP-pulled read stored in a hand-rolled `useState` with imperative `.then(setState)`
and no in-flight / unmount guard. Two consequences: (a) opening the menu twice in
quick succession can let an older slow response overwrite a newer one
(`react.md` race), and a response landing after unmount calls `setState` on an
unmounted component; (b) the two call sites (`AgentTabs` + `AddWorkspacePage`) keep
independent copies of the same list (`duplicate_state_across_siblings`). Moving to
`useQuery` (key `["sculptor", …]`, `staleTime: 0`, expose `refetch` for the on-open
refresh) fixes the rule violation, the race, and the duplicate state in one change.

**LOW** — `AgentTerminalPanel.tsx:30` hardcodes `isVisible: true` because the panel
only mounts for the active tab; correct given the mount strategy and the comment
explains it.

IconButton-in-Flex `gap="2"` rule **satisfied** (`AgentTabs.tsx` split-button Flex).
No effect-for-derived-value, ref-during-render, missing-cleanup, or unstable-key
issues; `useTerminal.ts` `terminalPath` refactor correctly lists the path in the WS
effect deps and retains the cleanup guard; list keys use stable `registrationId`.

### Integration test issues

(Read `docs/review/integration-tests.md` in full.)

**MEDIUM** — `use_pom_hierarchy`. Across `test_registered_terminal_agent.py`,
`test_terminal_agent_automated_prompts.py`, `test_terminal_agent_basic.py`,
`test_terminal_agent_signals.py`, `test_agent_type_menu.py`,
`test_add_workspace_agent_type.py`, and `test_claude_code_terminal_agent.py`, test
bodies directly call `page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)` /
`CHAT_INPUT` / `AGENT_TAB` ~10×. The terminal-panel visibility check is a prime
candidate for a single POM method (e.g. `expect_terminal_panel_visible()`). The new
`get_agent_type_menu_item_*` POM methods are good additions; the panel/chat-input
access should get the same treatment. (xterm helpers in `terminal.py` are the
documented third-party-DOM exception — fine.)

**LOW** — `no_lowered_timeouts`. `test_registered_terminal_agent.py:60,71` and
`test_terminal_agent_automated_prompts.py:78,90,101` use `timeout=15_000`/`20_000`
on `data-dot-status` assertions, tightening the 30s default. These gate on a real
PTY→HTTP→WS→React round-trip; per the rule they should use the default 30s rather
than a window that can flake under CI load.

**LOW (informational)** — `test_registered_terminal_agent.py:29-31` `_FAKE_TUI_COMMAND`
uses `sleep 8` to hold the busy dot. Non-racy as written (the `busy` signal is
latched and asserted *before* the sleep, then the post-sleep transition is awaited),
but flagged so a future edit doesn't "bump the sleep" into raciness.

No violations of `use_expect_not_assert` (the `assert`s read non-DOM SQLite/JSONL/
xterm-buffer state), `no_sleep_then_assert`, `no_snapshot_iteration`, or
`correct_launch_mode_markers` (`@real_claude` is correctly the only marker on the
token-burning test).

### Style guide & ratchets

Module-level constants for all timeouts/intervals (no magic numbers); imports at top;
no relative imports; no mutable default args; early-exit style.

**LOW** — `v1.py:46` imports a private `_on_exception` from the chat handler
(`run_agent.v1`); reuses its error contract but crossing a module boundary for a
`_`-prefixed symbol is a smell — consider promoting to a shared helper.

**LOW** — `AddWorkspacePage.tsx`/`AgentTabs.tsx` repeat the magic string `"registered:"`
and `.slice("registered:".length)` in three places; extract a `REGISTERED_PREFIX`
const + parse/encode helpers.

### Git hygiene

No issues found. Commits are atomic and per-task, messages explain the change. (The
`Task N.N:` prefixes are plan-phase references; harmless in commit subjects, but the
same phase-reference habit leaked into code comments — see Comments.)

### Public-facing text (commit messages & PR/MR description)

No issues found. No secrets, PII, internal hostnames, customer data, or candid
internal commentary in the commit messages in range. No PR/MR body was provided.

## Overall Assessment

**Ready to merge after a cleanup pass — no hard blockers.** The feature is
well-architected and faithfully implements the spec and architecture; the unit
suite and `just check` are green. Before merging:

1. **(HIGH, mechanical)** Scrub the 69 `REQ-*` / `architecture §N` / `phase N`
   references from code comments and test docstrings.
2. **(HIGH, convention + race)** Move `useTerminalAgentRegistrations` onto TanStack
   Query.
3. **(MEDIUM, concurrency)** Use `immediate=True` for the two new `current_state`
   read-evolve-upsert write paths and soften their "not clobbered" comments.
4. **(MEDIUM, cleanup)** Remove/narrow the unreachable `AGENT_TYPE_LABELS.registered`
   entry; convert the most-repeated `get_by_test_id` panel checks to a POM method.
5. **Run the feature's Playwright integration tests** via `/run-integration-test`
   before merge — they were not re-executed in this review pass.

Biggest risk: the deferred-transaction clobber (#3) is the only finding that could
cause wrong runtime behavior (a lost `session_id` → resume falls back to a plain
launch, or a lost `shell_pid` → a stale shell not reaped). Low probability, easy fix.
Everything else is convention, cleanup, or comment hygiene.
