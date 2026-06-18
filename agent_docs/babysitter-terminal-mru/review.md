# Preserve Terminal-Agent Type When Auto-Creating Agents (SCU-1504) — Review

## Status: findings addressed

All findings below were fixed in this tab, one commit per issue, after the
review was written:

- `859448a` — drop REQ-ID / plan-phase pointers from comments (Comments, MEDIUM)
- `877dd59` — clarify the overlapping-drive coalescing comment (Correctness, LOW)
- `9a215e3` — clear the in-progress guard if the terminal-drive spawn fails, with
  a regression test (Correctness, LOW)
- `3d28a45` — prefix the in-progress guard boolean with `is_` (Style, LOW)

The one remaining finding (the `wait_for_timeout` in
`test_plain_terminal_mru_shows_disabled_reason`) was left as-is: its assertions
are retrying `expect()` calls and it mirrors the existing convention in that
file — see the note below. Full `just check` and `just test-unit` are green
after the fixes.

## Summary

- **The implementation meets the spec.** All 24 requirements across the six
  requirement groups (SET / AGENT / DRIVE / LIFE / DISABLE / LEGACY) are
  covered in the diff, with code citations below. The architecture's single
  `deliver_prompt_to_agent` seam and `_resolve_babysitter_agent` decision point
  are implemented as designed, keeping all babysitter policy in one place and
  isolating only the chat-vs-terminal delivery mechanism.
- **Tests are strong and green.** 28 new coordinator unit tests (full resolver
  matrix + terminal drive + transient reason + proactive snapshot), 4 shared
  helper tests, 5 config tests, and 3 Playwright e2e tests all pass. Full
  `just check` and `just test-unit` are green; the 3 e2e tests pass in 50s.
- **Nothing blocks merge.** The findings are minor: pervasive `REQ-*` IDs in
  code comments (a Comments-category convention violation), and one narrow
  coalescing edge case that self-heals on the next poll. Both are non-blocking.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-SET-1 (agent field on `CIBabysitterConfig`) | Covered | `config/user_config.py:150-153` (`agent: BabysitterAgentChoice`) + discriminated union `:89-128` |
