# UI state design

This document describes the **UI state model** for the workspace redesign: what
state exists, how it is scoped, how it is persisted, and how that model satisfies
the non-functional behavior in `goals.md`.

`goals.md` is the source of truth for behavior — this document must stay
consistent with it and is written in its vocabulary (section, sub-section, panel,
open vs. active panel, collapsed/expanded, maximized, active section, split). The
companion `component_hierarchy.md` covers the React component tree that consumes
this state, and `design_extraction.md` covers styling. Concrete type and atom
signatures live in the companion documents under `supplemental/` (referenced
throughout); this document stays at the level of model and rationale.

> **On the prototype.** The `bryden/scu-1474-compact-workspace-layout` branch
> already implements most of this model. We treat the redesign as a **rewrite**:
> the model below renames everything to `goals.md` vocabulary and removes the
> deprecated/experimental state the prototype still carries. See
> `supplemental/naming_map.md` for the old→new rename table. Do not anchor to the
> prototype's in-branch notes — only its code.

## Goals this model must satisfy

These come directly from `goals.md` → "Non-functional Behavior" and "Sections".
Every decision below traces back to one of them:

1. **Seamless workspace switching.** On switch, the sidebar, workspace header,
   every section header, and the section frames at their persisted sizes are
   present in the *first committed frame* — no layout shift, no delayed or
   duplicated renders. This requires a **pre-paint, single-read layout restore**.
2. **Minimize re-renders.** Dragging, resizing, and switching must not cascade
   re-renders across the tree. This requires **narrow, per-section/per-panel state
   subscriptions** and explicit memoization boundaries (the boundaries themselves
   are documented in `component_hierarchy.md`).
3. **Consolidated, swappable persistence.** UI state is consolidated and
   persisted, with the per-workspace vs. global split from `goals.md`. We are
   moving toward a hosted web Sculptor that may persist layouts in a backend, so
   the **storage backend must be swappable** (localStorage today → backend API
   later) without reworking the state model.
4. **Mobile-ready.** A mobile variant (branch `bryden/mobile-frontend`) reuses the
   same content and data, with a different layout shell. The model must keep
   **layout state separate from content/data state** so the mobile shell can
   simply not consume the layout state.

## State library: Jotai

We keep **Jotai** as the UI state library.

- Its `atomFamily` gives us per-workspace scoping as a first-class primitive (one
  family keyed by workspace id), and switching scope is a single atom write.
- Its derived atoms (`selectAtom` with custom equality) give us the **narrow
  subscriptions** goal (2) demands: a component subscribes to exactly the slice it
  renders, and re-renders only when that slice changes — not when unrelated layout
  state churns during a drag or resize.
- Synchronous reads make the **pre-paint restore** in goal (1) achievable: the
  first render reads the restored layout straight out of memory.

Content/data continues to use its existing atoms (tasks, terminals, diffs, etc.);
this document is only about *layout/UI* state.

## The state, by concern

The model has three buckets, distinguished by **scope** — this is the central
organizing idea and maps directly to `goals.md` → "Sections":

| Bucket | Scope | Persisted? | Examples |
|---|---|---|---|
| **Global layout** | Shared across all workspaces | Yes | Section sizes, sidebar width, sidebar collapsed, panel-internal view prefs (e.g. file-tree width) |
| **Per-workspace layout** | Independent per workspace | Yes | Which sections are expanded, the open-panel set + placement, tab order, active panel, split state, active section |
| **Transient** | Current session only | No | Maximized section, drag preview, active-section highlight ring |

`goals.md` is explicit about the split: *"Section sizes are global: they are
shared across all workspaces."* and *"Section visibility (collapsed/expanded), the
set of open panels, and which panel is active are stored per workspace and are
independent between workspaces."* Split state and active section are part of a
workspace's arrangement, so they are per-workspace too. The **split ratio** rides
with the per-workspace split (a split that exists only in one workspace cannot
have a globally shared ratio).

### Sections and sub-sections (the flat keyspace)

`goals.md` → "Sections" / "Split sections" defines four sections — **left,
center, right, bottom** — each of which can be split into **exactly two
sub-sections** (at most one split per section). A panel always lives inside a
*sub-section*.

We identify sub-sections with a **flat keyspace**:

