You are bringing a single Sculptor **frontend component group** into full
compliance with our review rules. A "component group" is one logical unit: a
source file (`.tsx`/`.ts`) together with its co-located stylesheet
(`.module.scss`/`.scss`/`.css`) and its co-located unit test
(`.test.tsx`/`.test.ts`/`.spec.*`), when those exist. You will identify issues,
apply complete fixes (including in shared files when needed), verify your
changes don't break the build or tests, flag anything you can't safely fix,
then write a markdown report and commit.

You are running headless via the batch runner. Other agents may run after you
in this same worktree, also sequentially — never concurrently — so it is safe
to edit shared files.

**Bias hard toward fixing.** Your default for every real issue is to FIX it
completely — including across call sites and shared files — and prove it with
the Step 4 checks (`just typecheck` + `just lint` + the frontend unit suite).
FLAG is reserved for the narrow set of issues that genuinely *need a human*
(listed in Step 2); it is the exception, not the safe fallback. Do not flag
something just because it touches more than one file or feels risky — if you
can resolve it and the checks pass, resolve it. The whole point of this run is
to leave the codebase better, not to produce a long list of work for someone
else.

## Your inputs — read this first

Above this prompt, the batch runner lists the files of **one component group**
under "Files to read and analyze:". Immediately below this paragraph the
wrapper has injected two values:

- **PRIMARY FILE** — the single file that names this group. It is your
  `<TARGET>`. Most fixes land here.
- **REPORT PATH** — the exact path where you must write your markdown report.
  Do not derive your own; use this verbatim.

The other listed files (stylesheet, test) are part of the same group and you
own them too — review and fix them alongside `<TARGET>`.

You are running from the Sculptor repo root. `just` recipes work from here. Do
not `cd` anywhere else except where a verify command below tells you to.

## Three deliverables — all required

1. **Markdown report** at the injected **REPORT PATH**.
2. **A single git commit** containing the group's file edits, any shared-file
   edits, and the markdown report.
3. **JSON response** to the batch runner — one entry in `findings` for
   **every single** Fixed and Flagged item in your markdown. The runner uses
   this to roll up an aggregate summary across all files; an empty findings
   array tells the runner nothing happened, which would be a lie if you
   actually fixed or flagged anything.

If your markdown has N Fixed paragraphs and M Flagged paragraphs, your JSON
`findings` array MUST have exactly N+M entries. This is non-negotiable.
Before responding, count the paragraphs in your markdown's Fixed and Flagged
sections and confirm `len(findings)` matches.

## Step 1 — Load the rules

Use your Read tool to read these in full. **Which docs are mandatory depends on
what file types are in your group:**

Always:
1. `.claude/skills/code-review-checklist/SKILL.md` — the checklist.
2. `docs/development/style/frontend.md` — the frontend style guide.
3. `docs/development/style_guide.md` — the short overview.

If your group contains any `.tsx` / `.ts` React or component file (it almost
always will), these are **mandatory** — do not skip, do not rely on summaries:
4. `docs/development/review/react.md` — generic React rules.
5. `docs/development/review/sculptor.md` — Sculptor-specific frontend
   conventions (backend data hooks, Jotai atoms, component invariants).

If your group contains any `.scss` / `.css` file:
6. `.claude/skills/frontend-design-tokens/SKILL.md` — design-token rules. Apply
   it to every stylesheet in the group.

Then read every file in your group. Read any helpers, hooks, components, or
modules the group imports if and only if a finding hinges on what they actually
do. Don't tour the codebase.

## Step 2 — Identify every issue

Walk every **applicable** category from the checklist against your group, apply
every rule from `docs/development/style/frontend.md`, and — for `.tsx`/`.ts`
files — every rule from `react.md` and `sculptor.md`, and — for stylesheets —
every rule from the design-tokens skill.

These categories don't apply to a standalone component group — emit the literal
text given below in the markdown report and produce zero JSON findings for them:

- "Consistency with stated goal" → `No stated goal provided — section skipped.`
- "Proof of work completeness" → `Not applicable — no MR/PR body under review.`
- "Integration test issues" → `Not applicable — frontend/src unit tests are not Playwright integration tests.`
- "Git hygiene" → `Not applicable — no diff under review.`
- "Public-facing text" → `Not applicable — no commit/PR text under review (your own commit message is covered by CLAUDE.md).`

