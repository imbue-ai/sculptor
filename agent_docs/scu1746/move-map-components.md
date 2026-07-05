# components/ placement map (SCU-1746)

Applies the placement rule from `docs/development/style/frontend_structure.md`:
code lives with the feature that renders it; it moves up to `components/` only
when a **2+ distinct surfaces** consume it. Surfaces counted: `pages/<area>`,
each `components/<feature>/`, the app shell (`app/` — today split across the
`src/` root entry files + `layouts/`), `common/`, `plugins/`. Storybook stories
mirror `src/` and are **not** counted as a surface; colocated tests ride with
their source.

Scope: every loose file directly in `components/` and every subdirectory
**except** `sections/` and `nav/` (already mapped). Analysis only — no files were
moved or edited. Importer counts were extracted by resolving every `import`/`from`
specifier in the tree back to its target.

Key cross-cutting findings:

- **A TipTap "editor" subfeature is hiding in the root.** `Editor.tsx` (shared by
  `components/actions` + `pages/workspace`) drags a ~16-file cluster of TipTap
  config, extensions, and mention/suggestion list machinery whose only consumers
  are each other + `Editor`. It stays under `components/` (Editor is shared) but
  should be grouped into a `components/editor/` subfeature with the standard
  kind-dir anatomy. Only two pieces of the mention system escape the cluster and
  stay at the root: `EntityMentionSuggestion.ts` and `MentionChip.tsx` (both
  consumed by `mentionDetailPanes` and workspace chat rendering too).
- **A file-preview/lightbox cluster is workspace-only.** `FilePreviewList` +
  `FilePreview` + `ImageLightbox` + `CopyImageContextMenu` + `AgentLightboxContext`
  are reachable only from `pages/workspace` chat — they belong in a
  `pages/workspace/components/filePreview/` subfeature.
- **`common/` already imports several root files** (`Toast`, `skillBadge`,
  `workspaceTabIds`, `statusDot/statusUtils`, `newWorkspace/newWorkspaceAtoms`,
  `CommandPalette/*`). `common/` importing `components/` violates the documented
  import layering, so the **non-UI** parts each want a `common/` home (the UI kept
  in `components/`). Flagged per row.
- **Naming violations** corrected in-row: `BranchSelectorCore` (banned `Core`
  suffix), `DiffUtils`/`SuggestionUtils`/`FileUploadUtils` (PascalCase non-component
  + `Utils`), plus kebab dirs (`add-repo`, `path-autocomplete`, `onboarding-wizard`)
  and PascalCase dirs (`CommandPalette`, `DevPanel`, `MarkdownDiff`, `PaletteDialog`)
  → camelCase, and banned basenames inside `CommandPalette/` (`atoms.ts`,
  `hooks.ts`, `types.ts`).

---

## Moves — loose files

