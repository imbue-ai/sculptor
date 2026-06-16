# Compact workspace layout — integration-test migration (follow-up)

The uniform-panels / compact-workspace-layout redesign deleted the agent tab
bar (`AgentTabs.tsx`) and moved agent + terminal **creation** into the
`AddPanelPalette` (the cmd+k "Add panel" launcher), opened from a section's
`+`. Agent **tabs** now render inside `SectionTabBar` instead of the old
dedicated strip.

These UI changes were made **without updating the frontend integration tests**
— intentionally, while the layout was still in flux. As a result the Playwright
page object `sculptor/sculptor/testing/elements/agent_tab.py` and the ~33 test
files that drive it target testids/elements that **no longer render**. This was
already true on this branch *before* the `origin/main` merge; the merge then
added more terminal-agent tests from main that target the old dropdown.

This doc records all the follow-up work to bring the integration tests back in
line with the new UI. It is a work list, not a description of shipped behavior.

> Run integration tests via the `run-integration-test` skill (background process
> + Monitor watchdog), **never** `pytest` directly. See `write-integration-test`
> for FakeClaude usage. Re-grep before editing — other in-flight branches move
> these files.

---

## 1. What changed in the UI (the new target surfaces)

### Creation moved into the palette
- The old `AgentTabs` split button (`+ New agent ▾`) is gone. The plain `+`
  created the last-used agent type; the chevron opened an agent-type dropdown
  (Claude / pi / Terminal / registered CLIs).
- Creation now lives in `AddPanelPalette` (`components/panels/AddPanelPalette.tsx`),
  opened by a section's `+` button (`SectionTabBar.tsx`). The palette has:
  - a root **"New {recently-used} agent"** row (dynamic label) — `Enter`/click
    creates the recently-used type in one keystroke;
  - a trailing chevron + `→` (ArrowRight) that drill into a **"Choose agent"**
    sub-page;
  - a separate **"New terminal"** row that creates a raw shell *panel*
    (`addTerminalAtom`), not an agent.

### The "Choose agent" sub-page (this feature)
Lists, recently-used first (tagged with a "Recently used" pill):
- **Claude** (`AGENT_TYPE_MENU_ITEM_CLAUDE`)
- **pi** (`AGENT_TYPE_MENU_ITEM_PI`) — only when pi-agent is enabled
- each **registered** terminal agent by its display name
  (`AGENT_TYPE_MENU_ITEM_REGISTERED`, with `data-registration-id`), e.g. the
  bundled Claude Code CLI registration (`claude-code`, display name "Claude CLI").

### Decisions baked into this redesign (confirmed with the product owner)
- User-facing word is **"agent"** (picker titled **"Choose agent"**), not
  "harness".
- The **bare `terminal` agent type is intentionally NOT offered** in the picker.
  A raw shell is the root **"New terminal"** panel; "Claude Code CLI" is the
  **registered** `claude-code` agent. So `AGENT_TYPE_MENU_ITEM_TERMINAL` is no
  longer rendered and any test that created a bare "Terminal N" agent must be
  reworked to use a registered agent instead.

### Tabs moved to `SectionTabBar`
- Agent tabs render as **`panel-tab-${panelId}`** (`SectionTabBar.tsx`), not
  `ElementIds.AGENT_TAB` (which is now an unused constant, rendered nowhere).
- The tab **context menu / rename / delete / close / diagnostics** testids
  (`TAB_CONTEXT_MENU_*`, `TAB_CLOSE_BUTTON`, `INLINE_RENAME_INPUT`) **still
  exist** and are rendered by `SectionTabBar.tsx` / `SortableTabContent.tsx`.

### Stable testids for the new flow
| Element | testid |
| --- | --- |
| Section `+` (opens palette) | `panel-section-add-<side>` (e.g. `panel-section-add-center`) — confirm the exact `side` for the default agent zone |
| Palette dialog | `add-panel-palette` |
| Palette search input | `add-panel-input` |
| Palette list | `add-panel-list` |
| Destination select | `add-panel-destination` |
| Root "New … agent" row | `ElementIds.ADD_AGENT_BUTTON` |
| Root row chevron (drill-in) | `ElementIds.ADD_AGENT_CHEVRON_BUTTON` |
| "Choose agent" sub-page container | `ElementIds.AGENT_TYPE_MENU` |
| Sub-page items | `AGENT_TYPE_MENU_ITEM_CLAUDE` / `_PI` / `_REGISTERED` (+`data-registration-id`) |
| Agent tab | `panel-tab-${panelId}` |

---

## 2. Retarget the page object (`testing/elements/agent_tab.py`)

This is the keystone — most test files only need it once the page object drives
the palette. Proposed API:

- `_open_add_panel_palette()` — click `panel-section-add-<side>` for the default
  (center) agent zone, wait for `add-panel-palette` to be visible. Used by the
  creation helpers below.
- `create_agent()` — replaces the old `get_add_agent_button().click()` one-shot:
  open the palette, click the **New agent** row (`ADD_AGENT_BUTTON`). Creates the
  recently-used type and the palette closes.
- `open_agent_type_menu()` — open the palette, click the chevron
  (`ADD_AGENT_CHEVRON_BUTTON`) (or press `→`) to drill into "Choose agent",
  return the `AGENT_TYPE_MENU` locator. Keep the existing retry-on-teardown loop.
- `create_agent_of_type(...)` — convenience: `open_agent_type_menu()` then click
  `get_agent_type_menu_item_claude/pi/registered(...)`.
- `get_agent_tabs()` / `get_agent_tab_by_name(...)` — retarget from `AGENT_TAB`
  to `panel-tab-*` (filter agent panels; exclude terminal/static panels).
