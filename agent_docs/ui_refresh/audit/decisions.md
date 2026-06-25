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

## Status
- Trajectory (offload, real_claude/real_pi excluded): 128 → 836 → 888 → 902 → 927
  → 958 passing. Driving the remaining tail to green now.