| REQ-SET-2 (default MRU) | Covered | `config/user_config.py:150-153` (`default_factory=BabysitterAgentMRU`); `user_config_test.py:27-43` |
| REQ-SET-3 (selector lists MRU + driveable harnesses) | Covered | `CIBabysitterSettingsSection.tsx:111-140`; e2e `test_settings_selector_lists_only_driveable_harnesses` |
| REQ-SET-4 (plain / non-opt-in excluded) | Covered | `CIBabysitterSettingsSection.tsx:69-71` (`driveableRegistrations` filter); e2e asserts non-opt-in + Terminal absent |
| REQ-SET-5 (pinned unavailable → disabled, no fallback) | Covered | `coordinator.py:_resolve_babysitter_agent` pinned-Pi/registered branches → `Disabled(_DISABLED_REASON_PINNED_UNAVAILABLE)`; `test_pinned_pi_is_disabled_when_pi_disabled`, `test_pinned_registered_unavailable_is_disabled` |
| REQ-AGENT-1 (pinned harness for every workspace) | Covered | `coordinator.py:_resolve_babysitter_agent` (pinned branches ignore MRU) |
| REQ-AGENT-2 (MRU single most-recent, no skip) | Covered | `_resolve_babysitter_agent` takes `tasks[0]` only; `test_mru_does_not_skip_terminal_to_reach_older_chat` |
| REQ-AGENT-3 (Claude/Pi as today) | Covered | `deliver_prompt_to_agent` chat branch = verbatim `ChatInputUserMessage` flow |
| REQ-AGENT-4 (driveable terminal → own task, PTY) | Covered | `DriveableTerminal` → `_create_babysitter_task(config)` + worker PTY drive; e2e `test_babysitter_drives_registered_terminal_agent` |
| REQ-AGENT-5 (non-driveable terminal MRU → no spawn) | Covered | `_dispatch_prompt` returns on `Disabled`; `test_mru_most_recent_plain_terminal_is_disabled` |
| REQ-AGENT-6 (no prior agent → Claude) | Covered | `_resolve_babysitter_agent` `if not tasks: return ChatAgent(Claude)`; `test_mru_no_prior_task_resolves_chat_claude` |
| REQ-DRIVE-1 (PTY write gated like `/terminal/input`) | Covered | `web/terminal_input.py:deliver_prompt_to_terminal_agent` (Guards 1-3) shared by endpoint + coordinator |
| REQ-DRIVE-2 (bounded wait for IDLE/WAITING) | Covered | `coordinator.py:_wait_for_terminal_ready` (subscribe + 30s backstop); `test_terminal_drive_waits_for_idle_then_delivers` |
| REQ-DRIVE-3 (retries reuse same task) | Covered | `_ensure_babysitter_task` memoization; `test_terminal_drive_retries_reuse_same_task` |
| REQ-DRIVE-4 (never-ready → transient reason, give up cycle, count retry) | Covered | `_run_terminal_drive` sets `_TRANSIENT_REASON_UNREACHABLE`; retry counted at dispatch; `test_terminal_drive_never_ready_times_out` |
| REQ-LIFE-1 (task lifecycle like chat, no auto-archive) | Covered | terminal task reuses memoized `babysitter_task_id`; no archive-on-resolve path added |
| REQ-DISABLE-1 (per-workspace proactive on every read) | Covered | `get_state_snapshot` runs `_resolve_babysitter_agent` per read; e2e `test_plain_terminal_mru_shows_disabled_reason` (no failure needed) |
| REQ-DISABLE-2 (reason copy + remedy) | Covered | `_DISABLED_REASON_MRU_NON_DRIVEABLE` (`coordinator.py`) |
| REQ-DISABLE-3 (view/response `disabled_reason` field) | Covered | `CIBabysitterWorkspaceStateView` + `CIBabysitterWorkspaceStateResponse` (`app.py:1879-1880`) |
| REQ-DISABLE-4 (toggle reflects inert) | Covered | `PrDetailDropdown.tsx:75-78,173-175` (`isPersistentlyDisabled`); e2e asserts toggle disabled |
| REQ-DISABLE-5 (pinned unavailable reason) | Covered | `_DISABLED_REASON_PINNED_UNAVAILABLE`; `test_snapshot_surfaces_pinned_unavailable_reason` |
| REQ-DISABLE-6 (transient reason, clears) | Covered | `state.transient_disabled_reason`; cleared on PIPELINE_PASSED / MR merge/close; `test_transient_reason_clears_on_pipeline_passed` |
| REQ-LEGACY-1 (user-initiated creation unchanged) | Covered | No change to `lastUsedAgentType` / `+`/Cmd+K path (verified by absence in diff) |
| REQ-LEGACY-2 (chat path unchanged) | Covered | chat branch of `deliver_prompt_to_agent` is the prior flow verbatim; chat scenario tests unchanged |
| REQ-LEGACY-3 (pause/enabled compose) | Covered | all gates retained at top of `_dispatch_prompt`; `test_scenario_4_pause_toggle_prevents_prompt` unchanged |

## User Scenarios

**Claude/Pi user — unchanged.** The chat branch of `deliver_prompt_to_agent`
selects the model and enqueues a `ChatInputUserMessage` exactly as before, and
`_resolve_babysitter_agent` returns `ChatAgent` for a Claude/Pi MRU. The
existing chat scenario tests (`test_scenario_*`) are unmodified and still pass —
strong evidence the legacy path is untouched.

**Driveable terminal user — babysitter drives their tool.** Delivered and
verified end-to-end by `test_babysitter_drives_registered_terminal_agent`: with
an opt-in registered terminal agent as MRU, a CI failure spawns a distinct "CI
Babysitter" terminal task, the readiness wait blocks until the program signals
idle, and the fix-CI prompt is written to its PTY (`RECEIVED:Investigate the
failing pipeline` observed in the xterm buffer).

