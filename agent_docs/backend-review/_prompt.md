You are bringing a single Sculptor backend (non-test) Python file into full
compliance with our review rules. You will identify issues, apply complete
fixes (including in shared files when needed), verify your changes don't break
the corresponding tests, flag anything you can't safely fix, then write a
markdown report and commit.

You are running headless via the batch runner. Other agents may run after you
in this same worktree, also sequentially — never concurrently — so it is safe
to edit shared files.

**Bias hard toward fixing.** Your default for every real issue is to FIX it
completely — including across call sites and shared files — and prove it with
the Step 4 checks (`just check` + the unit suites). FLAG is reserved for the
narrow set of issues that genuinely *need a human* (listed in Step 2); it is
the exception, not the safe fallback. Do not flag something just because it
touches more than one file or feels risky — if you can resolve it and the
checks pass, resolve it. The whole point of this run is to leave the codebase
better, not to produce a long list of work for someone else.

## Three deliverables — all required

1. **Markdown report** at `agent_docs/backend-review/<report-name>.md` (see
   Step 5 for how to derive `<report-name>` — it is NOT the bare basename).
2. **A single git commit** containing the source file edits, any shared-file
   edits, and the markdown report.
3. **JSON response** to the batch runner — one entry in `findings` for
   **every single** Fixed and Flagged item in your markdown. The runner uses
   this to roll up an aggregate summary across all ~320 files; an empty
   findings array tells the runner nothing happened, which would be a lie if
   you actually fixed or flagged anything.

If your markdown has N Fixed paragraphs and M Flagged paragraphs, your JSON
`findings` array MUST have exactly N+M entries. This is non-negotiable —
returning empty `findings` after you fixed things is a bug, not an option.
Before responding, count the paragraphs in your markdown's Fixed and Flagged
sections and confirm `len(findings)` matches.

## Inputs

The batch runner lists exactly one file under "Files to read and analyze:"
above. That is the file you own end-to-end. Refer to it below as `<TARGET>`.

You are running from the Sculptor repo root. Absolute imports and `just`
recipes work from here. Do not `cd` anywhere else.

## Step 1 — Load the rules

Use your Read tool to read these in full:

1. `.claude/skills/code-review-checklist/SKILL.md` — the checklist.
2. `docs/development/style/backend.md` — the backend style guide. This is
   mandatory and is the source of truth for backend structure (immutability,
   domain primitives, pure functions, Pydantic models, IDs, paths, etc.).
3. `docs/development/style_guide.md` — the short overview that points at the above.
4. `<TARGET>` itself.

Read any helpers, models, or modules `<TARGET>` imports if and only if a
finding hinges on what they actually do. Don't tour the codebase.

## Step 2 — Identify every issue

Walk every **applicable** category from the checklist against `<TARGET>`, and
apply every rule from `docs/development/style/backend.md`.

These categories don't apply to a standalone non-test source file — emit the
literal text given below in the markdown report and produce zero JSON findings
for them:

- "Consistency with stated goal" → `No stated goal provided — section skipped.`
- "Test coverage" → `Not applicable — no diff under review; this is a standalone source file.`
- "Frontend issues" → `Not applicable — not a .tsx file.`
- "Integration test issues" → `Not applicable — not an integration test.`
- "Git hygiene" → `Not applicable — no diff under review.`

The categories you DO apply: **Correctness**, **Dead code & leftover
artifacts**, **Error handling**, **Security & secrets**, **Type safety**,
**Backwards compatibility**, **Style guide & ratchets**.

### Fix-vs-flag policy — read this carefully

**FIX is the default. Flag only what truly needs a human.** Every real issue
you find — correctness, error handling, dead code, type safety, style/ratchets,
naming, structure — you FIX, unless it lands in one of the five FLAG-only
buckets below. When you fix something that spans call sites or a shared file,
update *all* the in-repo call sites and let Step 4 (`just check` + the unit
suites) prove you didn't break anything. That verification is exactly why you
can afford to be aggressive: a regression shows up as a red check, and you
iterate (Step 4) rather than guess.

Concretely, **FIX** all of these (non-exhaustive — fix anything similar):

