# Compact workspace layout — agent-lifecycle simplification (follow-up)

This doc records a proposed follow-up to the compact-workspace-layout work:
**simplify how agents are added and removed** so that an agent tab is just the
agent — closing it deletes it — and remove the "move / re-open existing agent"
machinery (the panel pool + the cmd+k / "+" picker entries that re-place a
still-alive agent).

It is a **work list and a set of decisions**, not a description of shipped
behavior. Re-grep before editing — other in-flight branches touch these files.

---

## 0. The two things that prompted this

1. **"Why can't I close an agent?"** When a workspace has exactly **one**
   agent, that agent's tab renders **without** a close (X) button (see the
   screenshot: `Agent 1` with only a status dot). This is intentional today —
   see §1 — but it reads as a bug.
2. **Agent "removal" today is really a move, not a delete.** Closing an agent
   tab *unplaces* the panel (it returns to a pool of "open existing" agents you
   can re-add from the "+" picker), while *deleting* is a separate, explicit
   action behind a context menu / cmd+k. We carry a fair amount of code to
   support that "unplaced but alive" middle state. The proposal is to collapse
   the two: **removing an agent deletes it**, and the move/re-open paths go
   away.

---

## 1. Why the only agent has no close button (current behavior)

`SectionTabBar.tsx` decides per tab whether to show a close affordance:

```ts
// SectionTabBar.tsx — tab definition
closeable: isAgentPanelId(panelId) && !hasMultipleAgents ? false : undefined,
```

- `hasMultipleAgents` comes from `hasMultipleAgentPanelsAtom`
  (`pages/workspace/panels/panelDerivedAtoms.ts`): true only when **>1** agent
  panel is placed anywhere in the layout.
- So when there's a single agent, `closeable` is `false` and no X renders.

The rationale (comment in `SectionTabBar.tsx`):

> The only/active agent can't be closed (there's nothing to fall back to and the
> bootstrap keeps the URL agent visible), so its close affordance is hidden
> rather than shown as a silent no-op. Relocating it via drag is still allowed.

And `handleClose` bails for the same reason:

```ts
const otherAgent = Object.keys(zoneAssignments).find((id) => isAgentPanelId(id) && id !== panelId);
if (!otherAgent) return; // can't close the only/active agent
```

The motivation is the **bootstrap invariant**: the workspace always keeps the
URL's agent on screen, so "closing" the last agent would have nothing to show.
The fix for the complaint is therefore tied up with deciding what an empty
workspace (zero agents) should look like — see §4, Decision B.

> Note: with the always-visible compact close button (the just-shipped tab-X
> change), an agent tab still shows no X when `closeable === false`, because the
> compact strip only renders the button when the tab is closeable. So the gate
> above is the single source of truth.

---

## 2. Current agent lifecycle (what exists today)

### a. Close tab (X) → *unplace*, not delete
`SectionTabBar.handleClose` → `useRemovePanelFromSection` (`sectionHooks.ts`):

