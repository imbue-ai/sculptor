# common/ cleanup move-map (SCU-1746)

Analysis-only proposal for eliminating the loose files at `sculptor/frontend/src/common/`
root, plus `common/shared`-adjacent stragglers (`shared/types.ts`), `pages/home/Utils.ts`,
and `pages/workspace/utils/utils.ts`. Governed by
`docs/development/style/frontend_structure.md`:

- **Placement rule** — code lives with the feature that renders it; it rises to a shared
  home only when a 2nd feature imports it.
- **Helper ladder** — private fn → feature `utils/` → its own named file → `common/utils/`.
- **Kind vocab is fixed**: `atoms/ hooks/ utils/ types/` (rarely). No ad-hoc kind dirs.
- **Naming**: components `PascalCase.tsx`; everything else `camelCase.ts`. Banned basenames
  everywhere (incl. inside kind dirs): `utils/helpers/hooks/atoms/types/misc.ts`. `index.ts`
  reserved for public-API barrels. Name the topic, or the feature for the lone-file case.

All paths below are under `sculptor/frontend/src/`. Colocated `.test.*` files move with
their source. **No files were moved or edited — this is the map only.**

---

## 1. Summary: every loose `common/` root file

| Source file | Kind | Shared by | Destination | Notes |
| --- | --- | --- | --- | --- |
| `common/Analytics.ts` | infra (pure) | 1 (Telemetry) | `common/telemetry/analyticsId.ts` | Only Telemetry imports it; keep separate for its pinned snapshot test. |
| `common/Auth.ts` | infra (stateful) | 4+ features | `common/utils/sessionToken.ts` | Rename `Auth`→`sessionToken`. Holds module state — not a pure util (flagged §6). `app/` is the doc-correct home. |
| `common/Constants.ts` | constant | 3 features | `common/utils/elementIds.ts` | Single const `CHAT_INPUT_ELEMENT_ID`; `common/` has no constants kind, `utils/` is the pragmatic home. |
| `common/Errors.ts` | classes+helper | 8+ features | `common/utils/errors.ts` | Error classes + `getErrorMessage`; broadly shared. |
| `common/Guards.ts` | type guards | see §3 | **SPLIT** (§3) | 13 block guards are workspace-only; `isLlmModel` is state-only. |
| `common/Hooks.ts` | hook | 5 (all workspace) | `pages/workspace/hooks/useTimedLatch.ts` | Misnamed single-export file, not a true grab-bag. Consumed only by workspace → push down. |
| `common/NavigateUtils.ts` | hooks | 30+ files | `common/hooks/navigation.ts` | Cohesive routing-hook cluster (`useImbueNavigate/useImbueLocation/useWorkspacePageParams/useActiveProjectID/useImbueParams` + param types). Could split per-hook to match `common/hooks/` convention. |
| `common/ShortcutUtils.ts` | keybinding infra | see §4 | **SPLIT** (§4) | Matching engine + display formatter + overlay check + an Enter hook → into `common/keybindings/`. |
| `common/Telemetry.ts` | infra | 8+ features | `common/telemetry/telemetry.ts` | PostHog/Sentry lifecycle. `app/` is doc-correct (shell wiring); `common/telemetry/` groups it in-common (flagged §6). |
| `common/Types.ts` | types | see §3 | **SPLIT** (§3) | `PropsWithClassName` (1 consumer) vs id aliases (state-only). |
| `common/Utils.ts` | mixed | see §2 | **SPLIT** (§2) | 5 unrelated exports. |
| `common/autoUpdateUtils.ts` | pure formatters | 2 features | `common/utils/autoUpdate.ts` | Rename (drop `Utils` suffix — it's in `utils/`). |
| `common/builtinActions.ts` | data+guards | 3 features | `common/utils/builtinActions.ts` | Static catalog + `isBuiltIn*` predicates. Already topic-named. |
| `common/builtinSkills.ts` | data | 2 features | `common/utils/builtinSkills.ts` | `BUILTIN_SKILLS` catalog. |
| `common/copyImageToClipboard.ts` | helper | 1 (CopyImageContextMenu) | `components/copyImageToClipboard.ts` | Single consumer lives in `components/`; colocate. Keeps its test. |
| `common/formatRelativeTime.ts` | pure helper | 6+ features | `common/utils/formatRelativeTime.ts` | Widely shared. |
| `common/formatRepoUrl.ts` | pure helper | 1 (EntityMentionSuggestion) | `components/formatRepoUrl.ts` | Single consumer → colocate in `components/`. Promote to `common/utils/` if a 2nd appears. |
| `common/highlightMatch.tsx` | UI helper | 4 (all `components/`) | `components/highlightMatch.tsx` | Returns JSX; all consumers in `components/`. Stays in `components/`. |
| `common/modelCapabilities.ts` | data+getter | 2 features | `common/utils/modelCapabilities.ts` | Keyed by `LlmModel`; pairs with `modelConstants`. |
| `common/modelConstants.ts` | model catalog | 4 features | `common/utils/modelConstants.ts` | Cohesive (names/list/provider/routing) — not split. Could merge with `modelCapabilities` into `common/utils/models.ts`. |
| `common/overlayUtils.ts` | DOM query | 2 features | `common/utils/overlays.ts` | Rename. **Duplicate** of ShortcutUtils' `isDismissibleOverlayOpen` — consolidate (§6). |
| `common/pseudoSkills.ts` | parser+data | 2 features | `common/utils/pseudoSkills.ts` | Slash-command parsing (`/clear`, `/copy`, `/btw`). |
| `common/queryClient.ts` | state singleton | 20+ files | `common/state/queryClient.ts` | Server-state cache; sits with the state layer it serves. |
| `common/setupDefaults.ts` | data+resolver | 2 features | `common/utils/setupDefaults.ts` | Mirrors a backend default. Already topic-named. |
| `common/testUtils.tsx` | test helper | 6 test files | `common/utils/renderWithProviders.tsx` | Rename to its single export (content-named); drops the generic `testUtils`. |
| `common/tracing.ts` | perf infra | 3 files | `common/perf/tracing.ts` | Joins `perf/` alongside `workspaceSwitchProfiler.ts`. |
| `common/useInterval.ts` | hook | 3 features | `common/hooks/useInterval.ts` | Shared. |
| `common/useManagedDependency.ts` | hook | 2 (both settings) | `pages/settings/hooks/useManagedDependency.ts` | Single feature (Claude/pi settings sections) → push down. |
| `common/useOnMountIf.ts` | hook | 1 (settings/RepoRow) | `common/hooks/useOnMountIf.ts` | Keep in `common/` (flagged §6): its purpose is to be the one audited lint-suppression seam; inlining undercuts that. |
| `common/usePollingInterval.ts` | hook | 2 features | `common/hooks/usePollingInterval.ts` | Shared. |

---

## 2. `common/Utils.ts` — SPLIT (grab-bag, 5 unrelated exports)

| Export | Consumers | Destination |
| --- | --- | --- |
| `mergeClasses` | 8+ components/pages | `common/utils/classNames.ts` |
| `optional` | very wide (20+) | `common/utils/optional.ts` |
| `neutral` (`"gray"` const) | 3 components | `common/theme/neutralColor.ts` — it's a Radix color default; joins `theme/`. |
| `makeRequestId` | 1 (`apiClient.ts`) | inline into `apiClient.ts` (single consumer). Alt: `common/utils/requestId.ts`. |
| `useResolvedTheme` | 4 features | `common/state/hooks/useResolvedTheme.ts` — fronts the theme state domain (resolves config→concrete via `useThemeAppearance`). Alt: `common/hooks/`. |

---

## 3. `common/Guards.ts` + `common/Types.ts` — SPLIT

### `common/Guards.ts`

Every block guard is consumed **only** inside `pages/workspace/` (chat-alpha, `utils/`,
`hooks/`, `panels/fileBrowser`). Per the placement rule they move down out of `common/`.

| Export | Consumers | Destination |
| --- | --- | --- |
| `BlockUnion` (type) | workspace only | `pages/workspace/utils/blockGuards.ts` |
| `isTaskListArtifact` | 1 (workspace/hooks/useArtifactSync) | `pages/workspace/utils/blockGuards.ts` |
| `isTextBlock` | workspace only | `pages/workspace/utils/blockGuards.ts` |
| `isToolUseBlock` | workspace only | `pages/workspace/utils/blockGuards.ts` |
| `isToolResultBlock` | workspace only | `pages/workspace/utils/blockGuards.ts` |
| `isErrorBlock` | 1 (chat-alpha/buildRenderGroups) | `pages/workspace/utils/blockGuards.ts` |
| `isWarningBlock` | 1 (chat-alpha/buildRenderGroups) | `pages/workspace/utils/blockGuards.ts` |
| `isContextSummaryBlock` | 1 (chat-alpha/buildRenderGroups) | `pages/workspace/utils/blockGuards.ts` |
| `isContextClearedBlock` | 1 (chat-alpha/buildRenderGroups) | `pages/workspace/utils/blockGuards.ts` |
| `isResumeResponseBlock` | 1 (chat-alpha/buildRenderGroups) | `pages/workspace/utils/blockGuards.ts` |
| `isFileBlock` | workspace only | `pages/workspace/utils/blockGuards.ts` |
| `isGenericToolContent` | chat-alpha only | `pages/workspace/utils/blockGuards.ts` |
| `isDiffToolContent` | chat-alpha only | `pages/workspace/utils/blockGuards.ts` |
| `isLlmModel` | 1 (`common/state/atoms/userConfig`) | inline into `userConfig.ts` (single consumer). Alt: `common/utils/llmModel.ts`. |

### `common/Types.ts`

| Export | Consumers | Destination |
| --- | --- | --- |
| `PropsWithClassName` | 1 (`components/TooltipIconButton`) | inline into `TooltipIconButton.tsx`. Alt: `common/types/props.ts` if kept shared. |
| `RequestID` | `common/state` only | `common/state/ids.ts` |
| `TaskID` | `common/state` only | `common/state/ids.ts` (wire-shaped name persists per the task→agent migration note). |
| `ProjectID` | `common/state` only | `common/state/ids.ts` |

---

## 4. `common/ShortcutUtils.ts` — SPLIT (into existing `common/keybindings/`)

| Export | Consumers | Destination |
| --- | --- | --- |
| `parseShortcut` | keybindings, palette | `common/keybindings/matching.ts` |
| `matchesShortcut` | keybindings, palette | `common/keybindings/matching.ts` |
| `shouldHandleKeybinding` | keybindings/hooks, workspace | `common/keybindings/matching.ts` |
| `ShortcutParsed` (type) | internal + callers | `common/keybindings/matching.ts` |
| `initializeKeyboardLayoutMap` | `Main.tsx` | `common/keybindings/matching.ts` |
| `setKeyboardLayoutMapForTesting` | test seam | `common/keybindings/matching.ts` |
| (`matchesKey`, `KEY_TO_CODE`, layout-map internals) | private | `common/keybindings/matching.ts` (unexported) |
| `formatShortcutForDisplay` | palette, dialog, HotkeyChip, story | `common/keybindings/format.ts` |
| `isDismissibleOverlayOpen` (simple) | 1 (keybindings/hooks) | **DELETE** — consolidate onto `common/utils/overlays.ts` (§6). |
| `useModifiedEnter` | 2 (workspace: AskUserQuestion, ChatInput) | `pages/workspace/hooks/useModifiedEnter.ts` — workspace-only, push down. |

---

## 5. `shared/types.ts` — the `shared/` dir dies

Contents are the renderer's view of the Electron/backend bridge (the `window.sculptor`
contract defined in `preload.ts`/`main.ts`). Natural owner is `electron/`.