- Dead code, unused imports/variables/functions, commented-out code, debug
  statements (`print`, `breakpoint`, `pdb`, leftover debug logging).
- Every style-guide / ratchet / backend-structure violation: import ordering,
  relative→absolute imports, boolean naming, `num_`→`count_`/`_idx`, mutable
  default args, magic numbers → named constants, deep nesting → early-exit,
  "what" comments, missing/wrong type hints, primitive obsession the style
  guide says to replace (`str` path → `pathlib.Path`, raw IDs → ID classes),
  `logger` level misuse, ad-hoc dicts → Pydantic models, etc.
- **Correctness bugs where the intended behavior is clear** (off-by-one,
  inverted condition, wrong operator, missing `None`/empty/edge-case guard,
  obvious resource-lifecycle leak). Fix it and rely on the unit suites.
- **Error-handling defects with a clear correct form** (a bare `except:` that
  should catch a specific exception, a swallowed error that should be logged or
  re-raised). Fix it.
- **Internal API / signature / structure changes** — renaming a private helper,
  adding a public method, changing a function signature, widening a return
  type — **as long as every consumer lives in this repo and you update them
  all.** This is a fix, not a flag. The `just check` typecheck (pyre) will
  catch any call site you missed.

**FLAG** — only these five, and only when the issue is *real*:

1. **Genuinely ambiguous intent.** A correctness or error-handling change where
   you cannot tell what the code is *supposed* to do, so any fix is a coin-flip.
   (If you can determine intent, it's a FIX.)
2. **A true external contract.** The fix would change something a consumer
   *outside this repo* depends on, or that you cannot update in-repo: a wire
   schema, a persisted / serialized data format read by already-stored data, a
   public CLI flag or env var, an HTTP API shape. These may need a migration.
3. **Needs test changes.** The fix would require writing new tests, unskipping
   a skipped test, or changing what an existing test asserts.
4. **Genuinely architectural / out of scope.** A sweeping multi-module redesign
   that a single-file cleanup pass shouldn't attempt.
5. **A real security issue with a non-obvious fix.** If the remediation is
   obvious and safe (stop logging a secret, drop a hardcoded credential), FIX
   it and note it prominently; flag only when the right fix is unclear.

If something isn't actually a defect — an intentional broad `except Exception`
in a long-lived polling loop, a deliberate design choice the code or comments
justify — it is **neither fixed nor flagged.** Don't manufacture flags for
working-as-intended code; just note "no issues" for that category.

When in doubt between FIX and FLAG, prefer FIX and lean on Step 4. Reserve FLAG
for cases that clearly match one of the five buckets above.

**Editing shared files is allowed and expected** when a fix needs it. You may
add methods, change internal signatures, and update call sites — provided every
caller is in this repo, you update them all, and Step 4 stays green. The only
hard limit is the external-contract bucket (FLAG #2). Record any shared-file
edit and its blast radius in the report so the user can audit it.

**Never edit the batch runner or skill machinery.** Do not touch
`.claude/skills/batch-claude-runner/**` or `agent_docs/backend-review/_prompt.md`
even if `<TARGET>` happens to be one of them — skip the file (report it as out
of scope) so you don't modify the harness mid-run.

## Step 3 — Apply the fixes

Make focused edits — but fix everything you found a fix for, including across
call sites and shared files. Constraints:

- **Fix completely.** A half-applied fix is worse than none. If a rename or
  signature change ripples to other files in this repo, update every one of
  them in the same commit; don't leave the tree inconsistent.
- **Don't reformat code you didn't change.** Touch only the lines your fixes
  need. Don't widen scope into unrelated rewrites.
- **Keep imports at the top of the file** (use `# noqa: E402` only for
  intentional late imports that already exist).
- If at any point you realize a fix is wrong, revert that edit before moving
  on. Don't leave the file in a half-fixed state.
- The Step 4 checks are your safety net — they're what let you fix boldly. Run
  them before committing and iterate on any failure your edits caused.

## Step 4 — Verify

Before you commit, run the pre-commit checks and confirm they pass. This is
your safeguard against regressions: it catches a bad edit on the file you just
touched, rather than letting it surface later. Run them in this order:

1. `just format`
2. `just check`
3. The unit-test suites for the package(s) your edits touch (see below).

**Which unit suites to run.** Base this on the top-level package of *every*
file you created or modified — your `<TARGET>` plus any shared-file edits — not
just `<TARGET>`. `sculptor/sculptor/foundation/` is the leaf package (the rest
of `sculptor/sculptor/` and `tools/sculpt/` both import it), so an edit under
`foundation/` can break their tests too:

- Touched anything under `sculptor/sculptor/foundation/` → run all three Python
  suites: `just test-unit-foundation`, `just test-unit-backend`,
  `just test-unit-sculpt`.
- Else, touched anything under `sculptor/sculptor/` or `sculptor/builder/` →
  run `just test-unit-backend`.
- Else, touched only `tools/sculpt/` → run `just test-unit-sculpt`.
- Else (e.g. `scripts/`, `container/`) → no unit suite covers these; rely on
  `just check` plus careful reading, and say so in the report.

Do **not** run `just test-unit-frontend` or the bundled `just test-unit` — a
Python edit cannot affect the frontend JS/TS unit tests, so running them is
wasted time. `just format` and `just check` are always run in full.

**CRITICAL — run these recipes with NO arguments.** The positional argument to
`just test-unit-backend` / `just test-unit-sculpt` is a *junitxml output path*,
not a test selector. Running e.g. `just test-unit-backend path/to/foo_test.py`
will **overwrite `path/to/foo_test.py` with an XML report**, corrupting the
file. Always invoke the suite bare: `just test-unit-backend` (it runs the whole
suite). If you want to run just one test module for speed, invoke pytest
directly and read-only: `uv run --project sculptor pytest <path_to_test_file>`
— never via the `just` recipe with a path argument.

Everything you run must be green before you commit. The full integration suite
runs once at the very end of the cleanup.

**Iterate-then-revert protocol** when `just check` or a unit suite fails
after your edits:

1. Read the actual failure output, not just the exit code.
2. Confirm the failure is caused by your edits. If the failing check or test
   has nothing to do with `<TARGET>` or the symbols you changed, it is likely
   pre-existing (or introduced by an earlier commit on this branch) — note it
   in your report, leave it alone, and proceed with your commit. Do not chase
   failures you did not cause.
3. If your edits did cause it, form a hypothesis about which edit, apply a
   follow-up fix, and re-run the failing check.
4. Repeat up to **3 attempts** total.
5. If it still fails, revert **only the narrow edit that caused the failure**
   — keep the other, independent fixes — re-run to confirm green, and FLAG the
   reverted issue with a note on what you tried.

Do not commit with a failing check or test that your edits caused.

## Step 5 — Write the markdown report

Derive the report name from `<TARGET>`'s full relative path (NOT the bare
basename — many files are named `__init__.py`, `models.py`, `utils.py`, and
would collide). Replace each `/` with `__` and strip the `.py`:

```
sculptor/sculptor/services/foo_service/api.py
  → agent_docs/backend-review/sculptor__sculptor__services__foo_service__api.md

sculptor/sculptor/foundation/pydantic_serialization.py
  → agent_docs/backend-review/sculptor__sculptor__foundation__pydantic_serialization.md
```

Use your Write tool to create that file with this exact structure:

```
# <TARGET path>

## Outcome

- Review status: COMPLIANT / FIXED / FLAGGED-ONLY (after your work)
- Verification: which unit suites you ran (per Step 4's package rule) and the
  result of `just format` / `just check` / those suites (e.g. "test-unit-backend
  + check + format all green"). Note any failure you determined was
  pre-existing / unrelated to your edits and left in place.
- Files edited: <list of paths, including shared files>
- Blast radius: <if you edited any shared file, name it and list which other
  modules import the symbol you changed; write `None — TARGET only.` otherwise>

## Fixed

One paragraph per fix. Lead with **[FIXED] SEVERITY** in bold, then the file
path and line numbers (in the post-edit file), then 1–3 sentences: what was
wrong, what you changed, and why the change preserves behavior.

If you fixed nothing, write: `No issues required fixing.`

## Flagged

One paragraph per flagged issue. Lead with **[FLAGGED] SEVERITY** in bold,
then file path and line numbers, then 1–3 sentences: what's wrong, and which of
the five FLAG buckets it falls into (e.g. "ambiguous correctness — can't tell
intended behavior", "changes a persisted schema read by stored data", "would
need a new test"). If it doesn't clearly match a bucket, you should have fixed
it, not flagged it.

Expect this section to be short. On most files it will be `No issues flagged.`
— flagging several items means either the file genuinely has multiple
human-only issues, or you were too timid; re-check each flag against the five
buckets before finalizing.

If you flagged nothing, write: `No issues flagged.`

## Categories

One `### <Category>` heading per checklist category, in checklist order. Under
each, list which issues from above belong to it, or write `No issues found.`,
or the skip / not-applicable text from Step 2.

## Summary

2–4 bullets. Cover: the file's compliance state after your work, anything you
flagged that needs a human, and anything the user must audit — especially any
shared-file edit and its blast radius.
```

## Step 6 — Commit your work

After verification and the markdown report are done, commit the files you
edited so the worktree is clean for the next agent. Each agent owns one source
file and produces one commit — do not bundle multiple agents' work.

1. You already ran `just format`, `just check`, and the unit suites selected in
   Step 4, and confirmed them green. If `just format` rewrote a line you
   edited, those updated lines stay in your commit.

2. Track every file you touched. The set MUST include `<TARGET>`, the markdown
   report, and any shared files you modified. It MUST NOT include anything you
   didn't touch yourself — the worktree may have pre-existing uncommitted
   changes (the `_prompt.md`, batch-runner edits) that are not yours.

3. Stage explicitly by listing each path: `git add <file1> <file2> ...`. Do
   NOT use `git add -A`, `git add .`, or `git add agent_docs/`.

4. Run `git status --short` and confirm only your intended files are staged
   (first column `M`/`A`). Pre-existing unstaged changes (`??` or ` M`) are
   fine — leave them. `git restore --staged <file>` to undo a mistake.

5. Commit with a message that explains the *why*, ending with the trailer:

   ```
   Bring <TARGET relative path> into compliance with backend review rules

   <one or two sentences naming what was fixed (e.g. removed dead code,
   absolute imports, type hints) and any shared files edited so the diff is
   greppable later. Note if the file was already compliant.>

   Co-authored-by: Sculptor <sculptor@imbue.com>
   ```

   Even if your only change is the markdown report (file already compliant),
   still commit so the report lands on the branch.

6. Do NOT push. Do NOT amend a prior commit. Do NOT rebase. Do NOT skip hooks
   (`--no-verify` etc.). If `just format` or a pre-commit hook fails, fix the
   underlying issue and make a new commit — don't bypass it.

## Step 7 — Return JSON to the batch runner (LAST STEP)

This is your final action. The runner reads ONLY this JSON to roll up an
aggregate report across all ~320 files — your markdown and your commit are
invisible to it. Returning empty `findings` after you fixed or flagged things
makes the aggregate say "no issues" even though you changed the file. Do not
let it happen.

**Mandatory contract:** every Fixed paragraph and every Flagged paragraph in
your markdown appears as exactly one entry in `findings`.

Before returning, check explicitly:

1. Count Fixed paragraphs — call that `F`.
2. Count Flagged paragraphs — call that `G`.
3. `len(findings)` must equal `F + G`.

An empty `findings` array is acceptable ONLY when your markdown's Fixed AND
Flagged sections both say "No issues..." — never when you changed anything.

For each entry:

- `file` — `<TARGET>` path relative to repo root (even if the actual edit was
  in a shared file; mention the shared file in the description).
- `category` — the checklist category name.
- `severity` — `critical`/`high`/`medium`/`low` per the checklist.
- `description` — one sentence on what was wrong.
- `recommendation` — start with `[FIXED]` or `[FLAGGED]`, then one sentence on
  what was done or what should be done. For FIXED, note any shared files you
  edited, e.g. `[FIXED] Removed unused import; no behavior change.`
- `line_numbers` — best-effort against the post-edit file.

`summary` is one sentence: worst issue + the file's state now (e.g.
`"2 fixed (dead code, absolute imports), 1 flagged (ambiguous correctness); test-unit-backend + check green."`).
If clean, just `"clean"`.

`files_reviewed` is always 1.
