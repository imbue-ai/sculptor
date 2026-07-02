# UI-refresh Phase 99.1 — autonomous decisions audit

This log records decisions made autonomously while driving the integration suite
to green (overnight session). Review and adjust anything you disagree with.

## Test-running infrastructure
- **Full-suite verification runs on Modal via `just test-offload`.** The local
  `RUN_ALL=1 just test-integration` run was SIGTERM-killed (the machine can't hold
  the whole suite). Installed `offload@0.9.8` (matches CI; `cargo install offload@0.9.8`).
- **`offload.tmp.toml` (untracked, repo root) is a local workaround** — a copy of
  `offload.toml` with the `[groups.isolated]` group removed. That group filters
  `-m 'isolated and not real_claude and not real_pi'`, which currently matches **0
  tests**, and offload treats a 0-collection discovery as a fatal error. Running
  `just test-offload -c offload.tmp.toml` skips the empty group.
  - **OPEN ITEM for review:** either (a) delete the dead `[groups.isolated]` group
    from the tracked `offload.toml`, or (b) mark some tests `@pytest.mark.isolated`.
    I left `offload.toml` untouched and used the temp file. `offload.tmp.toml`
    should be deleted before merge (it's a local artifact, never committed).
  - **Resolved 2026-07-02:** option (a) — the dead `[groups.isolated]` group is
    deleted from `offload.toml` (a 0-collection group is a fatal offload error, and
    no test carries the `isolated` marker). `offload.tmp.toml` is no longer needed
    and is removed before merge.

## Deleted tests (features removed in the section shell)
- `test_workspace_banner_overflow.py` — the progressive-collapse banner + its inert
  overflow menu were replaced by the simpler `WorkspaceHeader`; the regression it
  guarded can't recur.
- `test_review_all_visibility.py` — the gated "Review all" *button* was removed
  (review-all is now a panel opened via the section `+` dropdown).
- Multi-tab diff tests (no-duplicate-tab, distinct-tabs, combined-tab-remains) +
  the diff expand/fullscreen tests + the debug-view test — the section shell uses a
  SINGLE embedded DiffViewer (your decision), with no `DIFF_TAB` bar, no diff-local
  expand control, and no debug view. (Full list in removed-and-changed-features.md.)

## Frontend behavior completed in the new shell (product changes, not test-only)
These were genuine new-shell gaps the harness exposed; fixed to match intended UX:
- **Diff/file reveal + render:** opening a file/diff (sculpt open-file, chat
  file-chip, plan-mode) now opens + expands + activates the host panel and the
  embedded viewer renders the active file from the shared diff-tab atom.
- **Agent auto-open:** a newly-created/backend-spawned agent now opens as a center
  panel tab (`agentPanelPlacement.ts`) — fixes ci-babysitter etc.
- **Panel-tab rename:** wired `onRename` through the panel registry →
  `renameWorkspaceAgent` (was a no-op stub).
- **Per-agent chat isolation:** `ChatInput` keys model/fast-mode/effort/draft on the
  panel's agent, not the route's.

## Test-harness conventions adopted
- `reset_active_panel_to_files` is best-effort (a prior test may have moved Files).
- `navigate_to_add_workspace_page` routes Home when parked on Settings; accepts the
  empty-first-run page as a valid Home landing.
- `get_workspace_tabs()` retained as a shim onto sidebar rows for un-swept suites.

## Frontend product changes (rounds 2-4, to call out in review)
- Diff/file open reveal + single-viewer render (host panels read the shared
  diff-tab atom); agent auto-open (`agentPanelPlacement.ts`); panel-tab rename
  wiring (`onRename` → `renameWorkspaceAgent`); per-agent chat isolation
  (`ChatInput`/`ChatPanelContent` key on the panel's agent); Linear workspace
  widget in `WorkspaceHeader`. These are genuine new-shell completions, not
  test-only changes — the reviewer should sanity-check them.

## Command-palette flakiness
- `ensure_workspace_exists` now waits for the sidebar workspace row before
  returning, so the Cmd+K palette / global shortcuts (gated on a non-empty
  workspace list) don't fire before the list atom syncs. This was the dominant
  source of flaky (passed-on-retry) command-palette / keybindings tests.

## Status / trajectory (offload, real_claude+real_pi excluded; ~1005 tests)
- Passing: 128 → 836 → 888 → 902 → 927 → 958 → 986 (round 6) → **regression** (756,
  714) → **992 / 1005 (final, round 9)** after the strict-mode fix. 13 truly-failed
  + 18 flaky remain (the genuine residual below).
- **Follow-up debug session (2026-06-26): all residuals triaged + resolved.** Of the
  13, **11 were real** (the other 2 — `test_open_command_palette_via_topbar_button`,
  `test_customized_keybinding_is_honored` — are flaky, pass in isolation). All 11 now
  pass locally (`RUN_ALL=1`, `11 passed`). See "Residual resolution" below.

## Final residual (13 truly-failed, round 9 — for the review / a live-run debug)
- **chat message-count (4)**: `test_branch_switching_with_untracked_file`,
  `test_in_place_mode_displayed_correctly`, `test_turn_footer_shows_bash_created_file_in_worktree_workspace`,
  `test_worktree_on_local_only_repo_shows_all_tab_and_uncommitted_changes` — the
  FakeClaude reply / message count not reaching the expected number in these
  branch/worktree flows. POM + testids verified correct; needs `/debug-integration-test`.
- **command palette (3)**: `test_command_palette_report_problem_opens_popover`,
  `test_open_command_palette_via_topbar_button` (NOTE: "topbar" is a removed surface —
  likely a stale test to delete/repoint), `test_customized_keybinding_is_honored`.
  Possibly still flaky (they pass on retry in some runs).
- **sidebar resize (2)**: `test_resize_handle_widens_sidebar`, `test_resize_clamps_to_a_minimum_width`
  — dragging the thin `SIDEBAR_RESIZE_HANDLE`; finicky drag actionability.
- **linear plugin panel (1)**: `test_linear_panel_follows_workspace_branch_and_sends_key`
  — the bundled Linear plugin's `linear-issue` panel isn't offered in the add-panel
  dropdown (plugin-contributed panels may not be wired into the section-shell registry).
- **agent-type default (1)**: `test_first_agent_type_defaults_to_shared_last_used`
  — `useCreateWorkspace.ts` doesn't optimistically set `lastUsedAgentType`.
- **unread indicator (1)**: `test_unread_indicator_when_switching_agents_within_workspace`.
- **terminal close (1)**: `test_close_terminal_tab_kills_shell_process` (bottom-section tab).

## IMPORTANT — strict-mode regression (introduced + fixed this session)
- A round-5 change added `EMPTY_FIRST_RUN_PAGE` to the `navigate_to_add_workspace_page`
  settle `or_()` chain. On the empty-first-run page that surface OVERLAPS the inline
  `NEW_WORKSPACE_CREATE_BUTTON`, so the combined locator matched 2 elements and the
  strict-mode `to_be_visible()` raised "resolved to N elements". Since per-test
  cleanup leaves every test starting on that page, this failed the WHOLE suite
  (offload rounds 7-8: 756/714 passing, 400+ "flaky" — the flakiness was the
  timing-dependent overlap, not infra). **Fixed** by adding `.first` to the settle
  locator (commit fixing the strict-mode violation). Lesson: a sudden jump in the
  flaky count + a uniform single-locator failure can be a strict-mode-overlap race,
  not infra — always reproduce locally before blaming infra.

## Auto-update fix (real product bug, fixed this session)
- `EmptyFirstRunGate` swaps out `AppShell` when the workspace list is empty, and
  `AppShell` hosted `useAutoUpdateListener()` + `<AutoUpdateToasts/>` — so the
  update callback was unregistered whenever a user had zero workspaces (which the
  test cleanup always produces). Hoisted both into `EmptyFirstRunGate` (always
  mounted). This is a genuine product fix, not test-only: auto-update would have
  been silently dead in the empty-first-run state for real users too.

## Residual (documented for the review / a real-run debug session)
After the final round these remained red/uncertain — each needs either a live test
run to diagnose or a deeper product decision, so I stopped autonomous blind edits:
- **Chat message-count (~4)**: `test_branch_switching_integration` (untracked-file,
  in-place-mode), `test_turn_summary_worktree`, `test_read_unread_status`. The POM +
  testids verified correct by source; the FakeClaude reply / 2nd-agent-tab not
  materializing is a runtime/timing question (possibly flaky, possibly a chat-alpha
  regression in a specific switch/worktree flow). Needs `/debug-integration-test`.
- **Linear plugin panel (1)**: `test_linear_panel_follows_workspace_branch_and_sends_key`
  — the bundled Linear plugin's `linear-issue` panel isn't offered in the add-panel
  dropdown. Plugin-contributed panels may not be wired into the section-shell
  dropdown (`addPanelCore.ts` / registry) — a plugin-system gap.
- **Sidebar resize (2)**: `test_resize_handle_widens_sidebar` / `_clamps_to_a_minimum_width`
  — dragging the thin `SIDEBAR_RESIZE_HANDLE` doesn't change width; flagged
  `WorkspaceSidebar.module.scss` / `SectionGrid.tsx`. Finicky drag actionability.
- **Add-workspace agent-type default (1)**: `test_first_agent_type_defaults_to_shared_last_used`
  — `useCreateWorkspace.ts` doesn't optimistically set `lastUsedAgentType`.
- The command-palette / keybindings flakiness should be resolved by the
  `ensure_workspace_exists` wait; confirm in the final run.

## Hand-off notes (for the review agent)
- The review doc the instructions mean is **docs/development/review/integration_tests.md**
  (also docs/development/review/sculptor.md, react.md). The `code-review-checklist`
  skill is present.
- The branch changed **~829 files** (whole shell rebuild over 144 commits) — "every
  changed file" is huge; scope to substantive source (skip generated `types.gen.ts`,
  pure deletions) and consider a fan-out workflow.
- **~31 source files** carry comments referencing ui_refresh planning docs
  (`goals.md`, `state_design.md`, `Task X.Y`, `PANEL-06`, etc.) — these are the
  comment-cleanup targets (remove references to agent_docs/ui_refresh).
- These audit docs (agent_docs/ui_refresh/audit/) are deliverables — KEEP them.
- `offload.tmp.toml` (repo root, untracked) is a local run artifact — delete before merge.

## Residual resolution (follow-up debug session, 2026-06-26)
Drilled into each of the 13. The doc's earlier guesses were partly wrong — several
"chat message-count" failures were OVERSHOOT (4 messages, not undershoot), and two
"residuals" were just flaky. Final tally: **11 real, fixed + verified; 2 flaky.**

Real fixes (each verified by re-running the affected test under `RUN_ALL=1`):
- **chat message-count (4)** — root cause was test-side, not a chat regression. The
  empty-first-run inline form pre-seeds the prompt with `/sculptor:help` (via
  `NewWorkspaceForm initialPrompt={HOME_PROMPT_PREFILL}`); these tests submitted the
  form WITHOUT clearing it (unlike `start_task_and_wait_for_ready`), so an extra turn
  ran at creation with the default model (→ the Claude-stub error turn = 2 extra
  messages). Fix: clear `get_task_input()` before submit in all four flows.
- **report-problem popover** — duplicate mount: the sidebar footer rendered the
  `SIDEBAR_REPORT_BUG` button AND `VersionDisplay → StatusIndicators`'s own
  `ReportProblemPopover`, both bound to the shared `reportProblemAtom` → two open
  dialogs (strict-mode "2 elements"). Fix: drop the redundant popover from
  `StatusIndicators.tsx` (delete its now-dead `.module.scss`).
- **Linear plugin panel** — the add-panel re-add list was built from the hardcoded
  `STATIC_PANEL_METADATA`, which excludes plugin panels, so `linear-issue` was never
  offered. Fix: source the list from `panelRegistryAtom` (`kind === "static"`, which
  includes plugin panels) in both `addPanelCore.listAvailableStaticPanels` and
  `useAddPanelActions`.
- **agent-type default** — `useCreateWorkspace` never optimistically set
  `lastUsedAgentType`, and there is NO live user-config push to the frontend (the test
  comment claiming a "WebSocket sync" was wrong). The add-panel path sets it
  optimistically; the form path didn't. Fix: mirror `addPanelCore.ts`'s optimistic
  `set(userConfigAtom, …)`; corrected the test comment.
- **sidebar resize (2)** — not "finicky drag": the handle had ZERO area. The base
  `.horizontalResizeHandle` (`position:relative; width:1px`) won the cascade over the
  sidebar's `.resizeHandle` (`position:absolute; top/bottom/right:0`), collapsing it to
  1px×0 — invisible AND un-grabbable for real users. Fix: scope the sidebar rule under
  `.sidebar` so its absolute positioning wins.
- **unread indicator** — `useMarkRead` tracked the ROUTE's agent, but switching agents
  via the center tab bar only flips the active panel (no navigation), so the focused
  agent wasn't marked read on update. Fix: `useMarkRead`/`useArtifactSync` follow the
  active center panel's agent (matches ChatInput's per-panel isolation).