The categories you DO apply: **Correctness**, **Test coverage** (only as it
applies to a test file *already in the group* — see below), **Dead code &
leftover artifacts**, **Comments**, **Error handling**, **Security & secrets**,
**Type safety**, **Backwards compatibility**, **Frontend issues**, **Style
guide & ratchets**.

For **Test coverage**: you are not under a diff, so do not demand *new* tests
for untested behavior — that's FLAG bucket #3. But if a `.test`/`.spec` file is
in your group, review *it* for quality: flaky patterns (arbitrary `setTimeout`,
real timers, real network, ordering deps), unfocused assertions, and disabled
tests without justification — and FIX those. If the group has no test file,
write `No test file in group — nothing to review.` for this category.

### Fix-vs-flag policy — read this carefully

**FIX is the default. Flag only what truly needs a human.** Every real issue
you find — correctness, render bugs, effect/state misuse, dead code, type
safety, style/ratchets, naming, token misuse in CSS — you FIX, unless it lands
in one of the five FLAG-only buckets below. When you fix something that spans
call sites or a shared file, update *all* the in-repo call sites and let Step 4
prove you didn't break anything.

Concretely, **FIX** all of these (non-exhaustive — fix anything similar):

- Dead code: unused imports, variables, functions, types, components, props;
  commented-out code; `console.log`/`debugger` left behind; unused CSS classes
  or design-token misuse (hardcoded colors/sizes that should be tokens).
- Every style-guide / ratchet / React-rule / Sculptor-convention violation:
  effect dependency-array bugs, missing cleanup in `useEffect`, derived state
  that should be computed during render, unstable inline objects/functions
  passed as props or deps, missing `key`s, prop drilling the conventions say to
  replace, incorrect Jotai atom usage, backend-data-hook misuse, `IconButton`
  in a `Flex` missing `gap="2"`, magic numbers/strings → named constants,
  "what" comments, editorializing comments.
- **Correctness bugs where the intended behavior is clear** (inverted
  condition, wrong operator, off-by-one, missing null/empty/loading guard,
  subscription/listener/timer not cleaned up). Fix it and rely on the checks.
- **Type-safety defects**: new or existing `any` that can be typed properly,
  missing types on changed public functions/props, unsafe casts. Fix them; a
  real type error surfaces in `just typecheck`.
- **Internal API / signature / prop / structure changes** — renaming a private
  helper or component, changing a prop shape, widening a return type — **as long
  as every consumer lives in this repo and you update them all.** This is a fix,
  not a flag. `just typecheck` (tsc) catches any call site you missed.

**FLAG** — only these five, and only when the issue is *real*:

1. **Genuinely ambiguous intent.** A correctness change where you cannot tell
   what the code is *supposed* to do, so any fix is a coin-flip.
2. **A true external contract.** The fix would change something a consumer
   *outside this repo* depends on, or that you cannot update in-repo: the
   frontend↔backend wire/API shape, a persisted/serialized format, an
   `ElementID` contract relied on by tests you can't see, a public config knob.
3. **Needs test changes.** The fix would require writing a *new* test,
   unskipping a skipped test, or changing what an existing test asserts.
4. **Genuinely architectural / out of scope.** A sweeping multi-component
   redesign that a single-group cleanup pass shouldn't attempt.
5. **A real security issue with a non-obvious fix.** If the remediation is
   obvious and safe (stop logging a token, remove a hardcoded secret,
   `dangerouslySetInnerHTML` with an obvious sanitization fix), FIX it and note
   it prominently; flag only when the right fix is unclear.

If something isn't actually a defect — an intentional pattern the code or
comments justify — it is **neither fixed nor flagged.** Don't manufacture flags
for working-as-intended code; just note "no issues" for that category.

When in doubt between FIX and FLAG, prefer FIX and lean on Step 4. Reserve FLAG
for cases that clearly match one of the five buckets above.

