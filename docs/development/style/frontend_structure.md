# Frontend file structure

How `sculptor/frontend/src` is organized: where code lives, what files are named,
and how features grow. The goal is inferability — a reader should be able to guess
where existing code lives, and where new code goes, without a map.

Code-level conventions (types, identifier naming, React patterns) live in
[frontend.md](frontend.md). Review rules that check this document live in
`docs/development/review/`.

## The placement rule

**Code lives with the feature that renders it. It moves up only when a second
feature needs it.**

| What | One consumer | Shared by 2+ surfaces |
| --- | --- | --- |
| UI components | the feature's directory | `components/` |
| State (atoms + state hooks) | the feature's `atoms/` | `common/state/` |
| Other hooks | the feature's `hooks/` | `common/hooks/` |
| Pure helpers | private function, then the feature's `utils/` | `common/utils/` |
| App-shell wiring | — | `app/` |

Promotion is import-driven: the moment a second feature needs something, it moves
to the shared home for its kind. The import-boundary lint (below) is what makes a
stale placement visible — a cross-feature import fails until the code moves up.

## Top-level map

```
src/
├── app/          # shell: Main, App, Router, sidebar, tabs, global shortcuts
├── pages/        # routed surfaces, one directory per feature area
│   └── workspace/    # the dominant surface: layout/, panels/, chat/, diff/, …
├── components/   # UI shared by 2+ surfaces (CommandPalette, addRepo, kit widgets)
├── common/       # shared non-UI: state/, hooks/, utils/, keybindings/, theme/
├── api/          # generated client — never hand-edited
├── plugins/      # plugin SDK and runtime
├── electron/     # main-process bridge
├── styles/       # global styles and design tokens
└── stories/      # Radix catalog + Storybook intro (component stories sit beside their component)
```

Import layering follows the same shape and is lint-enforced: `app/` is the
composition root and may import anything; a page never imports from another page;
`components/` never imports from `pages/`; `common/` never imports from
`components/` or `pages/`.

## Anatomy of a feature

**The feature root shows what renders; plumbing shelves into kind directories.**
Opening a feature folder should look like the UI it draws.

```
fileBrowser/
├── FileBrowser.tsx              # components with their styles/tests, flat at the root
├── FileBrowser.module.scss
├── FileBrowser.test.tsx
├── FileTreeRow.tsx
├── FileTreeRow.module.scss
├── FileContextMenu.tsx
├── atoms/
│   └── fileBrowser.ts           # topic-named; a lone file takes the feature's name
├── hooks/
│   ├── useFileMenuGroups.tsx
│   └── useTreeKeyboardNav.ts
└── utils/
    └── fuzzyFileScorer.ts
```

- The kind vocabulary is fixed: `atoms/`, `hooks/`, `utils/`, and (rarely)
  `types/`. No ad-hoc kind names.
- Files inside kind directories are topic-named (`atoms/selection.ts`,
  `atoms/dragPreview.ts`). The path already carries the feature and the kind, so
  basenames stay short and natural.
- Tests sit beside the file they test; `.module.scss` beside its component.
- A tiny feature (one or two components plus a couple of support files) stays
  flat; shelve once the root stops being glanceable. Glanceability counts
  **components**, not files — styles and tests ride along without penalty.
- **When in doubt, use the standard anatomy.** Unneeded shelving costs mild
  ceremony; missed shelving compounds into drift.

## How helpers grow

A helper's default home is no file at all:

1. **Private function** in the file that uses it. This covers most helpers.
2. Needed by a second file in the feature → the feature's `utils/`, in a
   topic-named file.
3. A standalone unit with real mass (a parser, an engine) → its own named file.
4. Needed by a second feature → `common/utils/`.

## Subfeatures and depth

- Subcomponents sit flat at the feature root by default. A `.tsx` +
  `.module.scss` pair does not earn a folder.
- A cluster earns a **subfeature folder** when it has plumbing of its own
  (its own hooks/atoms/utils) or 3+ components of its own. The subfeature
  repeats the same anatomy one level down.
- Never a folder per component (`Button/Button.tsx`): it doubles depth and adds
  a hop for every component.
- **Depth cap:** below a feature, the maximum is `feature/subfeature/kind/file`.
  Subfeatures do not nest; kind directories are leaves. A subfeature that seems
  to need its own subfeatures is a feature — move it up to be a sibling.
- Above features, grouping directories are allowed and expected
  (`workspace/panels/fileBrowser/`).

## State modules

- One `atoms/<feature>.ts` per feature by default, holding the atoms **and**
  their write-atoms — the nouns and the verbs together.
- Split by **lifecycle or subdomain, never by kind**. Persisted layout vs
  transient drag state (`atoms/section.ts` vs `atoms/transient.ts`) is the
  canonical split: it answers "what survives a reload" by filename alone.
- A large state module may split reads from writes (an `…Actions` topic file in
  the same `atoms/` directory). That split is earned by size, not required.
- Never define atoms in `.tsx` files.
- Shared state lives in the `common/state/` mirror: `atoms/<domain>.ts` ↔
  `hooks/use<Domain>.ts`. A hook belongs in `common/state/hooks/` iff it fronts
  a state domain; a hook that doesn't is not a state hook and lives with its
  consumers (or in `common/hooks/` when shared).

## File and directory naming

- Directories are camelCase, without exception.
- Component files are `PascalCase.tsx`, named for their exported component;
  everything else is `camelCase.ts`.
- Generic basenames are banned everywhere, including inside kind directories:
  `utils.ts`, `helpers.ts`, `hooks.ts`, `atoms.ts`, `types.ts`, `misc.ts`. Name
  the topic, or the feature for the lone-file case. (`index.ts` barrels remain
  reserved for public API surfaces.)
- Directory casing and the basename blocklist are lint-enforced.

## Stories and tests

Unit tests and Storybook stories both colocate with source: a component's
`.test.tsx` and `.stories.tsx` sit beside its `.tsx`, and move with it when it
moves. The exception is `stories/radix/`, the central catalog of Radix UI
primitives — those stories render library components that have no source file in
`src/` to sit beside, so they live together under `stories/`, alongside the
Storybook intro (`Welcome.stories.tsx`).

## Keeping the tree healthy

- A change that pushes a feature past a threshold — root no longer glanceable, a
  helper gaining a second consumer, a cluster forming — carries the
  corresponding move in the same PR.
- Periodic structure sweeps re-audit the tree against this document; the review
  rules in `docs/development/review/` catch violations at review time.

## Migration status and follow-ups

_This section tracks the adoption of this document and comes out once the work
lands._

- **Structure moves**: `components/sections` → `pages/workspace/layout`, the
  `app/` shell directory, kind-dir adoption in existing features, and the
  camelCase directory renames are being applied on the UI-refresh stack.
- **task → agent rename (SCU-1736)**: hand-written frontend code says "agent"
  for agent runs; only the generated `api/` keeps the wire's `task` vocabulary.
  Wire-shaped field names (`task_id`) persist inside the state layer until the
  backend renames. The agent's internal todo items are genuinely "tasks" and
  keep the name. Lands as its own mechanical change after the structure moves.
- **`chat-alpha` → `chat` rename**: stacked separately on top of this pass,
  including dropping the `Alpha*` component prefixes and auditing the legacy
  non-alpha chat code for deletion first.
