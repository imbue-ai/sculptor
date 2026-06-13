# Terminal Agents — Review

Fresh review pass over `origin/main...HEAD` (55 commits, 114 files,
+7,686/−549) against `spec.md`, `architecture.md`, and the plan. This pass
re-derived every requirement against current code, re-ran `just format` /
`just check` / `just test-unit`, re-ran the feature's Playwright integration
suite, and re-ran `/code-review-checklist` (fanned out across backend Python,
frontend, tests, and commit/sample text).

It supersedes an earlier in-branch review that concluded "ready to merge, all
findings resolved." That pass covered an earlier tip (29 commits); **26 more
commits have landed since** (split-button refactor, shared-MRU pickers,
auto-naming, roomier terminal typography, the bundled-registration
auto-install, session-id-on-first-prompt, the waiting-dot and tab-leak fixes).
This pass re-verified the whole diff and surfaces a handful of findings the
prior pass did not — most of them introduced by those newer commits.

## Summary

- **The implementation meets the spec.** All 24 `REQ-*` requirements are
  Covered (two with benign, documented deviations — REQ-SIG-2 and REQ-TYPE-4).
  Every architecture decision is reflected in the diff.
- **All deterministic suites pass.** `just format` (no-op), `just check`
  (lint, typecheck, ratchets, generate-api, generate-sculpt-client — tree
  clean afterward, so generated TS/sculpt-client types are current), and
  `just test-unit` (backend, frontend, imbue-core, sculpt) all exit 0. The
  feature's Playwright suite: **16/16 passed (114.5s)**. The token-burning
  `@real_claude` e2e was not re-run this pass (see Test Coverage).
- **No CRITICAL or HIGH findings; nothing that strictly blocks merge.** Five
  MEDIUM items were surfaced and have all been **fixed in this pass** (commits
  `16026043bf`, `2108c3a257`, `b1f8bfb82e`, `f5d858279e` — see each finding
  below). A sixth — the `enable_multi_harness` → `enable_pi_agent` config
  rename — was reviewed and consciously **won't-fixed**: the flag is
  experimental and no real users have it set, so an upgrade migration isn't
  worth the added complexity.
- **The amended REQ-CLAUDE-1 is correctly implemented.** The bundled Claude
  Code registration is now **auto-installed out of the box** as a user-owned
  registration (sentinel-guarded so deletion sticks and user edits are never
  overwritten) — not the "copyable sample, absent from the menu" the prior
  review and architecture §8 describe. Verified by code and the passing
  `test_bundled_claude_code_registration_installed_by_default`.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-TYPE-1 (per-agent type, mixed workspace) | Covered | `web/data_types.py:39-48` (`AgentTypeName`); `web/app.py:1598-1630` `_agent_config_for_request` stamps config per task; `interfaces/agents/agent.py:519-523` config variants; `test_multi_agent_workspace.py` |
