# Supplemental: state atom inventory

Companion to `../state_design.md`. Concrete Jotai atom shapes and signatures for
the workspace layout state. Names use `goals.md` vocabulary (see
`naming_map.md`). Signatures are illustrative TypeScript, not final code.

## Core types

```ts
type SectionId = "left" | "center" | "right" | "bottom";

// A panel lives in a sub-section. Unsplit → the sub-section id IS the section id
// (primary). Split → the section gains a secondary sub-section.
type SubSectionId = SectionId | `${SectionId}:secondary`;

type PanelId = string;                       // static id ("files") or dynamic ("agent:<taskId>")

type SplitAxis = "horizontal" | "vertical";  // horizontal divider → stacked; vertical → side-by-side
type SectionSplit = { axis: SplitAxis; ratio: number };  // ratio = primary half's fraction (0..1)
```

Helpers: `toSecondary(s: SectionId): SubSectionId`, `toSection(ss: SubSectionId):
SectionId`, `isSecondary(ss: SubSectionId): boolean`.

## Scope atoms (source of truth)

```ts
const activeWorkspaceIdAtom: PrimitiveAtom<string | null>;   // set by usePerWorkspacePanelLayout
const layoutScopeAtom: Atom<LayoutScope>;                    // derived: workspace scope or global sentinel
```

Switching workspaces is a single write to `activeWorkspaceIdAtom` (via
`switchActiveWorkspaceAtom`, below), which flips every per-workspace proxy
atomically. See `persistence_interface.md` → "Switch sequence".

## Per-workspace layout (consolidated)

One consolidated snapshot per workspace, persisted via the adapter (see
`persistence_interface.md`). `WorkspaceLayoutState` shape is defined there.

```ts
// Family keyed by workspace id; backed by the persistence adapter.
const workspaceLayoutFamily: AtomFamily<string, WritableAtom<WorkspaceLayoutState, [Updater], void>>;

// Proxy resolving the active scope on each read/write — the app reads THIS.
const workspaceLayoutAtom: WritableAtom<WorkspaceLayoutState, [Updater], void>;
```

### Read-side narrow slices (derived; stable instances)

Derived from `workspaceLayoutAtom` with `selectAtom` + custom equality, so a
mutation notifies only subscribers whose slice changed. Per-`SubSectionId` /
per-`SectionId` atoms are memoized into a `Map` at module load (a new atom per
render causes Jotai re-render loops — see prototype `atoms.ts`).

```ts
const panelsInSubSectionAtom: (ss: SubSectionId) => Atom<readonly PanelId[]>;        // open panels, ordered
const activePanelIdInSubSectionAtom: (ss: SubSectionId) => Atom<PanelId | undefined>;
const activePanelComponentInSubSectionAtom: (ss: SubSectionId) => Atom<ComponentType | undefined>;
const isSectionExpandedAtom: (s: SectionId) => Atom<boolean>;
const sectionSplitForSectionAtom: (s: SectionId) => Atom<SectionSplit | undefined>;
const isSplitHalfAtom: (ss: SubSectionId) => Atom<boolean>;
const activeSubSectionAtom: Atom<SubSectionId | null>;                               // persisted active pane
const isActiveSubSectionAtom: (ss: SubSectionId) => Atom<boolean>;
```

### Write-side action atoms

All mutations go through write-only action atoms that update the consolidated
`workspaceLayoutAtom`. This keeps multi-field moves atomic (one snapshot write →
one debounced persist) and keeps the rules (split self-heal, center-never-collapse,
single-instance) in one place.

```ts
const movePanelAtom:        WriteAtom<{ panelId; to: SubSectionId; index?: number }>;
const openPanelAtom:        WriteAtom<{ panelId; in: SubSectionId }>;
const closePanelAtom:       WriteAtom<{ panelId }>;        // also collapses/un-splits emptied sections
const setActivePanelAtom:   WriteAtom<{ panelId; in: SubSectionId }>;
const toggleSectionAtom:    WriteAtom<{ section: SectionId }>;     // collapse/expand (center is no-op)
const splitSectionAtom:     WriteAtom<{ section: SectionId; panelId; axis: SplitAxis }>;
const closeSplitAtom:       WriteAtom<{ section: SectionId }>;     // merge secondary back into primary
const setSplitRatioAtom:    WriteAtom<{ section: SectionId; ratio: number }>;
const setActiveSectionAtom: WriteAtom<{ subSection: SubSectionId }>;   // silent (plain click)
const jumpToSectionAtom:    WriteAtom<{ subSection: SubSectionId }>;   // sets active + pulses ring
const switchActiveWorkspaceAtom: WriteAtom<{ workspaceId; defaultLayout }>;  // seeds default on first visit
const removeWorkspaceLayoutAtom: WriteAtom<{ workspaceId }>;                 // on workspace delete
```

