---
name: update-specs
description: |
  Bring the product specification set under docs/specs/ (SPEC.md,
  requirements.md, scenarios.md, scenario_coverage.md) up to date with the
  code that has merged to origin/main since the specs were last refreshed.
  Reviews the merged PRs since a recorded baseline, filters out non-product
  churn, and applies the needed edits to each doc — preserving its format and
  ID scheme. Use periodically to keep the specs from going stale, or when
  asked to "update the specs" / "refresh docs/specs".
argument-hint: [baseline-commit (optional; defaults to the recorded baseline)]
---

# Update the Product Specs

Reconcile the spec set under `docs/specs/` with everything merged to `origin/main` since the specs
were last refreshed. The job is **review the new commits, decide what changed about the product, and
edit the docs to match** — nothing more. Do not invent behavior, and do not document implementation
detail the product docs deliberately omit.

## The doc set

`docs/specs/` holds four long-lived, related documents. Read `docs/specs/README.md` first — it is the
authority on how they relate. In brief:

| Doc | What it captures | When a change touches it |
|---|---|---|
| `SPEC.md` | The narrative product spec: what Sculptor is and how each feature **behaves**, in prose. | A new/changed user-facing capability or behavior. |
| `requirements.md` | The measurable & contractual facts the prose omits: numeric targets, version/platform bars, persistence/migration guarantees, integration contracts, open questions. (This is the "architecture/requirements" doc — there is no separate `architecture.md`.) | A change that sets or moves a number, a version floor, a contract, or a guarantee. |
| `scenarios.md` | Every user-facing interaction as a Given/When/Then scenario with a stable `AREA-NNN` ID. | A change to what happens **on screen** for any interaction. |
| `scenario_coverage.md` | Maps each scenario to the integration test that demonstrates it (Complete / Partial / Missing). | Any scenario you add, change, or remove — and any new/changed test that moves a scenario's status. |

Discover the docs dynamically (`ls docs/specs/*.md`) rather than hard-coding the list, so the skill
still works if a doc is added or renamed. Apply the per-doc guidance above by matching the doc's role,
not its exact filename.

## Step 1: Determine the baseline commit

The baseline is the commit the specs were last reconciled against. Everything after it is unreviewed.

1. If the user passed a commit as `$ARGUMENTS`, use that.
2. Else read `docs/specs/.spec-baseline` — a file holding the baseline SHA on its first line. Use that SHA.

```bash
head -1 docs/specs/.spec-baseline
```