| REQ-TYPE-2 (`+` menu lists all types) | Covered | `AgentTabs.tsx:535-569`; registrations route `web/app.py:3179`; `test_agent_type_menu.py` |
| REQ-TYPE-3 (replace `Workspace.harness`) | Covered | Column dropped (migration `b3f1a9c2d6e5`, symmetric downgrade + version test); `HarnessName`, `_agent_config_for_workspace`, request/response shims grep-clean |
| REQ-TYPE-4 (pi gated by flag) | Covered (deviation) | `AgentTabs.tsx:543-551`, `AddWorkspacePage.tsx:459-463`. Flag renamed `ENABLE_MULTI_HARNESS` → `enable_pi_agent`/`enablePiAgent` (commit `c406b95e2f`); functionally identical gate |
| REQ-TYPE-5 (new-workspace flow choice) | Covered | `AddWorkspacePage.tsx:432-478` type select replaces harness picker; first agent still prompt-less (`:252-260`); old `test_workspace_harness_picker.py` deleted |
| REQ-TYPE-6 (split button, last-used type) | Covered | `AgentTabs.tsx:494-572` split `+`/chevron; `agentTabs.ts:42-44` MRU atom (initial `claude`); `test_agent_type_menu.py`, `test_first_agent_type_defaults_to_shared_last_used` |
| REQ-REG-1 (user-scope declarative config) | Covered | `services/terminal_agent_registry/registry.py` loads `<sculptor folder>/terminal_agents/*.toml`; no repo scope, no settings UI |
| REQ-REG-2 (name + launch cmd; resume template) | Covered | `TerminalAgentRegistration` (registry.py:30-60) requires display_name + launch_command; optional `resume_command_template` (validated: `{session_id}` only, ≤1) + `accepts_automated_prompts` |
| REQ-REG-3 (re-read without restart) | Covered | Listing route re-reads dir per request (`app.py:3179-3190`); both pickers refetch on open (`staleTime: 0`); `test_registered_terminal_agent_appears_in_menu_and_creates` |
| REQ-SIG-1 (local HTTP event API) | Covered | `POST /api/v1/agents/{agent_id}/signal` (`app.py:3205`); `terminal_signal_test.py` |
| REQ-SIG-2 (inject env vars) | Covered (deviation) | `run_terminal_agent/v1.py:207-217` injects `SCULPT_API_PORT`/`SCULPT_AGENT_ID`/etc. The auth token is **not** injected as env; `sculpt` self-fetches it from the loopback-exempt `/api/v1/session-token` (`web/auth.py:107-118`). Functionally equivalent (arguably tighter — no credential in env). Architecture §4 says "inject the token"; worth one doc line |
| REQ-SIG-3 (`sculpt signal` subcommands) | Covered | `tools/sculpt/sculpt/commands/signal.py:57-89` (busy/idle/waiting/files-changed/session-id; `waiting`→wire `waiting-on-input`); `tools/sculpt/tests/unit/test_signal.py` |
| REQ-SIG-4 (closed v1 vocab, ignore unknown) | Covered | `app.py:3195-3199, 3261-3262` (unknown → `logger.info` + 204) |
| REQ-SIG-5 (drive tab indicators) | Covered | `derived.py:477-481` busy→RUNNING (spinner), waiting→WAITING (attention dot); unread dot deliberately not driven (spec amendment); `derived_task_status_test.py`, `test_terminal_agent_signals.py` |
| REQ-SIG-6 (files-changed → diff refresh) | Covered | `app.py:3246-3248, 3263-3264` → `maybe_refresh_workspace_diff` (outside the txn); integration-tested |
| REQ-TERM-1 (terminal panel = shell in code dir) | Covered | `run_terminal_agent/v1.py` handler + `AgentTerminalPanel.tsx`; no chat UI/parsing; `test_terminal_agent_basic.py` |
| REQ-TERM-2 (neutral status w/o signals) | Covered | `derived.py:481` (no signal → READY); fail-open hooks degrade to plain-terminal behavior |
| REQ-TERM-3 (periodic diff refresh, swappable) | Covered | `diff_refresh.py` `PeriodicDiffRefresher` (3s; `git status`+HEAD fingerprint pre-check; encapsulated class); `diff_refresh_test.py` |
| REQ-LIFE-1 (PTY survives tab/window close) | Covered | PTY owned by backend task, not the WS; `test_terminal_agent_basic.py`, `agent_terminal_ws_test.py` |
| REQ-LIFE-2 (terminate on archive/teardown) | Covered | `v1.py:276-277` finally → `stop_agent_terminal`; manager registered under env id so `stop_terminals_for_environment` is the backstop (`local_terminal_manager.py:156-166`) |
| REQ-LIFE-3 (resume after restart via session id) | Covered | `launch_command_for_start` (`v1.py:65-78`) renders the resume template when session id + template exist; `render_resume_command` validates+quotes; `test_registered_terminal_agent_resumes_after_restart` |
| REQ-LIFE-4 (plain terminal → fresh shell) | Covered | Plain config returns no launch command; `test_plain_terminal_agent_gets_fresh_shell_after_restart` |
| REQ-LIFE-5 (program in shell; exit → prompt) | Covered | `write_launch_command` types the command as a shell job; WS-respawn is a bare shell, no auto-relaunch; `test_registered_terminal_agent_launches_program` |
| REQ-UI-1 (terminal occupies chat space) | Covered | `ChatPanelContent.tsx:42-49` switches on `useTaskSupportsChatInterface`; no chat input/model picker |
| REQ-UI-2 (capability-gate, not ad-hoc) | Covered | `supports_chat_interface` on `HarnessCapabilities` (`harness.py:76`, no default → every harness declares); FE reads via capability atom/hook |
| REQ-UI-3 (tab behaves like any other) | Covered | Rename/archive/delete type-agnostic; dots from the same `data-dot-status` path; `test_terminal_agent_tab_rename_and_delete` |
| REQ-CLAUDE-1 (bundled Claude Code, **amended: installed out of the box**) | Covered | `terminal_agent_registry/bundled.py` auto-installs `samples/terminal_agents/claude-code/` into `<sculptor folder>/terminal_agents/` on first run (`web/app.py:407`), sentinel-guarded (`.claude-code.installed`), never overwrites user files, deletion sticks; `samples/.../{claude-code.toml,claude-code-hooks.json,README.md}`; `bundled_test.py`, `test_bundled_claude_code_registration_installed_by_default`, `real_claude/test_claude_code_terminal_agent.py` |