- A section's id is one of `left | center | right | bottom`.
- When a section is **not** split it has one sub-section, the **primary**, whose
  id *is* the section id.
- When a section is split it gains a **secondary** sub-section, identified by
  suffixing the section id (e.g. the secondary half of `left` is `left:secondary`).

```
section "left"  (unsplit)         section "center" (split, vertical)
┌──────────────┐                  ┌──────────────┬──────────────┐
│ sub-section  │                  │ sub-section  │ sub-section  │
│   "left"     │                  │  "center"    │"center:      │
│  (primary)   │                  │ (primary)    │   secondary" │
└──────────────┘                  └──────────────┴──────────────┘
```

Every piece of per-sub-section state (open panels, order, active panel) is keyed
by sub-section id, so the **primary and secondary halves run through the exact
same machinery** — a split sub-section is just another addressable container.
This keeps the component tree uniform (see `component_hierarchy.md`) and is the
clean rewrite of the prototype's `:split` zones.

Split geometry follows `goals.md` → "Split sections": left/right split
top/bottom, bottom splits left/right, center splits either direction. The split
state records the axis and the primary half's ratio. Closing a split (from the
empty sub-section) merges the remaining panels back into the single section.

### Panel placement, tabs, and the active panel

Per `goals.md` → "Sections" / "Panels", a sub-section holds **N open panels**, one
**active**. Three per-workspace pieces capture this, all keyed by sub-section id:

- **Placement** — a panel → sub-section map. A panel's presence in this map *is*
  its "open" state; removing it closes it (returns it to the unplaced pool, where
  it is offered again by the add-panel "+").
- **Order** — the tab order within each sub-section.
- **Active panel** — which open panel is active (its content is shown) per
  sub-section.

Section **expanded/collapsed** is a separate per-workspace map over sections.
Center is always expanded and is never in the collapsed set (`goals.md` →
"Collapsed vs. expanded"). Collapsing preserves a section's open panels and active
panel, restored on expand. An invariant the model enforces: a section shown as
expanded must have at least one open panel — an empty-but-expanded section shows
the section empty state (`goals.md` → "Section empty state"), which is valid, but
a *collapsed* flag never hides a section that the user can see content in.

### Section sizes (global)

Global sizes are stored as the left/right section widths and the bottom section
height, expressed as percentages of the workspace content area; the center fills
the remainder. At render time these resolve to pixels with the floors from
`goals.md` / `design_extraction.md` (center keeps a minimum width; sides have a
floor; sides give way before the center shrinks). The sidebar width and the
shared file-tree (master-detail) width are likewise global. See
`design_extraction.md` for the concrete pixel floors and `supplemental/persistence_interface.md`
for the stored shape.

### Active section and the highlight ring

`goals.md` → "Active section": the active section is the last one interacted with;
a collapsed section cannot be active; it defaults to center when nothing else
qualifies (e.g. on workspace load); the keyboard cycle steps through split
sub-sections; and on cycle / on workspace load it is briefly highlighted with a
ring that fades within ~2 seconds.

Because the cycle steps through *sub-sections*, the model tracks the **active
sub-section** (a `SubSectionId`, which may be a split half). "Active section" in
`goals.md` is the section that contains the active sub-section. This is
per-workspace and persisted, so re-entering a workspace restores where the user
was working — and re-pulses the ring as a wayfinding cue.

The **ring is a separate, transient layer** from the logical active section:

- The logical active sub-section *persists* (it survives reload and workspace
  switches).
- The ring's *visibility* is transient — it flashes on a deliberate jump
  (keyboard cycle, adding/dropping a panel, workspace entry) and fades after
  ~2 seconds. A plain click sets the active section **without** flashing the ring,
  so the ring stays wayfinding, not steady-state chrome.

Splitting these two concerns is what lets a single fade timer touch only the one
highlighted section rather than re-rendering every section (goal 2).

### Maximized section (transient)

`goals.md` → "Maximized section": one section at a time fills the workspace content
area; when the maximized section is split, only one sub-section is shown. This is
**transient (non-persisted)**: maximize is a modal-ish view, so reload always
returns to the normal layout and a stale flag can never strand the app maximized.
A keyboard shortcut maximizes/restores the active section.

### Drag preview (transient)

