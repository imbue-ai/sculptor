# Task 3.7: PanelTab + AddPanelDropdown POMs + agent/terminal panel tests

## Goal

Build the shared `PanelTab` and `AddPanelDropdown` POMs (the agent/terminal analog
of FCC's shared viewer POMs) and the agent/terminal panel test files, consolidating
today's agent-tab and terminal-tab tests onto the panel-tab model.

## Stories addressed

AGENT-01..09 (agent panel: chat preserved, zero/one/multiple, center+right at once,
close=delete-confirm + empty center, concurrent streaming, diagnostics, status dot,
optimistic delete, numbering), TERM-01..05 (terminal panel + close-confirm +
numbering + kill-shell + terminal-agents), PANEL-01..07/11/12/14/15 (dropdown +
rename/close/context-menu, shared with Sections).

## Background

**Project:** Sculptor integration tests (Playwright + pytest) in
`sculptor/tests/integration/frontend/`; harness in `sculptor/sculptor/testing/`.
Run via **`/run-integration-test`**; write via **`/write-integration-test`**
(FakeClaude); `just generate-api` after `ElementIDs` changes.

**The structural insight** (`agent_terminal_panels.md`): agents and terminals become
panel tabs created from the **same** section `+` dropdown, so `agent_tab.py` and the
tab half of `terminal.py` collapse into two shared POMs. The live suite already
shares the tab-affordance ids (`TAB_CONTEXT_MENU_*`, `TAB_CLOSE_BUTTON`,
`INLINE_RENAME_INPUT`, `DELETE_CONFIRMATION_*`) across both surfaces — only the
**host testid** moves `AGENT_TAB`/`TERMINAL_TAB` → `PANEL_TAB`. Separate the
**CONTENT** (xterm I/O, chat streaming — KEEP, re-reached via the panel) from the
**TAB-MODEL** (create/switch/rename/close/mark-unread/numbering/optimistic-delete —
on the panel tab).

**POMs to build** (`harness_migration.md` §1; `agent_terminal_panels.md` §3):
- **`PanelTab`** (on `workspace_section.py` or `elements/panel_tab.py`) — tab
  affordances from both `agent_tab.py` and `terminal.py`: rename/close (close →
  delete/close confirmation), diagnostics submenu, copy-id/name, mark-unread,
  double-click rename, the `data-dot-status` reader. Preserve
  `delete_agent_via_close_button` (as `delete_panel_via_close_button`).
- **`AddPanelDropdown`** (`elements/add_panel_dropdown.py`, **shared with
  Sections**) — add affordances from `agent_tab.py`
  (`get_add_agent_button`/chevron/agent-type menu, with the Radix-teardown retry) +
  `terminal.py` (`get_add_terminal_button`).

**Helpers:** `create_agent_panel(page, section="center", agent_type=...)`,
`create_terminal_panel(page, section="bottom")`, `delete_panel_via_close_button` /
`close_panel_via_context_menu`, `expect_panel_tab_dot(tab, status)`. The xterm
content helpers **stay** in `terminal.py` (only tab/add getters leave).

**Test files to CREATE** (`e2e_test_plan.md` §1; `agent_terminal_panels.md` §2):
- `test_agent_panel.py` (AGENT-01..04, PANEL-11) — absorbs much of
  `test_multi_agent_workspace.py`.
- `test_agent_concurrent_streaming.py` (AGENT-05) — **regression, new**; two agents
  (center + right) streaming at once.
- `test_terminal_panel.py` (TERM-01..03) — absorbs the add/switch/close/number half
  of `test_terminal.py`.
- `test_panel_tab_context_menu.py` (PANEL-07/11/14, AGENT-04/06, TERM-02) —
  consolidates `test_agent_tab_context_menu.py` + `test_agent_diagnostics_context_menu.py`
  + the rename/context halves of `test_terminal_tab_enhancements.py` /
  `test_tab_context_menus.py`.
- `test_panel_add_dropdown.py` (PANEL-01..06/12/15) — **co-owned with Sections**;
  absorbs `test_agent_type_menu.py` (agent-type sub-menu, pi gating, registered,
  bundled Claude). Asserts center-targeting (PANEL-06).
- `test_panel_optimistic_deletion.py` (AGENT-04/08) — agent half of
  `test_optimistic_deletion.py`: optimistic removal, 500→rollback+toast+Retry,
  last-agent-close → **empty center** (Decision B1).

This task depends on **Tasks 2.5 (agent panel), 3.1 (terminal panel), 3.5
(AddPanelDropdown component)** and the Phase-2 harness spine.

## Files to modify/create

- `sculptor/sculptor/testing/elements/panel_tab.py` (or extend `workspace_section.py`)
  — `PanelTab` POM.
- `sculptor/sculptor/testing/elements/add_panel_dropdown.py` — `AddPanelDropdown`
  POM (shared).
- Split `elements/agent_tab.py` (then delete) and the tab half of `elements/terminal.py`
  per `agent_terminal_panels.md` §5; keep xterm content helpers in `terminal.py`.
- The six CREATE test files above.
- `sculptor/sculptor/constants.py` — `PANEL_TAB`, `PANEL_TAB_CLOSE` (and confirm the
  `ADD_PANEL_*` ids from Task 3.5); `just generate-api`.

## Implementation details

1. Build `PanelTab` + `AddPanelDropdown` POMs reusing the salvaged method bodies +
   Radix-teardown retry from `agent_tab.py`/`terminal.py`, re-keyed to `PANEL_TAB` /
   `ADD_PANEL_*`. Keep `TAB_CONTEXT_MENU_*`/`TAB_CLOSE_BUTTON`/`INLINE_RENAME_INPUT`/
   `DELETE_CONFIRMATION_*` unchanged.
2. `test_agent_panel.py`: chat preserved; zero/one/multiple agents (AGENT-02); agent
   in center + right at once (AGENT-03); close = delete confirmation + closing the
   last agent leaves the center **empty** (AGENT-04, Decision B1); numbering reuses
   lowest after delete (AGENT-09).
3. `test_agent_concurrent_streaming.py` (AGENT-05): create two agents (center +
   right) with two streaming FakeClaude tasks; assert both dots + contents update
   independently — neither blocks/drops/overwrites the other. New scaffolding helper
   (two agents, drive both) — not a new FakeClaude verb.
4. `test_terminal_panel.py`: terminal as a panel; multiple; switch; numbering;
   **close = confirmation** (TERM-02 — new).
5. `test_panel_tab_context_menu.py`: the shared menu on agent **and** terminal tabs —
   rename (multi-instance only; single-instance can't rename), close=delete/close
   confirm, diagnostics submenu (copy session/transcript/agent-id/name, disabled
   without session — AGENT-06), mark-unread (AGENT-07), copy-id.
6. `test_panel_add_dropdown.py`: dropdown order + recent-agent pin + Cmd+Shift+T;
   agent-type sub-menu (Claude / pi gated / registered; **no bare Terminal** —
   Decision B2); New terminal; single-instance list; center-targeting (PANEL-06);
   Cmd+K add-panel (PANEL-12).
7. `test_panel_optimistic_deletion.py`: agent optimistic removal; 500 → rollback +
   toast + Retry; last-agent-close → empty center (replaces the old auto-create
   assertion).
8. Migrate the CONTENT-preserving terminal-agent files in **Task 8.2** (UPDATE
   in-place); this task owns the new panel/agent CREATE tests.

## Testing suggestions

- Run via `/run-integration-test` (background + Monitor). Use controlled FakeClaude
  for agent-type and streaming tests.
- Coordinate shared ownership with Sections (PANEL-07/11/14 also touched by Task 4.6's
  `test_panel_rename_and_close.py`) so rename/close aren't double-asserted — see
  Decision B9.

## Gotchas

- Only the **host testid** changes (`AGENT_TAB`/`TERMINAL_TAB` → `PANEL_TAB`);
  reuse the shared context-menu/close/rename/confirmation ids.
- Keep xterm content helpers in `terminal.py`; only tab/add getters move.
- Last-agent-close → **empty center** (Decision B1), not auto-create.
- No bare "Terminal" agent type (Decision B2).
- `just generate-api` after `constants.py` edits.

## Verification checklist

- [ ] `PanelTab` + `AddPanelDropdown` POMs built; `agent_tab.py` split/deleted; xterm
  content helpers kept in `terminal.py`.
- [ ] The six CREATE test files pass via `/run-integration-test`.
- [ ] AGENT-01..09 + TERM-01..03 + PANEL-01..07/11/12/14/15 covered; last-agent →
  empty center; no bare Terminal type.
- [ ] `PANEL_TAB`/`PANEL_TAB_CLOSE` added + `just generate-api`.
