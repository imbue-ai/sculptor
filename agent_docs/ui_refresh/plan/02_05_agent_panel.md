# Task 2.5: Agent panel — wrap the existing chat surface as a panel

## Goal

Wrap the existing agent/chat interface in an `AgentPanel` and wire it into the
registry as the dynamic `agent:<taskId>` panel. The chat surface is **reused, not
rewritten** — with one surgical change: `ChatPanelContent` is decoupled from the
route so each panel can render a **specific** agent. The panel is a thin,
shell-agnostic wrapper that takes its task id from the registry and passes it down;
data still comes from the existing data atoms.

## Stories addressed

AGENT-01 (renders the existing chat with all functionality preserved), AGENT-02
(zero/one/multiple agents — incl. the backend zero-agent relaxation below), AGENT-03
(an agent in center and another in right at once), AGENT-04 (closing an agent = delete
confirmation; closing the last leaves the center empty), AGENT-05 (two agents stream
independently — via the identity cache + per-panel `taskId`), AGENT-06 (tab
diagnostics actions), AGENT-07 (tab status dot: read/unread + running/waiting),
AGENT-08 (optimistic agent deletion + rollback), AGENT-09 (tab numbering reuses the
lowest available number). (The e2e for these land in Task 3.7; this task builds them.)

## Background

**Project:** Sculptor frontend (TS + React + Jotai). We are rewriting the workspace
shell into the section/panel model from `agent_docs/ui_refresh/goals.md`. Per
`goals.md` → "Agent Panel", the agent panel displays the existing agent/chat
interface with all functionality preserved; the new capability is that a workspace
can have zero, one, or multiple agents.

**The chat surface to reuse** (`design_extraction.md` → "Agent & terminal panels"):
the existing chat lives under `sculptor/frontend/src/pages/workspace` — the
`ChatPanelContent` / `chat-alpha/AlphaChatInterface` surface (centered scroll area,
persistent thumb, bottom bar). Find the exact current entry component by grepping
`AlphaChatInterface`, `ChatPanelContent`, and the component today's `WorkspacePage`
renders for a task. **Do not rewrite it** — wrap it.

**One required change — decouple the chat from the route.** Today `ChatPanelContent`
reads its task id from the route (`useWorkspacePageParams()`), so it can only ever
show the route's agent. To render a *specific* agent per panel — one agent in center
and another in right at once (AGENT-03), two agents streaming concurrently
(AGENT-05) — `ChatPanelContent` must take an **explicit, required `taskId` prop** and
stop reading the route. This is a small, surgical move (lift the route read up one
level), not a rewrite, and it is exactly principle 2: content components never read
shell/route state. Concretely: delete the `useWorkspacePageParams()` read inside
`ChatPanelContent`, and update its **one** current call site (`WorkspacePage`) to
pass `useWorkspacePageParams().agentID` explicitly. `AgentPanel({ taskId })` is then
just `<ChatPanelContent taskId={taskId} />`.

**The wrapper must be shell-agnostic** (`component_hierarchy.md` → principle 2;
`state_design.md` → "Mobile"): `AgentPanel` takes a `taskId` and renders
`<ChatPanelContent taskId={taskId} />`; neither it nor the chat reads
section/split/size layout state (or, now, the route). This keeps them reusable and
keeps the memo boundary at `SectionBody` (Task 2.4) valid.

**Registry wiring** (Task 1.6): the agent panel is a **dynamic, multi-instance**
panel. `dynamicPanels.tsx` derives one `agent:<taskId>` definition per task for the
active workspace, with the **component identity cached per id** so the chat never
remounts on a registry rebuild. This task provides the component the cache binds.

This task depends on **Task 1.6** (`registerPanelComponent`, `dynamicPanels.tsx`
agent derivation + cache) and **Task 2.4** (`SectionBody` renders the resolved
component).

## Files to modify/create

- `sculptor/frontend/src/pages/workspace/panels/AgentPanel.tsx` — new. The thin
  wrapper around the existing chat surface, parameterized by `taskId`.
- `sculptor/frontend/src/pages/workspace/components/ChatPanelContent.tsx` — modify:
  add a **required `taskId` prop** and **delete** its internal
  `useWorkspacePageParams()` route read.
- `WorkspacePage` (the current `ChatPanelContent` call site) — modify: pass
  `useWorkspacePageParams().agentID` to `ChatPanelContent` explicitly.
- `sculptor/frontend/src/components/sections/registry/dynamicPanels.tsx` — modify
  (from Task 1.6): bind the agent component per `agent:<taskId>` in the identity
  cache; derive the display name with **lowest-available-number reuse** (AGENT-09);
  provide the agent's `tabIcon` status dot (AGENT-07) and `contextMenuActions`
  diagnostics (AGENT-06).