Dragging a panel tab between sections is previewed without committing: the model
holds an in-flight drag-preview value (dragged panel, target sub-section,
insertion index) that the real placement state ignores until drop. This is
non-persisted and exists only to drive the live preview. Critically, components
subscribe to **narrow per-section slices** of it (is-this-section-the-drop-target,
the ghost panel for this section) rather than the whole drag value, so a pointer
move during a drag re-renders only the affected sections (goal 2). The drag
architecture itself is in `component_hierarchy.md`.

### Panel registry

Panels are described by a **registry** (`goals.md` → "Panels"): a list of panel
definitions (id, display name, icon, kind, default placement, the component to
render, context-menu actions, etc.). Two layers feed it:

- **Static panels** — Files, Changes, Commits, Review All, Actions, Skills,
  Browser, Notes. Single-instance.
- **Dynamic panels** — one **agent** panel per task and one **terminal** panel per
  terminal, for the *active* workspace only. These are the only **multi-instance**
  panels, and they are renamable (`goals.md` → "Panels"). Their ids embed the
  task/terminal identity, so they cannot live in a static config; they are derived
  from the task/terminal data atoms and merged into the registry at runtime.

The registry is the join point between layout state (which references panels by
id) and content (which renders them). Panel keyboard shortcuts, context-menu
actions, and Cmd+K entries are all attached via the registry; per `goals.md`,
panel shortcuts are configured on the **keybindings settings page** (not the
deprecated Panels settings page). Single- vs. multi-instance and the
add/close/rename rules are detailed in `supplemental/panel_registry.md`.

## Scoping: one atomic workspace switch

Every per-workspace layout atom is an `atomFamily` keyed by the **active layout
scope** (the active workspace id, or a global sentinel when no workspace is
shown). The atoms the rest of the app reads are thin **proxies** that resolve the
active scope on each read/write:

```
                    activeWorkspaceIdAtom ── "ws-42"
                              │
                              ▼
   read/write  ──►  proxy  ──►  family("ws-42")  ──►  persisted snapshot for ws-42
                              ▲
   (switching workspace = one write to activeWorkspaceIdAtom;
    every proxy now resolves to the new workspace's snapshot,
    atomically, in the same commit)
```

Switching workspaces is therefore a **single atom write** (`activeWorkspaceIdAtom`)
that flips the *entire* layout in one store transaction — there is no
save-then-restore copy between workspaces, and no frame in which the previous
workspace's layout renders under the new workspace's URL. On a workspace's first
visit, the same switch action seeds its default layout (`goals.md` → "Default
layout"). The full switch sequence (including how the registry and the dynamic
agent/terminal panels are placed in the same pre-paint flush) is in
`supplemental/persistence_interface.md`.

This mechanism is the backbone of the "seamless switching" acceptance bar.

## Persistence and the swap boundary

This is the part the prototype does *not* yet have and the redesign must add for
the hosted-web future.

### Consolidated snapshots

Instead of scattering per-workspace layout across many storage keys (as the
prototype does), the model **consolidates** each scope into a single serializable
snapshot:

- **`WorkspaceLayoutState`** — one object per workspace: placement, order, active
  panel, section expanded/collapsed, split state, active section.
- **`GlobalLayoutState`** — one object: section sizes, sidebar width/collapsed,
  panel-internal view prefs.

Consolidation satisfies `goals.md` → "Persistence" (*"UI state is consolidated"*)
and maps cleanly onto a backend: one row per workspace, one global row per user.

### The persistence adapter

All reads and writes go through a single **`LayoutPersistenceAdapter`** interface.
The state model never talks to `localStorage` (or any backend) directly:

```
   Jotai layout atoms  ◄────read snapshot────  LayoutPersistenceAdapter
   (in-memory, the          ────write snapshot──►   ├─ LocalStorageLayoutAdapter   (today)
    sync read source)       ────remove scope────►   └─ BackendLayoutAdapter        (later)
```

- **Reads are always synchronous** from the in-memory atoms — this is what makes
  the pre-paint restore possible. The adapter's job is to *populate* that memory
  and to *flush* changes back.
- **`LocalStorageLayoutAdapter`** (today): reads are a synchronous
  `JSON.parse(localStorage[...])` on first access; writes are debounced/coalesced
  `setItem`s.