| current path | importers (by surface, stories/tests excluded) | proposed target | note |
| --- | --- | --- | --- |
| components/AgentLightboxContext.tsx | pages/workspace 2 (FilePreviewList, AlphaChatInterface) | pages/workspace/components/filePreview/AgentLightboxContext.tsx | part of the workspace-only lightbox cluster |
| components/AgentSettingsControls.tsx | components/newWorkspace 1 | components/newWorkspace/AgentSettingsControls.tsx | single consumer NewWorkspaceForm |
| components/AtomToast.tsx | app-shell 1 (layouts) | app/ (shell) | shell-mounted toast host; +AtomToast.test.tsx |
| components/AutoUpdateToasts.tsx | app-shell 1 (EmptyFirstRunGate) | app/ (shell) | shell-mounted toast host |
| components/BackendStatusBoundary.tsx | app-shell 1 (App.tsx) | app/ (shell) | shell wiring |
| components/BranchSelector.tsx | components/newWorkspace 1 | components/newWorkspace/BranchSelector.tsx | single consumer NewWorkspaceForm |
| components/CapabilityGate.tsx | pages/workspace 2 (ChatInput, QueuedMessageBar) | pages/workspace/components/CapabilityGate.tsx | +CapabilityGate.test.tsx |
| components/CodeBlockExtension.ts | editor-internal (TipTapConfig) | components/editor/codeBlockExtension.ts | TipTap extension; +.test.ts, +codeBlockExtension.testUtils.ts |
| components/ConfigLoader.tsx | app-shell 1 (App.tsx) | app/ (shell) | shell wiring |
| components/CopyImageContextMenu.tsx | editor-internal → workspace cluster (FilePreview, ImageLightbox) | pages/workspace/components/filePreview/CopyImageContextMenu.tsx | +test |
| components/DevModeIndicator.tsx | components/nav 1 (WorkspaceSidebar) | components/nav/DevModeIndicator.tsx | |
| components/DiffUtils.ts | pages/workspace 8 | pages/workspace/utils/diff.ts | rename: PascalCase+`Utils` → topic-named `diff.ts` |
| components/Editor.tsx | components/actions 1 + pages/workspace 2 | components/editor/Editor.tsx | stays shared, but becomes the `editor/` subfeature entry |
| components/EntityMentionHydration.ts | editor-internal (Editor) | components/editor/entityMentionHydration.ts | +test |
| components/EntityMentionList.tsx | editor-internal | components/editor/EntityMentionList.tsx | +test |
| components/FilePreview.tsx | pages/workspace (FilePreviewList) | pages/workspace/components/filePreview/FilePreview.tsx | +test |
| components/FilePreviewList.tsx | pages/workspace 3 (ChatInput, Alpha*Message) | pages/workspace/components/filePreview/FilePreviewList.tsx | cluster entry; +test |
| components/FileUpload.tsx | pages/workspace 1 (ChatInput) | pages/workspace/components/FileUpload.tsx | |
| components/FileUploadUtils.ts | components/editor 1 + pages/workspace 2 | common/utils/fileUpload.ts | non-UI helper shared by 2 surfaces; rename `Utils`→topic; +test |
| components/ImageLightbox.tsx | pages/workspace (via cluster) | pages/workspace/components/filePreview/ImageLightbox.tsx | +test |
| components/IndeterminateProgress.tsx | pages/workspace 1 (diffViewer/DiffViewer) | pages/workspace/components/diffViewer/IndeterminateProgress.tsx | generic bar; single consumer today |
| components/KeyboardShortcutsDialog.tsx | app-shell 1 (layouts) | app/ (shell) | global-shortcuts dialog |
| components/MentionList.tsx | editor-internal | components/editor/MentionList.tsx | |
| components/MentionNodeView.tsx | editor-internal (TipTapConfig) | components/editor/MentionNodeView.tsx | |
| components/MentionPickerList.tsx | editor-internal | components/editor/MentionPickerList.tsx | +test |
| components/MentionPickerSuggestion.ts | editor-internal | components/editor/mentionPickerSuggestion.ts | camelCase plumbing module |
| components/NotificationToasts.tsx | app-shell 1 (layouts) | app/ (shell) | shell-mounted toast host |
| components/RepoPathDialog.tsx | app-shell 1 (layouts) | app/ (shell) | |
| components/RepoSelector.tsx | components/newWorkspace 1 | components/newWorkspace/RepoSelector.tsx | single consumer NewWorkspaceForm |
| components/ReportProblemPopover.tsx | components/nav 1 | components/nav/ReportProblemPopover.tsx | |
| components/RequireOnboarding.tsx | app-shell 1 (App.tsx) | app/ (shell) | shell gate |
| components/SendButton.tsx | pages/workspace 1 (ChatInput) | pages/workspace/components/SendButton.tsx | |
| components/SkillList.tsx | editor-internal | components/editor/SkillList.tsx | editor suggestion list (distinct from `skills/`); +test |
| components/SkillSuggestion.ts | editor-internal | components/editor/skillSuggestion.ts | |
| components/SplitSuggestionLayout.tsx | editor-internal | components/editor/SplitSuggestionLayout.tsx | +test |
| components/SuggestionDismissalPlugin.ts | editor-internal | components/editor/suggestionDismissalPlugin.ts | +test |
| components/SuggestionListContainer.tsx | editor-internal | components/editor/SuggestionListContainer.tsx | +test |
| components/SuggestionUtils.ts | editor-internal (Editor + cluster) | components/editor/utils/suggestion.ts | rename: PascalCase+`Utils` → `utils/suggestion.ts` |
| components/ThemeProvider.tsx | app-shell 1 (App.tsx) | app/ (shell) | theme provider; alt: `common/theme/` |
| components/TipTapConfig.ts | editor-internal (Editor) | components/editor/tipTapConfig.ts | central TipTap config/engine |
| components/TipTapMarkdown.test.ts | editor-internal (tests TipTapConfig/hydration) | components/editor/tipTapMarkdown.test.ts | editor round-trip test (no separate source) |
| components/VersionPopover.tsx | components/nav 1 (WorkspaceSidebar) | components/nav/VersionPopover.tsx | +test |
| components/VerticalOverlayScrollbar.tsx | pages/workspace 2 (AlphaChatInterface, fileBrowser/FileTree) | pages/workspace/components/VerticalOverlayScrollbar.tsx | page-level shared across 2 ws subfeatures |
| components/WarningStatusBanner.tsx | app-shell 1 (layouts) | app/ (shell) | |
| components/fuzzyFileScorer.ts | editor-internal (SkillSuggestion, SuggestionUtils) | components/editor/utils/fuzzyFileScorer.ts | +test |
| components/skillBadge.ts | common 2 + components/editor + components/skills + pages/workspace | common/utils/skillBadge.ts | non-UI helper; **common already imports it** (layering) |
| components/useCapabilityGate.ts | components(shared ModelSelector) + pages/workspace 2 | common/hooks/useCapabilityGate.ts | shared hook; can't live in ws (ModelSelector is shared). `common/state/hooks/` if it fronts a capability state domain |
| components/useWorkspaceTabActions.ts | components/CommandPalette + components/nav + pages/workspace | common/state/hooks/useWorkspaceTabActions.ts | 3-surface shared hook over tab state |
| components/workspaceTabIds.ts | app-shell 1 + common 2 + components/nav 1 | common/utils/workspaceTabIds.ts | tab-id constants; **common already imports it** (layering) |