If the file is missing, stop and tell the user — the baseline must be seeded first (write the last
reconciliation commit's SHA to `docs/specs/.spec-baseline`). Don't guess a baseline.

Then fetch and confirm where the baseline sits relative to the current tip:

```bash
git fetch origin --quiet
git rev-parse origin/main
git merge-base --is-ancestor <baseline> origin/main && echo "baseline on main" || echo "WARN: baseline not on main"
git rev-list --count <baseline>..origin/main
```

If the baseline is not an ancestor of `origin/main`, stop and ask the user how to proceed (it may be on
a feature branch or have been rebased away). Reconcile **against `origin/main`**, not the local HEAD,
unless the user says otherwise.

## Step 2: Enumerate the merged PRs since the baseline

This repo merges with no-fast-forward, so every PR is one merge commit on the first-parent spine. Use
the **merge commits as the source of truth** for what landed, and the non-merge subjects for detail.

```bash
# Source of truth — one line per merged PR:
git log <baseline>..origin/main --merges --first-parent --format='%h %s'
# Detail — individual commit subjects, for understanding each PR:
git log <baseline>..origin/main --no-merges --format='%s'
```

If the lists are large, write them to the scratchpad and read them with the Read tool rather than
scrolling shell output.

## Step 3: Separate product changes from noise

Most commits do **not** change the product and must not trigger spec edits. Classify each PR.

**Ignore (noise) — does not touch the spec:**

- Comment scrubs and rewording ("Bring … into compliance with review rules", "Prune/Trim … comments").
- Dependency upgrades (Electron/Node/Python/React/Vite/etc.) and lockfile refreshes.
- CI / build / release plumbing (release gating, telemetry-key injection, apt-get hardening, CI concurrency, pyre-cache ignore).
- Test-only changes: new tests, flaky-test fixes, test infra — **with one exception** (see Step 6: they can still move a `scenario_coverage.md` status even when no behavior changed).
- Style-guide / review-rule / internal-doc edits, version bumps, frozen-schema regeneration.

**Review (product) — may touch the spec.** Apply the inclusion test from the spec's scope discipline:

> Would a user **see**, **name**, or **configure** this? If yes, it likely belongs in the product docs.

New capabilities, new settings, new panels/screens, changed defaults, changed keybindings, new CLI
flags, changed error/reliability behavior a user would notice, and removed features all qualify.

**Keep implementation detail OUT of the product docs.** Internal services, the task/Environment
substrate, WebSocket/HTTP transport, Alembic/DB migrations, schema regen, and similar plumbing are
impl-only — they belong (if anywhere) in `requirements.md` as a contract, never as product narrative.

The signal-to-noise ratio is typically ~10:1 (≈15 product features out of ≈80 PRs). If your "to edit"
list is much larger than that, you are probably letting noise through — re-apply the filter.

## Step 4: Understand each product change

Branch names embed ticket IDs (`scu-NNNN`) and squashed subjects are descriptive, but **do not write
spec text from the subject line alone** — it describes the fix, not the resulting behavior. For each
product PR, read what actually changed:

```bash
git show --stat <merge-sha>                 # files touched → which area/doc
git log <merge-sha>^1..<merge-sha>^2 --format='%s'   # the PR's own commits
git diff <merge-sha>^1..<merge-sha> -- <relevant paths>   # the real change
```

**Group related PRs into one feature** before editing (e.g. a dozen plugin-system PRs are one new
product surface, not a dozen edits). Decide, per feature, the *current* user-visible behavior — what
the product does now, on main — because that is what the spec must describe.

## Step 5: Plan the edits

For each feature, decide which docs are affected and what each edit is. This is mostly a straight
translation from "what the commits changed" to "what the product now does" — **don't check in with the
user for routine edits.** Make the changes and let the user review the diff at the end (Step 8).

Only pause to ask the user when there is **genuine ambiguity you cannot resolve from the code and
docs** — e.g. a default changed but you can't tell which value is now authoritative, or it's unclear
whether a feature is shipped vs. gated behind an experimental flag and the code doesn't say. Resolve
everything you can on your own first (read the code, read the surrounding doc); ask only about what's
truly left over, and batch those questions rather than interrupting per-feature.

## Step 6: Apply the edits

Edit each doc in place, **matching its established format, tone, and structure**. Read enough
surrounding context in each doc to slot the change in where it belongs, not at the end.

**Describe what the code does today — never what it used to do.** These are living descriptions of the
current product, not a changelog. Don't leave a trace of the change: no "now …", "no longer …",
"previously …", "used to …", "formerly …", "renamed from …", "instead of …", or any before/after
phrasing. The commit history already records what changed; the doc records what *is*. When you revise a
section, rewrite it so a reader with no knowledge of the old behavior gets an accurate, self-contained
description — then delete any wording that only makes sense relative to the past.

- **`SPEC.md`** — prose behavior. Add to or revise the relevant feature section; remove text for
  removed features. Keep the descriptive, present-tense product voice. Experimental/off-by-default
  features go in the experimental section, marked as such.
- **`requirements.md`** — only when the change sets or moves a measurable target, version/platform
  bar, persistence/migration guarantee, integration contract, or resolves an open question. Don't
  restate prose here; record the *fact*.
- **`scenarios.md`** — Given/When/Then with a stable `AREA-NNN` ID. **Preserve the ID scheme**: reuse
  the right area prefix (see its "Areas / ID prefixes" table), and **assign the next free number in
  that area — never renumber existing scenarios**. Every Then must be visible on screen. Delete
  scenarios for removed behavior; revise in place for changed behavior.
- **`scenario_coverage.md`** — for every scenario you added/changed/removed, add/update/remove its
  coverage row, set status (Complete / Partial / Missing) by checking whether an integration test
  actually drives the action and asserts the visible outcome, and **update the per-area counts in the
  executive summary table** so the totals stay consistent. A test-only PR that newly covers an
  existing scenario can move a status here even though no other doc changes.

**Public-visibility rule:** these docs are world-readable. Scrub PII, internal hostnames/service
names, customer data, and security-sensitive detail, per CLAUDE.md's "Public Visibility" section.

## Step 7: Verify consistency, then record the new baseline

Cross-check that the docs still agree with each other and with the code:

- Every new/changed `scenarios.md` ID has a matching `scenario_coverage.md` row, and the summary
  counts add up.
- A feature added to `SPEC.md` is referenced consistently wherever else it's mentioned (CLI table,
  settings list, experimental section, etc.) — grep the doc for the feature's name.
- No implementation-only detail leaked into the product narrative.
- Quickly sanity-check a couple of the riskiest claims against the code (don't trust the commit
  subject) — e.g. confirm a changed default's actual value, or that a listed CLI model is still
  selectable.

Then **update the baseline pointer** so the next run starts here:

```bash
git rev-parse origin/main > docs/specs/.spec-baseline
```

## Step 8: Hand back, don't commit

Leave the working tree dirty for the user to review — do **not** commit or push (matching the other
doc-update skills). Summarize what you changed: the baseline range reviewed (`<baseline>..<tip>`, with
counts), the features that drove edits, the docs touched, the new baseline SHA recorded, and anything
you intentionally skipped or flagged as uncertain for the user to decide.

## Notes for recurring runs

- The whole point of `.spec-baseline` is that each run only reviews *new* commits. Keep it accurate.
- Scale effort to the range: a week of commits is a quick pass; a multi-month gap (like the first run)
  is a large review — work through it feature-group by feature-group.
- This skill reviews and edits docs; it never changes product code or tests.