| Export(s) | Consumers | Destination |
| --- | --- | --- |
| `SculptorElectronAPI`, `SculptorDevInfo`, `ZoomCommand`, `CustomBackendSettings` | electron/preload/globals.d.ts, hooks, settings | `electron/bridge.ts` — the preload/IPC contract. |
| `BackendStatus`, `BackendStatusPayloads`, `AnyBackendStatus` | `common/state/atoms/backend`, `components/BackendStatusBoundary` | `electron/backendStatus.ts` |
| `AutoUpdateStatus`, `UpdateChannel` | `common/autoUpdateUtils`, `common/state/atoms/autoUpdate`, toasts, hooks, settings | `electron/autoUpdate.ts` |

**Layering caveat (flagged §6):** `common/` currently imports these (e.g.
`common/state/atoms/autoUpdate.ts`, the `autoUpdate.ts` util from §1). If the import-boundary
lint forbids `common/ → electron/`, host the three renderer-domain unions
(`BackendStatus*`, `AutoUpdateStatus`, `UpdateChannel`) in `common/types/backend.ts` instead
and keep only the pure preload surface (`SculptorElectronAPI` et al.) in `electron/bridge.ts`.

---

## 6. `pages/workspace/utils/utils.ts` + `pages/home/Utils.ts` — SPLIT