Architecture decisions verified: dedicated handler instead of the chat loop
(`tasks/api.py` dispatch); no `TerminalAgent`/`create_agent_for_run` extension
(documented in `harness_registry.py`); agent-scoped PTY `agent:<task_id>`
registered under the environment id; run-scoped **ephemeral**
`TerminalAgentSignalRunnerMessage` anchored on `EnvironmentAcquiredRunnerMessage`
and short-circuited by `EnvironmentReleasedRunnerMessage` (so a pre-restart
`waiting` is never resurrected); shell-self-exit keeps the task RUNNING with
on-demand respawn; shell pid persisted and reaped with session-leader/create-time
guards; CI babysitter inherits its chat-agent config type from the most recent
chat agent and skips terminal configs in model selection
(`coordinator.py:355-393`); first-agent intro message skipped for terminal agents.

**Two doc-currency deviations (not code defects):** architecture §8 still
describes the bundled registration as a copyable sample absent from the menu
(superseded by the amended REQ-CLAUDE-1 auto-install); architecture §9's
consumer-file edits were superseded by a cleaner seam — routing is decided by
which hook registers `chatActionsAtom` (`useChatData` for chat agents,
`useTerminalChatActions` for opted-in terminal agents, nothing → disabled
buttons), so Commit/PR/custom-action consumers are untouched. Both deliver the
specified behavior.

## User Scenarios

- **Plain terminal in place of chat** — Delivered. Login shell in the code
  dir, neutral dot, periodic diff refresh, PTY survives tab switches. Covered
  by `test_terminal_agent_basic.py` (passed).
- **Claude Code TUI as a registered terminal agent** — Delivered, and now
  installed out of the box. Hooks report busy/idle/waiting/files-changed/
  session-id via `sculpt signal`; dots driven accordingly. Covered
  deterministically by the fake-program tests (passed) and the real-TUI
  `@real_claude` e2e (not re-run this pass — see Test Coverage).
- **Resume after Sculptor restart** — Delivered. Session id persisted on
  `AgentTaskStateV2` (validated charset), relaunch renders the resume template
  (shell-quoted), surviving prior shell reaped first. Covered by
  `test_registered_terminal_agent_resumes_after_restart` (passed). Note: the
  bundled hooks now report the session id on **first prompt** (UserPromptSubmit),
  not TUI startup, so a restart before the user's first message lands a fresh
  shell — intended, and asserted in the updated real-claude e2e.
- **Quitting the TUI drops to a shell** — Delivered. Program runs as a shell
  job; exit lands at a usable prompt; status neutral; no relaunch. Covered by
  `test_registered_terminal_agent_launches_program` (passed).