> Remove a panel from its section (the tab's close button). The panel becomes
> "unplaced" — available again in every section's "+" dropdown.

It deletes the panel's entry from `zoneAssignmentsAtom` / `zoneOrderAtom` and
collapses/un-splits the emptied section. The **agent itself is untouched** — it
stays in `tasksArrayAtom`, so its panel definition stays in the registry
(`dynamicPanels.tsx`, `useWorkspaceDynamicPanels`).

### b. The "unplaced but alive" pool
`useAddableDynamicPanels("agent")` (`sectionHooks.ts`) = agents with **no zone
assignment**. These surface as:

- **`AddPanelPalette.tsx`** root page → **"Open existing agent"** row
  ("Move an existing agent into this section"), drilling into an `agents`
  sub-page that lists each unplaced agent. Selecting one calls
  `menu.openPanel(id)` → `useAddPanelToSection` → `movePanel` (re-places it).
- The same pool/menu data comes from `useAddPanelMenu` (`existingAgents`,
  `openPanel`).

### c. Switch to an existing agent via cmd+k
`components/CommandPalette/dynamic/agentCommands.ts` — **"Go to agent…"** page
plus one row per agent, calling `runtime.navigate.toAgent(workspaceId, agentId)`
(navigates / focuses; does not delete). This is the "open existing" path in the
command palette proper.

### d. Delete an agent (the real, destructive action)
- Triggered from: the tab **context menu** ("Delete agent",
  `SectionTabBar.contextMenuContent`) and the cmd+k **"Agent actions…"** page
  (`dynamic/agentActions.ts` + `contextActions/agentActions.ts`).
- Both set `agentDeleteTargetAtom` (`contextActions/atoms.ts`).
- `AgentWorkspaceCommands.tsx` owns the `DeleteConfirmationDialog`; confirming
  runs `useOptimisticTaskDelete` → `deleteWorkspaceAgent`
  (`DELETE /api/v1/workspaces/{id}/agents/{id}`), with optimistic removal and
  post-delete navigation.

### e. Create an agent
`AddPanelPalette` "New {type} agent" fast-path + "Choose agent type…" sub-page →
`useAddPanelMenu.createAgent` → `createWorkspaceAgent`, then `movePanel` +
`navigateToAgent`. Also cmd+k "New agent" (`builtinCommands/navigation.ts`).

---

## 3. Proposed model: "the tab **is** the agent"

Every live agent has exactly **one** tab, always placed in a section. There is
no "closed-but-alive" agent state. Concretely:

- **Close (X) on an agent tab = delete the agent** (with confirmation — see
  Decision A). The middle-click close path becomes delete too.
- **No move / re-open of existing agents.** Since agents are never unplaced,
  the "open existing agent" pool is always empty and its UI is removed.
- **Create** stays exactly as-is (fast-path + Choose agent type; cmd+k New
  agent).
- **Drag to relocate** an agent tab between sections is unaffected — that moves
  a *placed* panel between zones; it never creates an unplaced state. (Confirm
  we want to keep drag; it's the one legitimate "move" and doesn't conflict with
  delete-on-close.)

This makes the agent tab strip a faithful, always-complete view of the
workspace's agents: what you see is every agent, and the only ways to change the
set are **create** and **delete**.

---

## 4. Decisions

**Decision A — Confirm on close? → YES.** The tab X (and middle-click) routes
through the existing `DeleteConfirmationDialog` by setting `agentDeleteTargetAtom`,
so close and the context-menu "Delete agent" share one confirm + optimistic
delete path (`AgentWorkspaceCommands` → `useOptimisticTaskDelete` →
`deleteWorkspaceAgent`).

**Decision B — Last agent / empty workspace? → B2 (always keep ≥1 agent).**
Deleting the last agent immediately creates a fresh agent of the last-used type.

  **This is already the implemented behavior** — no new work, and the riskiest
  code (routing + bootstrap) stays untouched:
  - `AgentWorkspaceCommands.handleNavigateAfterDelete` already calls
    `createAgent()` when the deleted agent was the last one; otherwise it
    navigates to the neighbouring agent.
  - Because the X reuses that same delete flow (Decision A), close-the-last-agent
    inherits the auto-create for free.
  - `WorkspacePage` returns `null` when the URL has no `agentId`, and
    `useWorkspaceLayoutBootstrap` only places the URL agent — neither needs to
    learn a zero-agent state.

  Rejected alternatives:
  - **B1 (allow zero agents).** Honest "deleted = gone" + a real empty-workspace
    state, but more surface area and the most risk: remove the auto-create, make
    `WorkspacePage` render with `agentId === undefined`, teach the bootstrap +
    route-fallback (`WorkspacePage` redirect effect) about zero agents, and
    design an empty-workspace page (the per-section `EmptyPanelLauncher` exists,
    but the whole page currently bails to `null`).
  - **B3 (block deleting the only agent).** Status quo — the exact behavior being
    complained about.

  Known B2 headache (accepted): deleting the last agent instantly spawns a blank
  replacement, so a workspace can never be emptied. With confirm-on-close this
  reads as "confirm delete → a new agent appears," which can momentarily
  surprise. Judged acceptable: a workspace's whole point is to hold a live chat,
  and this matches "closing the last tab keeps one" behavior common in editors.

**Decision C — cmd+k "Go to agent…". → KEEP (as a pure focus-switch).** The list
in `dynamic/agentCommands.ts` only *navigates* to an agent; it does not re-place
or move one, so it doesn't conflict with the new model. It's left untouched —
losing keyboard agent-switching would be a downgrade, and it's now also the
primary way to surface an agent that exists but isn't currently a tab (e.g. one
created in another session and not in the persisted layout): navigating to it
bootstraps it into the Center.