Invariants enforced inside the actions:

- **Center never collapses** — `toggleSectionAtom` ignores `center`.
- **Active section must be expanded** — collapsing the section that holds the
  active sub-section reassigns the active sub-section (default: center).
- **Split self-heal** — emptying a split sub-section closes the split; emptying a
  split primary promotes the secondary's panels up and closes the split. (Guard
  against the reload window where a dynamic panel is assigned but its
  task/terminal source has not loaded yet — do not collapse during that window.)
- **Single-instance** — adding an already-open single-instance panel activates it
  in place instead of duplicating.

## Global layout (consolidated)

```ts
const globalLayoutAtom: WritableAtom<GlobalLayoutState, [Updater], void>;   // backed by adapter

// Narrow slices:
const sectionSizesAtom: Atom<Record<"left" | "right" | "bottom", number>>;  // percentages
const sidebarWidthAtom: WritableAtom<number, ...>;
const sidebarCollapsedAtom: WritableAtom<boolean, ...>;
const explorerListWidthAtom: WritableAtom<number, ...>;                     // shared across files/changes/commits
```

`GlobalLayoutState` shape is in `persistence_interface.md`.

## Transient atoms (non-persisted)

Plain atoms; reset on reload. Never go through the persistence adapter.

```ts
const maximizedSectionAtom: PrimitiveAtom<SectionId | null>;        // one at a time; reload clears

// Drag preview — updated continuously during a drag; real placement mutates on drop only.
type PanelDragState = { panelId: PanelId; from: SubSectionId; to: SubSectionId; index: number };
const panelDragStateAtom: PrimitiveAtom<PanelDragState | null>;
const draggedPanelIdAtom: Atom<PanelId | null>;                    // stable for the whole drag
const isDropTargetAtom: (ss: SubSectionId) => Atom<boolean>;       // narrow per-sub-section slice
const ghostPanelIdAtom: (ss: SubSectionId) => Atom<PanelId | null>;
const displayedPanelIdsAtom: (ss: SubSectionId) => Atom<readonly PanelId[]>;  // panels incl. in-flight ghost

// Active-section ring — transient visibility over the persisted active sub-section.
const activeSectionRingVisibleAtom: PrimitiveAtom<boolean>;        // FOCUS window ~2s, then false
const activeSectionRingNonceAtom: PrimitiveAtom<number>;           // bumped to restart the fade timer
const isRingVisibleAtom: (ss: SubSectionId) => Atom<boolean>;      // active AND ring visible
```

`RING_VISIBLE_MS = 2000` (`goals.md` → "Active section": fades within ~2 seconds).

## Registry atoms

```ts
const panelRegistryAtom: PrimitiveAtom<readonly PanelDefinition[]>;     // static + dynamic; see panel_registry.md
const panelShortcutsAtom: Atom<Record<PanelId, string>>;               // from the keybindings registry
```

See `panel_registry.md` for `PanelDefinition` and how dynamic agent/terminal
panels are derived and merged.

## Workspace creation atoms

The new-workspace modal (`../component_hierarchy.md` → "Workspace creation modal")
replaces the `/ws/new` page and its per-draft persisted state. The form fields are
**local component state** (the modal is ephemeral); only these app-level atoms are
needed:

```ts
// open/close + optional pre-selected repo (from a repo group's "+"); transient.
const newWorkspaceModalAtom: PrimitiveAtom<{ open: boolean; presetProjectId?: string }>;

// "keep open" switch — keeps the dialog open after Create for rapid multi-create.
const keepNewWorkspaceModalOpenAtom: PrimitiveAtom<boolean>;

// MRU of the last successful create — seeds the modal's defaults and powers the
// sidebar "+" direct-create (WSC-01). Persisted; extends today's MRU project +
// last-used agent type into the full set the direct-create reuses.
const lastWorkspaceCreationSettingsAtom:
  WritableAtom<{ projectId; sourceBranch?; agentType; initStrategy }, [Updater], void>;

// Derived over the live workspace list; gates the empty first-run page (FIRST-01)
// and the sidebar empty-workspace special case. NEW — today the empty check is
// computed locally inside RecentWorkspaces, not via an atom.
const isWorkspaceListEmptyAtom: Atom<boolean>;
```

Creation itself is a **`useCreateWorkspace` hook** (not an atom): the two-step
create-workspace → create-first-agent flow factored out of today's add-workspace page
submit handler, decoupled from the draft pseudo-tab atoms (which are deleted with the
page). The persisted-draft atoms and the new-workspace-tab plumbing are **not** carried
forward.