- **Mixed workspace** — Delivered. Agent type is per-task config; diffs/branch
  info/commit bar stay workspace-shared. Exercised by every feature test.
- **Registered agent without working hooks** — Delivered. No signals → neutral
  status, periodic refresh still works; terminal-input endpoint refuses writes
  in that state.

## Test Coverage

- **Tests added:** ~40 new/modified test files (~110 test functions). Backend
  unit: `run_terminal_agent/{v1,terminal_session,diff_refresh}_test.py`,
  `web/{terminal_signal,terminal_input,agent_terminal_ws,derived_task_status,
  app_basic,data_types}_test.py`, `terminal_agent_registry/{registry,bundled}_test.py`,
  `coordinator_test.py`, `terminal_agent/harness_test.py`, the migration version
  test, `tools/sculpt/tests/unit/test_signal.py`. Integration (Playwright):
  the six feature files plus ported pi/conformance updates. Real-claude e2e:
  `real_claude/test_claude_code_terminal_agent.py`. The "Add failing test
  for…" TDD pairs (session-id-before-message, waiting-signal mapping, tab-leak)
  are correctly ordered and substantive.
- **Test suite status:** `just format` no-op; `just check` **pass** (lint,
  typecheck, ratchets, generate-api, generate-sculpt-client — tree clean after);
  `just test-unit` **pass** (all four suites). Exit 0.
- **Integration tests run (this pass):** the six feature files —
  **16 passed in 114.5s**, zero failures. Includes the bundled-install,
  tab-leak, shared-MRU, and signal-dot tests.
- **Real-Claude e2e:** `real_claude/test_claude_code_terminal_agent.py` was
  **not** re-run this pass (it burns tokens and needs live Claude). The prior
  pass ran it green, but the session-id-on-first-prompt change (`a0662293c2`)
  and the POSIX-`sed` extraction (`3add040a8f`) both touched the bundled hooks
  it exercises — those production `sed`/hook-event paths are only end-to-end
  verified by this e2e. Worth one run before/at merge.
- **Skipped / xfail:** none introduced. Only two `skipif(sys.platform ==
  "win32")` PTY guards (POSIX-only) — correct.

## Code Review Findings

`/code-review-checklist` run against `origin/main...HEAD` with the spec as the
stated goal, fanned out across backend Python, frontend, tests, and
commit/sample text. No CRITICAL or HIGH findings.

### Correctness

**MEDIUM — RESOLVED (`b1f8bfb82e`)** — `frontend/.../AgentTabs.tsx:262-274`
(plain `+` click). The retry-as-Claude `catch` fired for **any** create
failure of a stored non-Claude type, not just the "registration unavailable"
case the comment described — so a transient failure while the stored type was
`terminal` silently created a *Claude* agent and rewrote the MRU. The retry is
now scoped to `agentType === "registered"`; other failures propagate.

**LOW (informational, safe)** — `web/app.py:537-553` (`start_task`,
prompt-ful path). For a brand-new workspace with a terminal `agent_type`, the
workspace is upserted before the 422 reject. Confirmed safe: the upsert and
the raise share one transaction, so the workspace rolls back; `create_workspace`
has no filesystem side effects at that point. Validate-after-create is slightly
awkward but correct.

Otherwise no correctness issues: run-scoped status reset balances on every
path (incl. error paths); ephemeral signal/anchor messages land in the live
buffer under the subscription lock; the manager register/unregister race has a
winner + self-identity guard; `write_launch_command` snapshots its callback and
removes it in `finally`; the handler `finally` always stops + unregisters the
PTY with environment-teardown as the backstop.

### Consistency with stated goal

Covered above (Requirements Coverage). Two documented deviations: REQ-SIG-2
(token bootstrapped from the loopback endpoint rather than injected as env —
functionally equivalent, arguably tighter) and REQ-TYPE-4 (flag renamed to
`enable_pi_agent`). No unrequested scope creep. Architecture §8/§9 are stale
relative to the amended spec and the cleaner `chatActionsAtom` seam,
respectively — doc-currency, not code.

### Test coverage

