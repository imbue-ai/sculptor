# SCU-1746 move map

The executable plan for the structure moves, per docs/development/style/frontend_structure.md.
Commit order matters: each commit compiles and passes lint/tests on its own.
Pure renames (git mv + mechanical import updates) stay separate from content changes.

## Commit order

1. **Fixes (in place, before moves)**: SCU-1741 `SidebarFirstRunState` → `SidebarEmptyState`
   (identifier + file); `NewWorkspaceModal` → `NewWorkspaceDialog` (suffix glossary).
2. **app/ shell**: `App.tsx`, `Router.tsx`, `EmptyFirstRunGate.tsx`, `components/nav/*` → `app/nav/`,
   `layouts/*` → `app/` (its hooks into `app/hooks/`), `src/hooks/{useAppZoom,useAutoUpdateListener,useInstallUpdate}` → `app/hooks/`,
   `src/hooks/useFocusOnMountIfUnclaimed` → `common/hooks/`, `components/useWorkspaceTabActions.ts` → `app/hooks/`,
   `apiClient.ts` → `common/apiClient.ts`. Root keeps `Main.tsx`, `instrument.ts`, `preload.ts`, css/env decls.
3. **sections → workspace/layout** (deterministic map below).
4. **Dissolve `pages/workspace/components/`**: subdirs become sibling features of `panels/`
   (`chat-alpha` → `chatAlpha`, `diffPanel`, `diffViewer`, `tools`); loose files sorted per
   classification (move-map-workspace.md).
5. **components/ + common/ cleanup**: camelCase dir renames (`add-repo`→`addRepo`,
   `onboarding-wizard`→`onboardingWizard`, `status-dot`→`statusDot`, `CommandPalette`→`commandPalette`,
   `MarkdownDiff`→`markdownDiff`, `DevPanel`→`devPanel`); single-feature strays move to their feature
   (per move-map-components.md); `common/` flat files get content-named homes under `common/utils/`,
   `common/hooks/` (per move-map-common.md); `shared/types.ts` merges into `common/`; generic
   basenames eliminated (`Utils.ts`, `Hooks.ts`, `utils.ts`, `atoms.ts`, …).
6. **Kind-dir adoption** in features that outgrew flat (atoms.ts → `atoms/<topic>.ts` etc.),
   per the per-area classification docs.
7. **Stories mirror realignment** to the new src paths.
8. **Lint layer**: eslint-plugin-check-file (camelCase folders, basename blocklist),
   import/no-restricted-paths layering (app → anything; pages ↛ pages; components ↛ pages;
   common ↛ components/pages).
9. **task → agent rename** (SCU-1736), file renames separate from identifier renames.

## Deterministic map: components/sections → pages/workspace/layout/

Root (components + scss + their tests): AddPanelDropdown, CollapsedSectionDropOverlay,
EmptySectionState, PanelDndProvider, PanelSection, ResizeHandle, SectionBody, SectionGrid,
SectionHeader, SplittableSection, TabPill.

- `sectionAtoms.ts` → `atoms/section.ts`
- `transientAtoms.ts` → `atoms/transient.ts`
- `sectionActions.ts` → `atoms/sectionActions.ts` (reads/writes split, earned by size)
- `addPanelCore.ts` → `atoms/addPanel.ts` (resolves SCU-1747; *Core retired)
- `useActiveSectionRing.ts`, `useAddPanelActions.ts`, `useWorkspaceShortcuts.ts` → `hooks/`
- `layoutQueries.ts`, `panelDnd.ts`, `panelDndKeyboard.ts`, `sectionGeometry.ts` → `utils/`
- `sectionTypes.ts` → `types/section.ts`
- `shallowArrayEqual.ts` → `common/utils/shallowArrayEqual.ts` (resolves SCU-1749)
- `persistence/` stays a subfeature; its `types.ts` → `snapshot.ts`
- `registry/` stays a subfeature
- every `.test.*` follows its subject

Classification outputs (importer-analysis proposals, reviewed before execution):
- `move-map-components.md` — components/ root + subdirs
- `move-map-workspace.md` — pages/workspace/components/ loose files
- `move-map-common.md` — common/ flat files + shared/ + workspace utils/
