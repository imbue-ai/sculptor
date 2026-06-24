# Supplemental: component tree, files, and subscriptions

Companion to `../component_hierarchy.md`. The intended final component names and
locations for the rewrite, plus the exact narrow subscription each memoized
component holds. Names use `goals.md` vocabulary (see `naming_map.md`).

> The rewrite builds the new shell **in place** in `sculptor/frontend/src`, alongside
> the reused content/creation components, and deletes the old shell once unreferenced
> (Decision A1 — strangler; **no `frontend_old` move**). Paths below are the intended
> *final* locations. A prototype counterpart (shape to copy) or an existing
> this-branch component (reused as-is) is noted where useful; do not carry prototype
> names forward.

## Intended file layout

```
components/
  nav/
    WorkspaceSidebar.tsx            ← prototype WorkspaceNavSidebar; resizable + version + report-a-bug
    CollapsedSidebarToggle.tsx
  layout/
    sidebarAtoms.ts                 width / collapsed (global)
  sections/
    SectionGrid.tsx                 ← prototype CompactLayout; four-section frame + resize
    SplittableSection.tsx
    PanelSection.tsx
    SectionHeader.tsx               ← prototype SectionTabBar
    SectionBody.tsx
    EmptySectionState.tsx           ← prototype EmptyPanelLauncher
    ResizeHandle.tsx
    AddPanelDropdown.tsx            dropdown (reuse AddPanel row styling only)
    PanelDndProvider.tsx
    sectionAtoms.ts                 per-workspace layout slices (see state_atoms.md)
    sectionActions.ts               write-side action atoms
    persistence/
      LayoutPersistenceAdapter.ts   the interface
      LocalStorageLayoutAdapter.ts  today's impl
      types.ts                      WorkspaceLayoutState / GlobalLayoutState / LayoutScope
    registry/
      panelRegistry.ts              static defs + registry atom
      dynamicPanels.tsx             agent/terminal derived defs (id helpers, component cache)
  newWorkspace/
    NewWorkspaceModal.tsx           ← prototype PaletteDialog styling; shell host, opened via newWorkspaceModalAtom
    NewWorkspaceForm.tsx            rewrite form: title + prompt textarea + context pills + footer
    BranchNameField.tsx             ← prototype styling; pairs with this branch's branch-name-preview hook
    AgentTypeSelect.tsx             extracted from today's AddWorkspacePage inline agent picker
    ModeSelect.tsx                  extracted from today's AddWorkspacePage inline mode picker
    newWorkspaceAtoms.ts            modal open/context · keep-open · MRU creation settings (state_atoms.md)
pages/
  workspace/
    WorkspacePage.tsx               useIsMobile branch → shell
    WorkspaceLayoutShell.tsx        header + SectionGrid, inside PanelDndProvider
    WorkspaceHeader.tsx             ← prototype WorkspaceBanner
    mobile/
      MobileWorkspaceShell.tsx      single-column shell (from bryden/mobile-frontend)
    panels/
      AgentPanel.tsx · TerminalPanel.tsx
      FilesPanel.tsx · ChangesPanel.tsx · CommitsPanel.tsx · ReviewAllPanel.tsx
      ActionsPanel.tsx · SkillsPanel.tsx · BrowserPanel.tsx · NotesPanel.tsx
      ExplorerLayout.tsx            ← prototype MasterDetailPanel; shared file-list + diff viewer scaffold
common/
  hooks/useLayoutMode.ts            useIsMobile / useLayoutMode (from bryden/mobile-frontend)
  state/hooks/usePerWorkspacePanelLayout.ts   keeps active scope in sync with the route
  state/hooks/useCreateWorkspace.ts           create-workspace → create-first-agent; no draft-tab coupling
```

**Reused as-is from the current branch** (not recreated; A1 strangler builds in
place): `components/RepoSelector.tsx`, `components/BranchSelector.tsx` (+
`BranchSelectorCore`), today's branch-name-preview hook, the repo-info hook, and the
projects / agent-type atoms. The new `isWorkspaceListEmptyAtom` is a derived atom added
to the existing workspace atoms (it does not exist today). The new-workspace modal
copies only the `scu-1494` *styling/shape* — not the prototype's divergent form
component.