- Drop / deprecate `get_agent_type_menu_item_terminal()` — no longer rendered.
- Tab context-menu / rename / delete / diagnostics helpers — verify they still
  resolve against `SectionTabBar` / `SortableTabContent` (testids unchanged);
  fix selectors only if the DOM nesting changed.

Note the behavioral shift for assertions: the old `get_add_agent_button()`
returned an always-visible locator (usable with `expect(...)` and repeated
`.click()`); the new create surface only exists while the palette is open.
Convert call sites to the `create_agent()` action method.

---

## 3. Test-file work

### A. Creation-only call sites — swap `get_add_agent_button().click()` → `create_agent()`
These create an agent as setup and don't care about type. Mechanical once the
page object is retargeted (watch for the `add_agent_button = ...` + repeated
`.click()` pattern — replace each click with a fresh `create_agent()`):

- `integration/frontend/test_add_workspace_agent_type.py` (line ~100 only; the
  rest uses `ADD_WORKSPACE_AGENT_TYPE_SELECT` on the new-workspace form and is
  unaffected)
- `integration/frontend/test_agent_diagnostics_context_menu.py`
- `integration/frontend/test_agent_settings.py`
- `integration/frontend/test_agent_tab_context_menu.py`
- `integration/frontend/test_alpha_scroll_behaviors.py`
- `integration/frontend/test_alpha_scroll_padding_agent_switch.py`
- `integration/frontend/test_entity_picker_workspace_drill.py`
- `integration/frontend/test_fast_mode_persistence.py`
- `integration/frontend/test_image_upload.py`
- `integration/frontend/test_mark_unread.py`
- `integration/frontend/test_model_capability_gating.py`
- `integration/frontend/test_multi_agent_workspace.py` (5 call sites)
- `integration/frontend/test_optimistic_deletion.py`
- `integration/frontend/test_read_unread_status.py`
- `integration/frontend/test_workspace_peek.py`
- `integration/frontend/test_workspace_scoped_changes.py`
- `integration/regression/test_regression_model_selection.py`

### B. Agent-type dropdown call sites — retarget to the "Choose agent" sub-page
- `integration/frontend/test_agent_type_menu.py` — **rework**. Drop the bare
  "Terminal N" creation/MRU test (the type no longer exists). Re-express the
  "remembers last-used type" assertion using a **registered** agent (the
  `fake-reg` echo registration) or pi. Keep: pi gating, registered-agent appears
  without restart, bundled `claude-code` present. Add the new-feature coverage
  in section 4.
- `integration/frontend/test_registered_terminal_agent.py` — retarget the menu
  calls to the palette sub-page.
- `integration/frontend/test_terminal_agent_basic.py`,
  `…/test_terminal_agent_signals.py`,
  `…/test_terminal_agent_automated_prompts.py` — these created the agent under
  test via the dropped **Terminal** item. Recreate the agent via a **registered**
  terminal agent (a fake registration whose `launch_command` is an `echo`/script
  appropriate to what the test asserts). The terminal-panel / signal / automated-
  prompt behavior under test is unchanged; only the creation path moves.
- `integration/real_claude/test_claude_code_terminal_agent.py` — retarget to the
  palette sub-page; the registered `claude-code` row launches the real TUI.

### C. Tab-targeting call sites — `AGENT_TAB` → `panel-tab-*`
All ~30 callers of `get_agent_tabs()` / `get_agent_tab_by_name()` flow through
the page object, so retargeting it (section 2) should fix most. Spot-check the
files that build tab locators directly:
`test_alpha_chat_intro.py`, `test_ask_user_question.py`, `test_btw.py`,
`test_command_palette.py`, `test_error_states.py`, `test_zen_mode.py`, and the
`regression/test_regression_*` restart/replay suite.

---

## 4. New coverage to ADD for the "Choose agent" feature

Once the page object is retargeted, add tests for behavior introduced by this
feature:

- Root row label is **dynamic**: "New Claude agent" by default; after creating a
  pi/registered agent it becomes "New {that} agent".
- `Enter` on the root row creates the recently-used type in **one keystroke**.
- `→` (ArrowRight) **and** the trailing chevron both drill into "Choose agent".
- The recently-used option is **ordered first** and shows the "Recently used"
  pill.
- **pi gating**: the pi row is absent when pi-agent is disabled, present when
  enabled.
- Registered agents are listed by display name; the bundled **Claude CLI**
  (`claude-code`) appears out of the box.
- The bare **Terminal** agent type is **absent** from the sub-page; the root
  **"New terminal"** row still creates a shell panel.
- A registered agent whose registration was deleted out from under the stored
  default falls back to creating Claude (the `createAgent` retry path).

---

## 5. Manual QA (not yet done)

The cmd+k interactions in this feature are **not yet runtime-verified**:
- the trailing-chevron `IconButton` click uses `stopPropagation` to avoid
  triggering the row's create-on-select inside the cmdk `Command.Item`;
- the `ArrowRight` drill-in reads the active row via `[cmdk-item][data-selected]`.

Run the `auto-qa-changes` skill to confirm: open the palette, see the dynamic
"New … agent" row, drill in via both `→` and the chevron, confirm Claude / pi /
registered rows + the "Recently used" pill, and that selecting each creates the
right agent and focuses it in the section.

---

## 6. Suggested sequencing

1. Retarget `agent_tab.py` (section 2) — unblocks everything.
2. Run one representative file (e.g. `test_multi_agent_workspace.py`) via the
   `run-integration-test` skill to validate the page object end-to-end.
3. Sweep group A (mechanical), then groups B and C.
4. Add the new feature coverage (section 4).
5. Manual QA (section 5).
