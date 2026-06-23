# Sections & panel layout — test audit (sections, splits, drag-and-drop, empty-state; net-new foundation)

> Produced by a parallel deep-audit of the live test suite (the FCC-style exercise). Structural outcomes folded into the core docs; this file keeps the granular detail. Grounded in the live suite, not the prototype notes. **This area is mostly NET-NEW (no coverage to migrate) — it is shared-harness DESIGN + a CREATE-file plan, plus the drag-and-drop testability approach.** Story proposals below have been resolved in `user_stories.md` (see §5).

## 1. COVERAGE AUDIT

**Net-new confirmed.** No section/split/empty-state/panel-DnD test file or POM exists. The only adjacent coverage is the old **zone/docking** model, deleted not migrated.

**DELETED (no behavior salvage):**
- `elements/panel_zones.py` (`PlaywrightPanelZonesElement`) — zone-keyed (`PANEL_TOP_RIGHT`/`PANEL_BOTTOM_RIGHT`/`PANEL_RIGHT_AREA`, `SIDE_TOGGLE_*`, `FOCUS_MODE_BUTTON`, `move_panel_to_zone()`). Replaced by `workspace_section.py` + `section_split.py`.
- `test_panel_zones.py` (5 tests: auto-hide, empty-zone-on-load, stale-id pruning, new-panel reconciliation, inner-split-height persistence) — assert **zone** invariants + old `sculptor-zone-*` localStorage keys, replaced by the consolidated `WorkspaceLayoutState`. Concepts re-expressed as net-new SEC/SPLIT/PERSIST; **no 1:1 migration**.
- `test_side_toggle.py` (2 tests) — bottom-bar side-toggle gone; re-expressed as collapse/expand (SEC-05..07).

**PARTIALLY SALVAGEABLE (pattern only):**
- `elements/panels.py` helpers (`close_bottom_panel`, `ensure_right_area_visible`, `ensure_terminal_visible`) — **rewrite** as `ensure_section_expanded`/`collapse_section`; keep the idempotent ensure-visible shape, not the selectors.
- `elements/agent_tab.py` — add affordances seed `AddPanelDropdown` (shared w/ Agent & terminal panels); tab affordances seed the panel-tab POM. Salvage method bodies + Radix-retry idioms, re-keyed to `PANEL_TAB`/`ADD_PANEL_*`.
- Prototype `data-testid` shape (`panel-section-${side}`, `panel-section-add-${side}`, `panel-section-maximize-${side}`) → formalize into ElementIDs.

No "share panel sizes" test exists — the deprecated setting deletes nothing here.

## 2. CREATE FILES (validated/refined)

The e2e_test_plan §1 split is sound. Refinements assign each story to exactly one **owning** file (incidental noted). All default FakeClaude unless flagged.

| File | Owns (primary) | Also touches (incidental) | FakeClaude |
|---|---|---|---|
| `test_section_default_layout.py` | SEC-01, 02, 03, 04, 09 | PANEL-15 | default |
| `test_section_collapse_expand.py` | SEC-05, 06, 07, 08, 20 | PERSIST-01 | default |
| `test_section_active_and_maximize.py` | SEC-10, 11, 12, 13, 14, 15, 16, 21, SPLIT-06 | — | default |
| `test_section_resize.py` | SEC-17 | SEC-18 (e2e "restored across workspaces" only; zero-reflow is `[perf]`) | default |
| `test_section_empty_state.py` | SEC-19, SPLIT-04, SPLIT-05 | PANEL-04, AGENT-02 (center empty) | default (one variant needs a **closed** agent/terminal to populate ≤3 recent-closed slots) |
| `test_section_splits.py` | SPLIT-01, 02, 03 | SPLIT-04/05/06, PANEL-08 | default |
| `test_panel_add_dropdown.py` (co-owned w/ Agent & terminal panels) | PANEL-01..06, 12 | PANEL-15 | controlled (agent-type sub-menu needs ≥2 types; PANEL-06 create-in-center) |
| `test_panel_drag_and_drop.py` | PANEL-08, 09, 10 | SPLIT-04 | default — **affordance-gated (§4 DnD)** |
| `test_panel_rename_and_close.py` | PANEL-07, 11, 14 | AGENT-04/TERM-02 (Agent/terminal owns the dialog) | default |