## Moves — subdirectories

| current path | importers (by surface) | proposed target | note |
| --- | --- | --- | --- |
| components/MarkdownDiff/ | pages/workspace 1 (diffPanel/ReadOnlyPreview) | pages/workspace/components/markdownDiff/ | single ws consumer; camelCase; shelve `anchorBehavior`/`frontmatter`/`markdownPlugins` → `utils/`. Sibling of `diffPanel/` (depth cap forbids nesting) |
| components/PaletteDialog/ | components/newWorkspace 1 (NewWorkspaceDialog) | components/newWorkspace/PaletteDialog.tsx | dir dissolves; 1 component goes flat into the feature |
| components/layout/ | components/CommandPalette + nav 2 + sections 2 + app-shell 2 + pages/workspace 2 | common/state/atoms/sidebar.ts | dir holds only `sidebarAtoms.ts` = shared layout **state** → `common/state/`; rename `sidebarAtoms`→`sidebar` |
| components/onboarding-wizard/ | app-shell 1 (RequireOnboarding gate) | pages/onboarding/ | standalone surface entered via the shell gate; kebab→camelCase; `dependencyTypes.ts`→`types/`. Tradeoff: keep as `components/onboardingWizard/` if treated as shell-gated shared UI rather than a page |
| components/__tests__/ | — (holds `entityMentionRendering.bench.ts`) | components/editor/entityMentionRendering.bench.ts | central `__tests__/` violates colocation; bench belongs beside the editor mention code |

---

## Stays — loose files (shared by 2+ surfaces)

| current path | importers (by surface) | proposed target | note |
| --- | --- | --- | --- |
| components/BranchSelectorCore.tsx | components/newWorkspace(via BranchSelector) + pages/workspace(TargetBranchSelector) | components/BranchCombobox.tsx | **stays** shared; rename — `Core` suffix is banned. It's the shared branch combobox both selectors build on |
| components/Code.tsx | components(shared MarkdownBlock) + pages/settings 2 | components/Code.tsx | **stays**; shared code-render component |
| components/DeleteConfirmationDialog.tsx | CommandPalette + nav + pages/add-workspace + pages/workspace 2 | components/DeleteConfirmationDialog.tsx | **stays**; +test |
| components/EffortSelector.tsx | components/newWorkspace(AgentSettingsControls) + pages/workspace(ChatInput) | components/EffortSelector.tsx | **stays** |
| components/effortConstants.ts | components(shared EffortSelector) + pages/settings | components/effortConstants.ts | **stays**; non-UI — could promote to `common/utils/effort.ts` |
| components/EntityMentionSuggestion.ts | components/editor 7 + components/mentionDetailPanes 3 + pages/workspace 1 | components/EntityMentionSuggestion.ts | **stays**; the shared mention definition — 3 surfaces, so it does *not* fold into `editor/` |
| components/FastModeToggle.tsx | components/newWorkspace(AgentSettingsControls) + pages/workspace(ChatInput) | components/FastModeToggle.tsx | **stays** |
| components/HoverCard.tsx | components(shared MentionChip) | components/HoverCard.tsx | **stays**; generic kit widget |
| components/InlineRenameInput.tsx | components/nav + components/sections | components/InlineRenameInput.tsx | **stays** |
| components/KeyboardHint.tsx | components/newWorkspace + components/path-autocomplete + pages/workspace | components/KeyboardHint.tsx | **stays**; 3 surfaces |
| components/MarkdownBlock.tsx | pages/workspace 3 + plugins 1 | components/MarkdownBlock.tsx | **stays**; plugin-SDK facing |
| components/MentionChip.tsx | components/editor(MentionNodeView) + pages/workspace(AlphaMarkdownBlock) | components/MentionChip.tsx | **stays**; rendered chip used by editor + chat markdown; +test |
| components/ModelSelectOptions.tsx | components(shared ModelSelector) + pages/settings | components/ModelSelectOptions.tsx | **stays** |
| components/ModelSelector.tsx | components/newWorkspace(AgentSettingsControls) + pages/workspace(ChatInput) | components/ModelSelector.tsx | **stays**; +test |
| components/PulsingCircle.tsx | components/statusDot + pages/settings + pages/workspace | components/PulsingCircle.tsx | **stays**; 3 surfaces |
| components/popoverFriendlyModal.ts | components(shared DeleteConfirmationDialog only) | components/popoverFriendlyModal.ts | **stays** with its shared consumer; single-consumer helper (candidate to inline) |
| components/TitleBar.tsx | app-shell(BackendStatusBoundary) + onboarding + pages/error | components/TitleBar.tsx | **stays**; 3 surfaces |
| components/Toast.tsx | app-shell + common 5 + 4 components subfeatures + pages/settings + pages/workspace | components/Toast.tsx | **stays** (shared UI). **Split:** `ToastType`/`ToastContent` types are pulled by `common/state` → extract them to `common/state/atoms/toasts.ts` to fix the common→components import; +test |
| components/TooltipIconButton.tsx | components/nav + components/skills + pages/workspace | components/TooltipIconButton.tsx | **stays** |