### `pages/workspace/utils/utils.ts`

| Export | Consumers | Destination |
| --- | --- | --- |
| `stripHtml` | ChatInput, QueuedMessageBar, chat-alpha | `pages/workspace/utils/stripHtml.ts` |
| `isDiffTool` | chat-alpha/chipRowUtils, panels/fileBrowser | `pages/workspace/utils/toolPredicates.ts` |
| `DIFF_TOOLS` | internal only (no external importer) | private const inside `toolPredicates.ts` |
| `isHiddenTool` | 2 (chat-alpha) | `pages/workspace/utils/toolPredicates.ts` |
| `isEnterPlanModeTool` | 1 (chat-alpha/AlphaToolGroup) | `pages/workspace/utils/toolPredicates.ts` (sibling grouping; or inline). |
| `formatSubagentType` | 1 (chat-alpha/AlphaSubagentPopover) | inline into `AlphaSubagentPopover.tsx`. Alt: `toolPredicates.ts`. |

### `pages/home/Utils.ts`

| Export | Consumers | Destination |
| --- | --- | --- |
| `getBranchName` | 1 (`pages/workspace/WorkspaceHeader.tsx`) | inline into `WorkspaceHeader.tsx`; **delete** `pages/home/Utils.ts`. |

`getBranchName` is a trivial `?? null` normalizer, and its only consumer is a **cross-page**
import (`workspace` reaching into `home`) — a layering violation. Inlining removes both the
straggler file and the violation. (`homeViews.ts` is already correctly topic-named.)

