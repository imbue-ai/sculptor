# Component hierarchy

This document describes the **React component tree** for the workspace redesign:
the shell, the uniform section/panel components, the drag-and-drop architecture,
and — critically — the **memoization boundaries** that keep dragging, resizing,
and workspace switching from cascading re-renders.

`goals.md` is the source of truth for behavior; this tree realizes it.
`state_design.md` describes the state these components consume.
`design_extraction.md` maps which prototype components/styles to copy forward.
Intended final file names and locations, and the full per-component subscription
list, are in `supplemental/component_tree.md`.

> **Rewrite, not a refactor.** Components are named with `goals.md` vocabulary
> (Section, SubSection, panel, active section, maximized) and the deprecated
> components (DockingLayout, the left/right zone sidebars, Zen/Focus mode chrome,
> the `/btw` popup, the old top bar) are not carried forward. The prototype's
> structure is the reference for *shape*; its names and dead code are not. See
> `supplemental/naming_map.md`.

## Principles

1. **One uniform section component.** Left, center, right, and bottom are the same
   `PanelSection` component (`goals.md` → "Sections"). A split sub-section is just
   another `PanelSection`. There is no special-cased "chat area" or "terminal
   area" — chat and terminal are panels.
2. **Content decoupled from shell.** A panel's content component (chat, terminal,
   diff viewer) takes its data from data atoms and its identity — *which* task or
   terminal it is — as an explicit prop (e.g. the chat takes a required `taskId`
   prop, not `useWorkspacePageParams()`). It never reads section/split/size layout
   state or route params. This is what lets the same content components power the
   mobile shell (`state_design.md` → "Mobile") and lets one agent live in center
   while another lives in right (AGENT-03).
3. **Memoization at every heavy boundary.** Shell components that re-render on
   resize/drag/switch sit *above* memoized children with primitive props, so the
   churn stops before it reaches panel content. The boundaries are enumerated
   below and are a hard design requirement, not an optimization afterthought
   (`goals.md` → "Minimize re-renders").

## Top-level tree

```
AppShell
├─ WorkspaceSidebar ............. collapsible vertical nav rail (global)
│   ├─ sidebar top actions ...... home · Cmd+K · new workspace
│   ├─ repo groups .............. collapsible; per-repo add-workspace + settings
│   │   └─ workspace rows ....... status dot · name · hover delete/menu
│   ├─ sidebar bottom ........... settings · report a bug · version
│   └─ sidebar resize handle .... drag right border (min width)
├─ NewWorkspaceModal ........... global; opened via atom (sidebar + · Cmd/Meta+T · Cmd+K · repo +)
│
└─ <route outlet>
    ├─ WorkspacePage (a workspace route)
    │   └─ WorkspaceLayoutShell  (desktop)        ── or ──  MobileWorkspaceShell (mobile)
    ├─ HomePage / empty-workspace first-run
    └─ SettingsPage
```

