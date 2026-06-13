# Task 1.6: Gate-state integration tests across all gated surfaces

## Goal

Deterministic, fake_pi-driven integration coverage proving every gated
surface's two states: under pi (capability `False`) the affordance is
disabled-with-tooltip (or hidden, where that's the sanctioned fallback);
under Claude (capability `True`) it renders enabled and unchanged. This
is the FOLLOWUPS-9 lesson institutionalized: a gate is only trusted when
a test asserts the gated-off state.

## Requirements addressed

REQ-TEST-4, REQ-BASE-5 (testability of the treatment).

## Background

This cycle (pi-capabilities) hardens Sculptor's per-harness capability
gates and upgrades pi's gated-off affordances from hidden to
disabled-with-tooltip. Earlier phase-1 tasks built what this task tests:
Task 1.1 split the capability model (`supports_context_reset` new) and
made typo'd reads compile errors; Task 1.2 added the five missing narrow
atoms/hooks (ContextReset, Compaction, BackgroundTasks, SessionResume,
ToolUseRendering) in
`sculptor/frontend/src/common/state/atoms/tasks.ts` /
`hooks/useTaskHelpers.ts`; Task 1.3 added the shared capability-gate
primitive, migrated the interactive surfaces, and added a stable
ElementID per upgraded surface to `sculptor/sculptor/constants.py`
(`ElementIDs` StrEnum, regenerated via `just generate-api`).

Test infrastructure that already exists:

- **The gating test file**:
  `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  parametrizes a `harness` fixture over "claude"/"pi" (indirect;
  `HarnessTestConfig` from
  `sculptor/tests/integration/frontend/conftest.py`), with the
  `_create_workspace_for_harness` helper: for pi it calls
  `install_fake_pi_binary(sculptor_instance_.fake_bin_dir)`
  (`sculptor/sculptor/testing/fake_pi.py:322-334`) and passes
  `model_name=None`; for Claude it selects `FAKE_CLAUDE_MODEL_NAME`.
  Five tests exist (plan-mode toggle, fast-mode toggle, sub-agent render
  path, uploads gating, skills panel) — Task 1.3 already updated their
  pi-side assertions from `to_have_count(0)` to disabled+tooltip where
  surfaces were upgraded.
- **fake_pi** (`sculptor/sculptor/testing/fake_pi.py`): a stdin/stdout
  replacement for `pi --mode rpc` speaking the real wire shapes
  (response → agent_start → user-echo message_end → message_update(s) →
  message_end → agent_end); directives embedded in prompts
  (`fake_pi:emit_text` etc., registry at lines 213-218). It is installed
  as the default pi stub in integration runs.
- **Element assertions**: `page.get_by_test_id(ElementIDs.X)`; the
  `@user_story(...)` decorator annotates intent (see the existing tests).
- The `/write-integration-test` skill documents FakeClaude setup and
  general integration-test patterns — read it before writing tests.

## Files to modify/create

- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  extend to a complete per-surface matrix. New/updated coverage:
  - Plan-mode toggle (backchannel) — exists; assert disabled+tooltip
    ElementID for pi.
  - Stop button (`StatusPill`) + queued-message bar (interruption) — new.
  - Fast-mode toggle — exists; align to the upgraded treatment.
  - File-attachments affordance — extend the existing uploads test to the
    disabled+tooltip ElementID.
  - Image entries: `+`-menu Images row; toolbar image button — new.
  - Skills: panel + slash-picker skill rows — extend the existing
    skills-panel test to the upgraded treatment (or suppression where
    that was the recorded fallback).
  - `/clear` entry: picker row treatment AND execution refusal (type
    `/clear` in a pi workspace; assert no clear-context call fires —
    e.g. assert the refusal toast, and that the chat stays intact).
  - Status-only chrome (compaction pill state, token-popover context
    row): assert ABSENT for pi (the sanctioned graceful fallback) — these
    have no tooltip treatment by decision.
- (Only if a surface lacked a usable hook) `sculptor/sculptor/constants.py`
  — any missed ElementID, plus `just generate-api`; flag it back to Task
  1.3's surface list in the MR.

## Implementation details

1. Follow the file's established shape: one focused test per surface,
   `@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)`,
   `@user_story(...)`, `_create_workspace_for_harness`, branch on
   `harness.workspace_harness` for the two assertions.
2. Assert the pi side via the Task-1.3 ElementIDs: the disabled control
   is VISIBLE, carries the standardized tooltip copy (hover or
   accessible-content assertion per the Radix Tooltip pattern used in
   the component), and is non-interactive (clicking produces no effect —
   e.g. plan-mode state does not change).
3. Assert the Claude side renders the enabled affordance (the meaningful
   baseline — per the file's docstring philosophy).
4. Where fake_pi needs no new directives (all these are static-UI
   states), don't add any — capability tranches grow fake_pi later. The
   `/clear` refusal test must not depend on backend behavior: the refusal
   is frontend-side (Task 1.3's `executePseudoSkill` guard).
5. Keep tests independent and parallel-safe (fresh workspace per test via
   the existing helper; unique workspace names).

## Testing suggestions

- These ARE the tests. Run scoped first
  (`sculptor/tests/integration/frontend/test_pi_capability_gating.py`)
  via the repo's integration-test skill/runner (`/test-integration`
  governs how integration tests must be launched), then the sibling pi
  files: `test_pi_basic.py`, `test_minimum_interface_conformance.py`,
  `test_workspace_harness_picker.py`.

## Gotchas

- Tooltip assertions against Radix: content renders in a portal on
  hover/focus — assert via the pattern the component uses (Task 1.3
  followed `TooltipIconButton`); avoid brittle raw-DOM traversal.
- `?? true` load-race: assertions must wait for the task to be loaded
  (the existing helpers' ready-waits do this) — asserting too early can
  see the optimistic enabled state and flake.
- Don't reach for `data-testid` strings inline — always the generated
  `ElementIDs` enum (that's the testability contract REQ-BASE-5 pins).
- The pi side has NO model picker entry (`model_name=None` — see
  `_create_workspace_for_harness`'s docstring); don't assert
  model-dependent chrome for pi.
- Integration tests must run as background processes with a watchdog per
  the repo's `/test-integration` skill — don't run pytest directly.

## Verification checklist

- [ ] Every interactive gated surface from Task 1.3's list has a
      two-sided test (pi: disabled+tooltip+ElementID; Claude: enabled).
- [ ] Status-only chrome (compaction pill, token-popover row) asserted
      absent for pi.
- [ ] `/clear` execution refusal covered (no endpoint call from a pi
      workspace).
- [ ] All tests parallel-safe and deterministic (fake_pi/FakeClaude only,
      no real model calls).
- [ ] Integration tests: the extended
      `tests/integration/frontend/test_pi_capability_gating.py` plus
      `test_pi_basic.py`, `test_minimum_interface_conformance.py`,
      `test_workspace_harness_picker.py` — all green.