---

## 7. Internal generic-basename violations in existing subdirs

Existing subdirs (`state/ keybindings/ theme/ perf/ hooks/ openInApp/`) stay put. Only
`keybindings/` has banned basenames:

| Current | Contents | Proposed |
| --- | --- | --- |
| `keybindings/atoms.ts` | `keybindingsAtom`, `keybindingsMapAtom` (resolve user overrides onto definitions) | `keybindings/resolvedBindings.ts` |
| `keybindings/hooks.ts` | `useKeybinding`, `useKeybindingDisplayText`, `useKeybindingHandler` | `keybindings/useKeybinding.ts` (name for the primary hook) |
| `keybindings/types.ts` | `KeybindingId`, `KeybindingDefinition`, `Category*` types+constants | `keybindings/model.ts` (domain types + category constants) |
| `keybindings/index.ts` | barrel re-exporting the above | Keep **only if** it's the module's sole public surface. Today it's inconsistent — several files deep-import `keybindings/atoms.ts`/`hooks.ts`/`types.ts` (CommandPalette, KeyboardShortcutsDialog, useGlobalKeyboardShortcuts, useTerminal, workspace components). Either route all imports through the barrel or drop it; the rename above must update those deep importers regardless. |

Clean elsewhere: `state/` root files (`requestStore/requestTracking/taskDetailReducers/agentPanelPlacement`) and all of `state/atoms/`, `state/hooks/` are topic-named; `theme/`, `perf/`, `common/hooks/` are clean.

