# Task 3.1: Terminal panel — wrap the xterm container as a panel (+ close confirmation)

## Goal

Wrap the existing xterm terminal in a `TerminalPanel` and wire it into the registry
as the dynamic `terminal:<wsId>:<n>` panel. The terminal I/O is reused unchanged;
closing a terminal panel now shows a confirmation dialog (new behavior).

## Stories addressed

TERM-01 (terminal works as before; zero/one/multiple terminals), TERM-02 (closing
shows a confirmation — **new**; see Decision B3), TERM-03 (numbering reuses lowest
available), TERM-04 (close kills the backend shell; siblings unaffected — existing
backend behavior preserved).

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "Terminal Panel", the terminal functions the same as before, except a
workspace can have zero/one/multiple terminals, and closing now shows a confirmation
(for now).

**The terminal surface to reuse** (`design_extraction.md` → "Agent & terminal
panels"): the xterm container lives under `sculptor/frontend/src/pages/workspace` —
the `TerminalPanel` / `AgentTerminalPanel` surface (`--terminal-panel-bg`, overlay
scrollbar). Find the current entry component by grepping `xterm`, `AgentTerminalPanel`,
`TerminalPanel`. **Reuse the xterm I/O verbatim** — the integration tests keep all
xterm-buffer assertions (`agent_terminal_panels.md`: the content half is KEEP).

**Registry wiring** (Task 1.6 `dynamicPanels.tsx`): the terminal panel is **dynamic,
multi-instance**, `kind: "terminal"`, `defaultSection: "bottom"`, id
`terminal:<wsId>:<index>`, **component identity cached per id** so the xterm buffer
never remounts on a registry rebuild.

**Close = confirmation** (TERM-02): reuse the close/delete `AlertDialog` pattern.
The prototype has `pages/workspace/components/TerminalCloseConfirmation.tsx`
(`design_extraction.md` → "DeleteConfirmationDialog"). Closing kills the backend
shell process (TERM-04) — that is existing behavior; preserve it (don't just
disconnect).

This task depends on **Task 1.6** (terminal derivation + cache), **Task 2.4**
(`SectionHeader` renders close affordances), and the `DeleteConfirmationDialog`
shared component (copy from prototype if not on `main`).

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/panels/TerminalPanel.tsx` (+ `.module.scss`)
  — new wrapper around the xterm container, parameterized by terminal identity.
- `sculptor/frontend/src/components/sections/registry/dynamicPanels.tsx` — modify:
  bind the terminal component per `terminal:<wsId>:<n>` (identity cache); display
  name with lowest-available-number reuse (TERM-03).
- `sculptor/frontend/src/components/DeleteConfirmationDialog.tsx` /
  `TerminalCloseConfirmation.tsx` — copy from prototype if absent.

## Implementation details

1. `TerminalPanel`: render the existing xterm container for the given terminal,
   reading from the existing terminal data atoms; shell-agnostic (no layout reads).
2. In `dynamicPanels.tsx`, derive `terminal:<wsId>:<index>` defs with cached
   component identity and lowest-available-number names (TERM-03 — reuse today's
   terminal numbering logic).
3. Wire **close = confirmation**: when the section header's close button is hit on a
   terminal tab, show the terminal close confirmation; on confirm, close the
   terminal (which kills the backend shell, TERM-04) and remove the panel
   (`closePanelAtom`, Task 1.4). The agent close-confirmation is wired in Task 3.7;
   share the dialog component.
4. Zero/one/multiple terminals: closing the last terminal leaves the bottom section
   empty (empty state) — consistent with the agent behavior.

## Testing suggestions

- TERM-01/02/03 e2e land in Task 3.7 (`test_terminal_panel.py`). TERM-04 (close kills
  the backend PID; sibling survives) is a content test preserved from
  `test_terminal_close_kills_shell.py` — migrated/UPDATE in Task 8.2.
- A smoke check (a terminal panel renders in the bottom section and accepts input)
  can ride the Task 4.6 / 3.7 suites.

## Gotchas

- **Reuse, don't rewrite** the xterm container; all xterm-buffer test helpers stay.
- Identity-cache the terminal component per id or the buffer remounts (lost
  scrollback) on every tick.
- TERM-02 confirmation is **new** — today terminal close has none; add it.
- Close must **kill** the backend shell (TERM-04), not just disconnect — that is
  existing behavior; ensure the panel-close path still calls it.

## Verification checklist

- [ ] `TerminalPanel` wraps the existing xterm; reads no layout state.
- [ ] `dynamicPanels.tsx` derives `terminal:<wsId>:<n>` with cached identity +
  lowest-number names.
- [ ] Closing a terminal panel shows a confirmation, then kills the shell; siblings
  unaffected.
- [ ] Zero/one/multiple terminals supported.
- [ ] `just check` passes.