- **terminal close** — closing a terminal tab now opens a confirmation dialog
  (intended; mirrors agent delete). The test clicked close but never confirmed. Fix:
  call the existing `confirm_close_terminal` helper.

Two secondary issues the fixes uncovered (tests ran further than before):
- `navigate_to_add_workspace_page`'s settle set used `CHAT_PANEL` as the "on a
  workspace" signal, which a terminal-agent workspace lacks → added `SECTION_CENTER`.
- **Mode badge was never ported to the new shell** — `RepoSegment` (with
  `TASK_MODE_BADGE`) was dropped in Task 7.1 and not re-added. Ported a minimal badge
  into `WorkspaceHeader` with the original rule (shown for non-worktree modes).

Flaky (not real): `test_open_command_palette_via_topbar_button` (also misnamed — its
POM already uses the sidebar Cmd+K link, not a topbar) and
`test_customized_keybinding_is_honored`. Both pass in isolation.

Still open (unchanged): the dead `[groups.isolated]` offload group (collects 0 tests).
Left `offload.toml` untouched; the `offload.tmp.toml` workaround is still needed.
(Resolved 2026-07-02 — see "Resolutions" below.)

## Resolutions (user-approved verdicts, 2026-07-02)
- **Dead offload group:** `[groups.isolated]` deleted from `offload.toml`;
  `offload.tmp.toml` removed at commit time.
- **Misnamed palette test:** `test_open_command_palette_via_topbar_button` renamed to
  `test_open_command_palette_via_sidebar_cmdk_link` (its POM already drove the
  sidebar Cmd+K link; there is no topbar).
- **Comment cleanup:** the source/test comments referencing the ui_refresh planning
  docs (`Task X.Y`, decision ids, story ids, `e2e_test_plan.md`, `goals.md`, plan/
  file pointers) are scrubbed and reworded to self-contained behavior descriptions.
- **Feature verdicts** (Review All unconditional with default scope "All" on open,
  visible panel-tab status dot, keybinding relabels, close-others removal, flat
  diagnostics copy items, mark-as-unread shipped, splits persist when emptied,
  explorer list drag-resize, debug chat view deletion, bare-terminal pinned-row
  normalization, per-workspace maximize, automated-prompt routing) are recorded in
  `removed-and-changed-features.md`.
