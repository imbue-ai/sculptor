# Task 8.2: Migrate the agent/terminal + panel content tests (UPDATE-in-place)

## Goal

Execute the agent/terminal + registered-panel content slice of `e2e_test_plan.md`:
UPDATE-in-place the content-heavy tests (xterm I/O, terminal-agents, babysitter) to
reach panels via the new POMs, REWRITE the Browser panel (enable model removed), and
confirm the large content-only KEEP majority rides the harness shim.

## Stories addressed

AGENT-*/TERM-* (content reach via panel tabs), PANEL-05 (Browser/Skills/Actions/Notes
as registered panels), FCC-* (any remaining content reach), plus the KEEP majority.

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`. Run
via **`/run-integration-test`**. The new panel surfaces + the shared `PanelTab`/
`AddPanelDropdown` POMs + the xterm content helpers (kept in `terminal.py`) already
exist (Phase 3); the new agent/terminal CREATE tests landed in Task 3.7 and FCC in
Tasks 3.6a–e.

**The migration** (`e2e_test_plan.md` §4a/§4e/§6; `agent_terminal_panels.md` §4):
separate **CONTENT** (xterm I/O, chat streaming, signals, PTY lifecycle — KEEP, only
the create/switch/close reach changes) from **TAB-MODEL** (handled by the Task 3.7
CREATE files). Most content tests need only the harness shim + a helper swap.

**Work items** (`agent_terminal_panels.md` §4; `e2e_test_plan.md` §4):
- **UPDATE-in-place (+rename):** `test_registered_terminal_agent.py`,
  `test_terminal_agent_basic.py`, `test_terminal_agent_external_rename.py`,
  `test_terminal_agent_signals.py`, `test_terminal_agent_automated_prompts.py`,
  `test_ci_babysitter.py`, `test_terminal_close_kills_shell.py`,
  `test_terminal.py` (CONTENT/xterm half — the add/switch/close/number TAB-MODEL half
  moved to `test_terminal_panel.py` in Task 3.7). Swap create via `create_agent_panel`/
  `create_terminal_panel`, switch via the section/panel-tab POM, signal→`data-dot-status`
  on the panel tab; keep all xterm/PTY/signal/resume assertions.
- **UPDATE (§4d — `panels.py`-helper importers):** `test_alpha_scroll_behaviors.py`,
  `test_alpha_scroll_padding_agent_switch.py`, `test_alpha_scroll_to_top.py`,
  `test_linear_plugin_runtime.py` — swap the old `panels.py` helper calls
  (`close_bottom_panel` / `ensure_*_visible`) to the new `section_helpers.py`
  (`collapse_section` / `ensure_section_expanded`, Task 4.6), and re-point
  `test_linear_plugin_runtime.py`'s plugin panel off the deleted `panel_zones` onto a
  section. (Task 4.6 keeps the old helper names as aliases, so these break softly until
  migrated here.)
- **UPDATE:** `test_skills_panel.py` (panel placement shim — content KEEP).
- **REWRITE:** `test_browser_panel.py` — the opt-in/opt-out (enable) stories reflect
  the removed enable model; rewrite those as add/close-panel; the isolation /
  in-page-state-persistence stories survive (UPDATE). Browser is a registered panel
  with no default section.
- **MINIMAL:** `test_custom_actions.py`, `test_notes_panel.py` — Actions/Notes are
  slated for deprecation; just make them appear as registered panels.
- **CREATE/finish:** `test_review_all_panel.py` (REVIEW-01/02) if not done in Task 3.4 —
  absorbs `test_review_all_visibility` + `test_workspace_scoped_changes` +
  `test_auto_collapse_combined_diff`.
- **KEEP (~120 files):** content-only tests (`test_alpha_chat_*`, `test_alpha_scroll_*`
  non-panel, `test_ask_user_question*`, `test_at_mention_*`, `test_image_*`, `test_pi_*`,
  `test_pr_*`, `test_settings_*` non-Panels, `test_sculpt_cli`, real-agent suites) ride
  the shim — they change only if a renamed POM method they transitively call breaks
  (then a trivial UPDATE) or they carry old vocab (RENAME in Task 8.3).

This task depends on **Phases 2–7** + Tasks 3.6a–e/3.7.

## Files to modify/create

- The UPDATE-in-place terminal-agent / babysitter / terminal-content files (helper +
  reach swap; content assertions unchanged).
- The §4d `panels.py`-helper importer files (`test_alpha_scroll_behaviors.py`,
  `test_alpha_scroll_padding_agent_switch.py`, `test_alpha_scroll_to_top.py`,
  `test_linear_plugin_runtime.py`) — helper swap to `section_helpers.py`; re-point the
  linear-plugin panel off `panel_zones`.
- `test_skills_panel.py` (UPDATE shim), `test_browser_panel.py` (REWRITE),
  `test_custom_actions.py` / `test_notes_panel.py` (minimal), `test_review_all_panel.py`
  (CREATE/finish).
- Remove any obsolete source files fully absorbed by Task 3.7's CREATE files.

## Implementation details

1. Do the UPDATE-in-place swaps: `create_agent_panel`/`create_terminal_panel` for
   creation, the panel-tab POM for switch/rename/close, `data-dot-status` for signals.
   **Keep every xterm/PTY/signal/resume/streaming assertion.**
2. REWRITE `test_browser_panel.py`: drop the enable/opt-in stories; rewrite as
   add/close-panel; keep isolation + in-page-state-persistence.
3. UPDATE `test_skills_panel.py` (placement shim, content KEEP); MINIMAL handling for
   Actions/Notes (appear as registered panels).
4. Finish `test_review_all_panel.py` (REVIEW-01/02) if not in Task 3.4.
5. Spot-check the KEEP majority: run a representative subset; anything red is either a
   missed shim method (fix the shim) or old vocab (defer to Task 8.3).

## Testing suggestions

- Run via `/run-integration-test` in batches by area (background + Monitor). Use
  controlled FakeClaude / real-Claude where the audits flag it (terminal-agent /
  babysitter behaviors that depend on real Claude → `/auto-qa-changes` for after-fix
  verification per `.sculptor/testing.md`).

## Gotchas

- **Content assertions are unchanged** — only the create/switch/close reach swaps.
- Browser **enable** stories are removed (REWRITE as add/close); isolation/in-page
  state survive.
- Keep xterm helpers in `terminal.py`; the TAB-MODEL half already moved to
  `test_terminal_panel.py` (Task 3.7) — don't duplicate.
- Behaviors depending on **real Claude** (agent stdin/stdout, babysitter runtime) must
  be verified against real Claude, not `fake_claude` (`.sculptor/testing.md`).

## Verification checklist

- [ ] Terminal-agent / babysitter / terminal-content tests UPDATEd (reach swapped,
  content kept) and green.
- [ ] `test_browser_panel.py` REWRITTEN (enable removed); Skills UPDATEd;
  Actions/Notes minimal; `test_review_all_panel.py` covers REVIEW-01/02.
- [ ] KEEP majority passes via the shim (spot-checked); reds triaged to shim-fix or
  Task 8.3 rename.
- [ ] Area green via `/run-integration-test`; `just check` passes.