**Story-assignment notes:** SPLIT-04/05 co-owned by `splits` (structural outcome) + `empty_state` (the launcher's close-split affordance). SPLIT-06 lives in the maximize file. PANEL-08 owned by `drag_and_drop`, incidentally in `splits`. PANEL-13 (`[unit]`) out of e2e scope. PANEL-12 shares the Cmd+K surface with Agent & terminal panels.

## 3. SHARED HELPERS / POMs (the foundation the other areas reuse)

**POMs (`sculptor/sculptor/testing/elements/`):**
- **`workspace_section.py` → `PlaywrightWorkspaceSection`** *(name avoids collision with the logging util `testing/section.py`)*. The spine, constructed with a `SubSectionId` (`left|center|right|bottom|left:secondary|center:secondary`) so primary + secondary run identical code. `get_section`, `get_header`, `get_panel_tabs`, `get_panel_tab(panel_id)`, `get_active_tab`; `get_add_panel_button` (→ `AddPanelDropdown`), `get_maximize_button`, `maximize`/`restore`; `get_collapse_toggle` + collapse/expand; `get_resize_handle`, `get_active_ring`; **panel-tab sub-POM** (salvaged from `agent_tab.py`): `rename_tab`, `close_tab` (→ confirmation for agent/terminal), context-menu getters, `assert_cannot_rename(panel_id)`.
- **`section_split.py` → `PlaywrightSectionSplit`**: `create_split(panel_id, direction)`, `get_subsection(half)`, `close_split_from_empty_state(half)`, `assert_split_count`, `assert_directions_available`.
- **`panel_empty_state.py` → `PlaywrightEmptySectionState`**: `get_add_panel_button`, `get_quick_actions` (≤5), `get_quick_action(label)`, `get_close_split_button`, `assert_quick_actions([...])`.
- **`add_panel_dropdown.py` → `PlaywrightAddPanelDropdown`** *(SHARED WITH Agent & terminal panels)*: `open`, `get_new_agent_item` (+ asserts Cmd+Shift+T binding), `open_agent_type_submenu`, `get_new_terminal_item`, `get_panel_option(panel_id)`, `assert_single_instance_options([...])`. Reuses `agent_tab.py`'s agent-type method bodies + Radix-retry, as a dropdown not a cmdk overlay.
- **`workspace_sidebar.py`** *(primarily Workspace creation / Sidebar)* — Sections only consumes `get_expand_icon`/`is_collapsed` for SEC-16.

**Helper functions** (`workspace_section.py`/`section_split.py`/`section_helpers.py`): `collapse_section`, `expand_section`, `ensure_section_expanded` *(replaces `panels.py`)*; `maximize_section`, `restore_section`; `set_active_section` (click), `cycle_sections(direction)` (hotkey; steps through split sub-sections); `split_section`, `close_split`; `drag_panel_to_section(panel_id, target_subsection_id, index)` *(DnD — §4)*; `add_panel_via_dropdown`, `add_agent_via_dropdown` *(shared w/ Agent & terminal panels)*. The most-leaned-on helpers: `drag_panel_to_section`, `add_panel_via_dropdown`, panel-tab close→confirmation.

## 4. HARNESS CHANGES

**New POM modules:** the six in §3 + a thin `section_helpers.py`. **Delete** `panel_zones.py`; **rewrite** `panels.py`; **split** `agent_tab.py`.

**ElementIDs to ADD (run `just generate-api`):**
- Sections: `SECTION_LEFT/CENTER/RIGHT/BOTTOM`, `SECTION_HEADER`, `SECTION_ADD_PANEL_BUTTON`, `SECTION_MAXIMIZE_BUTTON`, `SECTION_RESIZE_HANDLE`, `SECTION_ACTIVE_RING`, `SECTION_EMPTY_STATE`, `SECTION_EMPTY_QUICK_ACTION`, `SECTION_SPLIT_SUBSECTION`.
- Panel tabs: `PANEL_TAB`, `PANEL_TAB_CLOSE` (re-key prototype `panel-section-${side}` etc.).
- Splits: `SPLIT_CREATE_OPTION`, `SPLIT_CLOSE_OPTION`.
- Add-panel dropdown: `ADD_PANEL_DROPDOWN`, `ADD_PANEL_NEW_AGENT`, `ADD_PANEL_AGENT_TYPE_SUBMENU`, `ADD_PANEL_NEW_TERMINAL`, `ADD_PANEL_PANEL_OPTION`.
- **Parameterization:** section/sub-section-keyed ids should suffix the `SubSectionId` at the `data-testid` level (e.g. `${SECTION_HEADER}-left:secondary`), not mint `*_SECONDARY` enum members (matches harness_migration §2 + the flat keyspace).

**ElementIDs to REMOVE (Sections's share):** `PANEL_TOP_RIGHT`, `PANEL_BOTTOM_RIGHT`, `PANEL_RIGHT_AREA`, `PANEL_RIGHT_RESIZE_HANDLE`, `SIDE_TOGGLE_LEFT/RIGHT/BOTTOM`, `FOCUS_MODE_BUTTON`, `EXIT_ZEN_MODE_BUTTON`, `PANEL_CONTEXT_MENU_MOVE_TO`, `PANEL_CONTEXT_MENU_ZONE_OPTION`, `PANEL_ICON_*`, `FILE_BROWSER_TAB_*`. `AGENT_TAB`→`PANEL_TAB`, `ADD_AGENT_*`→`ADD_PANEL_*`. (Coordinate shared removals with Agent & terminal panels/FCC.)

**Fixtures:** Default-layout (SEC-01..04) — move the shared `sculptor_instance_` + `resources.py` setup off "terminal visible"/"right area" to the new default (center agent expanded; left/bottom/right collapsed-with-seed). Zero-agent variant (AGENT-02 / center empty-state) — coordinate with Agent & terminal panels. No new FakeClaude commands.

### Drag-and-drop testability (Playwright + dnd-kit)

Pointer-based DnD is not reliably driveable in Playwright as the provider is built: the prototype's `PanelDndProvider` uses `useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))` — a single `PointerSensor`, no `KeyboardSensor`. dnd-kit's `PointerSensor` listens on PointerEvents; Playwright's `drag_to()`/`mouse.*` dispatch MouseEvents that don't faithfully drive dnd-kit's `requestAnimationFrame`/collision pipeline, so synthetic drags are flaky-to-non-functional.

**Decided: add a `KeyboardSensor` + drag handle to `PanelDndProvider`** (also an accessibility win). Playwright drives the real sensor pipeline (`Space`→arrows→`Space`), wrapped in a `drag_panel_to_section()` helper so test bodies stay affordance-agnostic. This unblocks `test_panel_drag_and_drop.py` and PANEL-08/09/10/16.

## 5. USER STORIES

**Covered:** SEC-01..21 (SEC-18 `[perf]` excluded from e2e), SPLIT-01..06, PANEL-07..15 (PANEL-13 `[unit]`).
**Proposals — resolved in `user_stories.md`:**
- **SEC-22** Section resize clamps to min/max (sides have a minimum, center keeps a larger minimum, sides give way first). — **accepted.**
- **SEC-23** Resize is pure-geometry (doesn't change active panel or collapse state). — **demoted** to a test case under SEC-17.
- **SEC-24** Panel-cycle wraps + no-op in single/empty sections. — **merged** into SEC-20.
- **SEC-25** Maximize transfer. — **rejected**: not reachable (a maximized section covers the others, so a second maximize can't be triggered).
- **SPLIT-07** Drag last panel out → empty state. — **rejected**: the empty state appears on drop, already covered by SPLIT-04.
- **PANEL-16 (no-op drop guard)** — **demoted** to a test case under PANEL-08/09.
- **Reorder persists across collapse/switch** — **accepted** as PANEL-16.

## 6. OPEN QUESTIONS / CROSS-AREA OVERLAP

- **AddPanelDropdown shared with Agent & terminal panels:** Sections owns dropdown *mechanics* (opens from `+`, single-instance list, PANEL-01/05/12); Agent/terminal owns the **creation** semantics (agent-type sub-menu contents, Cmd+Shift+T/Cmd+K → center targeting PANEL-06, zero-agent AGENT-02). Decide which file asserts the *agent-type sub-menu contents*. Tied to the "Terminal" picker question.
- **Section `+` agent/terminal creation:** Agent/terminal owns lifecycle/confirmation; Sections owns "the action originates from the section's dropdown and lands in that section" (vs Cmd+Shift+T → center). Needs an explicit owner for the create-in-this-section assertion.
- **Sidebar collapse vs section collapse:** SEC-16 (maximize + sidebar-collapsed → show-sidebar icon in section header + OS-control padding) straddles Sections (maximize) and Sidebar (collapse). Keep `collapse_section` and `collapse_sidebar` distinctly named; decide which area asserts SEC-16.
- **`[perf]` SEC-18 / PERSIST-02:** the e2e "size restored across workspaces" aspect lives in `test_section_resize.py`; the zero-reflow guarantee is checked with the workspace-switch profiler (`common/perf/workspaceSwitchProfiler.ts`, carried forward from the prototype).