- **Backend zero-agent support** (Decision B1): relax the backend "≥1 agent"
  assumption and remove the auto-create-an-agent-on-last-delete path so a workspace can
  exist with zero agents (the empty center). Grep the backend/data layer for the
  ≥1-agent invariant + the last-agent auto-create. Breadcrumb: the *visible*
  auto-create-on-last-delete lives in the frontend today —
  `src/pages/workspace/components/AgentTabs.tsx` → `handleNavigateAfterDelete` calls
  `handleCreateAgent()` when no agents remain (old-shell code, deleted in Phase 7) — so
  zero-agent support spans both dropping that frontend path and hardening the
  backend/data layer where an agent is assumed.

## Implementation details

1. **Decouple `ChatPanelContent` from the route, then wrap it:** give
   `ChatPanelContent` a required `taskId` prop, delete the
   `useWorkspacePageParams()` read inside it, and update its one current call site
   (`WorkspacePage`) to pass `useWorkspacePageParams().agentID` explicitly.
   `AgentPanel({ taskId })` is then just `<ChatPanelContent taskId={taskId} />`. The
   chat still reads its task data from the existing data atoms — only the *source of
   the task id* moves from the route to a prop. Add nothing shell-related.
2. In `dynamicPanels.tsx`, for each task in the active workspace produce a
   `PanelDefinition` with `id = agent:<taskId>`, `kind: "agent"`, `defaultSection:
   "center"`, `displayName` = the agent's name/number, and a `component` that is the
   **cached** `() => <AgentPanel taskId={taskId} />` (cache keyed by the panel id so
   the reference is stable across rebuilds). Provide the agent's `tabIcon` status dot
   (read/unread + running/waiting — AGENT-07) and its `contextMenuActions` (the
   diagnostics submenu: copy session id / transcript path / agent id / name, disabled
   when there is no session — AGENT-06), both reusing today's agent-tab readers.
3. **AGENT-09 numbering:** when naming unnamed agents (e.g. "Agent 2"), reuse the
   lowest available number after deletions (mirror today's numbering logic — grep
   for the existing agent-tab numbering and reuse it).
4. **Close = delete (AGENT-04/08):** wire the panel-tab close (built in Task 2.4) for
   an agent to the existing agent-delete flow — the same delete confirmation dialog as
   today, optimistic tab removal, and rollback + error toast + Retry on failure
   (preserve today's optimistic-delete behavior; the e2e are Task 3.7). Closing the
   **last** agent leaves the center **empty** (AGENT-04 + the backend relaxation in
   step 5), not auto-create. Confirm zero/one/multiple agents: zero → center empty
   state (Task 2.4's `EmptySectionState`); multiple → `agent:*` panels in different
   sections (AGENT-03). Center-targeting of new agents (Cmd+Shift+T / Cmd+K) is Task
   4.5/3.5.
5. **Backend zero-agent relaxation (Decision B1):** remove the "a workspace needs ≥1
   agent" invariant and the auto-create-on-last-delete behavior so the center can be
   empty (AGENT-02/04). This is the precondition for the empty-center state and the
   zero-agent test fixture (Task 2.7); without it, closing the last agent cannot leave
   the center empty. Coordinate with `01_06`/`06_01` (Decision B1's other bite points).

## Testing suggestions

- AGENT-01..03/09 e2e land in Task 3.7 (`test_agent_panel.py`). A smoke check (the
  center section renders the chat for the active agent after cutover) lands in Task
  2.7.
- AGENT-05 (two agents streaming concurrently) is a dedicated regression test in
  Task 3.7 — the identity cache + independent data subscriptions here are what make
  it pass.

## Gotchas

- **Reuse, don't rewrite** the chat — the *only* change to chat code is making
  `taskId` an explicit prop (the route read is lifted up to `WorkspacePage`).
  `goals.md` preserves all existing chat functionality and the test plan keeps ~all
  chat-content tests as-is.
- **Don't keep the `useWorkspacePageParams()` read as a "fallback"** inside
  `ChatPanelContent`. A route fallback re-couples it to the route and breaks AGENT-03
  (every panel would render the route's agent instead of its own `taskId`).
- The wrapper must not read layout or route state (keep it shell-agnostic).
- The agent component **must be identity-cached per id** (Task 1.6) or the chat
  remounts on every task tick (violating SWITCH-02 and dropping streaming state).
- Reuse the existing numbering logic for AGENT-09 rather than inventing a new scheme.

## Verification checklist

- [ ] `ChatPanelContent` takes a **required** `taskId` prop; its
  `useWorkspacePageParams()` read is removed and `WorkspacePage` passes `agentID`
  explicitly.
- [ ] `AgentPanel({ taskId })` renders `<ChatPanelContent taskId={taskId} />` and
  reads no layout or route state.
- [ ] `dynamicPanels.tsx` derives `agent:<taskId>` defs with cached component
  identity and lowest-available-number display names.
- [ ] Zero/one/multiple agents supported; an agent can live in center and right at
  once.
- [ ] Backend ≥1-agent invariant relaxed + auto-create-on-last-delete removed
  (zero-agent workspace works end-to-end; closing the last agent leaves the center
  empty).
- [ ] Agent close = delete confirmation + optimistic removal/rollback (AGENT-04/08);
  tab status dot + diagnostics actions provided (AGENT-06/07).
- [ ] `just check` passes.