**Editing shared files is allowed and expected** when a fix needs it (a shared
component, hook, type, or stylesheet). Update every in-repo caller, keep Step 4
green, and record the blast radius in the report. The only hard limit is the
external-contract bucket (FLAG #2).

**Never edit the harness.** Do not touch `.claude/skills/**` or
`agent_docs/frontend-review/_prompt.md` even if one of them happens to be in
your group — skip it (report it as out of scope) so you don't modify the
machinery mid-run. (The driver script that invokes you lives outside the repo,
so it can't be in your group.)

## Step 3 — Apply the fixes

Make focused edits — but fix everything you found a fix for, including across
call sites and shared files. Constraints:

- **Fix completely.** A half-applied fix is worse than none. If a rename or
  prop change ripples to other files in this repo, update every one of them in
  the same commit; don't leave the tree inconsistent.
- **Don't reformat code you didn't change.** Touch only the lines your fixes
  need. Don't widen scope into unrelated rewrites. `just format` handles
  whitespace — don't hand-reformat.
- **Keep imports at the top of the file.**
- If you realize a fix is wrong, revert that edit before moving on.
- The Step 4 checks are your safety net — run them before committing and
  iterate on any failure your edits caused.

## Step 4 — Verify

Before you commit, run these and confirm they pass. Run in this order:

1. `just format` — auto-formats Python + JS/TS + SCSS. (The Python half is a
   no-op for your edits; that's fine.)
2. `just lint` — ESLint + Stylelint (+ Python ruff, a no-op here).
3. `just typecheck` — `tsc` over the whole frontend (+ pyrefly, a no-op here).
   This is your strongest safety net: it catches any consumer you missed when
   you changed a prop or signature.
4. The frontend unit suite — **only if your edits could affect runtime
   behavior or tests** (any `.tsx`/`.ts`/test-file edit). Run `just
   test-unit-frontend` (it runs `npm run generate-api` then the full suite). If
   your group was **stylesheet-only** (you edited only `.scss`/`.css`), skip
   the suite — CSS cannot break JS unit tests — and say so in the report.
5. `just ratchets` if you suspect any ratcheted count changed (e.g. you added
   or removed an `any`, a `console.log`, etc.). Flag any increase you can't
   bring back down.

Do **not** run the Python unit suites (`just test-unit-backend`, etc.) or the
bundled `just test-unit` — a frontend edit cannot affect Python tests, so
running them is wasted time.

**Note on `just test-unit-frontend`:** it runs `npm run generate-api`. If that
regenerates files under `sculptor/frontend/src/api/` (e.g. because you added an
`ElementID`), those regenerated files are part of your change — include them in
your commit and note it in the report. If generate-api produces unrelated churn
you didn't cause, leave it unstaged.

Everything you run must be green before you commit.

**Iterate-then-revert protocol** when `just typecheck`/`just lint`/the suite
fails after your edits:

1. Read the actual failure output, not just the exit code.
2. Confirm the failure is caused by your edits. If the failing check has nothing
   to do with your group or the symbols you changed, it is likely pre-existing —
   note it in your report, leave it alone, and proceed. Do not chase failures
   you did not cause.
3. If your edits did cause it, form a hypothesis, apply a follow-up fix, re-run.
4. Repeat up to **3 attempts** total.
5. If it still fails, revert **only the narrow edit that caused the failure** —
   keep the other, independent fixes — re-run to confirm green, and FLAG the
   reverted issue with a note on what you tried.

Do not commit with a failing check or test that your edits caused.

## Step 5 — Write the markdown report

Write the report to the injected **REPORT PATH** (verbatim — do not derive your
own name). Use your Write tool to create that file with this exact structure:

```
# <PRIMARY FILE path>

## Outcome

- Review status: COMPLIANT / FIXED / FLAGGED-ONLY (after your work)
- Group files: <list every file in the group you reviewed>
- Verification: which checks you ran and their result (e.g. "format + lint +
  typecheck + test-unit-frontend all green"; or "stylesheet-only group —
  test-unit-frontend skipped"). Note any failure you determined was
  pre-existing / unrelated to your edits and left in place.
- Files edited: <list of paths, including shared files outside the group>
- Blast radius: <if you edited any shared file, name it and list which other
  modules import the symbol/component/type you changed; write `None — group
  only.` otherwise>

## Fixed

One paragraph per fix. Lead with **[FIXED] SEVERITY** in bold, then the file
path and line numbers (in the post-edit file), then 1–3 sentences: what was
wrong, what you changed, and why the change preserves behavior.

If you fixed nothing, write: `No issues required fixing.`

## Flagged

One paragraph per flagged issue. Lead with **[FLAGGED] SEVERITY** in bold,
then file path and line numbers, then 1–3 sentences: what's wrong, and which of
the five FLAG buckets it falls into. If it doesn't clearly match a bucket, you
should have fixed it, not flagged it.

If you flagged nothing, write: `No issues flagged.`

## Categories

One `### <Category>` heading per checklist category, in checklist order. Under
each, list which issues from above belong to it, or write `No issues found.`,
or the skip / not-applicable text from Step 2.

## Summary

2–4 bullets. Cover: the group's compliance state after your work, anything you
flagged that needs a human, and anything the user must audit — especially any
shared-file edit and its blast radius.
```

## Step 6 — Commit your work

After verification and the markdown report are done, commit the files you
edited so the worktree is clean for the next agent. Each agent owns one group
and produces one commit — do not bundle multiple agents' work.

1. You already ran the Step 4 checks and confirmed them green. If `just format`
   rewrote a line you edited, those updated lines stay in your commit.

2. Track every file you touched. The set MUST include your group's edited files,
   the markdown report, and any shared files you modified (including regenerated
   `api/` files if `generate-api` changed them because of your edit). It MUST
   NOT include anything you didn't touch — the worktree may have pre-existing
   uncommitted changes that are not yours.

3. Stage explicitly by listing each path: `git add <file1> <file2> ...`. Do
   NOT use `git add -A`, `git add .`, or `git add agent_docs/`.

4. Run `git status --short` and confirm only your intended files are staged
   (first column `M`/`A`). Pre-existing unstaged changes (`??` or ` M`) are
   fine — leave them. `git restore --staged <file>` to undo a mistake.

5. Commit with a message that explains the *why*, ending with the trailer:

   ```
   Bring <PRIMARY FILE relative path> into compliance with frontend review rules

   <one or two sentences naming what was fixed (e.g. removed dead code, fixed an
   effect cleanup, replaced hardcoded color with a design token) and any shared
   files edited so the diff is greppable later. Note if the group was already
   compliant.>

   Co-authored-by: Sculptor <sculptor@imbue.com>
   ```

   Even if your only change is the markdown report (group already compliant),
   still commit so the report lands on the branch.

6. Do NOT push. Do NOT amend a prior commit. Do NOT rebase. Do NOT skip hooks
   (`--no-verify` etc.). If a pre-commit hook fails, fix the underlying issue
   and make a new commit — don't bypass it.

## Step 7 — Return JSON to the batch runner (LAST STEP)

This is your final action. The runner reads ONLY this JSON to roll up an
aggregate report across all groups — your markdown and your commit are invisible
to it. Returning empty `findings` after you fixed or flagged things makes the
aggregate say "no issues" even though you changed the group.

**Mandatory contract:** every Fixed paragraph and every Flagged paragraph in
your markdown appears as exactly one entry in `findings`.

Before returning, check explicitly:

1. Count Fixed paragraphs — call that `F`.
2. Count Flagged paragraphs — call that `G`.
3. `len(findings)` must equal `F + G`.

An empty `findings` array is acceptable ONLY when your markdown's Fixed AND
Flagged sections both say "No issues..." — never when you changed anything.

For each entry:

- `file` — the path of the file the issue was in (group member or shared file),
  relative to repo root.
- `category` — the checklist category name.
- `severity` — `critical`/`high`/`medium`/`low` per the checklist.
- `description` — one sentence on what was wrong.
- `recommendation` — start with `[FIXED]` or `[FLAGGED]`, then one sentence on
  what was done or what should be done. For FIXED, note any shared files edited.
- `line_numbers` — best-effort against the post-edit file.

`summary` is one sentence: worst issue + the group's state now (e.g.
`"2 fixed (effect cleanup, dead import), 1 flagged (ambiguous correctness); typecheck + test-unit-frontend green."`).
If clean, just `"clean"`.

`files_reviewed` is the number of files in your group.
