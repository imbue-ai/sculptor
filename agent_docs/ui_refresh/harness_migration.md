# Test-harness migration — workspace UI refresh

The page-object, ElementID, fixture, and terminology changes the redesign forces
on the integration-test harness. `e2e_test_plan.md` references this doc for the
"how" of every UPDATE/REWRITE/RENAME row; `user_stories.md` defines the story IDs.

The harness lives in `sculptor/sculptor/testing/` — `pages/` (layout shells),
`elements/` (component POMs), plus fixtures in `resources.py` /
`tests/integration/frontend/conftest.py`. Test IDs are the `ElementIDs` `StrEnum`
in `sculptor/sculptor/constants.py` (559 entries today). **Any new or changed
`ElementIDs` requires `just generate-api`** to regenerate the TypeScript types.

The redesign's structure is fixed by the companion architecture docs, and the
harness must follow them rather than re-deriving names: `state_design.md` (state
scope + the flat sub-section keyspace), `component_hierarchy.md` (the React tree
the POMs traverse), `supplemental/naming_map.md` (the canonical prototype →
rewrite vocabulary — the source of truth for the rename pass in §4), and
`supplemental/panel_registry.md` (the exact panel ids the selectors target).

---

## 1. Page objects

Section/panel selectors are keyed by the **flat sub-section keyspace** from
`state_design.md`: a section id is `left | center | right | bottom`; an unsplit
section's only sub-section *is* the section id; a split's secondary half suffixes
it (`left:secondary`, `center:secondary`). New section/panel POM getters should
take a `SubSectionId` so the primary and secondary halves run through the same
methods. Panel POMs target the registry ids from `supplemental/panel_registry.md`
(`files`, `changes`, `commits`, `review-all`, `actions`, `skills`, `browser`,
`notes`, `agent:<taskId>`, `terminal:<wsId>:<n>`).

### Rewrite — the layout spine

- **`pages/project_layout.py`** (`PlaywrightProjectLayoutPage`, base of every
  workspace page; used by 22 tests directly and transitively by ~all).
  Today it is built entirely on the top-bar + tab model: `get_topbar()`,
  `get_home_tab()`/`close_home_tab()`, `get_settings_tab()`/`open_settings_tab()`,
  `get_workspace_tabs()`/`close_workspace_tab()`/`delete_workspace_via_context_menu()`,
  `get_add_workspace_button()`/`get_add_workspace_tabs()`, `get_bottom_bar()`,
  `get_component_gallery_tab()`, plus tab context-menu getters.
  **Replace** the tab API with sidebar + section API:
  - sidebar: home link, Cmd+K link, new-workspace button, repo groups
    (collapse, add-workspace, repo-settings), workspace rows (click / hover
    delete+menu / right-click context menu), Settings link, report-bug, version,
    collapse-toggle, resize handle.
  - sections: get a section (left/center/right/bottom), its header, panel tabs,
    add-panel `+`, maximize/restore, collapse/expand, resize border, active-ring.
  - Keep the cross-cutting bits that survive: `press_keyboard_shortcut`,
    command palette, warning banner, dialogs (git-init, add-repo, project-path),
    keyboard-shortcuts dialog. The command palette's **open** path moves from the
    topbar button to the sidebar (`open_command_palette`).

- **`pages/task_page.py`** (`PlaywrightTaskPage`; 48 tests). Re-home its
  composition: `get_workspace_banner()` → workspace **header**;
  `get_agent_tab_bar()` → section panel-tab POM; and split the
  `file_browser` / `changes_panel` / `history_panel` / `diff_panel` bundle into
  three independent panel POMs, each owning its embedded viewer. PR button +
  diff-summary getters move with the header.

### Refactor — Files / Changes / Commits panels + a shared viewer

The three panels embed the same explorer shape, so the POMs are factored to
avoid triplication (the four `test_*` files in `e2e_test_plan.md` §1 consume
these):
- `elements/files_panel.py` — refactor of `file_browser.py`; **drop** the
  `get_tab_all/changes/history` tab getters (tabs → separate panels).
- `elements/changes_panel.py` — keep; it already models the scope picker +
  changes tree + discard dialog. Re-anchor to its own embedded viewer.
- `elements/commits_panel.py` — rename of `history_panel.py` (terminus, merge
  spur, commit metadata, popover, per-commit file rows).