- **`BackendLayoutAdapter`** (later): the snapshot is **prefetched** into the
  in-memory cache before the workspace renders (on app load, navigation intent, or
  hover), so the synchronous read still finds it. When it is not yet present, the
  shell shows the last-known layout or an in-place skeleton and updates when the
  fetch resolves — never a spinner (`goals.md` → "Workspace switching should look
  seamless"). Writes are debounced PUTs.

Swapping the backend is a one-line change of which adapter is installed; no atom
or component changes. The full interface, snapshot shapes, the hydrate/restore
sequence, and scope deletion are in `supplemental/persistence_interface.md`.

### No backwards compatibility

Per `goals.md`, we do **not** migrate layouts created before this work. "Persisted"
means state created on this branch. The adapter reads only the new consolidated
keys/rows; old keys are ignored (and the rewrite stops writing them).

## How the model meets the non-functional bars

- **Seamless switching (goal 1).** Layout restore is a single synchronous read,
  applied in a pre-paint (layout-effect) flush along with the registry swap and
  dynamic-panel placement, so the first committed frame already shows the full
  layout at persisted sizes. Content is prefetched or shown stale-then-updated;
  the shell never shows a spinner. (See the switch sequence in
  `supplemental/persistence_interface.md`.)
- **Minimize re-renders (goal 2).** Every subscription is a narrow per-section or
  per-panel slice (placement, active panel, drop-target, split ratio, ring), so a
  drag/resize/switch notifies only the sections it actually touches. The
  memoization boundaries that turn these narrow subscriptions into skipped renders
  are enumerated in `component_hierarchy.md`.
- **Consolidated, swappable persistence (goal 3).** One snapshot per scope behind
  one adapter interface, with the per-workspace vs. global split above.
- **Mobile-ready (goal 4).** See next section.

## Mobile

The mobile variant (branch `bryden/mobile-frontend`) is achieved with **one
detection hook + a per-page shell branch + reuse of shared content/data atoms** —
*not* a second state model. The state model supports this because **layout state
is separate from content/data state**:

- The desktop shell consumes the section/split/size layout state described here.
- The mobile shell renders a single full-screen panel and a chat-first surface. It
  **reuses the same content components and the same data atoms** (tasks,
  terminals, diffs) but **does not mount the desktop layout shell**, so it never
  reads or writes the section-layout state — desktop layouts are untouched by a
  mobile session.
- Detection is a single `useIsMobile`/`useLayoutMode` hook (viewport breakpoint OR
  touch phone), and the branch happens at the page level.

The design rule the redesign must preserve: **never couple a content component
(chat, terminal, diff viewer) to the layout/section state.** Content components
take their data from data atoms and their identity from the registry; the *shell*
owns the layout. This is what lets the mobile shell slot in without duplicating
state. See `component_hierarchy.md` → "Mobile shell variant".

## Removed state (no dead code)

Per `goals.md` → "Features to deprecate" and the rewrite cleanliness mandate, the
following state is **deleted**, not carried forward:

- **Docking "expand"/review mode** — the old single-panel review flag. Replaced by
  the maximized section.
- **The "share section sizes between workspaces" experimental setting** — sizes
  are *always* global now; there is no per-workspace-sizes mode and no toggle.
- **Tab-strip-position setting** (top/bottom) — not in `goals.md`; removed.
- **Panel enable/disable machinery** (the per-panel enabled flag and built-in
  flag) — it backed the deprecated Panels settings page. Panels are registered
  statically; there is no user-facing enable/disable.
- **Zen mode, Focus mode, and the `/btw` popup** state — removed entirely.

The rename of every retained atom from the prototype's "zone/focus" vocabulary to
the "section/active-section" vocabulary is tabulated in `supplemental/naming_map.md`.

## Related documents

- `goals.md` — source of truth for behavior.
- `design_extraction.md` — styling and components to copy forward.
- `component_hierarchy.md` — the React tree that consumes this state, and the
  memoization boundaries.
- `supplemental/naming_map.md` — prototype → rewrite rename table.
- `supplemental/state_atoms.md` — concrete atom inventory and signatures.
- `supplemental/persistence_interface.md` — the adapter interface, snapshot
  shapes, and switch/hydrate sequence.
- `supplemental/panel_registry.md` — panel definitions, kinds, and add/close/rename
  rules.
