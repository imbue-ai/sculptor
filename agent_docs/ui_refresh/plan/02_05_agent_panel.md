# Task 2.5: Agent panel — wrap the existing chat surface as a panel

## Goal

Wrap the existing agent/chat interface in an `AgentPanel` and wire it into the
registry as the dynamic `agent:<taskId>` panel. The chat surface is **reused
unchanged**; the panel is a thin, shell-agnostic wrapper that takes its task id from
the registry and its data from the existing data atoms.

## Stories addressed

AGENT-01 (renders the existing chat with all functionality preserved), AGENT-02
(zero/one/multiple agents), AGENT-03 (an agent in center and another in right at
once), AGENT-09 (tab numbering reuses the lowest available number).

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

**The wrapper must be shell-agnostic** (`component_hierarchy.md` → principle 2;
`state_design.md` → "Mobile"): `AgentPanel` takes a `taskId` and reads task data
from the existing data atoms; it must **not** read section/split/size layout state.
This keeps it reusable and keeps the memo boundary at `SectionBody` (Task 2.4)
valid.

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
- `sculptor/frontend/src/components/sections/registry/dynamicPanels.tsx` — modify
  (from Task 1.6): bind the agent component per `agent:<taskId>` in the identity
  cache; derive the display name with **lowest-available-number reuse** (AGENT-09).
- (No change to the chat components themselves.)

## Implementation details

1. `AgentPanel({ taskId })`: render the existing chat surface for that task, reading
   the task from the existing data atoms (the same hooks today's `WorkspacePage`
   uses). Pass through everything the chat needs; add nothing shell-related.
2. In `dynamicPanels.tsx`, for each task in the active workspace produce a
   `PanelDefinition` with `id = agent:<taskId>`, `kind: "agent"`, `defaultSection:
   "center"`, `displayName` = the agent's name/number, and a `component` that is the
   **cached** `() => <AgentPanel taskId={taskId} />` (cache keyed by the panel id so
   the reference is stable across rebuilds). Include the live status dot as
   `tabIcon` (reuse today's status-dot reader).
3. **AGENT-09 numbering:** when naming unnamed agents (e.g. "Agent 2"), reuse the
   lowest available number after deletions (mirror today's numbering logic — grep
   for the existing agent-tab numbering and reuse it).
4. Confirm zero/one/multiple agents work: zero agents → center shows the empty state
   (Task 2.4's `EmptySectionState`); multiple agents → multiple `agent:*` panels can
   be placed in different sections (AGENT-03). The center-targeting of new agents
   (Cmd+Shift+T / Cmd+K) is Task 4.5/3.5; closing-an-agent = delete confirmation is
   Task 3.7.

## Testing suggestions

- AGENT-01..03/09 e2e land in Task 3.7 (`test_agent_panel.py`). A smoke check (the
  center section renders the chat for the active agent after cutover) lands in Task
  2.7.
- AGENT-05 (two agents streaming concurrently) is a dedicated regression test in
  Task 3.7 — the identity cache + independent data subscriptions here are what make
  it pass.

## Gotchas

- **Reuse, don't rewrite** the chat — `goals.md` preserves all existing chat
  functionality and the test plan keeps ~all chat-content tests as-is.
- The wrapper must not read layout state (keep it shell-agnostic).
- The agent component **must be identity-cached per id** (Task 1.6) or the chat
  remounts on every task tick (violating SWITCH-02 and dropping streaming state).
- Reuse the existing numbering logic for AGENT-09 rather than inventing a new scheme.

## Verification checklist

- [ ] `AgentPanel({ taskId })` renders the existing chat surface and reads no layout
  state.
- [ ] `dynamicPanels.tsx` derives `agent:<taskId>` defs with cached component
  identity and lowest-available-number display names.
- [ ] Zero/one/multiple agents supported; an agent can live in center and right at
  once.
- [ ] No changes to the chat components themselves.
- [ ] `just check` passes.
