# Frontend structure rules — v3 (THE definitive spec)

This file is the single source of truth for the structure proposal. The
before/after tree in the review artifact is DERIVED from these rules plus the
feedback ledger below. To change the outcome, change a rule here. When v3 is
approved, these rules replace the structure sections of
docs/development/style/frontend_structure.md and the eslint config follows.

## The rules

**R1 — The top level is the product.** Every surface or feature a user can
point at gets a top-level folder: `app/` (shell: entry, router, frame, gates,
toast hosts, dev-tools, error pages), `sidebar/`, `home/`, `onboarding/`,
`settings/`, `workspace/`, `chat/`, `command-k/`, `create-pr/`,
`create-workspace/`, `custom-actions/`, `add-repo/`, `editor/`,
`workspace-peek/`. Infrastructure keeps five buckets: `ui/`, `common/`,
`electron/`, `plugins/`, plus generated `api/` and static `assets/ styles/
stories/`. `pages/` does not exist.

**R2 — Nesting, the whole convention in three lines.** Inside a feature:
components sit flat at the root; plumbing goes in `atoms/ hooks/ utils/
types/`. One level of subfolder is allowed only for (a) registered panels
under `workspace/panels/<panel>/`, and (b) a private sub-cluster that is
meaningless outside its parent (`editor/mentions/`, `chat/file-preview/`,
`panels/diff/markdown/`). If a cluster is used beyond its parent, or is a
thing a user could see and name, it is NOT nested — it goes top-level
(that's why `chat/`, `create-pr/`, `workspace-peek/` are top-level, not
inside `workspace/` or `sidebar/`).

**R3 — `ui/` is widgets only, one folder per widget.** Generic, reusable
display/input widgets, each in its own kebab-case folder holding the component
+ scss + test + story + its private helpers; no loose files at `ui/` root.
The membership test: if it has domain state, a flow, or backend data, it is a
feature (top level), not a widget — which is why `create-workspace/` and
`custom-actions/` are NOT in `ui/`.

**R4 — `common/` is shared non-UI, and backend data is organized by domain.**
`common/backend/` holds the data layer that mirrors the backend (the WS/API
cache): one folder per domain — `agents/ workspaces/ projects/ skills/
notifications/ user-config/` — each with `atoms/` + `hooks/` together
(colocation applies to state too; no giant by-kind hooks bucket), transport
(`useWebsocket`, `useUnifiedStream`, `queryClient`, request tracking) flat at
`backend/` root. Client-owned state lives in its owner feature's `atoms/`
(`chat/atoms/chatSearch.ts`, `app/atoms/toasts.ts`). `common/utils/` keeps
only genuinely cross-feature helpers; a util with one owning feature lives in
that feature's `utils/` (`app/utils/autoUpdate.ts`, `chat/utils/pseudoSkills.ts`).

**R5 — Casing.** Folders are kebab-case, no exceptions. Component files are
`PascalCase.tsx` named for their exported component. Everything else is
`camelCase.ts`. (Open question 3: whether non-component filenames also go
kebab.)

**R6 — Imports.** `~/` everywhere except same-folder siblings; lint-enforced.
The boundary lint keeps three edges: `common/` imports nothing above it,
`ui/` imports only `ui/` and `common/`, `electron/` never imports renderer
UI. There is no page-isolation rule and no promote-on-second-import rule —
features import each other where things live (owner-first).

**R7 — Names come from the product.** Actions are verbs (`create-pr`,
`create-workspace`, `add-repo`, `open-in-app`); surfaces are what users call
them (`command-k`, `sidebar`); panels are named like the panel
(`panels/files/`, `panels/diff/`). Component identifiers read unambiguously
outside their folder. Files are named for their content (`viewRegistry.ts`,
not `homeViews.ts`; `RepoNotFoundDialog`, not `RepoPathDialog`). No vestigial
qualifiers (Alpha, Core), no `*Utils`-style basenames.

**R8 — State shape.** `atoms/` and `hooks/` subfolders inside features and
backend domains; write-atoms live with their atoms; split state files by
lifecycle or subdomain when one file loses coherence; never define atoms in
`.tsx`.