**MEDIUM (flake) — RESOLVED (`f5d858279e`)** —
`tests/integration/frontend/test_registered_terminal_agent.py:28-30`
(`_FAKE_TUI_COMMAND`). The fake program did `sculpt signal busy; sleep 8;
sculpt signal idle`, and the test relied on that 8s wall-clock window to catch
the transient `running` dot — the `no_wall_clock_in_fake_claude` anti-pattern
(under CI load the first `expect()` poll could land after the sleep elapsed and
never see `running`). The busy state is now held on a blocking stdin `read`
(busy signals are sticky) and released by the test with a typed line, so the
assertion no longer races machine speed. Re-run green (3 passed, 82.9s).

Otherwise no issues: TDD pairs correctly ordered; error/edge paths well
covered (4404 WS contract, every 409 hazard on terminal-input, unsafe
session-id parametrization, unknown-event 204); the ported pi tests are a
faithful mechanical port with no weakened assertions.

### Proof of work completeness

N/A — the stated goal is a spec, not an autonomous-workflow MR body.

### Dead code & leftover artifacts

No issues found. The `enable_multi_harness`→`enable_pi_agent` and
`isMultiHarnessEnabledAtom`→`isPiAgentEnabledAtom` renames are complete; the
harness badge, harness ElementIDs, `HarnessName`, and `_agent_config_for_workspace`
are fully removed with no danglers; no commented-out code, debug prints, or
unowned TODO/FIXME in the diff.

### Comments

**MEDIUM — RESOLVED (`2108c3a257`)** —
`frontend/src/common/state/atoms/userConfig.ts:203-206`. Stale comment: it
still said the flag "gates only the new-workspace harness picker and the
harness badge; the `workspace.harness` execution path is independent of this
flag" — all three referents gone/renamed in this diff. Rewritten to say the
flag gates only the pi option in the agent-type pickers.

Otherwise no issues: no `agent_docs/`/`REQ-*`/`phase-N` references or real
people's names in source comments; new comments explain *why* (guard-order
rationale in `reap_stale_shell`, the `str.replace`-not-`.format` reasoning, the
split-button SCSS, the `ChatPanelContent` switch).

### Error handling

No issues found. The broad `except Exception` around `manager.start()`
(`terminal_session.py:121`) and the handler funnel (`v1.py:175`) are justified
graceful-degradation paths that log with context (info/debug per the
no-logger-warning ratchet) and mirror `run_agent_task_v1`. All external I/O
(git in `diff_refresh.py`, psutil in `reap_stale_shell`, httpx in `signal.py`)
has timeouts and scoped exception types; the registration loader skips+logs
per-file errors so one bad TOML can't break the menu.

### Security & secrets

**MEDIUM (docs) — RESOLVED (`16026043bf`)** —
`samples/terminal_agents/claude-code/README.md`. Now that this registration
**auto-installs**, an out-of-the-box "Claude CLI" agent launches `claude
--dangerously-skip-permissions` with `skipDangerousModePermissionPrompt: true`.
The README explained *what* the flags do but not the *premise* that makes
bypassing permission prompts acceptable out of the box. The README now states
that the agent runs inside the Sculptor-managed workspace environment with the
**same permission posture Sculptor already uses for its native Claude agents**
— so the bundled registration grants no privilege those agents don't already
have — and points users at editing/deleting it for a different posture.