- **`elements/diff_viewer.py`** — refactor of `diff_panel.py` into an embeddable,
  per-panel viewer. The toggle getters that today read toolbar icons
  (`get_split_view_toggle`, `get_line_wrap_toggle`, `get_render_toggle`,
  `get_find_in_file_button`) re-anchor **under the triple-dot menu**
  (`DIFF_FILE_HEADER_MENU_TRIGGER`) per FCC-07; `get_expand_toggle` is **deleted**
  (fullscreen-expand deprecated).
- **`elements/explorer_layout.py`** — new shared POM for the resizable list +
  shared-width sidebar + toggle + empty state, plus helper functions
  (`open_file_in_panel`, `toggle_view_option_via_menu`, `assert_diff_shows`).

### Replace — zone/docking POM → section POM

- **`elements/panel_zones.py`** (`PlaywrightPanelZonesElement`; 5 tests).
  Entirely zone-based (`PANEL_TOP_RIGHT`/`PANEL_BOTTOM_RIGHT`/`PANEL_RIGHT_AREA`,
  `SIDE_TOGGLE_*`, `FOCUS_MODE_BUTTON`, `move_panel_to_zone()` via "Move to" →
  zone option). **Delete** and replace with the new section POMs below.

- **`elements/panels.py`** helper module (7 tests): `close_bottom_panel`,
  `ensure_right_area_visible`, `ensure_terminal_visible` are written against
  `SIDE_TOGGLE_BOTTOM` / `PANEL_RIGHT_AREA` / `ADD_TERMINAL_BUTTON`. **Rewrite**
  as section collapse/expand helpers (`ensure_section_expanded(side)`,
  `collapse_section(side)`).

### New POMs

- `elements/workspace_sidebar.py` — the sidebar (SIDE-*). **Mirror the existing
  `pages/home_page.py::PlaywrightHomePage.get_workspace_rows()`** (`WORKSPACE_ROW`,
  `WORKSPACE_ROW_BRANCH`, `WORKSPACE_ROW_CONTEXT_MENU_DELETE` already exist) rather
  than inventing a new row model — the sidebar rows are the successor to home-page
  rows. Also relocate the shared nav helpers (`navigate_to_workspace`,
  `open_settings`, `open_home`, `open_command_palette`) here so the ~18
  route-to-feature tests swap one helper call.
- `elements/workspace_section.py` — a single section: header, panel tabs, add-`+`,
  maximize/restore, collapse/expand, resize, active-ring, empty state. *(Name
  avoids colliding with the unrelated logging util `testing/section.py`.)*