**R9 — When a folder is earned.** A feature-internal subfolder needs 3+
components or plumbing of its own. Two deliberate exceptions: `ui/` gives
every widget a folder uniformly (consistency beats economy in the kit), and a
top-level feature exists regardless of size when it names a product concept
(`create-pr/` is three files and that's fine).

**R10 — Tests and stories colocate.** Unchanged from v2. `stories/` keeps
only the Radix catalog and the Storybook intro.

## Feedback ledger (your words → what became of them)

| Your feedback | Disposition |
| --- | --- |
| addWorkspace vs newWorkspace confusion | addWorkspace had no page; its list components → `home/`. Create dialog → top-level `create-workspace/` with `CreateWorkspaceDialog/Form` renames. (R1, R7) |
| addWorkspace's lone components/ subfolder | Dir dissolved; same fix applied to `settings/components/` → `settings/sections/` + flat primitives. (R2) |
| queuedMessages is part of chat | Folded flat into `chat/`. (R2) |
| mentionDetailPanes unclear | → `editor/mentions/` with MentionChip + suggestion machinery. (R2, R7) |
| pathAutocomplete unclear | → `ui/directory-picker/`, component `DirectoryPicker`. (R3, R7) |
| statusDot non-descriptive (×2) | Folder → `ui/status-dot/` (uniform widget folder); its pure logic joins it; open Q on renaming the component. (R3) |
| openInApp/items.tsx bad name + folder | Folder dissolved → `command-k/OpenInAppMenuItems.tsx` (PascalCase — it exports components; your casing catch). (R7) |
| no onboarding folder | Top-level `onboarding/`. (R1) |
| AtomToast generic but in app/ | → `ui/toast/` beside Toast; hosts stay in `app/`. (R3) |
| diffSummary in components/ | → flat file in `workspace/` (header owns it); peek imports across. (R6 owner-first) |
| devPanel in components/ | → `app/dev-tools/`. (R1) |
| commandPalette → command-k | Top-level `command-k/`, component `CommandK`. (R1, R7) |
| prefer kebab over camel | R5. All folders regenerate kebab. |
| prButton → create-pr | Top-level `create-pr/`. (R1, R7) |
| diffPanel belongs in panels/ | `workspace/panels/diff/`, absorbing diffViewer — one diff home. (R7) |
| workspaceChrome weird | Dissolved flat into `workspace/` root. (R2) |
| inconsistent ~ vs relative | R6. |
| wanted the flatter early option | R1/R2 are that option, taken further per your later notes. |
| RepoPathDialog in app — onboarding? bad name | It's not onboarding: it's the "repo folder missing on disk" recovery dialog the shell shows. Renamed `RepoNotFoundDialog`, stays `app/`. (R7) |
| same tracing file in perf and electron? | Two different files: `common/perf/tracing.ts` (renderer perf spans) and `electron/tracing.ts` (main-process). Same basename was tab-ambiguous → electron's becomes `mainTracing.ts`. (R7) |
| what is EmptyFirstRunGate? | Route gate: when the workspace list is empty it renders EmptyFirstRunPage instead of any route (post-onboarding landing). The page moves from `workspace/` to `app/` beside its gate. (R1) |
| homeViews.ts name sucks | It's the home-view switcher registry (built-in + plugin views) → `home/viewRegistry.ts`. (R7) |
| why not a subfolder in ui for everything | R3: one folder per widget, uniformly. |
| pull chat + create-pr out of workspace; workspace = the page | R1/R2: both top-level; `workspace/` keeps page, layout, panels, header pieces. |
| create-workspace and custom-actions in ui seems arbitrary | R3 membership test added; both are features → top level. |
| common/state/hooks breaks colocation; <feature>/<atoms|hooks> | R4/R8: backend domains each hold their own atoms/ + hooks/; client state redistributed to owners. |
| that state was just everything from the backend | R4: the layer is literally named `common/backend/`. |
| openInApp.tsx casing | `OpenInAppMenuItems.tsx`. (R5) |
| sidebar could be top-level | R1: `sidebar/`. |
| workspace-peek similarly; nesting conventions unclear | R2 states the whole convention; workspace-peek → top level. |
| utils next to the features that use them (autoUpdate) | R4: `app/utils/autoUpdate.ts`, `custom-actions/utils/builtinActions.ts`, `chat/utils/pseudoSkills.ts`, `workspace/utils/parseDiffStats.ts`, `editor/utils/fileUpload.ts`, statusDot logic → `ui/status-dot/`. |

## Open questions (the only undecided items)

1. `common/backend/` — is that the name you want for the server-data layer
   (alternatives: `common/server/`, `common/data/`)?
2. `StatusDot` component rename (`StatusIndicator`?). Folder is `ui/status-dot/` either way.
3. Non-component filenames: stay camelCase (`useFileTree.ts`) or go kebab too?
4. `app/error/` vs top-level `error/`.
5. The common/state domain classification is drafted file-by-file in the
   artifact — rows marked draft get verified against importers at execution.

## Process from here

Feedback → edit this file (you or me) → regenerate the tree (the mapping
script derives from these rules; seconds, not sessions) → you review the
artifact. No code moves until you approve this file.