Otherwise no issues. The two injection vectors are double-guarded:
**session-id** is charset/length-validated at the route (`[A-Za-z0-9._-]{1,128}`,
`fullmatch`) *and* `shlex.quote`d at resume-render (which uses `str.replace`,
never `.format`), with the loader independently restricting the template
placeholder; **terminal input** requires opt-in registration + a current-run
IDLE/WAITING signal + a live PTY, is bracketed-paste-wrapped, and the prompt
text is never logged. The bundled `sed` extraction reads the hook's stdin JSON
anchored to the leading `session_id` field (prompt text cannot spoof it) and
fails open. Signal/input/registration routes use the standard local
session-token auth; agent calls are scoped by agent id in the path; chat-agent
ids return 404 (don't leak task type).

**LOW (informational)** — `web/app.py:3251`. `fullmatch` runs on an unbounded
`SignalEventRequest.session_id` string (no `max_length` on the field). The
`{1,128}` bound applies to the match, not the input length; a large body is
walked before rejection. Immaterial behind the loopback bind + Starlette body
limits; a `max_length` on the pydantic field would tidy it.

### Type safety

No issues found. `HarnessCapabilities.supports_chat_interface` has no default,
so every constructor site (all harnesses + the abstract base + mocks/stories)
was forced to declare it. New public functions are annotated; structured data
uses pydantic; the discriminated union was extended correctly. `tsc --noEmit`
is clean and generated TS/`ElementIds`/sculpt-client are current (`just check`
ran the generators and left the tree clean). The few casts in `AddWorkspacePage`
/`AgentTabs` are each properly guarded.

### Backwards compatibility

**MEDIUM — ACKNOWLEDGED, WON'T FIX (owner decision).**
`imbue_core/imbue_core/sculptor/user_config.py:252` (`enable_multi_harness` →
`enable_pi_agent`, commit `c406b95e2f`). `UserConfig` is persisted to a TOML
file; `SerializableModel` allows extras but `model_post_init` clears them, and
no alias bridges the old key, so a user who previously set
`enable_multi_harness = true` would silently lose the opt-in on upgrade. The
owner confirmed this is **not worth fixing**: the flag is experimental,
off-by-default, and dark-launched — no real users have it set, so the upgrade
migration is unnecessary complexity. Recorded here as a conscious trade-off,
not an open action. (Were that to change, the one-line fix is
`AliasChoices("enable_pi_agent", "enable_multi_harness")` or a `mode="before"`
migration validator mirroring `_migrate_claude_binary_mode`.)

Otherwise clean: migration `b3f1a9c2d6e5` symmetrically drops `harness` from
`workspace`/`workspace_latest` with a downgrade re-adding it
(`server_default="claude"`) and a row-survival version test; existing tasks
need no migration (config already per-task); the FE↔BE contract ships together
(`agentType`/`registrationId` added, `harness` removed both sides); new union
members and the open signal vocabulary are forward-compatible reads.

### Frontend issues

**MEDIUM — RESOLVED (`b1f8bfb82e`)** —
`frontend/.../AddWorkspacePage.tsx:252-260`. The new-workspace form had no
equivalent of the tab bar's fallback: if the preselected MRU was a
`registered:<id>` whose registration was deleted between MRU-write and
form-open, the workspace was created first and then `createWorkspaceAgent`
threw, leaving a **created-but-agentless workspace**. The form now pre-checks
the stored `registrationId` against the current `registrations` list and falls
back to Claude (effective type used for the create call, the posthog event, and
the MRU write-back) so the just-created workspace stays usable.

**LOW** — `frontend/.../useTerminal.ts:392-393, 472-477`. The mount-only
xterm-init effect now reads two new reactive props (`fontSize`, `lineHeight`)
but its `eslint-disable exhaustive-deps` exclusion comment only justifies
omitting `getTheme`. No live bug (both are "fixed at mount", the sole caller
passes literals, and the panel is `key`-remounted per task), but the exclusion
comment should be extended to note these are intentionally read once.

Everything else checks out: `useTerminalAgentRegistrations` returns the standard
`BackendQueryResult<T>` bundle intersected with its `registrations` accessor
(conforms to `use_tanstack_result_bundle` — refutes the prior pass's concern),
keyed under the `["sculptor", …]` prefix with `staleTime: 0`; the split-button
`gap="0"` is the documented Radix-margin exception (neutralized in SCSS); the
new capability atoms are narrow derived atoms read via `useAtomValue`;
`useTerminalChatActions` faithfully mirrors `useChatData`'s register/teardown;
the `key={taskID}` remount is the correct, complete fix for the cross-tab
scrollback leak; chat→terminal switch effect ordering is safe.

### Integration test issues

Covered under Test coverage (the `_FAKE_TUI_COMMAND` `sleep 8` flake, MEDIUM).
Otherwise clean on current HEAD: no lowered timeouts (the prior pass's five
`timeout=15_000` assertions are genuinely restored to default); panel-switch
assertions and tab lookups go through POM helpers (`expect_terminal_panel_replaces_chat`
/ the tab-bar page object); `wait_for_timeout` calls are sleep-then-*type* or
sleep-then-*retrying-wait*, never sleep-then-assert; xterm-buffer absence
asserts are bare only because `expect()` can't target the JS handle, and are
gated behind a positive `wait_for_xterm_substring`; `@real_claude` is on the
one token-burning test and nothing else; no layout-only tests.

### Style guide & ratchets

No issues found by `just check` (ratchets pass). **LOW (cosmetic)** —
`tools/sculpt/sculpt/commands/signal.py:42` (a 124-char ternary) and
`registry.py:53` (a 121-char f-string) exceed the 119 line-length but are *not*
lint failures (ruff's default `select` excludes E501 and `ruff format` won't
break either). The `signal.py:42` ternary would read better split into
`if/else`.

### Git hygiene

No issues found. 55 commits, atomic, each body explaining the *why*; the TDD
"Add failing test for…/Fix…" pairs are correctly ordered and scoped. Two
cosmetic notes (non-blocking): co-author trailer style/casing varies across the
range, and one fix commit bundles its own real-Claude e2e (appropriately
atomic).

### Public-facing text (commit messages & PR/MR description)

No issues found. No secrets, credentials, PII (beyond the normal author
trailer), internal hostnames/infra names, customer data, exploit recipes, or
candid internal commentary in any of the 55 commit messages. `REQ-*`/`§N`/
`Task N.N` references in bodies resolve against the in-repo
`agent_docs/terminal-agents/` artifacts. No MR/PR body exists yet — the same
scrub rules apply when one is written, and per CLAUDE.md it must sign off as
`(Sent by Claude)`.

## Overall Assessment

**Ready to merge.** The feature is faithfully implemented to the (amended) spec
and architecture, the structural decisions all landed as designed, every
deterministic suite is green (unit, lint/types/ratchets, 16 feature Playwright
tests), and all five actionable MEDIUM findings from this pass were fixed and
re-verified. There are no CRITICAL or HIGH findings.

Findings addressed in this pass:

1. **Bundled-registration README security premise** — RESOLVED `16026043bf`.
2. **`_FAKE_TUI_COMMAND` `sleep 8` flake** — RESOLVED `f5d858279e` (test
   re-run: 3 passed).
3. **Stale `workspace.harness` comment** (`userConfig.ts`) — RESOLVED
   `2108c3a257`.
4. **Over-broad retry-as-Claude** (`AgentTabs.tsx`) and **missing registered
   fallback in the new-workspace form** (`AddWorkspacePage.tsx`) — RESOLVED
   `b1f8bfb82e`.

After the fixes, `just format` / `just check` / `just test-unit` all pass
(exit 0, no generated-file drift) and the `test_registered_terminal_agent.py`
integration suite is green.

Consciously **won't-fixed** (owner decision): the `enable_multi_harness` →
`enable_pi_agent` config-migration — experimental flag, no real users set it.

Remaining LOW polish (optional, not addressed): the `useTerminal`
eslint-disable comment, a `session_id` `max_length`, two over-length lines, and
the doc-currency updates to architecture §4/§8.

LOW polish (optional): the `useTerminal` eslint-disable comment, the
`session_id` `max_length`, and the two over-length lines. Documentation: update
architecture §8 (auto-install) and §4 (token bootstrap) to match the code, and
run the `@real_claude` e2e once to re-verify the bundled hooks after the
session-id-on-first-prompt / `sed` changes.

Biggest residual risk: the bundled hooks JSON is pinned to Claude Code 2.x hook
names and CLI flags; a future CLI rename degrades gracefully to plain-terminal
behavior by design, but silently loses the rich integration — the
`@real_claude` e2e is the canary for that.