## Tree with subscriptions

Memoized components are marked `[memo]`; their subscription is the narrow slice
they read. Anything not listed is rendered from props.

```
AppShell
├─ WorkspaceSidebar            sidebarWidthAtom, sidebarCollapsedAtom, workspaces/repos data atoms
└─ WorkspacePage               useIsMobile()
   └─ WorkspaceLayoutShell
      └─ PanelDndProvider      draggedPanelIdAtom (STABLE for the drag — not the moving preview)
         ├─ WorkspaceHeader    maximizedSectionAtom (to hide itself), branch/PR data atoms
         └─ SectionGrid        sectionSizesAtom, isSectionExpandedAtom(left|right|bottom),
            │                   maximizedSectionAtom
            └─ SplittableSection(section)            [memo] sectionSplitForSectionAtom(section)
               └─ PanelSection(subSection)           [memo] isDropTargetAtom(ss),
                  │                                          isActiveSubSectionAtom(ss),
                  │                                          isRingVisibleAtom(ss),
                  │                                          maximizedSectionAtom == section
                  ├─ SectionHeader(subSection)        [memo] displayedPanelIdsAtom(ss),
                  │                                          activePanelIdInSubSectionAtom(ss),
                  │                                          ghostPanelIdAtom(ss)
                  │   ├─ panel tabs (active / close / rename-for-multi-instance)
                  │   ├─ AddPanelDropdown             registry + placement (on open only)
                  │   └─ maximize toggle              maximizedSectionAtom (write)
                  └─ SectionBody(subSection)          [memo] activePanelComponentInSubSectionAtom(ss)
                      └─ <ActivePanelComponent />     OR EmptySectionState(ss)
```

### Why each boundary holds

- **`SectionGrid`** re-renders on resize (a `ResizeObserver` + size atom) and
  expand/collapse. Its children are `SplittableSection` `[memo]` with primitive
  props (`section`, `side`), so a per-pointer-move resize does not reach them.
- **`SplittableSection`** subscribes to its own section's split slice — a
  split-ratio drag in another section does not re-render it. When unsplit it
  renders one `PanelSection`; when split, primary + handle + secondary.
- **`PanelSection`** subscribes only to narrow per-sub-section flags. It also
  re-renders on dnd `over` changes (it is a droppable), so it stays deliberately
  thin; heavy state is below its memoized children.
- **`SectionHeader`** subscribes to the displayed-panel-ids slice
  (shallow-equal-deduped, so it does not churn when an unrelated section's panels
  change) and the active panel id. A tab drag updates a per-section ghost slice
  only.
- **`SectionBody`** subscribes to the *resolved active panel component* (identity
  cached per panel id in `dynamicPanels.tsx`), so a registry rebuild on a task
  tick — or a workspace switch — never remounts live panel content. This is the
  boundary that delivers "each panel mounts at most once per switch".
- **`PanelDndProvider`** subscribes to the stable dragged-panel id, so it does not
  re-render on every insertion-index change during a drag; the moving preview is
  read only by the narrow per-section slices above.

## Hooks wiring (in `WorkspacePage` / `WorkspaceLayoutShell`)

- `useIsMobile()` — desktop vs. mobile shell branch.
- `usePerWorkspacePanelLayout(workspaceId)` — layout effect; writes
  `switchActiveWorkspaceAtom` so the active scope follows the route in one
  pre-paint commit (`persistence_interface.md` → "Switch sequence").
- `useWorkspaceLayoutBootstrap({ workspaceId, agentId })` — layout effect; places
  the active agent into center and seeds the bottom terminal on first visit.
- `useWorkspaceDynamicPanels(workspaceId)` — derives agent/terminal panel defs and
  feeds the registry (`panel_registry.md`).

## Related documents

- `../component_hierarchy.md` — the prose + diagram overview.
- `../state_design.md` — the state model.
- `state_atoms.md` — atom signatures referenced above.
- `persistence_interface.md` — adapter + switch sequence.
- `panel_registry.md` — panel defs and lifecycle.
- `naming_map.md` — prototype → rewrite renames.