- `elements/section_split.py` — split creation (right-click "Create {direction}
  split and move panel"), sub-section access, close-split.
- `elements/add_panel_dropdown.py` — the section `+` dropdown + agent-type
  sub-menu + Cmd+K "Add panel" flow (PANEL-01..06, PANEL-12). Reuse the row
  styling but render as a **dropdown**, not the cmd+k overlay.
- `elements/panel_empty_state.py` — empty-section launcher + ≤5 quick actions.
- `elements/new_workspace_dialog.py` — the modal form (WSC-*), replacing
  `pages/add_workspace_page.py`.
- `elements/empty_first_run.py` — the no-workspaces special page/inline form
  (FIRST-*).

### Refactor — agent + terminal tab bars → one shared panel-tab POM

Agents and terminals become panel tabs created from the **same** section `+`
dropdown, so `agent_tab.py` and the tab half of `terminal.py` collapse into **two
shared POMs** (the agent/terminal analog of FCC's shared `DiffViewer`/`ExplorerLayout`):

- **`PanelTab`** (on `workspace_section.py`, or `elements/panel_tab.py`) — the tab
  affordances pulled out of **both** `agent_tab.py` and `terminal.py`:
  rename/delete/close, diagnostics submenu, copy-id/name, mark-unread, double-click
  rename, the `data-dot-status` reader. The close = delete/close-confirmation flow
  (`delete_agent_via_close_button`) is preserved.
- **`AddPanelDropdown`** (`elements/add_panel_dropdown.py`, **shared with Sections & panel layout**)
  — the add affordances from `agent_tab.py`
  (`get_add_agent_button`/`get_add_agent_chevron_button`/`get_agent_type_menu*`,
  with the Radix-teardown retry) and `terminal.py` (`get_add_terminal_button`).
- **The `terminal.py` content half stays put** — all xterm-buffer helpers
  (`run_command_in_active_terminal`, `wait_for_xterm_substring`, …) are CONTENT and
  untouched; only the tab/add getters leave. Rewrite `ensure_terminal_panel_open` /
  `open_terminal_and_wait` (today keyed off `zoneVisibilityAtom`/`PANEL_ICON_TERMINAL`)
  → `create_terminal_panel` + section-expand.
- **Shared `TAB_CONTEXT_MENU_*` ids (Sidebar ↔ Agent/terminal coordination):** these
  ids are consumed today by workspace tabs (`project_layout.py`), agent tabs
  (`agent_tab.py`), **and** terminal tabs (`terminal.py`). The redesign splits the
  menu into a **workspace-row** menu (Sidebar & navigation) and a **panel-tab** menu
  (Agent & terminal panels) — coordinate so the two areas don't independently
  rename/remove the same ids. `AGENT_TAB`/`TERMINAL_TAB` → unified `PANEL_TAB`.

### Delete

- `elements/zen_mode.py` — Zen/Focus modes removed (2 importers; one is the
  incidental `test_alpha_chat_tool_density.py`, repointed to a section helper).
- `elements/btw_popup.py` — `/btw` removed (1 importer).
- `elements/settings_panels.py` — Panels settings page removed.

### Adjust

- **`elements/workspace_peek.py`** — peek moves from hovering a workspace **tab**
  to hovering a sidebar **row**; popover content preserved.
- **`pages/add_workspace_page.py`** (`PlaywrightAddWorkspacePage`, the `/ws/new`
  route; 20 importers) — **delete**; its form helpers (`get_task_input`,
  `get_workspace_name_input`, `get_branch_name_input`, `select_branch`,
  `get_submit_button`, repo selector) move into `new_workspace_dialog.py`. The
  load-bearing piece is the shared **`create_workspace(...)`** helper — a refactor
  of `playwright_utils.start_task_and_wait_for_ready` (**~177 importers**). **Keep
  its signature** and rewrite only the internals (navigate-to-page +
  `START_TASK_BUTTON` → open-dialog + Create) so the ~17 "create-to-reach-a-feature"
  tests swap **zero** call sites. Also rename `navigate_to_add_workspace_page`
  (19 importers) → `open_new_workspace_dialog`.

---

## 2. ElementIDs (`sculptor/sculptor/constants.py`)

Run `just generate-api` after editing. Section/panel ids should be parameterized
by the flat sub-section keyspace (above) rather than hard-coding `*_SECONDARY`;
panel-tab and panel-content ids should derive from the `panel_registry.md` ids.
The Actions/Skills/Browser/Notes panels survive as **registered panels** (not zone
sidebar-icons), so their content testids stay but their `PANEL_ICON_*` host ids
are removed; there are **no** panel enable/disable ids (the machinery is deleted —
`naming_map.md` → "Deleted").

### Remove (surface gone)
`TOP_BAR`, `BOTTOM_BAR`, `HOME_TAB`, `SETTINGS_TAB`, `WORKSPACE_TAB`,
`ADD_WORKSPACE_TAB`, `ADD_WORKSPACE_BUTTON`, `ADD_WORKSPACE_EMPTY_STATE`,
`COMPONENT_GALLERY_TAB` (Component Gallery removed), `AGENT_TAB` (→ panel-tab),
`ADD_AGENT_BUTTON`/`ADD_AGENT_CHEVRON_BUTTON` (→ add-panel dropdown),
`PANEL_TOP_RIGHT`, `PANEL_BOTTOM_RIGHT`, `PANEL_RIGHT_AREA`,
`PANEL_RIGHT_RESIZE_HANDLE`, `SIDE_TOGGLE_LEFT`/`SIDE_TOGGLE_RIGHT`/`SIDE_TOGGLE_BOTTOM`,
`EXIT_ZEN_MODE_BUTTON`, `FOCUS_MODE_BUTTON`, `BTW_POPUP*` (all 6),
`SETTINGS_PANELS_*` + `SETTINGS_NAV_PANELS`, `PANEL_CONTEXT_MENU_MOVE_TO`,
`PANEL_CONTEXT_MENU_ZONE_OPTION`, `PANEL_CONTEXT_MENU_CONFIGURE`,
`FILE_BROWSER_TAB_ALL`/`FILE_BROWSER_TAB_CHANGES`/`FILE_BROWSER_TAB_HISTORY`
(tabs → separate panels), `PANEL_ICON_*` (the zone sidebar-icon set).

The **TanStack devtools panel is kept** (no one relies on the Component Gallery, but
the devtools panel stays) — leave its ids and `test_tanstack_devtools_panel.py` in
place.

### Add (new surfaces)
- Sidebar: `WORKSPACE_SIDEBAR`, `SIDEBAR_HOME_LINK`, `SIDEBAR_CMDK_LINK`,
  `SIDEBAR_NEW_WORKSPACE_BUTTON`, `SIDEBAR_REPO_GROUP`, `SIDEBAR_REPO_ADD_WORKSPACE`,
  `SIDEBAR_REPO_SETTINGS`, `SIDEBAR_WORKSPACE_ROW`, `SIDEBAR_WORKSPACE_ROW_DELETE`,
  `SIDEBAR_WORKSPACE_ROW_MENU`, `SIDEBAR_SETTINGS_LINK`, `SIDEBAR_REPORT_BUG`,
  `SIDEBAR_VERSION`, `SIDEBAR_COLLAPSE_TOGGLE`, `SIDEBAR_RESIZE_HANDLE`,
  `SIDEBAR_EXPAND_ICON`.
- Sections: `SECTION_LEFT`/`CENTER`/`RIGHT`/`BOTTOM`, `SECTION_HEADER`,
  `SECTION_ADD_PANEL_BUTTON`, `SECTION_MAXIMIZE_BUTTON`, `SECTION_RESIZE_HANDLE`,
  `SECTION_ACTIVE_RING`, `PANEL_TAB`, `PANEL_TAB_CLOSE`, `SECTION_EMPTY_STATE`,
  `SECTION_EMPTY_QUICK_ACTION`, `SECTION_SPLIT_SUBSECTION`, `SPLIT_CREATE_OPTION`,
  `SPLIT_CLOSE_OPTION`.
- Add-panel dropdown: `ADD_PANEL_DROPDOWN`, `ADD_PANEL_NEW_AGENT`,
  `ADD_PANEL_AGENT_TYPE_SUBMENU`, `ADD_PANEL_NEW_TERMINAL`, `ADD_PANEL_PANEL_OPTION`.
- New-workspace dialog / first-run: `NEW_WORKSPACE_DIALOG`,
  `NEW_WORKSPACE_FORM`, `EMPTY_FIRST_RUN_PAGE`, `SIDEBAR_ADD_REPO_BUTTON`,
  `SIDEBAR_NO_WORKSPACES_HINT`. (Reuse existing form ids — `TASK_INPUT`,
  `WORKSPACE_NAME_INPUT`, `BRANCH_NAME_INPUT`, `BRANCH_SELECTOR` — inside the
  dialog where possible.)

Names are indicative; match the redesign code's actual `data-testid`s when the
components are built.

---

## 3. Fixtures & FakeClaude

- **FakeClaude:** no new commands required — the redesign does not change agent or
  terminal semantics, so the existing `text`/`write_file`/`bash`/`multi_step`/
  `parallel_tools`/`ask_user_question`/etc. cover the new tests. AGENT-05 (two
  agents streaming at once) needs **new test scaffolding** — a helper to create two
  agents in two sections (center + right) and drive both concurrently — but **not**
  a new FakeClaude verb.
- **Default-layout assumption:** the shared `sculptor_instance_` fixture and any
  helper that assumes the old layout must move to the new default (center agent
  expanded; left/bottom/right collapsed with their seed panels — SEC-01..04).
  Audit setup helpers in `resources.py` for hard-coded "terminal visible" /
  "right area" assumptions.
- **Zero-agent workspaces:** AGENT-02 relaxes today's "≥1 agent" requirement.
  Fixtures/flows that assume a workspace always has an agent (and the
  default-response path that auto-creates one) need a zero-agent variant so the
  center empty-state can be exercised.
- **Restart fixture:** persistence tests (PERSIST-03) use the existing
  `sculptor_instance_factory_` multi-instance fixture; no change beyond the new
  layout assertions.
- **Persistence adapter:** `state_design.md` consolidates layout into one
  `WorkspaceLayoutState` / `GlobalLayoutState` snapshot behind a
  `LayoutPersistenceAdapter` (localStorage today). This gives a cheaper test
  surface than full e2e for the per-workspace-vs-global split (PERSIST-01/02) and
  the "old keys ignored, no migration" rule — exercise the adapter directly where
  a full restart isn't needed.
- **Open-a-panel helper:** a shared helper that opens a panel the way a user does —
  clicking the section `+` add-panel dropdown (reusing the `AddPanelDropdown` POM) — so
  content tests can bring their panel on screen before asserting, instead of each test
  re-implementing the open flow. Files/Changes/Commits and agent/terminal panels all
  open this way; no layout-state/localStorage seeding.

---

## 3b. Drag-and-drop testability

Pointer-based DnD is not reliably driveable by Playwright as the panel DnD
provider is built today: it uses a dnd-kit **`PointerSensor`** (5px activation, no
`KeyboardSensor`), and Playwright's `drag_to()` / `mouse.*` dispatch MouseEvents
that don't faithfully drive dnd-kit's PointerEvent + `requestAnimationFrame`
collision pipeline.

**Decided: add a `KeyboardSensor` + drag handle to the panel DnD provider.** It is
also an accessibility win, and it lets Playwright drive the *real* sensor pipeline
(`Space` → arrow keys → `Space`) rather than synthesizing pointer drags. Wrap it in
a `drag_panel_to_section()` helper so test bodies stay affordance-agnostic. This
unblocks `test_panel_drag_and_drop.py` and stories PANEL-08, PANEL-09, PANEL-10,
PANEL-16.

---

## 4. Terminology rename pass

Project decision: realign the suite's vocabulary even where behavior is
unchanged. Apply to **file names, test-function names, `@user_story` strings,
and POM method names**.

The canonical prototype → rewrite map (atoms, types, vocabulary) is
`supplemental/naming_map.md`. The table below is the test-facing subset and must
stay consistent with it; when in doubt, `naming_map.md` wins.

| Old vocab | New vocab |
|---|---|
| zone / docking / top-right / bottom-right | section / sub-section |
| zen mode / focus mode | (removed) |
| `/btw` | (removed) |
| side toggle / bottom bar toggle | section collapse / expand |
| agent tab / file-browser tab / diff tab | panel / panel tab |
| add workspace page / `/ws/new` | new workspace dialog |
| top bar | sidebar / workspace header |
| focus (the active surface) | active section |

The per-diff "expand"/fullscreen toggle is **deprecated, not renamed** — there is
no diff-specific fullscreen in the rewrite; section maximize (SEC-13/15) is the
generic replacement, and the `DIFF_EXPAND_TOGGLE` testid + `expandedPanelIdAtom`
are deleted. Do not add an `expand → maximize` POM alias.

**Starting worklist** — files whose name or `@user_story` text carry old vocab
(grep-derived; subset already handled by plan §2–§4 inherit the rename there):
`test_zen_mode`, `test_btw`, `test_panel_zones`, `test_side_toggle`,
`test_panels_settings`, `test_add_workspace_page`, `test_add_workspace_agent_type`,
`test_alpha_chat_tool_density` (zen ref), `test_command_palette` (topbar ref),
`test_workspace_tab_enhancements`, `test_workspace_close_vs_delete`,
`test_workspace_peek`, `test_closed_workspaces_dropdown`, `test_home_page_tab`,
`test_settings_tab`, `test_component_gallery_tab`, `test_expand_escape`,
`test_diff_tab_close_others`, `test_tab_context_menus`, `test_terminal_tab_enhancements`,
plus the `@user_story` strings in the FCC/agent tests that say "tab" meaning a
panel tab. Re-grep before each edit — other in-flight branches move these files.

> The `git mv` + rename is mechanical but touches many files; do it as its own
> commit, separate from behavioral rewrites, so review can verify "rename only".

---

## 5. Perf tooling (not e2e)

`goals.md`'s non-functional acceptance bars are **not** Playwright tests:

- **SWITCH-01** (zero layout-shift on switch) and **SEC-18 / PERSIST-02**
  (global sizes present in the first committed frame) → the **workspace-switch
  profiler** (`sculptor/frontend/src/common/perf/workspaceSwitchProfiler.ts`,
  `ws-switch.*` perf marks). It already exists on the SCU-1474 prototype and is
  carried forward into the rewrite — not net-new.
- **SWITCH-02** (≤1 mount per panel per switch) and **SWITCH-05** (memoized
  re-renders during drag/resize) → the existing **`measure-react-renders`**
  skill (compares render counts between `origin/main` and the branch for a
  user-defined scenario). Define scenarios: "switch between two workspaces",
  "drag a panel between sections", "resize the left section".

Recommendation: keep these out of the pytest suite; track them as a perf
checklist run via the skill and the profiler at integration time.

---

> **Per-area detail.** The full coverage audits, per-file dispositions, shared-POM
> designs, and ElementID lists for the four areas live in
> `supplemental/test_area_audits/` (`workspace_creation.md`, `sidebar_nav.md`, `agent_terminal_panels.md`, `sections_panel_layout.md`).
> This doc carries the integrated, cross-area view.