**Plain-terminal user — babysitter goes inert and says why.** Delivered and
verified by `test_plain_terminal_mru_shows_disabled_reason`: the PR popover
proactively shows the non-driveable reason and a disabled pause toggle without
needing a pipeline failure first, exercising the proactive `get_state_snapshot`
recomputation.

**Power user pins a specific harness.** Covered by the pinned-harness branches
of `_resolve_babysitter_agent` and `test_pinned_*` unit tests. No dedicated e2e
asserts the *runtime* effect of a pinned choice, but the resolver matrix tests
cover every pinned outcome including unavailable harnesses.

**Settings selector.** Verified by
`test_settings_selector_lists_only_driveable_harnesses`: the selector lists
Most recently used + Claude + the opt-in registration and excludes the
non-opt-in registration and plain terminals.

## Test Coverage

- **Tests added:**
  - `coordinator_test.py` — 28 tests: resolver matrix (MRU & pinned, Claude/Pi/
    driveable-terminal/plain-terminal/revoked-opt-in/none), terminal-drive worker
    (delivers + clears transient, never-ready times out, overlapping coalesce,
    guard clears on exception, dispatch doesn't block consumer loop, retries reuse
    task), and proactive snapshot (persistent reason, self-heal, pinned-unavailable,
    transient surfaced, healthy chat MRU).
  - `terminal_input_test.py` — 4 direct helper tests (each guard outcome + multiline
    bracketed-paste bytes), complementing the existing endpoint HTTP tests.
  - `user_config_test.py` — 5 tests (default MRU, back-compat without key, variant
    round-trip, registration_id preserved, camelCase alias round-trip).
  - `test_ci_babysitter.py` — 3 Playwright e2e (terminal drive, plain-terminal
    disabled reason, selector contents).
- **Test suite status:** PASS. `just check` (lint + types + ratchets +
  generate-api) green; `just test-unit` (backend + frontend + foundation +
  sculpt) green; targeted 69-test backend run green.
- **Integration tests run:** the 3 new e2e tests — **3 passed in 50.08s**.
- **Anything skipped / `xfail` / pending:** none.

## Code Review Findings

Output of the configured `/code-review-checklist` skill, run over
`origin/main...HEAD` against the SCU-1504 spec.

### Correctness

**LOW — RESOLVED (`877dd59`).** `coordinator.py` `_dispatch_prompt` (DriveableTerminal coalescing
branch) and `_run_terminal_drive`. The architecture's risk note says a coalesced
overlapping drive will "write the latest prompt," but the in-flight worker
captured `prompt_text` at its own dispatch, so a *different* transition's prompt
(e.g. a MERGE_CONFLICT arriving during an in-flight PIPELINE_FAILED drive) is
dropped for that cycle rather than upgraded to the latest. The impact is narrow
and self-healing: the coalesced dispatch returns before setting its dedup marker
(`last_dispatched_merge_conflict` / `last_dispatched_pipeline_failed_id`), so the
next poll re-dispatches once the in-progress flag clears. Worth a one-line code
comment reconciling the implementation with the design note, or upgrading the
worker to re-read the latest prompt before writing.

**LOW — RESOLVED (`9a215e3`).** `coordinator.py` `_dispatch_prompt`.
`is_terminal_drive_in_progress` is set to `True` under the lock immediately
before `start_new_thread`. If thread spawn ever raised, the flag would latch on
and park the workspace. Fixed by wrapping the spawn in a guarded block that
clears the flag and logs on failure (skipping the retry bump, since no drive was
attempted), with a regression test (`test_terminal_drive_in_progress_clears_on_spawn_failure`).

No other correctness issues found. Resource lifecycle is sound: the
`subscribe_to_task` context manager closes on every path, and the worker's
`finally` always clears the in-progress guard so a crash cannot park the
workspace.

### Consistency with stated goal

The change implements the spec faithfully — see the Requirements Coverage table;
all 24 requirements are covered. The only deviation from the *architecture*
prose is the coalescing "latest prompt" nuance noted under Correctness, which is
a doc/implementation wording mismatch rather than a missing requirement. No scope
creep: the diff touches only the babysitter, the shared terminal helper, the
setting, and the two frontend surfaces named in the architecture's *Files to
Modify*.