The **`WorkspaceSidebar`** is global chrome rendered for every route (with the
empty-workspace and collapsed-on-home special cases from `goals.md` → "Workspace
sidebar" / "Empty workspace state"). The desktop vs. mobile decision is a single
`useIsMobile` branch at the page level (`state_design.md` → "Mobile").

## The workspace layout shell

```
WorkspaceLayoutShell
└─ PanelDndProvider .................. single app-level drag-and-drop context
   ├─ WorkspaceHeader ............... simplified header; HIDDEN when a section
   │                                  is maximized (goals.md → "Maximized section")
   └─ SectionGrid ................... the four-section frame + resize handles
       ├─ Section: left   → SplittableSection(primary="left")
       ├─ ResizeHandle (x)
       ├─ Section: center → SplittableSection(primary="center")   ← always present
       ├─ ResizeHandle (x)
       ├─ Section: right  → SplittableSection(primary="right")
       └─ Section: bottom → SplittableSection(primary="bottom")  + ResizeHandle (y)
```

- **`SectionGrid`** owns the geometry: it reads the global section sizes and the
  per-section expanded flags, resolves percentages to pixels (protecting the
  center's minimum width by shrinking the sides first), and renders only the
  expanded sections. It re-renders on resize and on expand/collapse — so its
  children are memoized (below).
- A **maximized** section short-circuits the grid: only the maximized section
  renders, filling the content area, with the workspace header hidden and OS
  window-control padding applied when the sidebar is collapsed (`goals.md` →
  "Maximized section"). The sidebar, if expanded, stays visible.

### Section subtree

```
SplittableSection(primaryZone)              ← memo; subscribes to THIS section's split slice
├─ unsplit:  PanelSection(subSection = primary)
└─ split:    PanelSection(primary)
             ResizeHandle (split axis)
             PanelSection(secondary)

PanelSection(subSectionId)                  ← memo; narrow per-sub-section atoms only
├─ SectionHeader                            ← memo
│   ├─ panel tabs (one per open panel; active highlighted; close button; rename for multi-instance)
│   ├─ add-panel "+"  → AddPanelDropdown    (goals.md → "Adding a panel")
│   └─ maximize toggle
└─ SectionBody                              ← memo; subscribes to the active panel COMPONENT
    ├─ <ActivePanelComponent />             (agent | terminal | files | changes | … )
    └─ EmptySectionState                    when the sub-section has no open panels
```

- **`SplittableSection`** renders one `PanelSection` when unsplit, or the primary
  + a resize handle + the secondary `PanelSection` when split (`goals.md` → "Split
  sections"). It self-heals: when the secondary half loses its last panel it
  collapses the split and the primary reclaims the space.
- **`PanelSection`** is the uniform section. It renders a single section header
  (tabs + add "+" + maximize) and the body. It subscribes only to *narrow*
  per-sub-section atoms (is-drop-target, is-active-section, is-ring-visible,
  is-this-maximized); heavy state lives behind its children's memo boundaries.
- **`SectionHeader`** renders the tab strip and the add-panel dropdown. Per
  `goals.md` → "Adding a panel", the dropdown pins recent-agent creation (with its
  Cmd+Shift+T binding), then new terminal, then every single-instance panel not
  already open. (The new-agent binding and Cmd+K always create the agent in the
  center section regardless of the active section.)
- **`SectionBody`** renders the active panel's component, or the
  `EmptySectionState` launcher (`goals.md` → "Section empty state": a centered
  add-panel button plus up to five quick actions, and a "close split" affordance
  when the empty pane is a split half). It subscribes to the *resolved component*
  for the active panel (stable identity per panel id), so registry rebuilds and
  tab churn never remount live panel content.

## The panel registry and dynamic panels

```
PanelRegistryProvider
├─ static panel definitions ....... Files, Changes, Commits, Review All,
│                                    Actions, Skills, Browser, Notes   (single-instance)
└─ dynamic panel definitions ...... one AgentPanel per task, one TerminalPanel
                                     per terminal, for the ACTIVE workspace
                                     (multi-instance, renamable)
```

The registry is hydrated into a Jotai atom and kept in sync as panels are toggled
or the workspace switches. Dynamic agent/terminal definitions are derived from the
task/terminal data atoms; their component identities are cached by id so rebuilding
the registry (which happens on every task tick) never remounts a live panel. A
panel's content component is decoupled from the shell (principle 2) — e.g. the
agent panel wraps the existing chat interface, the terminal panel wraps the xterm
container, and Files/Changes/Commits each wrap an explorer (file list + diff
viewer). Registry details, panel kinds, and the add/close/rename/confirmation
rules are in `supplemental/panel_registry.md`.

## Workspace creation modal

The `/ws/new` page and its draft pseudo-tab are removed (`goals.md` → "New workspace
dialog"). Creation moves into a single global **`NewWorkspaceModal`**, opened from
anywhere via a transient atom — the sidebar `+`, Cmd/Meta+T, Cmd+K, or a repo group's
`+` (which pre-selects that repo). The modal is **rebuilt reusing this branch's
existing creation pieces**; only the prototype's *styling and shape* are copied (the
`PaletteDialog` shell, the branch-name pill, the title + prompt + context-pill + footer
layout). The prototype's own form component is **not** copied — it is coupled to APIs
that diverged from this branch.

```
NewWorkspaceModal                    opened/contextualized by the modal atom
└─ PaletteDialog (shell)             ← prototype styling (opaque Raycast dialog)
   └─ NewWorkspaceForm
      ├─ title input + auto-growing prompt textarea
      ├─ context pills: RepoSelector · AgentTypeSelect · ModeSelect · BranchSelector
      ├─ BranchNameField             (monospace pill; sanitize / shuffle / error slot)
      └─ footer: "keep open" · Cmd+Enter hint · Create
```

- **Reused as-is from this branch** (data via props, no `/ws/new` coupling):
  `RepoSelector`, `BranchSelector`, the branch-name field + its branch-name-preview
  hook, the repo-info hook, and the projects / agent-type atoms.
- **Extracted from today's add-workspace page** (inline JSX → components):
  `AgentTypeSelect` and `ModeSelect` (the agent-type and worktree/clone/in-place
  pickers).
- **New (not in today's form):** the auto-growing **prompt textarea** — today's form
  creates the first agent with no prompt; the modal adds one and passes it to the
  create flow (the empty first-run prefills `/sculptor:help`, `goals.md` → "Empty
  workspace state").
- **Create flow:** factored out of today's add-workspace page submit handler into a
  single `useCreateWorkspace` hook (the two-step create-workspace → create-first-agent),
  **decoupled from the draft pseudo-tab model** (which is deleted). On success it
  navigates to the new agent; "keep open" resets the form but retains repo + agent type.

The **empty first-run** page (`goals.md` → "Empty workspace state") renders the **same**
`NewWorkspaceForm` inline (no modal chrome), gated on the workspace-list-empty atom.
Atoms are in `supplemental/state_atoms.md` → "Workspace creation"; the file layout +
the reuse-vs-copy list are in `supplemental/component_tree.md`.

## Drag-and-drop architecture

A single app-level **`PanelDndProvider`** wraps the whole layout. Each
`PanelSection` registers its body as a drop target (keyed by sub-section id) and
each tab as a draggable, so a tab can be dragged between sections, reordered within
a section, or dropped onto a collapsed section (which expands on drop). During a
drag, only the **transient drag-preview** state updates (`state_design.md` → "Drag
preview"); the real placement state is mutated once, on drop.

The provider subscribes only to the **stable dragged-panel id** (constant for the
whole drag), not the moving preview, so it does not re-render on every pointer
move. Sections subscribe to **narrow per-section slices** of the preview
(is-this-the-drop-target, the ghost panel for this section), so a pointer move
re-renders only the sections under/around the cursor. This is the crux of keeping
drag interactions cheap.

## Memoization boundaries (required)

This table is the contract for `goals.md` → "Minimize re-renders". Each boundary
is a memoized component subscribing to a *narrow* slice; churn above it must not
reach below it. (Exact atom names are in `supplemental/component_tree.md`.)

| Component | Re-renders when… | Memo boundary protects… | Why it holds |
|---|---|---|---|
| `SectionGrid` | section size or expand/collapse changes | the `SplittableSection` children | children are memoized with primitive props (sub-section id, side) |
| `SplittableSection` | *its* section's split state/ratio changes | the other sections | subscribes to a per-section split slice, not the whole split map |
| `PanelSection` | its drop-target / active-section / ring / maximized flags flip; dnd `over` changes | `SectionHeader` + `SectionBody` | subscribes only to narrow per-sub-section atoms; stays cheap |
| `SectionHeader` | this section's open-panel set or active panel changes | the panel content | tab list is a shallow-equal-deduped slice; tab drag uses a per-section ghost slice |
| `SectionBody` | the active panel's *resolved component* changes | the live panel content | component identity is cached per panel id → no remount on registry rebuild or switch |
| `PanelDndProvider` | the dragged panel id changes (drag start/end) | everything during the drag | subscribes to the stable dragged id, not the moving preview |
| active-section ring | the ring fade timer fires for *this* section | every other section | per-section ring-visible slice; the timer flips one section only |

The acceptance bars in `goals.md` ("each panel mounts at most once per switch",
"zero layout-shift frames") are verified with the existing render-count and
workspace-switch-profiler tooling.

## Maximize and active-section presentation

- **Maximize** is driven by the transient maximized-section state. When set, the
  grid renders only that section full-bleed, the workspace header is hidden, and
  (when the sidebar is collapsed) OS window-control padding is applied to the
  section header. A split maximized section shows only one sub-section.
- **Active-section ring** is a transient overlay on the active `PanelSection`. It
  pulses on a deliberate jump (keyboard cycle, add/drop, workspace entry) and
  fades within ~2 seconds; a plain click sets the active section without flashing
  it (`goals.md` → "Active section"). The fade is a per-section concern so it never
  re-renders other sections.

## Mobile shell variant

```
WorkspacePage
└─ useIsMobile()  ─── true ──►  MobileWorkspaceShell
                                ├─ MobileWorkspaceHeader (drawer toggle, agent/changes pills)
                                ├─ ChatPanelContent (full-screen, reused; explicit taskId prop)
                                └─ overlays: review-all, terminal, agent sheet, workspace drawer
                   ─── false ─►  WorkspaceLayoutShell  (everything above)
```

The mobile shell is a sibling branch at the page level, not a fork of the state
model. It **reuses the same content components** (the chat surface, the diff
viewer, the terminal) and the same **data atoms**, but it renders a single
full-screen panel instead of the section grid and **does not mount the layout
shell** — so it consumes none of the section/split/size state and leaves desktop
layouts untouched. The workspace sidebar becomes a slide-in drawer. Detection is
the single `useIsMobile`/`useLayoutMode` hook. See `state_design.md` → "Mobile".

## Related documents

- `goals.md` — source of truth for behavior.
- `state_design.md` — the state model these components consume.
- `design_extraction.md` — which prototype components/styles to copy forward.
- `supplemental/component_tree.md` — intended final file names/locations and the
  full per-component subscription list.
- `supplemental/panel_registry.md` — panel definitions, kinds, and lifecycle rules.
- `supplemental/naming_map.md` — prototype → rewrite rename table.
