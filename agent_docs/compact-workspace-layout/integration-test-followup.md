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
  opened by a section's `+` button (`SectionTabBar.tsx`). The "Create" group has
  three rows:
  - **"New {recently-used} agent"** (dynamic label) — `Enter`/click creates the
    recently-used type in one keystroke (`ADD_AGENT_BUTTON`);
  - **"Choose agent type…"** — `Enter`/click/`→`/chevron drills into the
    **"Choose agent"** sub-page (`ADD_AGENT_CHEVRON_BUTTON`);
  - **"New terminal"** — creates a raw shell *panel* (`addTerminalAtom`), not an
    agent.
- The empty-section quick add (`EmptyPanelLauncher.tsx`) shows the same dynamic
  **"New {recently-used} agent"** fast-path button.

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
| "New … agent" fast-path row | `ElementIds.ADD_AGENT_BUTTON` |
| "Choose agent type…" drill-in row | `ElementIds.ADD_AGENT_CHEVRON_BUTTON` |
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

---

## 7. File-browser master-detail redesign (separate follow-up)

The Files / Changes / Commits panels were reworked (see
`agent_docs/file-browser-panel/mocks.context.md`). The integration tests in
`integration/frontend/test_file_browser.py` (and two siblings) still drive the
**old** unified `FileBrowserPanel` — the in-panel tabs and the search-toggle
flow — which no longer renders. They need migration to the new per-panel UI.

### What changed (new target surfaces)
- **No in-panel tabs.** `FILE_BROWSER_TAB_ALL/CHANGES/HISTORY` are gone. Files,
  Changes, and Commits are now **separate section panels** (zone tabs); switch
  between them via the section tab bar (`panel-tab-*`), not `get_tab_*()`.
- **The tree side is search-only.** The tree header holds just
  `FILE_BROWSER_SEARCH_INPUT` (always visible — no search-toggle or close
  button). `FILE_BROWSER_SEARCH_FILES_BTN` and `FILE_BROWSER_SEARCH_CLOSE` are no
  longer rendered (the ids/helpers are kept for now to avoid colliding with this
  migration — remove them here). Commits has no search, so its tree side has no
  header at all.
- **All other controls live in the diff header (right pane):**
  - **Refresh** (`FILE_BROWSER_REFRESH_BTN`) — on the right of the diff header.
  - **Merged "…" menu** — `FILE_BROWSER_COLLAPSE_FOLDERS_BTN` and the tree/flat
    toggle are now `DropdownMenu.Item`s inside the diff header's
    `DIFF_FILE_HEADER_MENU_TRIGGER` menu (merged with the diff view options).
    Open that menu first, then click the item.
  - **Tree toggle** — a single folder-tree button at the **left of the diff
    header** (before the breadcrumb), solid white when the tree is shown / dim
    when collapsed. Its testid is `FILE_BROWSER_HIDE_TREE_BTN` when shown and
    `DIFF_HEADER_SHOW_TREE_BTN` when collapsed.
  - These controls render in the diff header when a file is open, and in the
    empty-detail header when no file is open but the panel is wide enough to show
    the detail pane. In a **narrow** panel with no file open (full-width tree)
    they are not shown — open a file or widen the panel first.

### Page object (`testing/elements/file_browser.py`)
- Drop `get_tab_all/changes/history()` and `get_search_button()/get_search_close()`.
- `get_search_input()` stays (now always present, tree side).
- `get_collapse_button()` → open the diff header's `DIFF_FILE_HEADER_MENU_TRIGGER`
  "…" menu first, then resolve the item.
- `get_refresh_button()` → look in the diff header (needs the detail pane shown).
- Add `get_tree_toggle_button()` resolving either id by state.

### Affected tests (retarget or rework)
- Tab-switching: `test_filter_tabs_switch_between_all_and_changes`,
  `test_review_all_button_opens_combined_diff`,
  `test_review_all_shows_all_branch_files`,
  `test_switch_between_file_tab_and_review_all`,
  `test_split_view_toggle_works_for_combined_diff` (and other `get_tab_changes/
  history` call sites) → switch panels via the section tab bar.
- Search: `test_file_search`, `test_file_search_filters_visible_rows`,
  `test_file_search_escape_closes`, `test_file_search_no_matches_shows_empty_state`,
  `test_file_search_uses_exact_substring_matching`,
  `test_file_search_folders_are_collapsible` → drop the toggle/close steps; type
  into the always-visible input.
- Collapse: `test_collapse_all_folders_button`,
  `test_collapse_all_changes_folders_button`, `test_collapse_all_commits_button`
  → open the "…" menu before clicking collapse (and switch panels, not tabs).
- Refresh: `test_file_browser_symlink_replaces_directory.py`,
  `test_diff_loading_bar_no_file.py` → refresh now lives in the diff header.

### New coverage to ADD
- **Fixed-width tree on resize:** widening the panel grows only the viewer; the
  tree keeps its px width (and persists per panel).
- **Hide/show-tree toggle:** hide from the tree header → tree collapses, viewer
  fills, and the show toggle appears left of the breadcrumb; clicking it restores
  the tree.
- **Always-visible search** filtering Files and Changes.