### Test coverage

No issues found. New behavior is covered at both unit and e2e levels, error/edge
paths (never-ready, revoked opt-in, pinned-unavailable, worker exception,
overlapping drive) have dedicated tests, and nothing is skipped or `xfail`. The
e2e terminal program is a deterministic shell script (not real Claude), so the
tests are not at the mercy of model output.

### Proof of work completeness

Not applicable — the stated goal is a spec, not an autonomous-workflow MR body.

### Dead code & leftover artifacts

No issues found. `_select_chat_agent_config_for_workspace` is deleted as planned;
`is_terminal_agent_config` is still imported and used (`coordinator.py:669`); the
bracketed-paste constants and `scan_terminal_signal_state` import moved out of
`app.py` cleanly (lint would have flagged a leftover unused import, and `just
check` is green). No debug prints, commented-out code, or stray TODOs.

### Comments

**MEDIUM — RESOLVED (`859448a`).** Multiple files. Ten added comment/docstring lines embed `REQ-*`
requirement IDs (`REQ-DRIVE-4` ×3, `REQ-AGENT-2` ×3, `REQ-SET-2/4/5`,
`REQ-AGENT-6`) in `coordinator.py`, and the integration test references
`_DISABLED_REASON_MRU_NON_DRIVEABLE` by name. The Comments review rule
explicitly bars pointers to plan/spec requirement IDs — "the comment must stand
on its own." The surrounding prose already explains the *why* in every case, so
the `REQ-*` tags can simply be deleted without losing information. Non-blocking
but worth a cleanup pass before merge to satisfy the repo's own comment policy.

Otherwise comments are good: they explain intent (the seam rationale, the
readiness-signal design, the persistent-vs-transient reason split) rather than
narrating the code, and none editorialize.

### Error handling

No blocking issues. `_run_terminal_drive` wraps its body in `except Exception`,
which the checklist flags by default, but here it is a legitimate worker-thread
boundary: it logs the exception *with workspace context* (not silent) and the
`finally` clears the in-progress guard, which is exactly the "a crash can't park
the workspace" invariant the design calls for. The shared helper returns a typed
`TerminalDeliveryResult` enum instead of raising, and the endpoint maps each
outcome to its historical HTTP status — clean and explicit.

### Security & secrets

No issues found. This change's security posture is actually a net improvement:
the three PTY-write guards (opt-in registration, at-prompt signal, live PTY) now
live in one shared helper, so the user-facing `/terminal/input` endpoint and the
babysitter can never drift apart. Guard 1 re-checks the live registration's
opt-in to defend against a since-revoked stamped config. The helper logs only the
prompt length, never its text (`# Log the event, never the text`). No secrets,
tokens, or credentials anywhere.

### Type safety

No issues found. The setting is a typed Pydantic discriminated union
(`build_discriminator()` + `Tag`), not an ad-hoc string — round-trip and alias
tests confirm it. New public functions are fully annotated; result types are
frozen dataclasses (`ChatAgent` / `DriveableTerminal` / `Disabled`). `ElementIDs`
changed and `just generate-api` was run (green), so the TS types are in sync.

### Backwards compatibility

No issues found. The new `agent` field is additive with a `default_factory` that
reproduces today's behavior; `test_ci_babysitter_config_without_agent_key_is_mru`
proves pre-existing configs deserialize to MRU. The response model's new fields
default to `None`/`False`, and the frontend↔backend contract ships together in
this branch. No DB migration needed (config is file-based; coordinator state is
in-memory).

### Frontend issues

No issues found (reviewed against `react.md` and `sculptor.md`).
`CIBabysitterSettingsSection.tsx` derives `driveableRegistrations` during render
(no effect), reads narrow derived atoms (`ciBabysitterAgentAtom`,
`isPiAgentEnabledAtom`) per `use_derived_atoms`, and keeps the encode/decode
helpers at module scope. `PrDetailDropdown.tsx` derives `disabledReason` /
`isPersistentlyDisabled` inline and — importantly per `no_silently_gated_handlers`
— reflects the inert state in the DOM via the Switch's `disabled` attribute
rather than only early-returning in the handler. Registrations are refetched on
select-open, a reasonable freshness trigger.

