# pages/workspace/components/ dissolution move-map (SCU-1746)

Analysis-only proposal for dissolving `sculptor/frontend/src/pages/workspace/components/`
(a generic grouping directory) and for sorting the loose plumbing at the
`pages/workspace/` root into the standard anatomy. Governed by
`docs/development/style/frontend_structure.md`:

- **Placement rule** — code lives with the feature that renders it; it rises to a shared
  home only when a 2nd feature imports it. Within `pages/workspace/` the sub-features
  (`chatAlpha/`, `panels/`, `diffPanel/`, …) each carry their own `atoms/ hooks/ utils/`;
  the `pages/workspace/{hooks,utils}/` kind dirs are the workspace-area shared bucket for
  things used by **2+ sub-features but nothing outside the page**. A 2nd *surface* (another
  page, or `components/`) forces promotion to `common/` or `components/`.
- **Helper ladder** — private fn → feature `utils/` → its own named file → `common/utils/`.
- **Naming** — components `PascalCase.tsx`; everything else `camelCase.ts`; banned basenames
  (`utils/atoms/types/hooks/helpers/misc.ts`) everywhere; `index.ts` reserved for barrels.
- **Depth cap** — `feature/subfeature/kind/file`; subfeatures don't nest.

All paths below are under `sculptor/frontend/src/`. Colocated `.module.scss` and `.test.*`
travel with their source and are omitted from the tables unless load-bearing. **No files
were moved or edited — this is the map only.**