**Decision D — Terminals? → SAME TREATMENT.** Terminals get close = delete +
confirm too, removing their "unplaced but alive" pool and the "Open existing
terminal" palette entries (`useAddableDynamicPanels("terminal")`).
  - Close (X) on a terminal tab → kill it (`removeTerminal` →
    `closeWorkspaceTerminal`) behind a confirmation, instead of unplacing.
  - **No auto-respawn / no "must keep one" for terminals** — they already allow
    zero (the Bottom zone just empties to `EmptyPanelLauncher`). So terminals are
    effectively B1 while agents are B2; this asymmetry is intentional (a
    workspace needs a chat; it doesn't need a shell).
  - Sub-question: is a confirm dialog warranted for terminals (killing a shell
    loses no durable history, unlike an agent)? Defaulting to confirm for
    symmetry; flag if that feels heavy.

---

## 5. Change inventory (once decisions are made)

Routing close → delete and dropping the move/re-open paths touches:

- **`components/panels/SectionTabBar.tsx`**
  - `closeable`: drop the `!hasMultipleAgents` gate so every agent tab shows the
    X (resolves §0.1).
  - `handleClose`: for agent panels, set `agentDeleteTargetAtom` (the confirm +
    delete flow, Decision A) instead of `removePanel`; for terminal panels,
    likewise route to a confirm + `removeTerminal` (Decision D). Keep
    `removePanel` for static panels. The agent-only-close no-op branch goes away.
  - Context-menu "Delete agent" / "Close terminal" become redundant with the X —
    decide whether to keep them (probably drop, or keep "Delete agent" as a
    discoverable duplicate).

- **`components/panels/sectionHooks.ts`**
  - `useAddableDynamicPanels` becomes dead for BOTH `"agent"` and `"terminal"`
    (always empty) — remove it and its callers.
  - `useRemovePanelFromSection`: still used by static panels; the agent/terminal
    callers change. Don't gut it.

- **`pages/workspace/panels/panelDerivedAtoms.ts`**
  - `hasMultipleAgentPanelsAtom` loses its only consumer (the `closeable` gate) —
    remove if nothing else uses it.

- **`components/panels/AddPanelPalette.tsx`**
  - Remove the **"Open existing agent"** and **"Open existing terminal"** root
    rows + the `agents` / `terminals` sub-pages (`menu.existingAgents`,
    `menu.existingTerminals`, the `ExistingPage` usages). Keep "New agent",
    "Choose agent type…", "New terminal", and static panels.

- **`pages/workspace/panels/useAddPanelMenu.ts`**
  - Drop `existingAgents` / `existingTerminals` and the dynamic-panel `openPanel`
    path; keep `createAgent` / `createTerminal`.

- **`components/CommandPalette/dynamic/agentCommands.ts`** (Decision C — open)
  - Remove (or repurpose as pure focus-switch) the "Go to agent…" list.

- **Keep as-is (the X reuses this plumbing):**
  - Agents: `AgentWorkspaceCommands.tsx` + `DeleteConfirmationDialog` +
    `useOptimisticTaskDelete` + `deleteWorkspaceAgent`, **including
    `handleNavigateAfterDelete`'s auto-create-on-last (this IS Decision B / B2)**.
  - Terminals: `removeTerminal` / `closeWorkspaceTerminal` (wrap with the confirm
    dialog).
  - The whole **create** flow (agents and terminals).

- **Bootstrap / routing — no change needed for B2.**
  `useWorkspaceLayoutBootstrap` (places the URL agent in Center) and
  `WorkspacePage` (returns `null` without an `agentId`; redirect effect picks the
  saved/first agent) stay as-is, because a workspace never reaches zero agents.
  (This is the main reason B2 was chosen over B1.)

- **Tests:** integration tests are already mid-migration (see
  `integration-test-followup.md`); the "open existing agent/terminal" / re-add
  flows and the only-agent no-close assertion will need updating alongside this.
  Unit tests touching `useRemovePanelFromSection` / `hasMultipleAgentPanelsAtom` /
  the palette pages move too. Add coverage for: X-on-agent → confirm → delete;
  delete-last-agent → auto-create; X-on-terminal → confirm → kill → empty Bottom.

---

## 6. Status / out of scope

**Implemented** (all four decisions resolved above): close = delete + confirm for
agents and terminals; the only-agent close gate is gone; the
move/re-open-existing machinery (`useAddableDynamicPanels`,
`useAddPanelMenu.existingAgents/existingTerminals`, the AddPanelPalette "Open
existing agent/terminal" rows + sub-pages, `hasMultipleAgentPanelsAtom`) is
removed; B2 auto-create-on-last is inherited from the existing delete flow; cmd+k
"Go to agent…" is kept as a focus-switch.

Out of scope:
- Workspaces that relied on closing-to-declutter (agents *or* terminals) lose
  that ability — closing now deletes. A separate hide/collapse concept is
  explicitly **not** part of this work.
- Drag-relocate of agent/terminal tabs between sections survives (it moves a
  placed panel; it never creates an unplaced state — see §3).
- Integration-test updates ride along with the existing migration
  (`integration-test-followup.md`).
