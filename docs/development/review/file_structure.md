# File Structure Review Rules

Review rules for file placement, feature layout, and naming: does a change put
code where the next reader would guess it lives, and name it what they would
guess it's called. The conventions themselves are defined in
[frontend_structure.md](../style/frontend_structure.md) (placement, feature
anatomy, depth) and the [frontend style guide](../style/frontend.md#naming)
(identifier naming, suffix glossary, domain vocabulary) — this doc is the
checklist for enforcing them in review.

These checks are deliberately the ones a linter *can't* make. ESLint already
rejects kebab-case directories, generic basenames (`utils.ts`, `atoms.ts`), and
function-declaration style — do **not** re-report those here. This doc is about
the judgments a machine can't: whether code is in the right *place*, whether a
new file was *warranted*, whether a name says the right *thing*. For component
correctness see [`react.md`](react.md); for data-flow conventions see
[`sculptor.md`](sculptor.md); for design quality see [`design.md`](design.md).

For each issue found, note the issue type, file/line, and a brief description of
what is wrong and how to fix it.

---

## `code_lives_with_its_feature`

**Question:** Is this code placed with the feature that renders it — or, if a
second surface needs it, promoted to the single shared home for its kind?

The placement rule is one sentence: code lives with the feature that renders it,
and moves up only when a second feature needs it. The shared homes are fixed —
UI in `components/`, state in `common/state/`, other hooks in `common/hooks/`,
pure helpers in `common/utils/`, shell wiring in `app/`. A file in a shared home
with a single consumer is mislocated in one direction; a feature importing
another feature's internals is mislocated in the other.

**What to look for:**
- A new file in `components/` or `common/` whose only importers are one feature
  — it belongs inside that feature
- An import that reaches into a sibling feature's directory
  (`pages/settings/... importing from pages/workspace/...`) — the shared part
  should be promoted, not borrowed
- A shared-looking helper parked in a feature because that's where it was
  written first, then imported from elsewhere
- New code added to a shared home "because it might be reused later" —
  placement follows *actual* consumers, not speculative ones

**Fix:** Move the file to its single-consumer feature, or promote it to the
shared home for its kind and update imports. If promotion feels wrong, the two
consumers may want different things — consider duplicating the small thing
instead of sharing the wrong abstraction.

---

## `feature_root_shows_what_renders`

**Question:** Does the feature's root directory read like the UI it draws —
components (with their styles and tests) at the root, plumbing shelved into
`atoms/` / `hooks/` / `utils/`?

Opening a feature folder should answer "what does this thing look like" at a
glance. Components sit flat at the root; everything supporting them shelves
into the fixed kind vocabulary. Kind directories keep basenames short
(`atoms/selection.ts`) because the path carries the context.

**What to look for:**
- Loose `camelCase.ts` plumbing files sitting at a feature root that has
  outgrown flat (the root is no longer glanceable — count components, not
  files; styles and tests ride along free)
- Ad-hoc kind names: `helpers/`, `lib/`, `state/`, `logic/` — the vocabulary is
  `atoms/`, `hooks/`, `utils/`, and (rarely) `types/`
- A component hidden inside a kind directory
- A tiny feature (a component or two) ceremonially shelved into three
  one-file directories — flat is correct until the root stops being glanceable
- A change that pushes a feature past the threshold without carrying the
  shelving move in the same PR

**Fix:** Shelve plumbing into the standard kind directories; lift components
back to the root. When in doubt, prefer the standard anatomy — unneeded
shelving costs mild ceremony, missed shelving compounds into drift.

---

## `helpers_start_private`

**Question:** Did this helper earn a file — or should it be a private function
in its consumer?

A helper's default home is no file at all. The ladder: private function in the
file that uses it → the feature's `utils/` topic file when a second file in the
feature needs it → its own named file only when it has real mass (a parser, an
engine) → `common/utils/` when a second feature needs it.

**What to look for:**
- A new exported helper with exactly one importer — it should be a private
  function in that importer
- A new one-function file that is neither shared nor substantial
- A grab-bag topic file accumulating unrelated functions because it exists
  (topic files are cohesive: `messageUtils.ts` holds message helpers, not
  "things I needed while editing messages")

**Fix:** Inline single-consumer helpers as private functions. Merge small
related helpers into the feature's topic file. Reserve standalone files for
units with genuine mass.

**Exceptions:** A single-consumer helper may warrant extraction for direct unit
testing when testing it through its consumer is impractical — say so in the PR.

---

## `subfeature_earned_not_speculative`

**Question:** Does every new directory correspond to an earned cluster — and
does nothing exceed the depth cap?

A subfeature folder is earned when a cluster has plumbing of its own (its own
hooks/atoms/utils) or 3+ components of its own; it then repeats the standard
anatomy one level down. Below a feature the maximum depth is
`feature/subfeature/kind/file` — subfeatures do not nest, kind directories are
leaves.

**What to look for:**
- A folder per component (`Button/Button.tsx`) — a `.tsx` + `.module.scss` pair
  never earns a folder
- A directory containing one or two files with no plumbing of their own
- A subfeature growing subfeatures — that's a feature asking to be moved up to
  sibling level
- Kind directories nested inside kind directories

**Fix:** Flatten unearned folders back to the feature root. Promote a nesting
subfeature to a sibling feature.

---

## `state_split_by_lifecycle`

**Question:** Are new atoms in the feature's `atoms/`, in topic files split by
lifecycle or subdomain — with their write-atoms beside them?

One `atoms/<feature>.ts` holds a feature's state by default, nouns and verbs
together. When a state module splits, it splits by lifecycle or subdomain —
persisted vs transient is the canonical split (`atoms/section.ts` vs
`atoms/transient.ts`), because it answers "what survives a reload" by filename
alone. A reads/writes split (`…Actions` topic file in the same `atoms/`) is
earned by size only. Shared state follows the `common/state/` mirror:
`atoms/<domain>.ts` ↔ `hooks/use<Domain>.ts`.

**What to look for:**
- Atoms defined in a `.tsx` file
- A new atoms file created per-component or per-PR rather than per
  lifecycle/subdomain — state modules follow the feature's concepts, not the
  change history
- Persisted and transient atoms mixed in one topic file when both sides are
  substantial
- A separate actions file wrapping a small state module — verbs belong with
  their nouns until size forces the split
- A hook added to `common/state/hooks/` that doesn't front a state domain, or a
  new domain atom without a mirror hook when components consume it directly

**Fix:** Move atoms into the feature's `atoms/` topic file; split by lifecycle
or subdomain when a file loses coherence; keep write-atoms with the atoms they
mutate.

---

## `component_named_for_what_renders`

**Question:** Does the component's name say what the user sees, read
unambiguously outside its own directory, and use the suffix vocabulary
correctly?

Components are named for what they render, not the circumstance they were built
for — `SidebarEmptyState`, not `SidebarFirstRunState`. Identifiers travel (JSX,
devtools, stack traces), so they keep their context prefix even though the path
repeats it: `FileTreeRow`, not `TreeRow`. Suffixes are a fixed vocabulary — see
the [suffix table](../style/frontend.md#components); `Panel` means a registered
workspace panel and nothing else, modal things are `Dialog`, and `Core` /
`Manager` / `Wrapper` / `Container` / `Helper` are banned.

**What to look for:**
- A name describing the trigger or project phase rather than the render
  (`FirstRun`, `New`, `Alpha`, `V2` qualifiers that won't age)
- A bare generic name that only makes sense inside its directory (`TreeRow`,
  `Header`, `Item`)
- `*Panel` on a component that isn't a registered panel; `*Layout` on something
  that isn't a reusable scaffold; `Modal` anywhere
- A banned suffix standing in for a real name
- The file name not matching the exported component

**Fix:** Rename to what it renders, carry the context prefix, and pick the
suffix from the table.

---

## `vocabulary_matches_glossary`

**Question:** Do identifiers use the canonical domain nouns from the
[domain vocabulary](../style/frontend.md#domain-vocabulary)?

Naming drift starts where vocabulary is improvised. The load-bearing case:
**agent** is one coding-agent run; **task** is an item in an agent's plan. The
wire calls an agent run a task (`CodingAgentTaskView`, `taskId`) — that
vocabulary stays inside generated `api/` and the reducers that consume wire
frames, and does not leak into hand-written names.

**What to look for:**
- "task" naming for agent runs in new hand-written code (components, hooks,
  atoms, labels) — wire field names like `task_id` are fine at the API seam
- Bare `tab` where panel tab vs workspace tab is ambiguous
- Synonyms standing in for canonical nouns (job/run/thread for agent, folder
  for project, view for panel)
- New user-facing copy using a different noun than the code around it

**Fix:** Use the glossary term; qualify ambiguous nouns. If a concept isn't in
the glossary, add it there in the same PR rather than improvising locally.

---

## `story_colocated`

**Question:** Does a component's Storybook story sit beside the component — and,
if the component moved or was renamed, did its story move in the same change?

Stories colocate with source, like tests: `Component.stories.tsx` beside
`Component.tsx`. The lone exception is `stories/radix/`, the central catalog of
Radix primitives, whose stories render library components that have no source
file to sit beside. Nothing mechanical checks colocation — the review does.

**What to look for:**
- A moved or renamed component whose story stayed behind at the old path
- A new story parked centrally instead of beside the component it renders
- A new shared presentational component that ships without a story

**Fix:** Move the story next to its component in the same PR; give a new shared
presentational component a colocated story.
