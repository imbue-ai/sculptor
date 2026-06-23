# Agent + terminal panel tabs

> Produced by a parallel deep-audit of the live test suite (the FCC-style exercise). Structural outcomes folded into the core docs; this file keeps the granular per-file dispositions. Grounded in the live suite, not the prototype notes. Canonical decisions are in `user_stories.md` / `goals.md`; some inline "open question / tension" notes below predate them.

Multi-instance agent and terminal panels created from the **same** section-header `+` dropdown and rendered as panel tabs. Replaces the dedicated agent tab bar (`PlaywrightAgentTabBarElement`) and the terminal tab strip (`terminal.py` tab helpers).

**Core structural insight (the FCC-analog):** the live suite already shares the tab-affordance ElementIDs across both surfaces — `TAB_CONTEXT_MENU_RENAME`, `TAB_CONTEXT_MENU_CLOSE_OTHERS`, `TAB_CLOSE_BUTTON`, `INLINE_RENAME_INPUT`, `DELETE_CONFIRMATION_*` are consumed by BOTH `agent_tab.py` and `terminal.py`. The redesign formalizes this: agents and terminals become panel tabs, so one shared **`PanelTab`** POM + one shared **`AddPanelDropdown`** POM serve both (the analog of FCC's shared `DiffViewer`/`MasterDetailPanel`). The split is FCC's: separate the **CONTENT** (xterm I/O, chat streaming, signals, PTY lifecycle — KEEP, re-reach via the panel) from the **TAB-MODEL** (creation/switching/rename/close/mark-unread/numbering/optimistic-delete — UPDATE to panel tabs).

## 1. COVERAGE AUDIT

| Existing file | Functionality | Redesign surface | Class |
|---|---|---|---|
| `test_agent_tab_context_menu.py` | Right-click agent tab → Rename / Delete (+confirm) | Panel-tab context menu | **TAB-MODEL** |
| `test_agent_diagnostics_context_menu.py` | Diagnostics submenu (copy session-id/transcript/sculptor-transcript/agent-id/name; disabled-without-session) | Panel-tab context menu (Diagnostics) | **TAB-MODEL** (reach changes; assertions identical) |
| `test_agent_type_menu.py` | Plain `+`=last-used; chevron menu → Claude/Terminal/Pi(gated)/registered; last-used persists; tab titles | Creation → `AddPanelDropdown` (`+` + agent-type sub-menu) | **TAB-MODEL** |
| `test_registered_terminal_agent.py` | Registered TOML in menu w/o restart; tab named from display_name; bundled Claude CLI present | Menu→`AddPanelDropdown`; tab-name + terminal-content otherwise unchanged | **MIXED** |
| `test_multi_agent_workspace.py` | Add 2nd agent via `+`; tab-count; per-ws isolation; survive-1-deleted; lowest-number reuse | Add via `AddPanelDropdown`; tabs→panel tabs; isolation→PERSIST/sidebar | **TAB-MODEL** |
| `test_terminal_agent_basic.py` | Terminal agent: shell round-trip, diffs refresh, PTY survives tab switch, rename/delete-like-agent | Create via dropdown; switch via panel tabs; **xterm I/O = CONTENT** | **MIXED** |
| `test_terminal_agent_external_rename.py` | External `sculpt`/PATCH rename propagates to tab label live | Tab label = panel-tab label; assertion unchanged | **TAB-MODEL** reach |
| `test_terminal_agent_signals.py` | `sculpt signal busy/waiting/idle/files-changed` → tab status dot | Status dot → panel tab (`data-dot-status`); signal mechanics = CONTENT | **MIXED** |
| `test_terminal_agent_automated_prompts.py` | Prompt routing to capable terminal agent; commit-button → PTY; opt-in gating; chat fallback | Creation via dropdown; **all I/O + commit-routing = CONTENT** | **CONTENT** |
| `test_ci_babysitter.py` | Babysitter spawns "CI Babysitter" agent tab; prompt delivery; pause; restart-reuse; drives terminal agent | Babysitter tab = panel tab; rest backend/CONTENT | **CONTENT** |
| `test_optimistic_deletion.py` (agent portion) | Agent tab disappears optimistically; 500→rollback+toast+Retry; last-agent→new agent | Close on panel tab; optimistic/rollback unchanged | **TAB-MODEL** |
| `test_mark_unread.py` (agent-tab unread) | Mark-unread context action; stays unread; adjacent tab; read-on-return; persists unfocused | Panel-tab context menu + `data-dot-status` | **TAB-MODEL** reach |
| `test_terminal.py` | xterm WS-dedup, modifier keys, multi-tab add/switch/close, DECRQM, Ctrl-D exit, CPR, numbering | Tabs→panel tabs (add/switch/close/number); **all xterm = CONTENT** | **MIXED** |
| `test_terminal_tab_enhancements.py` | Double-click rename; context Rename/Close-others; compact layout (no heading) | Rename/context → `PanelTab`; "compact/heading" is old chrome | **TAB-MODEL** (some deprecated) |
| `test_terminal_close_kills_shell.py` | Close X kills backend shell PID (not just disconnect); 2nd tab survives | Close on panel tab; **PID-kill = CONTENT** | **MIXED** |
| `test_tab_context_menus.py` | Terminal tab → "Close others" removes other tabs | `PanelTab` "close others" | **TAB-MODEL** |

## 2. CREATE FILES (split by surface)

| New file | Stories | FakeClaude | Notes |
|---|---|---|---|
| `test_agent_panel.py` | AGENT-01..04, PANEL-11 | controlled | Chat preserved; zero/one/multiple; **agent in center + right at once** (AGENT-03, new); close = delete-confirm (AGENT-04). **Absorbs** tab-count/multi-agent/survive-deleted/isolation from `test_multi_agent_workspace.py`. |
| `test_agent_concurrent_streaming.py` | AGENT-05 | controlled (**two streaming tasks**) | **Regression, NEW.** Two agents (center + right) each streaming; assert both dots + contents update independently, neither blocks/drops/overwrites. New fixture territory (§5). |
| `test_terminal_panel.py` | TERM-01, TERM-02 | default | Terminal as a panel: create via dropdown, multiple, switch, **close = confirmation** (TERM-02 — note: today terminal close has NO confirm; goals.md ADDS one). Absorbs the add/switch/close/number TAB-MODEL half of `test_terminal.py`. |
| `test_panel_tab_context_menu.py` (**NEW**) | PANEL-07, 11, 14, AGENT-04, TERM-02 | controlled | The shared panel-tab context menu on agent AND terminal tabs: rename (multi-instance only), close=delete/close-confirm, diagnostics submenu, mark-unread, copy-id. **Consolidates** `test_agent_tab_context_menu` + `test_agent_diagnostics_context_menu` + rename/context halves of `test_terminal_tab_enhancements` / `test_tab_context_menus`. Overlaps `test_panel_rename_and_close.py` (Sections). |
| `test_panel_add_dropdown.py` (co-owned w/ Sections & panel layout) | PANEL-01..06, 12, 15 | controlled (agent types) | Section `+` dropdown order: recent-agent pin + Cmd+Shift+T, **agent-type sub-menu** (Claude/Pi-gated/registered), "New terminal", single-instance list. **Absorbs** `test_agent_type_menu` (sub-menu + pi gating + registered-without-restart + bundled Claude). Center-targeting of Cmd+Shift+T / Cmd+K (PANEL-06). |
| `test_panel_optimistic_deletion.py` (**NEW — split**) | AGENT-04 (+Sidebar's ws optimistic-delete) | controlled / route-intercept | Agent-portion of `test_optimistic_deletion.py`: optimistic removal, 500→rollback+toast+Retry, last-agent→creates-new (or → empty center under AGENT-02 — decision flag, §7). Workspace-deletion portion → Sidebar. |

**Content tests that KEEP behavior but get a new reach** (NOT new files — see §4): xterm-I/O bodies of `test_terminal`, `test_terminal_agent_basic/signals/automated_prompts`, `test_terminal_close_kills_shell`, `test_ci_babysitter` keep content assertions; only create/switch/close calls swap to the shared POMs.

## 3. SHARED HELPERS / POMs

**POMs:**
- **`PanelTab`** (on `workspace_section.py` or `elements/panel_tab.py`) — tab affordances split out of `agent_tab.py` AND `terminal.py`: `get_panel_tabs(sub_section)`, `get_panel_tab_by_name`, `open_context_menu`, `get_context_menu_rename/close/delete/close_others/mark_unread_item`, `open_diagnostics_submenu` + copy-id/name/session/transcript getters, `get_tab_close_button`, `get_inline_rename_input`, `rename_tab`, `mark_tab_unread`, `dblclick_rename`, status-dot reader (`data-dot-status`). Reuses `TAB_CONTEXT_MENU_*`/`TAB_CLOSE_BUTTON`/`INLINE_RENAME_INPUT` unchanged — only the **host testid** moves `AGENT_TAB`/`TERMINAL_TAB` → `PANEL_TAB`.
- **`AddPanelDropdown`** (`elements/add_panel_dropdown.py`) — add affordances from `agent_tab.py` (`get_add_agent_button`/`chevron`/`open_agent_type_menu`/`get_agent_type_menu_item_*`) + `terminal.py` (`get_add_terminal_button`): `open(section)`, `get_new_agent_item`, `open_agent_type_submenu`, `get_agent_type_item(claude|pi|terminal)`, `get_registered_agent_item(registration_id)`, `get_new_terminal_item`, `get_panel_option(panel_id)`. Carries today's Radix-teardown retry from `open_agent_type_menu`.
- **`DeleteConfirmationDialog`** (likely already shared).

**Helpers:** `create_agent_panel(page, section="center", agent_type=...)` (replaces per-file `_create_terminal_agent`); `create_terminal_panel(page, section="bottom")` (replaces `ensure_terminal_panel_open`/`open_terminal_and_wait`'s zone-based sidebar-icon toggle); `delete_panel_via_close_button` / `close_panel_via_context_menu` (preserve today's `delete_agent_via_close_button`); `expect_panel_tab_dot(tab, status)`.

**xterm content helpers stay as-is** in `terminal.py` (`run_command_in_active_terminal`, `wait_for_xterm_substring`, `get_xterm_buffer_text`, `expect_terminal_panel_replaces_chat`, …) — only the **tab/add getters** leave.

## 4. PER-FILE DISPOSITION

| File | Disposition | Reason |
|---|---|---|
| `test_agent_tab_context_menu.py` | **MIGRATE** → `test_panel_tab_context_menu.py` | Rename/Delete/confirm on a panel tab; identical assertions. |
| `test_agent_diagnostics_context_menu.py` | **MIGRATE** → `test_panel_tab_context_menu.py` | Diagnostics submenu identical; clipboard assertions unchanged. |
| `test_agent_type_menu.py` | **MIGRATE** → `test_panel_add_dropdown.py` | Type creation → `+` dropdown sub-menu; pi/registered/bundled-Claude preserved. Flag "Terminal" tension. |
| `test_registered_terminal_agent.py` | **UPDATE-in-place** (+RENAME) | CONTENT-heavy (launch/resume/fresh-shell); swap menu→dropdown, tab-nav→sidebar; keep xterm/resume. |
| `test_multi_agent_workspace.py` | **MIGRATE/REWRITE** → `test_agent_panel.py` (+ `test_panel_add_dropdown.py`) | Tab-count/multi-agent/survive-deleted/lowest-number → panel tabs; isolation → sidebar/PERSIST. Drop 2 already-skipped tests. |
| `test_terminal_agent_basic.py` | **UPDATE-in-place** (+RENAME) | Create via helper, switch via panel tabs; xterm round-trip + diff-refresh + PTY-survives-switch = CONTENT, kept. |
| `test_terminal_agent_external_rename.py` | **UPDATE-in-place** (+RENAME) | Live rename → panel-tab label; PATCH + `to_have_text` unchanged. |
| `test_terminal_agent_signals.py` | **UPDATE-in-place** (+RENAME) | Signal→`data-dot-status` on the panel tab; signal-posting + Changes-refresh = CONTENT. |
| `test_terminal_agent_automated_prompts.py` | **UPDATE-in-place** | Pure CONTENT; only `_create_terminal_agent`/menu → helper. |
| `test_ci_babysitter.py` | **UPDATE-in-place** | Babysitter tab = panel tab; tab-nav→sidebar; glab/gh/coordinator/PTY = CONTENT/backend. |
| `test_optimistic_deletion.py` | **REWRITE/SPLIT** → `test_panel_optimistic_deletion.py` (agent) + B (workspace) | Agent optimistic-delete + rollback + Retry → panel-tab close. Workspace portion → Sidebar. |
| `test_mark_unread.py` | **UPDATE-in-place** (+RENAME) | Mark-unread + `data-dot-status` on panel tab; switches → sidebar nav. Overlap with Sidebar & navigation. |
| `test_terminal.py` | **REWRITE/SPLIT** → CONTENT stays in `test_terminal.py`; tab add/switch/close/number → `test_terminal_panel.py` | xterm tests = CONTENT, keep; 3 tab-model tests → panel tabs. Replace `open_terminal_and_wait`/`PANEL_ICON_TERMINAL` toggle with `create_terminal_panel`/section-expand. |
| `test_terminal_tab_enhancements.py` | **MIGRATE/REWRITE** → `test_panel_tab_context_menu.py` (+ DELETE compact-layout test) | Double-click rename + context → `PanelTab`. `test_terminal_compact_layout_no_heading` asserts old strip chrome (`TERMINAL_HEADING` absent) — DELETE or re-frame as section-header assertion (D/SEC). |
| `test_terminal_close_kills_shell.py` | **UPDATE-in-place** (+RENAME) | Close X kills PID = CONTENT; only the close affordance swaps to `PanelTab`. |
| `test_tab_context_menus.py` | **MIGRATE** → `test_panel_tab_context_menu.py` | "Close others" on a terminal panel tab folds in. |

## 5. HARNESS CHANGES

**`elements/agent_tab.py` (split, then delete):** add affordances → `add_panel_dropdown.py`; tab affordances → `PanelTab` on `workspace_section.py` (`get_agent_tabs`→`get_panel_tabs`, `delete_agent_via_close_button`→`delete_panel_via_close_button`, etc.).

**`elements/terminal.py` (split):** move tab/add getters out (`get_terminal_tabs`, `get_add_terminal_button`, `get_terminal_panel_icon` (delete — zone), `get_terminal_heading` (delete — old chrome), `get_tab_close_button`, `get_tab_context_menu_*`, `get_inline_rename_input`) → `PanelTab`/`AddPanelDropdown`. **Rewrite** `ensure_terminal_panel_open`/`open_terminal_and_wait` (today key off `zoneVisibilityAtom`/`PANEL_ICON_TERMINAL` — zone model) → `create_terminal_panel` + section-expand. Keep ALL xterm-buffer helpers (CONTENT).

**ElementIDs (run `just generate-api`):**
- **Remove/rename:** `AGENT_TAB`→`PANEL_TAB`, `TERMINAL_TAB`→`PANEL_TAB` (unify), `ADD_AGENT_BUTTON`/`ADD_AGENT_CHEVRON_BUTTON`→`ADD_PANEL_NEW_AGENT` + dropdown ids, `PANEL_ICON_TERMINAL` (zone icon — gone), `TERMINAL_HEADING`/`TERMINAL_STARTING_TEXT` (old strip chrome — reassess; keep `TERMINAL_STARTING_TEXT` if "Starting terminal…" survives as panel content), `AGENT_TYPE_MENU*`→`ADD_PANEL_AGENT_TYPE_SUBMENU` + items.
- **Keep (shared, now panel-tab-hosted):** all `TAB_CONTEXT_MENU_*`, `TAB_CLOSE_BUTTON`, `INLINE_RENAME_INPUT`, `DELETE_CONFIRMATION_*`, `AGENT_TERMINAL_PANEL`, `ADD_TERMINAL_BUTTON`→`ADD_PANEL_NEW_TERMINAL`. `AGENT_TYPE_MENU_ITEM_TERMINAL` survival depends on §7 picker decision.
- **Add:** `PANEL_TAB`, `PANEL_TAB_CLOSE`, `SECTION_ADD_PANEL_BUTTON`, `ADD_PANEL_DROPDOWN`, `ADD_PANEL_NEW_AGENT`, `ADD_PANEL_AGENT_TYPE_SUBMENU`, `ADD_PANEL_NEW_TERMINAL`, `ADD_PANEL_PANEL_OPTION`.

**Fixtures / FakeClaude:** No new FakeClaude commands. AGENT-05 needs scaffolding to create two agents in two sections (center + right) and drive both concurrently — net-new test helper, not a new FakeClaude verb. **Zero-agent support (AGENT-02):** today auto-creates an agent and `test_optimistic_deletion::...last_agent_creates_new_one` asserts last-delete→new agent; AGENT-02 relaxes this — needs a zero-agent fixture + a decision (last-agent-close → empty center vs auto-create). Default-layout assumption (center agent; bottom terminal collapsed-with-seed) — audit `resources.py`. Restart tests keep `sculptor_instance_factory_`; only post-restart tab-nav reach changes.

## 6. USER STORIES

**Covered:** AGENT-01..05, TERM-01/02, PANEL-01..06, PANEL-07/11/14.
**PROPOSED new IDs:**
- **AGENT-06** Agent panel-tab **diagnostics** actions (copy session-id/transcript/sculptor-transcript/agent-id/name; disabled-without-session). *(`test_agent_diagnostics_context_menu.py`.)*
- **AGENT-07** Agent panel-tab **status dot** reflects read/unread + running/waiting; **Mark unread** persists across switches when unfocused. *(`test_mark_unread.py`; overlaps B.)*
- **AGENT-08** **Optimistic agent deletion**: tab disappears instantly; 500 rolls back + error toast + Retry. *(`test_optimistic_deletion.py` agent portion; overlaps B.)*
- **AGENT-09** Agent **tab numbering** reuses lowest available number after deletion. *(`test_multi_agent_workspace`.)*
- **TERM-03** Terminal panel-tab numbering reuses lowest number after close. *(`test_terminal`.)*
- **TERM-04** Closing a terminal panel **kills the backend shell process**; siblings survive. *(`test_terminal_close_kills_shell.py`.)*
- **TERM-05** **Terminal-agent** types (plain + registered TOML) create from the agent-type sub-menu, run their program in the PTY, drive the tab dot via `sculpt signal`, support resume/fresh-shell across restart. *(The terminal-agent suite.)*

## 7. OPEN QUESTIONS / CROSS-AREA OVERLAP

- **Agent-type picker tension:** prototype dropped the bare "Terminal" type; goals.md keeps "New terminal" + agent-type sub-menu — decides `AGENT_TYPE_MENU_ITEM_TERMINAL` survival + how `test_panel_add_dropdown.py` asserts. `test_ci_babysitter::...settings_selector` is a separate Babysitter-agent settings selector (likely A/settings), independent of the creation dropdown.
- **Zero-agent / last-agent decision (AGENT-02):** `test_optimistic_deletion::...last_agent_creates_new_one` + `test_multi_agent_workspace::...deleted_when_last_agent_deleted` (already skipped) encode "≥1 agent". AGENT-02 + center empty-state relax it. Confirm: last-agent close → empty center vs auto-create new agent.
- **↔ Sidebar:** `test_optimistic_deletion.py` workspace-tab portion (localStorage, activeIndex clamp, `delete_workspace_via_context_menu`) is B, not C. `test_mark_unread.py` unread + `test_panel_rename_and_close.py` (Sections) overlap our `test_panel_tab_context_menu.py` — coordinate so rename/close/mark-unread aren't double-owned.
- **↔ Workspace creation:** first-agent type picker → Workspace creation's dialog (WSC-05); subsequent-agent picker → our `AddPanelDropdown`. Same list, two surfaces; keep assertions consistent, separately owned.
- **↔ Sections:** the `+` dropdown host, section-targeting (PANEL-06), panel-tab rendering/cycling are Sections's section machinery; our `AddPanelDropdown`+`PanelTab` are **consumed** by C, but placement/maximize/split is asserted in D. Define the POM boundary: C asserts agent/terminal-specific content; D asserts placement.
- **Deprecated terminal chrome:** `test_terminal_tab_enhancements::...compact_layout_no_heading` (old strip heading-absence) dies or re-frames as a section-header assertion (D/SEC).