Relationship to sibling docs: `chat-alpha` → `chatAlpha` and the `Alpha*` prefixes are a
separate stacked PR (per the doc's migration note) — this map keeps the name `chatAlpha`.
`pages/workspace/utils/utils.ts` is **owned by `move-map-common.md` §6**; its split is
restated in §8 here for completeness and is fully aligned. `diffPanel/` + `diffViewer/`
staying separate (not merged into `diff/`) follows `decisions.md` #3.

---

## 1. Feature dirs that emerge under `pages/workspace/`

After the dissolution, `pages/workspace/components/` is gone and its children become
siblings of `panels/`:

| Dir | Origin | Contents |
| --- | --- | --- |
| `chatAlpha/` | rename of `components/chat-alpha/` | the dominant chat feature; **absorbs** the chat container + input + streaming plumbing + AskUserQuestion + the one-file `tools/` subdir (§3, §4) |
| `diffPanel/` | `components/diffPanel/` moved up as-is | pure move (internal `atoms.ts`/`types.ts` basename cleanup is a follow-up, §9) |
| `diffViewer/` | `components/diffViewer/` moved up as-is | pure move (internal `types.ts` basename cleanup is a follow-up) |
| `queuedMessages/` | **new** | `QueuedMessages`, `QueuedMessageBar`, `UndoQueuedMessageDialog` (§5) |
| `workspaceChrome/` | **new** | shell frame: `WorkspaceLayoutShell`, `WorkspaceHeader`, the shell-owned confirmations, `TargetBranchSelector` (§6) |

Two of the `components/` children do **not** survive as their own sibling: `tools/`
dissolves into `chatAlpha/` (§4), and there is no `mentionDetailPanes/` here — that dir
lives at the top-level `src/components/mentionDetailPanes/` (already shared, out of scope).

Promoted **out** of the workspace page (a 2nd surface imports them): `components/prButton/`,
`components/workspacePeek/`, `components/diffSummary/`, and four items into `common/` (§7).

`WorkspacePage.tsx` and `EmptyFirstRunPage.tsx` stay at the `pages/workspace/` root as the
two routed top-level views (`Router` → `WorkspacePage`; `EmptyFirstRunGate` → `EmptyFirstRunPage`).

---

## 2. `components/` subdirectories — the directory moves

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `pages/workspace/components/chat-alpha/` | panels/AgentPanel (via ChatPanelContent), stories | `pages/workspace/chatAlpha/` | rename only; `Alpha*` prefixes untouched (stacked PR) |
| `pages/workspace/components/diffPanel/` | panels/*, chatAlpha/*, diffViewer, **and** `common/state/hooks/useUnifiedStream`, `components/MentionChip`, `components/sections/addPanelCore` | `pages/workspace/diffPanel/` | pure move. **Layering flag (§10):** its `atoms.ts`/`types.ts` are already imported by `common/` and `components/`; those cross-layer reads survive the move — promoting the diff-tab atoms to `common/state/` is a separate follow-up |
| `pages/workspace/components/diffViewer/` | diffPanel/atoms, panels/{Changes,Commits,Files}Panel, panels/selectionRecency, story | `pages/workspace/diffViewer/` | pure move; barrel `index.ts` kept (public surface) |
| `pages/workspace/components/tools/` | (only `askUserQuestionUtils.ts`, chatAlpha-only) | **dissolves into `chatAlpha/`** (§4) | one file, single consumer → no one-file sibling; deviates from the initial "tools becomes a sibling" assumption in `move-map.md` step 4 |

---

## 3. Loose files → `chatAlpha/` (components)

Everything here has **chatAlpha as its only feature-consumer** (the `ChatPanelContent`
container renders `AlphaChatInterface`/`AgentTerminalPanel`, so it and its dependents fold
into the chat feature; `panels/AgentPanel` importing `chatAlpha/ChatPanelContent` is a
normal cross-feature compose).

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `components/ChatInput.tsx` | chatAlpha/AlphaChatInterface, story | `chatAlpha/ChatInput.tsx` | large (34KB) but flat-at-root is fine |
| `components/ErrorInput.tsx` | chatAlpha/AlphaChatInterface | `chatAlpha/ErrorInput.tsx` | |
| `components/AskUserQuestion.tsx` (+`.behavior.md`) | chatAlpha/AlphaChatInterface, story | `chatAlpha/AskUserQuestion.tsx` | `.behavior.md` travels along |
| `components/ChatSearchBar.tsx` | chatAlpha/AlphaSearchBar | `chatAlpha/ChatSearchBar.tsx` | |
| `components/ChatPanelContent.tsx` | panels/AgentPanel | `chatAlpha/ChatPanelContent.tsx` | the chat/terminal container; anchor of the fold |
| `components/AgentTerminalPanel.tsx` | ChatPanelContent | `chatAlpha/AgentTerminalPanel.tsx` | terminal-mode body; slightly awkward under an "alpha" name — see §9 alternative |
| `components/BtwPopup.tsx` | ChatPanelContent | `chatAlpha/BtwPopup.tsx` | |
| `components/SetupConfigPrompt.tsx` | chatAlpha/SetupStatusCard | `chatAlpha/SetupConfigPrompt.tsx` | imports `ChatIntro.module.scss` (next row) |
| `components/ChatIntro.module.scss` | SetupConfigPrompt (only) | `chatAlpha/ChatIntro.module.scss` | orphaned-name style (no `ChatIntro.tsx`); rename-to-consumer is a minor follow-up |
| `components/useChatData.ts` | ChatPanelContent, chatAlpha/AlphaChatInterface | `chatAlpha/hooks/useChatData.ts` | |
| `components/useTerminalChatActions.ts` | AgentTerminalPanel (other mentions are comments) | `chatAlpha/hooks/useTerminalChatActions.ts` | |

---

## 4. Root `hooks/` + `utils/` + `tools/` files that follow the chat feature down

Single-consumer streaming/subagent plumbing whose only reachable consumer is the chat
feature; per the placement rule it moves **into** `chatAlpha/`, not the workspace-area bucket.

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `pages/workspace/hooks/useSmoothStreaming.ts` | useChatData (only) | `chatAlpha/hooks/useSmoothStreaming.ts` | exports `useChatSmoothStreaming` |
| `pages/workspace/hooks/useSmoothStreamingViewportObserver.ts` | useChatData (only) | `chatAlpha/hooks/useSmoothStreamingViewportObserver.ts` | |
| `pages/workspace/utils/StreamingEngine.ts` (+`.test`) | useSmoothStreaming (only) | `chatAlpha/utils/streamingEngine.ts` | engine class with mass → own file; camelCase per naming rule |
| `pages/workspace/utils/subagentTree.ts` (+`.test`) | chatAlpha (14 files) + story | `chatAlpha/utils/subagentTree.ts` | `SubagentTreeNode`/`SUBAGENT_TOOL_NAMES`/builders — chatAlpha-only |
| `components/tools/askUserQuestionUtils.ts` | chatAlpha/AlphaAskUserQuestionBlock (only) | `chatAlpha/utils/askUserQuestion.ts` | dissolves the one-file `tools/` subdir |

> Note: `chatAlpha/` today keeps its own helpers **flat at the root** and hooks in `hooks/`;
> it has no `utils/` dir yet. Recommended target is the standard `chatAlpha/utils/`, adopted
> together with a sweep of chatAlpha's existing flat `*Utils.ts` into `utils/` (a chatAlpha-wide
> anatomy pass, natural to bundle with the stacked chat-rename PR). If that sweep is deferred,
> land these flat at `chatAlpha/` root to match current convention.

---

## 5. New feature: `queuedMessages/`

Cohesive trio about queued messages; two external consumers (chatAlpha via `QueuedMessages`,
`panels/NotesPanel` via `UndoQueuedMessageDialog`) → a shared workspace-level feature dir.

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `components/QueuedMessages.tsx` | chatAlpha/AlphaChatInterface | `queuedMessages/QueuedMessages.tsx` | chatAlpha-only, but kept with the cluster for cohesion |
| `components/QueuedMessageBar.tsx` | QueuedMessages, story | `queuedMessages/QueuedMessageBar.tsx` | imports `workspace/utils/stripHtml` (§8) |
| `components/UndoQueuedMessageDialog.tsx` | QueuedMessages, panels/NotesPanel | `queuedMessages/UndoQueuedMessageDialog.tsx` | the shared member that justifies the dir |

Alternative considered: fold `QueuedMessages`+`QueuedMessageBar` into `chatAlpha/` and give
`UndoQueuedMessageDialog` a lone home — rejected as it splits a cohesive trio.

---

## 6. New feature: `workspaceChrome/`

The shell frame around the panels. `WorkspaceLayoutShell`/`WorkspaceHeader` currently sit at
the workspace root; moving them here with their subcomponents leaves the root glanceable
(`WorkspacePage.tsx` + `EmptyFirstRunPage.tsx` + feature dirs). `WorkspacePage` still imports
`workspaceChrome/WorkspaceLayoutShell`.

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `pages/workspace/WorkspaceLayoutShell.tsx` | WorkspacePage | `workspaceChrome/WorkspaceLayoutShell.tsx` | moved from root (see §9 scope note) |
| `pages/workspace/WorkspaceHeader.tsx` | WorkspaceLayoutShell | `workspaceChrome/WorkspaceHeader.tsx` | moved from root |
| `components/AgentDeleteConfirmation.tsx` | WorkspaceLayoutShell | `workspaceChrome/AgentDeleteConfirmation.tsx` | shell-owned dialog (useWorkspaceDynamicPanels only mentions it in a comment) |
| `components/TerminalCloseConfirmation.tsx` | WorkspaceLayoutShell, AgentDeleteConfirmation | `workspaceChrome/TerminalCloseConfirmation.tsx` | shell-owned dialog |
| `components/TargetBranchSelector.tsx` | WorkspaceHeader | `workspaceChrome/TargetBranchSelector.tsx` | |
| `pages/workspace/hooks/useWorkspaceTargetBranches.ts` | WorkspaceHeader (only) | `workspaceChrome/hooks/useWorkspaceTargetBranches.ts` | |

Naming: `workspaceChrome/` per the task's suggestion; `chrome/` is the shorter,
prefix-consistent alternative (siblings are unprefixed: `panels/`, `diffPanel/`) but reads
ambiguously — flagged for your call. `decisions.md` lists four coexisting delete-confirmation
components as a consolidation candidate; `AgentDeleteConfirmation`/`TerminalCloseConfirmation`
landing together here makes that easier later.

---

## 7. Promotions out of `pages/workspace/`

A 2nd **surface** imports these, so they rise to `components/` or `common/` (and doing so
resolves real, pre-existing layering violations).

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `components/PrButton.tsx` | **`pages/add-workspace/WorkspaceRow` (cross-page)**, WorkspaceHeader | `components/prButton/PrButton.tsx` | cross-page consumer forces promotion; a page never imports another page |
| `components/PrDetailDropdown.tsx` | PrButton (only) | `components/prButton/PrDetailDropdown.tsx` | rides with PrButton |
| `components/PrPromptDialog.tsx` | PrButton (only) | `components/prButton/PrPromptDialog.tsx` | rides with PrButton |
| `components/WorkspacePeekOverlay.tsx` | **`components/nav/WorkspaceSidebar` (cross-layer)**, chatAlpha/AlphaPromptNavigator, chatAlpha/hooks/usePillHoverDelay | `components/workspacePeek/WorkspacePeekOverlay.tsx` | a `components/` consumer forces promotion; fixes `components/ → pages/` violation |
| `components/WorkspacePeekPopover.tsx` | WorkspacePeekOverlay (only) | `components/workspacePeek/WorkspacePeekPopover.tsx` | |
| `components/AgentStatusDot.tsx` | WorkspacePeekPopover (only) | `components/workspacePeek/AgentStatusDot.tsx` | banner variant that wraps `components/statusDot`'s `AgentStatusDot`; **name collision** with that base — rename (e.g. `PeekAgentStatusDot`) recommended (§9) |
| `pages/workspace/hooks/useRelativeTime.ts` | AgentStatusDot (only) | `components/workspacePeek/hooks/useRelativeTime.ts` | colocate with sole consumer; promote to `common/hooks/` if reused |
| `components/DiffSummary.tsx` | WorkspaceHeader, WorkspacePeekPopover | `components/diffSummary/DiffSummary.tsx` | shared by the workspace header **and** the promoted peek → must live in `components/` |
| `pages/workspace/utils/parseDiffStats.ts` (+`.test`) | DiffSummary, WorkspacePeekPopover | `common/utils/parseDiffStats.ts` | pure diff-stat parser, 2 cross-surface consumers |

Coupling note: `DiffSummary` + `parseDiffStats` promote **because** peek promotes. If you
decide to leave `workspacePeek/` inside the workspace (accepting the existing sidebar
violation), then `DiffSummary` stays in the workspace (`workspaceChrome/`) and `parseDiffStats`
stays in `pages/workspace/utils/`.

---

## 8. Workspace-root plumbing → standard anatomy

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `pages/workspace/atoms.ts` | **`components/CommandPalette/hooks` (cross-layer)**, ChatPanelContent, panels/TerminalPanelView | `common/state/atoms/panelMounts.ts` | `chatPanelMountedAtom`/`terminalPanelMountedAtom` are read by a `components/` surface → promote to the shared state mirror; fixes `components/ → pages/`. (Naive "→ workspace `atoms/`" is wrong here because of the cross-surface reader.) |
| `pages/workspace/Types.ts` | **`common/state/atoms/taskDetails` (cross-layer)**, hooks/useArtifactSync, panels/useWorkspacePanelData | `common/state/types/artifacts.ts` (or fold `ArtifactsMap` into `taskDetails.ts`) | a stored state atom references `ArtifactsMap` → it belongs in the state layer; fixes `common/ → pages/` |
| `pages/workspace/hooks/useArtifactSync.ts` | **`common/state/hooks/useWorkspaceShellBootstrap` (cross-layer call)** | **stays** `pages/workspace/hooks/useArtifactSync.ts` | it's a workspace hook (imports block guards that `move-map-common.md` §3 pushes down to `workspace/utils/blockGuards.ts`). The fix for the violation is to **hoist the `useArtifactSync(...)` call out of the common bootstrap hook up into `WorkspacePage`**, not to promote the hook. Aligns with `move-map-common.md` §3 |
| `pages/workspace/hooks/useWorkspaceCodePath.ts` (+`.test`) | chatAlpha (3), panels/fileBrowser/useFileMenuGroups | **stays** `pages/workspace/hooks/useWorkspaceCodePath.ts` | 2 sub-features, page-only → workspace-area shared bucket |
| `pages/workspace/utils/utils.ts` | see below | **SPLIT — owned by `move-map-common.md` §6** | restated for completeness; fully aligned |

`utils/utils.ts` split (per `move-map-common.md` §6, aligned):
- `stripHtml` (ChatInput, QueuedMessageBar, chatAlpha) → `pages/workspace/utils/stripHtml.ts`
- `isDiffTool` (chatAlpha/chipRowUtils, panels/fileBrowser) → `pages/workspace/utils/toolPredicates.ts`
- `DIFF_TOOLS` (internal only) → private const inside `toolPredicates.ts`
- `isHiddenTool` (chatAlpha ×2) → `pages/workspace/utils/toolPredicates.ts`
- `isEnterPlanModeTool` (chatAlpha ×1) → `pages/workspace/utils/toolPredicates.ts`
- `formatSubagentType` (chatAlpha/AlphaSubagentPopover ×1) → inline into that component

After all moves, `pages/workspace/hooks/` retains `useArtifactSync` + `useWorkspaceCodePath`
(plus `useTimedLatch`/`useModifiedEnter` arriving from `common/` per `move-map-common.md`),
and `pages/workspace/utils/` retains `stripHtml.ts` + `toolPredicates.ts` (plus
`blockGuards.ts` from `common/`). Both remain valid workspace-area kind dirs.

---

## 9. Dead code

| Current path | Importers summary | Proposed target | Note |
| --- | --- | --- | --- |
| `components/RepoSegment.tsx` (+`.module.scss`) | **none** — the only `RepoSegment` references anywhere are two comments in `components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts` ("Mirrors RepoSegment's logic") | **DELETE** | a ~6.8KB component with zero import sites and no registry/dynamic/story reference found; recommend deletion rather than relocation (worth one final confirmation before removing) |

---

## 10. Layering violations surfaced (pre-existing; this pass fixes several)

- `components/CommandPalette/hooks.ts` → `pages/workspace/atoms.ts` — **fixed** by §8 (→ `common/state/`).
- `common/state/atoms/taskDetails.ts` → `pages/workspace/Types.ts` — **fixed** by §8 (→ `common/state/`).
- `common/state/hooks/useWorkspaceShellBootstrap.ts` → `pages/workspace/hooks/useArtifactSync.ts` — **fix proposed** in §8 (hoist the call to `WorkspacePage`).
- `components/nav/WorkspaceSidebar.tsx` → `pages/workspace/components/WorkspacePeekOverlay.tsx` — **fixed** by §7 (→ `components/workspacePeek/`).
- `pages/add-workspace/.../WorkspaceRow.tsx` → `pages/workspace/components/PrButton.tsx` — **fixed** by §7 (→ `components/prButton/`).
- `common/state/hooks/useUnifiedStream.ts`, `components/MentionChip.tsx`, `components/sections/addPanelCore.ts` → `diffPanel/atoms.ts` — **not fixed here** (out of scope). The move up to `pages/workspace/diffPanel/` preserves these reads; promoting the diff-tab atoms to `common/state/` is a recommended follow-up.

---

## 11. Judgment calls & follow-ups

1. **`tools/` does not survive as a sibling.** Its single file is chatAlpha-only → folded
   into `chatAlpha/utils/` (§4). Deviates from `move-map.md` step 4's subdir list.
2. **`ChatPanelContent` + `AgentTerminalPanel` fold into `chatAlpha/`** (§3). They are the
   chat/terminal container above `AlphaChatInterface`. Cleanest given they'll all become the
   `chat/` feature after the stacked rename. Alternative: a separate `agentPanel/` feature dir
   for the container (keeps terminal-mode code out of an "alpha"-named dir); rejected to avoid
   a second thin feature and because it collides with the coming `chat/` rename.
3. **`workspaceChrome/` absorbs the root shell `.tsx`** (`WorkspaceLayoutShell`,
   `WorkspaceHeader`), which is slightly beyond the literal "loose `components/` files" scope
   but is the natural completion (otherwise a root-level parent imports its own subfeature).
   Flag if you'd rather leave the shell components at the workspace root and put only the
   confirmations + `TargetBranchSelector` under `workspaceChrome/`.
4. **`AgentStatusDot` name collision.** The promoted banner variant and
   `components/statusDot/StatusDot`'s `AgentStatusDot` would coexist in `components/`; rename
   the peek wrapper (e.g. `PeekAgentStatusDot`). Trivial (one consumer).
5. **Peek promotion is the pivot** for `DiffSummary`/`parseDiffStats` (§7 coupling note).
6. **Follow-ups (not executed):** merge `diffPanel/` + `diffViewer/` into `diff/`
   (`decisions.md` #3); promote diff-tab atoms to `common/state/` (§10); chatAlpha internal
   anatomy sweep (flat `*Utils.ts` → `utils/`); rename `ChatIntro.module.scss` to its consumer;
   the four-confirmation-dialog consolidation (`decisions.md`).
