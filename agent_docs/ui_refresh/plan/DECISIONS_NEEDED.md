# Decisions — workspace UI refresh (RESOLVED)

**Status: all resolved (2026-06-23).** These were the open calls the autonomous plan
made a default on; the answers below are final and have been propagated into the
authoritative docs (`goals.md`, `user_stories.md`, `e2e_test_plan.md`,
`harness_migration.md`) and the task files. The A/B/C IDs are kept because the task
files reference them (e.g. "Decision B1").

Legend: **Resolved** = the final answer. **Bites at** = the task(s) that depend on it.

---

## A. Strategic calls

### A1. Strangler rewrite, not a `frontend_old` move — RESOLVED: confirmed
Build the new shell in `src` alongside the reused content (chat/terminal/diff) and
delete the old shell once unreferenced (Phase 7). Not a from-scratch `frontend_old`
recreate.
- **Bites at:** the entire phase structure (Phases 2–7).

### A2. Harness compatibility shim (signature-stable POMs) — RESOLVED: confirmed
Keep POM method signatures stable and rewrite their internals (Phase 2:
`project_layout.py`, `task_page.py`, `create_workspace()` with its ~177 importers);
migrate the legacy suite by area (Phase 8). A bounded red window between cutover and
each area's migration is accepted.
- **Bites at:** `02_07`, all of Phase 8.

### A3. Delivery — RESOLVED: single PR, split into semantic commits
**Do not** make stacked per-phase PRs. Ship **one PR** off `bryden/tungsten-seriema`,
split into **semantic commits** — the build commits once per task
(`implement_task.md`), so each commit is a coherent, independently reviewable unit. A
per-commit review tool walks them like a stack of small PRs while everything lands in
a single PR. Keep commits atomic and ordered by the phase sequence; the Phase 8
terminology rename is deliberately its own "rename only" commit.
- **Bites at:** nothing in the task files (the per-task commit model already produces
  this); reflected in `plan.md` → "Delivery".

### A4. Mobile out of scope; keep the seam — RESOLVED: confirmed
Do not build `MobileWorkspaceShell`; keep the page-level `useIsMobile` no-op seam and
enforce "content never reads layout state" so the separately-tracked mobile work can
slot in later.
- **Bites at:** `02_06`, every panel task.

---

## B. Product/design questions

### B1. Closing the last agent — RESOLVED: empty center; zero-agent fully supported
Closing the last agent **leaves the center empty** (AGENT-04, relaxing today's "≥1
agent"). **The zero-agent workspace must be fully supported end-to-end** — relax the
backend "≥1 agent" assumption, add the zero-agent fixture (`harness_migration.md` §3),
and rewrite `test_optimistic_deletion::..._last_agent_creates_new_one`.
- **Bites at:** `01_06`, `02_05`, `03_07`, `06_01` (+ backend zero-agent support).

### B2. The bare "Terminal" agent type — RESOLVED: dropped
No bare "Terminal" agent type. A raw shell is the "New terminal" panel; terminal-
running agents come from registered programs. Drop `AGENT_TYPE_OPTION_TERMINAL` /
`AGENT_TYPE_MENU_ITEM_TERMINAL` from the picker + add-panel dropdown.
- **Bites at:** `03_05`, `05_02`, `05_04`.

### B3. Terminal close confirmation — RESOLVED: add it
Closing a terminal panel shows a confirmation dialog (TERM-02, new) reusing the
delete/close `AlertDialog` pattern (`TerminalCloseConfirmation`).
- **Bites at:** `03_01`, `03_07`.

### B4. Closed-workspaces distinction — RESOLVED: removed (default path)
The open/closed-workspace distinction is removed; all workspaces appear in the
sidebar. Delete the pill/dropdown + its tests; SIDE-18 (reopen) is not built.
`goals.md` already records this under "Features to deprecate"; the
`user_stories.md` "pending a matching update" caveat has been removed, so the two are
now consistent.
- **Bites at:** `07_03`, `08_01`.

### B5. Component Gallery / TanStack devtools — RESOLVED: delete Gallery, KEEP devtools
**Delete the Component Gallery** (no one relies on it) — its tab test and the
theme-builder gallery assertion go with it. **Keep the TanStack devtools panel** and
`test_tanstack_devtools_panel.py` (UPDATE only if its nav reach changed). Propagated
to `e2e_test_plan.md`, `harness_migration.md`, `plan.md`, and `07_03`.
- **Bites at:** `07_03`, `08_01`.

### B6. Home / Settings "return to MRU" — RESOLVED: routes, no MRU-return
Home and Settings are full routes; you return by clicking a workspace row (SIDE-07).
No implicit MRU-return / back-affordance.
- **Bites at:** `02_02`, `05_03`, `08_01`.

### B7. File/diff load error & retry states — RESOLVED: preserve today's behavior
Preserve today's file/diff error/retry behavior verbatim; do not invent new error/
retry UI (FCC-01..07: keep whatever exists today).
- **Bites at:** `03_02`, `03_03`.

### B8. New-workspace dialog net-new surfaces + "keep open" — RESOLVED: confirmed
Copy the `scu-1494` styling; "keep open" keeps the dialog open after Create for rapid
multi-create (form resets; repo/agent-type retained). Rename the Create button id
`START_TASK_BUTTON` → `NEW_WORKSPACE_CREATE_BUTTON`. `/sculptor:help` prefill per
FIRST-04.
- **Bites at:** `05_01`, `05_02`, `05_04`.

### B9. Cross-area ownership of shared test surfaces — RESOLVED: confirmed
The plan's assignments stand: `AddPanelDropdown` agent-type sub-menu (`03_05`/`03_07`),
the `TAB_CONTEXT_MENU_*` workspace-row vs. panel-tab split (`02_07`/`08_01`), and
SEC-16 (`04_03`).
- **Bites at:** `03_05`/`03_07`, `02_07`/`08_01`, `04_03`.

---

## C. Logistics / housekeeping

- **C1. Commit when ready.** New docs are left as a working change for your review.
- **C6. This `plan/` folder is gitignored — decide if you want it tracked.**
  `.gitignore` line 10 (`**/agent_docs/**/plan/`) intentionally excludes
  `agent_docs/**/plan/` (the `/sculptor-workflow:plan` skill normally writes
  regenerable plan folders). So `README.md` and `plan.md` commit, but this `plan/`
  folder does **not** by default (it lives on disk, usable by `/sculptor-workflow:build`).
  To track it: `git add -f agent_docs/ui_refresh/plan/` (or relax the ignore). Left
  the convention in place rather than override it.
- **C2. `just generate-api`** is required after every `ElementIDs` edit (most-forgotten
  step).
- **C3. Perf bars are a checklist, not pytest** (Phase 9) — run the profiler +
  `measure-react-renders` by hand.
- **C4. The two mandatory final tasks** (`99_01`, `99_02`) assume a
  `/sculptor-workflow:build` run; still good checklists by hand.
- **C5. Scope:** ~42 tasks across 10 phases. Ask if you want a smaller first milestone.