- **`openInApp/items.tsx`** — `items` is not on the banned list but reads generic. Minor:
  consider the feature name or content name (e.g. `openInApp/appTargets.tsx`). Low priority.

---

## 8. Judgment calls & flags

1. **Duplicate `isDismissibleOverlayOpen`.** Two definitions exist: a simple one in
   `ShortcutUtils.ts` (checks `document.activeElement.closest(...)`, used by
   `keybindings/hooks.ts`) and a thorough one in `overlayUtils.ts` (walks Radix poppers +
   TipTap portals + an `ignoreDialog` escape hatch, used by `useGlobalKeyboardShortcuts` and
   `NewWorkspaceForm`). Consolidate onto the thorough version at `common/utils/overlays.ts`
   and point `keybindings/hooks.ts` at it; delete the `ShortcutUtils` copy.

2. **Infra singletons vs the fixed kind vocab.** `Telemetry`/`Analytics`, `Auth`
   (`sessionToken`), `queryClient`, and `tracing` are app-shell infrastructure, which the doc
   routes to `app/` — but `app/` is still mid-migration (see the doc's Migration status).
   The map lands them in the nearest established `common/` home (`common/telemetry/`,
   `common/utils/sessionToken.ts`, `common/state/queryClient.ts`, `common/perf/tracing.ts`).
   If/when `app/` exists, telemetry + sessionToken are the strongest candidates to rise there.
   `sessionToken` also carries module state, so it's not a pure `utils/` helper — flag on move.

3. **`common/ → electron/` layering** for `shared/types.ts` (see §5 caveat). Decide whether
   the renderer-domain unions live in `electron/` or `common/types/backend.ts` based on what
   the import-boundary lint allows.

4. **Data catalogs in `common/utils/`.** `builtinActions/builtinSkills/pseudoSkills/`
   `setupDefaults/elementIds/modelConstants` are constants (± predicates), not pure fns.
   `common/` has no constants kind dir, so `utils/` is the pragmatic bucket — noted so a future
   reader doesn't expect only pure functions there.

5. **`useOnMountIf` stays in `common/`** despite a single current consumer: it exists to be the
   one audited `react-hooks/exhaustive-deps` suppression seam. Pushing it into `pages/settings/`
   would defeat that intent. Contrast `useManagedDependency` (genuinely settings-specific → down).

6. **`modelCapabilities` + `modelConstants`** are a cohesive `LlmModel`-keyed cluster and could
   merge into `common/utils/models.ts`; kept separate here to minimize churn.

---

## 9. Split counts

- **8 files split** by export: `Utils.ts` (5), `Types.ts` (4), `Guards.ts` (2 groups /14 syms),
  `ShortcutUtils.ts` (into 2 keybindings files + 1 dedupe + 1 workspace hook),
  `shared/types.ts` (3), `pages/workspace/utils/utils.ts` (6), `pages/home/Utils.ts` (inline),
  `Hooks.ts` (single-export rename, not a true split).
- **Pushed down to a feature (out of `common/`):** block guards → `pages/workspace/utils/`,
  `useTimedLatch` + `useModifiedEnter` → `pages/workspace/hooks/`, `useManagedDependency` →
  `pages/settings/hooks/`, `copyImageToClipboard`/`formatRepoUrl`/`highlightMatch` →
  `components/`.
- **Inlined into single consumer:** `makeRequestId`, `isLlmModel`, `PropsWithClassName`,
  `formatSubagentType`, `getBranchName`.
- **Dirs eliminated:** `shared/` (→ `electron/`), `pages/home/Utils.ts`.
- **Renames landing in `keybindings/`:** `atoms.ts`/`hooks.ts`/`types.ts` → topic names.
