# SCU-1746 structure pass — decisions made autonomously (for Bryden's review)

## Inferability test: before 8/10 → after 7/10 (honest read: a wash on the headline)

Same 10 names-only navigation prompts, fresh agent each time. Improvements: the
new-workspace submit flow went partial→correct (`useCreateWorkspace` findable);
sidebar empty state and fuzzy scorer stayed one-guess hits at their new homes.
Regressions: more well-named directories means more *plausible* candidates —
"recently closed panels" now reads as `layout/atoms/addPanel.ts` (it lives in
`transient.ts`), and the workspace-delete dialog loses to the better-named-but-
wrong `workspaceChrome/AgentDeleteConfirmation`. Both remaining root causes
predate the pass and are catalogued follow-ups: the diff split/unified toggle
living in `common/state/atoms/userConfig.ts` (missed in BOTH runs), and the
delete-dialog proliferation. Conclusion: structure moves alone don't lift the
number until those two content-level fixes land; the navigation *depth* cost is
visible too (4-5 listings vs 2-4 at baseline).

Working log of judgment calls made while executing the agreed plan without you.
Nothing here changes the agreed principles; these are placements/namings the
principles didn't fully determine. Flip any of them and I'll rework.

## Made (flag if you disagree)

1. **`apiClient.ts` → `common/apiClient.ts`.** Root keeps only build/bootstrap
   entries (`Main.tsx`, `instrument.ts`, `preload.ts`, css/env types). The
   configured API client is shared non-UI glue → `common/`.
2. **`sectionTypes.ts` → `layout/types/section.ts`.** It's mostly types +
   guards; the guards ride with their types rather than splitting into utils/.
3. **`diffPanel/` and `diffViewer/` stay separate features** under
   `pages/workspace/` for now (pure moves only). They look like one `diff/`
   feature with two subfeatures — flagged as a candidate follow-up rather than
   mixing a merge into the rename commits.
4. **`CommandPalette/` → `commandPalette/`** per the camelCase-dirs rule (it
   was the one PascalCase directory).
5. **`sections/persistence/types.ts` → `persistence/snapshot.ts`** (generic
   basename ban applies inside subfeatures too; the file is the snapshot
   schema).
6. **`useWorkspaceTabActions` (SCU-1748) → `common/state/hooks/`.**
   (Superseded my earlier `app/hooks/` call: commandPalette imports it, and
   components/ must not import app/ — the hook fronts tab state, so the state
   mirror is its home. See execution-plan.md ruling 2.)
7. **`NewWorkspaceModal` → `NewWorkspaceDialog`** executed as part of the
   suffix-glossary cleanup (Modal suffix retired), per the approved glossary.
8. **Stories mirror is realigned in PR1** (cheap renames) even though PR3
   colocates stories — PR1 must be self-consistent with its own docs; PR3
   updates the docs and moves stories beside components.

## Blocked / needs you

- **Linear is unreachable from this workspace** (`LINEAR_API_KEY` vanished when
  the harness restarted mid-session; all calls 401). Child-ticket state
  updates and the two new follow-up tickets (chat rename, stories colocation)
  are pending — the work itself proceeded. A workspace restart or env re-sync
  should fix it.

9. **Layout state stayed feature-side (ruling 4 fallback).** Global and
   per-workspace layout snapshots share one persistence adapter (one debounce
   map, one flush path); splitting the global slice into `common/state` would
   mean carving that adapter in half or moving it wholesale to `common/`. So
   all layout state lives in `pages/workspace/layout/atoms/`, and the Stage H
   boundaries lint carries explicit exceptions for its commandPalette/app/
   common readers. The real fix is a follow-up: either promote the whole
   layout-state module to `common/state`, or invert the palette's workspace
   commands into a registration pattern (features register commands, like
   panels register components).

10. **Kebab-case directory renames (`add-workspace`→`addWorkspace`,
    `pill-animations`→`pillAnimations`, `app-icons`→`appIcons`).** The stage-H
    `check-file/folder-naming-convention` rule requires camelCase folders
    (frontend_structure.md: "directories are camelCase, without exception");
    these three predated the rule. Renamed via `git mv` with every importer
    updated. `appIcons` holds only PNGs so the lint never examines it, but it is
    renamed anyway for consistency with the documented rule. A tree-wide find
    now reports zero non-camelCase folder segments (excluding `__tests__`).

## Follow-up candidates surfaced during the work (not executed)

- Merge `diffPanel/` + `diffViewer/` into one `diff/` feature (see 3).
- Four delete-confirmation components coexist (`DeleteConfirmationDialog`,
  `WorkspaceDeleteConfirmation`, `AgentDeleteConfirmation`, plus a
  sidebar-local dialog) — consolidation candidate found by the baseline
  inferability test.
- Backend rename of wire `task` vocabulary (would let the frontend drop the
  last `task_id` field names at the API seam).