## Stays — subdirectories (shared by 2+ surfaces)

| current path | importers (by surface) | proposed target | note |
| --- | --- | --- | --- |
| components/CommandPalette/ | common 3 + nav 2 + sections 1 + app-shell 3 + pages/workspace 6 | components/commandPalette/ | **stays**; PascalCase→camelCase. Shelve plumbing: `atoms.ts`→`atoms/commandPalette.ts`, `hooks.ts`+`useCommandRuntime`+`useContextActionRuntimes`→`hooks/`, `types.ts`→`types/commandPalette.ts`, `filter`/`groups`/`groupCommands`/`registry`/`runtime`/`pages`/`commandActions`→`utils/` (fixes banned `atoms.ts`/`hooks.ts`/`types.ts`). `contextActions/atoms.ts` + `commandActions.ts` are imported by `common/state` → extract that command-action state to `common/state/` |
| components/DevPanel/ | app-shell 1 (App.tsx) + components/nav(VersionPopover) | components/devPanel/ | **stays** (dev tooling, 2 surfaces); camelCase; shelve `useReactGrab`/`useTanstackDevtools`/`useTanstackEventLog` → `hooks/` |
| components/actions/ | pages/settings 1 + pages/workspace 1 | components/actions/ | **stays**; already camelCase; all components, no loose plumbing |
| components/add-repo/ | components/nav + components/onboarding + pages/settings + components/newWorkspace(via RepoSelector) | components/addRepo/ | **stays**; kebab→camelCase. Shelve `useAddRepo`/`useCloneDefaults`/`useRemoteRepos`→`hooks/`, `providerMeta`/`remoteRepoFormHelpers`→`utils/` |
| components/mentionDetailPanes/ | components(shared MentionChip) | components/mentionDetailPanes/ | **stays**; camelCase already; subfeature (3 panes + shell) reached via shared MentionChip |
| components/newWorkspace/ | app-shell + common + CommandPalette 2 + nav 2 + layouts 2 + pages/workspace | components/newWorkspace/ | **stays**. Tidy kind dirs: `newWorkspaceAtoms.ts`→`atoms/newWorkspace.ts` (its `lastWorkspaceCreationSettingsAtom` is pulled by `common` → consider `common/state/atoms/`), `homePromptPrefill`/`sanitizeBranchName`→`utils/`, `useCreateWorkspaceFromSidebar`→existing `hooks/` |
| components/panels/ | pages/workspace 3 + plugins 1 | components/panels/ | **stays**; camelCase; single `PanelHeader` component, plugin-SDK facing |
| components/path-autocomplete/ | components/add-repo 3 + components/onboarding 1 | components/pathAutocomplete/ | **stays**; kebab→camelCase. Shelve `useDirectoryListing`→`hooks/`, `detectHomeDirPrefix`→`utils/` |
| components/skills/ | components(shared MentionChip) + pages/workspace(SkillsPanel) | components/skills/ | **stays**; camelCase; 2 components |
| components/statusDot/ | common 2 + CommandPalette + nav + sections 3 + pages/add-workspace + pages/workspace | components/statusDot/ | **stays** (shared UI, 6 surfaces). **Split:** `statusUtils.ts` is pure logic imported by `common/state` → move to `common/utils/statusDot.ts`; keep `StatusDot.tsx` UI here |