### Integration test issues

No blocking issues (reviewed against `integration_tests.md`). Tests use retrying
`expect()` throughout, raised (not lowered) timeouts, POM accessors
(`PlaywrightCIBabysitterSettingsElement`, `get_babysitter_status()`), and per-test
isolated registration TOMLs cleaned up in `finally`. No marker is needed (browser
mode suffices; the terminal program is a shell script, no real-Claude/`@release`
dependency).

**LOW** — `test_ci_babysitter.py:test_plain_terminal_mru_shows_disabled_reason`.
The test uses `page.wait_for_timeout(_BASELINE_POLL_SETTLE_MS)` to let the
polling service create per-workspace state before opening the popover. The
subsequent assertions are retrying `expect()` calls (so this is not the classic
sleep-then-snapshot anti-pattern), and the wait targets a timer-driven backend
poll that has no DOM proxy — mirroring the existing `_MERGED_MODE_STABLE_WAIT_MS`
convention already used throughout this file. Acceptable as-is, but if it ever
flakes, prefer waiting on an observable signal over a fixed delay.

### Style guide & ratchets

`just check` (which runs `ratchets`, `lint`, `typecheck`) is green, so no ratchet
regressions and no import/structure violations.

**LOW — RESOLVED (`3d28a45`).** `state.py` `terminal_drive_in_progress`. The boolean wasn't
prefixed `is_`/`has_`/`should_` per the style guide's boolean-naming convention.
Renamed to `is_terminal_drive_in_progress` (field + all references).

### Git hygiene

No issues found. Commits are atomic (one plan task each), messages explain the
*why*, and each carries the `Co-authored-by: Sculptor` trailer. Phasing matches
the plan (extract helper → setting → resolver/seam → worker/readiness →
status → frontend/e2e).

### Public-facing text (commit messages & PR/MR description)

No issues found. Commit messages contain no secrets, no PII (they refer to "the
user"/"dev", no real names or `/Users/<name>` paths), and no internal hostnames
or customer data. The bare `SCU-1504` ticket reference is fine. `REQ-*` and "Task
X.Y" references in commit prose are internal plan pointers but are not PII or
secrets, so they don't violate the public-visibility policy (unlike the code-comment
case above, which the Comments rule governs separately).

### Code-review summary

- The change accomplishes the stated goal: the CI Babysitter now preserves the
  MRU agent type including driveable terminals, drives them via the shared
  guarded PTY path, and surfaces a proactive disabled reason instead of silently
  spawning Claude.
- Address before merge (optional, non-blocking): strip the `REQ-*` IDs from code
  comments (MEDIUM, Comments-policy), and add a one-line comment reconciling the
  overlapping-drive coalescing with the "latest prompt" design note (LOW).
- Nothing blocks the change.

## Overall Assessment

**Ready to merge.** The implementation matches the spec and architecture
faithfully, the seam-based design keeps all babysitter policy in one place as
intended, and the security-sensitive PTY guards are correctly centralized so the
endpoint and babysitter cannot drift. Test coverage is comprehensive at both unit
and e2e levels, and the entire suite (`just check`, `just test-unit`, the 3 new
e2e tests) is green.

The biggest residual risk is the overlapping-drive coalescing edge case, which
is narrow (requires a second, *distinct* transition to arrive during a
multi-second terminal readiness window) and self-heals on the next poll cycle —
not a merge blocker. The only cleanup worth doing first is removing the `REQ-*`
IDs from code comments to satisfy the repo's own Comments convention.

Follow-up suggestions (non-blocking): consider a code comment reconciling the
coalescing behavior with the architecture's "latest prompt" wording, and — if the
proactive per-read transaction in `get_state_snapshot` ever shows up as hot — the
architecture already notes it can be memoized against the MRU task id.
</content>
</invoke>