- `stories/custom/.../chatAlpha/fixtures/{scenarios,messageBuilders}.ts` have
  zero importers (they only reference each other) — likely dead fixtures.
- `storybook build` is broken independently of this pass: `.storybook/main.ts`
  uses `__dirname` under ESM (Storybook v10) and dies while loading presets.
  Worth its own ticket if Storybook builds are expected to work.
- From the task→agent rename: normalize leftover `"task-1"`-style test-fixture
  id strings to agent spelling; a coordinated `data-taskid` → `data-agentid`
  rename with `sculptor/tests/integration/frontend/test_read_unread_status.py`;
  and a product-copy pass (e.g. "Describe a task for the agent") — copy was
  deliberately out of scope for the mechanical rename.

## Import-boundary exceptions (temporary)

Stage H turns `import/no-restricted-paths` on in `sculptor/frontend/eslint.config.ts`
to enforce the layering in `docs/development/style/frontend_structure.md`
(common ↛ components/pages/app/electron; components ↛ pages/app; a page ↛ another
page; electron ↛ renderer UI). Enforcement is real for aliased imports too:
`eslint-import-resolver-typescript` was added so the rule follows `~/…`
specifiers, not only relative ones.

Every cross-boundary import that exists today is captured by an `except` entry
in that config (the boundary is NOT weakened globally — each except names a
specific module). The full set is **87 import lines across 38 files**, grouped
below by the follow-up that deletes the exception. Removing a follow-up's code
lets the paired `except` entries come out.

**F1 — Promote workspace layout state to `common/state` (ruling 4 / decision 9).**
_55 import lines, 19 files._ `common/` state hooks and `components/` (chiefly
`commandPalette`, plus `newWorkspace`, `diffSummary`, `workspacePeek`) read
`pages/workspace/layout/**` (section/sectionActions/addPanel/transient/sidebar
atoms, the persistence adapter + snapshot, the panel registry + dynamicPanels,
and `types/section`). Excepts: `./workspace/layout` in both the `common→pages`
and `components→pages` zones. The alternative fix (decision 9) is inverting the
palette's workspace commands to a registration pattern.

**F2 — Invert the command palette to command registration (ruling 4).**
_3 import lines, 3 files._ `common/state/hooks/{useWorkspaceDynamicPanels,
useWorkspaceShellBootstrap}` (and the dynamic-panels test) reach back into
`components/commandPalette` command/context-action state. Excepts (in
`common→components`): `./commandPalette/contextActions/atoms/contextActions.ts`,
`./commandPalette/utils/commandActions.ts`.

**F3 — Move new-workspace form atoms to `common/state`.** _1 import line, 1 file._
`common/state/hooks/useCreateWorkspace.ts` reads
`components/newWorkspace/newWorkspaceAtoms.ts`. Except (in `common→components`):
`./newWorkspace/newWorkspaceAtoms.ts`.

**F4 — Promote the remaining workspace feature-state modules to their shared
home as second consumers appear.** _18 import lines, 11 files._ Shared UI/state
reaches into workspace feature internals beyond layout: `diffPanel` atoms/types,
`panels/browser` atoms, `panels/fileBrowser` atoms/types/`fileIcons`,
`panels/workspaceAgentActions`, `chatAlpha` atoms/`chipRowUtils`, and
`workspace/hooks/useTimedLatch`. Excepts: those specific files in the
`common→pages` and `components→pages` zones (kept at file granularity so the
boundary still catches new, unrelated reaches).

**F5 — Move the `SettingsSection` enum to `common/`.** _4 import lines, 4 files._
`components/commandPalette` (settings command + drift test), `components/
newWorkspace/AgentSettingsControls`, and `pages/workspace/chatAlpha/ChatInput`
import `pages/settings/sections.ts`. Excepts: `./settings/sections.ts` in the
`components→pages` zone and in the `pages/workspace` page zone.

**F6 — Promote `RecentWorkspaces` to `components/`.** _1 import line, 1 file._
`pages/home/RecentWorkspacesHomeView` imports the component from
`pages/addWorkspace`. Except (in the `pages/home` page zone):
`./addWorkspace/components/RecentWorkspaces.tsx`.

**F7 — Promote the `useTerminal` hook to `common/`.** _1 import line, 1 file._
`pages/settings/components/PiLoginTerminal` imports
`pages/workspace/panels/useTerminal.ts`. Except (in the `pages/settings` page
zone): `./workspace/panels/useTerminal.ts`.

**F8 — Move platform detection to `common/`.** _4 import lines, 4 files._
`common/{apiClient, keybindings/format, keybindings/matching, openInApp/items}`
import `isMac`/`isElectron`/`getMetaKey` from `electron/platform.ts`. This is
shared glue, not electron-main-process code; ruling 5 already relocated the
renderer-domain unions so `common/` need not import `electron/`, and `platform.ts`
is the last holdout. Except (in `common→electron`): `./platform.ts`.
