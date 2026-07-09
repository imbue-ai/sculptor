# Layouts — design

**Ticket:** SCU-1725 — "Allow users to edit and assign layouts and switch between them"
**Status:** Design / draft (pre-spec)

## Summary

Give users a first-class, user-facing concept of a **Layout**: a named, reusable
arrangement of the workspace shell that you can save, switch between, and set as the
default for new workspaces. Today the panel/section arrangement is persisted per
workspace but is anonymous and un-switchable — there is exactly one live arrangement
per workspace and one built-in default. This feature adds named Layouts on top of the
existing engine.

Non-goals for v1: syncing Layouts across devices, sharing/exporting Layouts, and
restoring stateful instances (agents/terminals). See [Out of scope](#out-of-scope).

## Motivating user stories

- Create a new Layout.
- Quickly switch the current workspace between Layouts.
- Save my current workspace arrangement as a Layout — either overwriting an existing
  one or creating a new one.
- Override the default Layout that new workspaces start from.
- Quickly switch (reset) to the default Layout.
- A keyboard shortcut opens a Layouts dialog (Cmd+K-like).
- A sidebar entry opens the Layouts dialog.

## Background: the layout engine that already exists

All under `sculptor/frontend/src/components/sections/persistence/`. A "layout" already
exists internally — it just isn't named, saveable, or switchable.

- **`WorkspaceLayoutState`** (`persistence/types.ts`) — the per-workspace arrangement:
  `placement` (open panels → which sub-section), `order` (tab order per sub-section),
  `activePanel` (selected tab per sub-section), `expanded` (section open/collapsed),
  `splits` (axis + ratio per section), `activeSubSection` (focused pane).
- **`GlobalLayoutState`** (`persistence/types.ts`) — one app-wide record: `sectionSizes`,
  `sidebarWidthPx`/`sidebarCollapsed`, `explorerListWidthPx`, `sidebarOrder`.
- **`buildDefaultWorkspaceLayout(...)`** (`persistence/defaultLayout.ts`) — the current
  "default layout," built by a function (not stored): agent in center, Files/Changes/
  Commits in left, one terminal collapsed in bottom, right empty. Seeded on a
  workspace's first visit by `useWorkspaceShellBootstrap.ts`.
- **`LayoutPersistenceAdapter`** (`persistence/LayoutPersistenceAdapter.ts`) — the single
  storage boundary; `LocalStorageLayoutAdapter` is the only impl. Explicitly designed so
  localStorage can be swapped for a backend by changing one export. Keys:
  `sculptor-layout-ws-<workspaceId>`, `sculptor-layout-global`.
- **Source of truth / mutations:** `sectionAtoms.ts` (the Jotai atoms:
  `workspaceLayoutFamily`, the `workspaceLayoutAtom` active-scope proxy, `globalLayoutAtom`)
  and `sectionActions.ts` (every arrangement mutation). Never write localStorage directly.
- **Maximize** is transient (`transientAtoms.ts` → `maximizedSectionAtom`), not persisted.

## Concept model (decided)

A **Layout** is a **reusable template**, not a literal snapshot of one workspace.

- **Templates, not snapshots.** A Layout describes structure and *stateless* content, not
  specific instances. It is portable across workspaces and usable as the new-workspace
  default. (A literal snapshot would embed one workspace's concrete `agent:<taskId>` /
  `terminal:<wsId>:<idx>` ids, which don't exist in any other workspace.)
- **Detach on apply.** Applying a Layout copies its config into the workspace. The
  workspace then diverges freely; the saved Layout only changes when you explicitly Save.
  (Not live-bound — a stray panel move must never silently rewrite a Layout you use
  everywhere.)
- **System Default.** There is always an undeletable "System Default" backed by
  `buildDefaultWorkspaceLayout`. A `defaultLayoutId` pointer decides what new workspaces
  seed from and what "switch to default" applies; if unset, it resolves to System Default.
- **Name:** user-facing term is **"Layouts."**

## What a Layout captures, and what "apply" does

Two independent rules keep the feature portable and non-destructive.

**Rule 1 — a Layout only *declares* static panels (portability).** A Layout is a portable
template, so it can only reference panels by a stable, workspace-independent id. Static
panels (Files, Changes, Commits, Browser, Notes, Skills, Actions, Review) have stable ids
and can be declared. Agent/terminal panels have instance-bound ids (`agent:<taskId>`,
`terminal:<wsId>:<idx>`) that don't exist in another workspace, so a Layout never declares
them — it can't say "this specific agent here" or "spawn N terminals." (That richer,
slot-based control is a deliberate future extension.)

**Rule 2 — apply is additive; it never removes a panel (safety).** "Static" is not the
same as "stateless" — the Browser panel holds a live session, Notes holds content. So the
dividing line that matters for safety is *adding vs removing*, not static vs dynamic.
Applying a Layout must never *close* a panel you have open, whether static or dynamic.

> Applying a Layout **adds and arranges** — it ensures the Layout's declared panels are
> present, sets the container geometry (splits, sizes, expanded/collapsed, maximize,
> focus) and active tabs, and **leaves every other open panel exactly where it is**. It
> never closes agents, terminals, the Browser, or anything else.

This makes a Layout a *positive* specification ("these panels present, arranged this way"),
not an *exhaustive* one ("exactly these and no others"). Concretely, it answers "switch to
a Layout that doesn't include the Browser while I have the Browser open": **the Browser
stays open.** Removal only ever happens by explicit user action.

A happy consequence: additive apply needs **no** new "hide-but-retain" machinery — the
untouched panels literally stay open — so it is both safer and simpler than a
replace-style apply. The cost is possible visual residue when switching a busy workspace,
so v1 ships an explicit escape hatch: a **"Tidy" ("Close panels not in this Layout")**
action. It closes only the *static* panels the Layout doesn't declare — **never agents or
terminals** — and always shows a confirmation dialog listing exactly what will close
(reusing `DeleteConfirmationDialog`); if nothing would close, it applies silently. This
also means "reset to default" can stay safely additive, with Tidy as the explicit
clean-slate button. (An opt-in per-Layout "exclusive" mode that auto-tidies on apply is a
natural fast-follow.)

**Communicating the agent/terminal boundary (decided):** handled by *framing and copy
only*. A Layout is presented as "your tool panels + space," with a one-line helper in the
dialog — e.g. "Layouts arrange your panels — your agents and terminals stay put." We are
deliberately **not** adding a hidden-sessions indicator or a visual tool-tab vs
session-tab distinction. Because apply never removes a session (Rule 2), sessions stay
visible as tabs — that is the safeguard, and it avoids reintroducing any "hidden" surface.

### Decision — Option B, with additive apply (decided)

- **Option A — geometry + active selection only.** Restores section open/collapsed,
  splits, sizes, maximize, focused pane, and which tab is active per section. Never opens,
  closes, or moves any panel. Simplest possible; zero risk. Downside: it can't *place*
  panels, so it barely changes what a brand-new workspace shows.
- **Option B — geometry + active selection + static-panel placement (recommended).**
  Everything in A, plus it opens/closes/orders the *static* panels (so "Files + Changes in
  the left, Browser in the right" is captured and restored). Agents/terminals untouched.
  On a new workspace, the agent + terminal come from existing default seeding and the
  Layout arranges the static panels + geometry around them.

**Decided: B**, refined by the additive-apply rule above — it captures the arrangement the
user built and makes "override the default for new workspaces" meaningful, while apply
never removes a panel. Known limitation of A and B: a Layout cannot express dynamic
placement like "two terminals in the bottom"; that stays with default seeding and is a
clean future extension (see [Out of scope](#out-of-scope)).

### Captured fields (under Option B)

| Field (from `WorkspaceLayoutState` unless noted) | In a Layout? |
| --- | --- |
| `expanded` (section open/collapsed) | Yes |
| `splits` (axis + ratio) | Yes |
| section sizes (`sectionSizes`, see migration below) | Yes |
| maximize (`maximizedSectionAtom`, transient today) | Yes |
| `activeSubSection` (focused pane) | Yes |
| `activePanel` (active tab per section) | Yes — stateful active tabs restored best-effort (only if that panel is present) |
| `placement`/`order` for **static** panels | Yes |
| `placement`/`order` for **agent/terminal** panels | **No** — left as-is in the workspace |
| sidebar width/collapsed, explorer list width | No — app chrome, orthogonal to a Layout |

## Apply / Save / Delete / Default semantics

- **Apply (switch to Layout):** additive — ensure the Layout's declared static panels are
  present and placed/ordered, set geometry + sizes + maximize + active tabs, and **leave
  every other open panel (static or dynamic) untouched. Never close anything.** Write via
  `sectionActions`/`workspaceLayoutAtom`. Record `appliedLayoutId` on the workspace;
  detached thereafter.
- **Tidy (opt-out of additive):** an explicit action that closes the *static* panels the
  current Layout doesn't declare. **Never** closes agents/terminals. Always confirms via a
  dialog listing what will close; no-op (applies silently) if nothing would close. This is
  how a user gets a true clean slate, including for "reset to default."
- **Save current as Layout:** snapshot the workspace's current captured fields, abstracting
  away agent/terminal instances. Either **overwrite** an existing Layout or **create new**
  (name prompt).
- **Set as default:** point `defaultLayoutId` at a Layout. New workspaces seed from it
  (composed with default dynamic-panel seeding); "switch/reset to default" applies it.
- **Delete:** removing the Layout that is `defaultLayoutId` → falls back to System Default.
  Removing a Layout that is some workspace's `appliedLayoutId` → the workspace keeps its
  arrangement, just drops the pointer.
- **Rename** in the dialog (via the ⌘J popover). Duplicate was cut from the v1 UI ("Save
  current arrangement as…" covers the copy case). Duplicate-name handling: TBD (allow, or
  auto-suffix).
- **"Modified" indicator (light):** track per-workspace `appliedLayoutId` + a dirty check
  so the dialog can show the active Layout and offer Save (overwrite) vs Save as new.
  Minimal version in v1; richer dirty-diff is a follow-up.

## Data model (proposed)

- `SavedLayout`: `{ id, name, capturedFields..., version }` — the captured subset above,
  with dynamic panels excluded.
- Storage: add `savedLayouts?: Array<SavedLayout>` and `defaultLayoutId?: string` to
  `GlobalLayoutState` (the existing app-wide store). This is an additive, optional field —
  no schema version bump needed (`normalizeSnapshot`/`isValidSnapshot` in
  `LocalStorageLayoutAdapter.ts` tolerate additive fields). Expose a `savedLayoutsAtom`
  slice over `globalLayoutAtom`, following the `src/components/layout/sidebarAtoms.ts`
  slice pattern.
- Per-workspace `appliedLayoutId`: add to `WorkspaceLayoutState`.
- **Section-sizes migration:** move `sectionSizes` from `GlobalLayoutState` (app-wide) into
  the per-workspace layout, matching how `splits` already work. Rationale + caveat below.

### Section sizes: global → per-workspace (trial)

Section sizes are **global** today — a deliberate choice so switching workspaces doesn't
force you to re-fiddle sizes. We are moving them **per-workspace on a trial basis** because
Layouts may solve that same problem a better way (apply a Layout to get your sizes back).
If cross-workspace size-fiddling returns as a pain, revisit this decision.

## Entry points & UX (finalized via mock iteration — see `agent_docs/layouts/mocks.html`)

The dialog is a **switcher first** (PyCharm ⌘E semantics), not a management screen.
Management hangs off it via a Raycast-style bottom bar. Visual truth is the mock's
`switcher` / `switcher-actions` / `save` / `tidy` / `palette` / `sidebar` states (the
`dialog` / `dialog-search` states are superseded v1 history — do not follow them).

- **Own dialog, not a palette sub-page (decided).** The switcher is its own dialog on the
  `PaletteDialog` shell, mounted in `AppShell` and atom-driven (`layoutsModalAtom`) — the
  New Workspace pattern. Palette sub-pages can't host the bottom bar, the ⌘J popover,
  MRU-bounce selection (pages auto-select the top-scored row), or inline rename.
- **Keyboard shortcut: ⌘⇧L** opens the switcher. Double-tap bounces: the list is
  MRU-ordered and selection starts on the *previous* layout, so ⌘⇧L ⌘⇧L toggles between
  the two most-recent layouts.
- **Sidebar:** a "Layouts" `NavItem` in bottom actions (between "Add repo" and "Settings")
  opens the switcher.
- **Command palette:** dynamic "Switch to <layout>" commands apply directly from Cmd+K
  (dynamic provider reading `savedLayoutsAtom`; register its input in
  `dynamicProviderInputsAtom`), plus a "Layouts…" opener command (shows the ⌘⇧L hint) that
  closes the palette and opens the switcher.
- **Switcher list:** palette-pure rows — per-layout wireframe icon + name + muted panel
  summary + at most ONE quiet trailing marker ("★ Default" on the default layout,
  "Current" on the applied one). Type-to-filter. No inline row actions, no management
  group in the list.
- **Bottom bar (Raycast style):** left slot is a quiet "Save current arrangement… ⌘S"
  button (opens the save dialog); right slot reads "Apply ↵ | More options ⌘J".
- **More options popover (⌘J — ⌘K stays the global palette):** headerless, anchored above
  the bar, scoped to the highlighted layout: Apply ↵ / Apply & tidy ⌘↵ / — / Set as
  default / Rename / Delete ⌘⌫ (danger). No Duplicate in v1. Esc layering mirrors the
  palette's two-stage Esc: popover → clear search → close dialog.
- **Apply at switch time:** ↵ is the only fast-path verb — additive, never destructive,
  never confirms. ⌘↵ "Apply & tidy" chains into Tidy's confirmation dialog (listing
  exactly what closes) when residue exists, and is silent otherwise. No persistent
  "also tidy" checkbox — a toggle that changes what ↵ means later is a footgun.
- **Save dialog:** its own dialog on the `PaletteDialog` shell — name input, capture
  preview (solid cells = saved panels; dashed = agents/terminals, labeled "stays as-is"),
  "Set as default for new workspaces" switch, primary Save button. The agent/terminal
  helper copy lives here and in the Tidy confirmation — not in the switcher.
- **Keybinding rendering:** register ⌘⇧L / ⌘J in the keybindings registry and render
  hints through the shared `formatShortcutForDisplay` / `ShortcutHint` path (plain muted
  text, user-remappable) — same as every other shortcut in the UI.
- **"Edited" indicator:** deferred — v1 shows only the "Current" row marker. (The bar's
  left slot went to Save; fold "· edited" into the row marker later only if missed.)

## Relationship to existing tickets

- **SCU-1713** (Cmd+K "reset to default layout") — subsumed by "switch/reset to default."
- **SCU-1721** (panels declare default placement) — complementary; a panel's declared
  default placement could inform static-panel slot resolution.
- **SCU-1737** (orphaned-layout GC → pub/sub) — the per-workspace `appliedLayoutId` and the
  `savedLayouts` collection interact with GC; keep in mind when that lands.
- **SCU-1778** (persist per-workspace UI state) — the foundation this builds on.

## Out of scope (candidate follow-ups)

- **Cross-device sync / a backend store** for Layouts (the adapter seam makes this clean;
  today Layouts are per-device localStorage).
- **Sharing / import / export** of Layouts.
- **Full dynamic-panel control** ("two terminals in the bottom," pin a specific agent) via
  slot-based reconciliation of stateful instances — deliberately deferred to keep apply
  safe and simple.

## Open questions

1. Duplicate-name handling (allow vs auto-suffix).
2. How much "modified/dirty" fidelity in v1 — the switcher shows no "edited" indicator
   (deferred, see Entry points); the dirty *tracking* may still be wanted for the
   overwrite/update-layout flow.
3. Overwrite-on-save: v1's save dialog only creates new layouts; an "Update <layout> with
   current arrangement" action (natural home: the ⌘J popover on the current layout) is
   deferred.
4. Precise behavior when a static panel in the Layout can't currently render (e.g. a plugin
   panel whose plugin isn't loaded) — likely reuse the existing best-effort resolution.
