---
name: update-specs
description: |
  Bring the product specification set under docs/specs/ (SPEC.md,
  requirements.md, scenarios.md, scenario_coverage.md) up to date with the
  code that has merged to origin/main since the specs were last refreshed.
  Reviews the merged PRs since a recorded baseline, filters out non-product
  churn, and applies the needed edits to each doc — preserving its format and
  ID scheme — then verifies every existing claim in the docs is still true of
  the current code. Use periodically to keep the specs from going stale, or
  when asked to "update the specs" / "refresh docs/specs".
argument-hint: [baseline-commit (optional; defaults to the recorded baseline)]
---

# Update the Product Specs

Reconcile the spec set under `docs/specs/` with everything merged to `origin/main` since the specs
were last refreshed. The job has two halves: **(1) review the new commits, decide what changed about
the product, and edit the docs to match** (Steps 2–6), and **(2) confirm every claim already in the
docs is still true of the current code** (Step 7) — because a standing claim can rot from a change the
commit review correctly skips as noise (a deletion, a rename, a moved default). Do not invent behavior,
and do not document implementation detail the product docs deliberately omit.

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

Most commits do **not** change the product and must not trigger spec edits — but **classify from the
diff, not the subject.** A subject and branch name describe *intent* ("cleanup", "flake fix", "build");
the spec cares about *effect*, and the two diverge exactly where it matters: a "cleanup" PR that
removes a documented feature, a "flake fix" that changes behavior. So before you can call a PR noise,
look at **what files it touched** — this is cheap:

```bash
# File list per PR — the real classification signal. Read this, not just the subject.
git show --stat <merge-sha>
# Or stat the whole range at once, one block per PR:
git log <baseline>..origin/main --first-parent --stat --format='### %h %s'
```

**Three hard escalation triggers. A PR hitting any of these gets its diff read no matter how its
subject reads — it cannot be dismissed as noise on the subject alone:**

- **Deletions & renames.** Any PR that deletes or renames a file
  (`git log <baseline>..origin/main --diff-filter=D,R --name-status`). A removal is the change most
  likely to be *both* filed as noise *and* to invalidate a standing doc claim — grep the docs for the
  removed path/symbol before letting it pass. (This is the class that kept a deleted helper script in
  the docs for multiple runs.)
- **Product-surface paths.** The diff touches `frontend/src/pages/**` or `frontend/src/components/**`,
  a web route handler, `config/user_config.py` (settings/defaults), a `*/registry.py`, a `sculpt` CLI
  command file, a keybindings map, or onboarding / add-repo / dependency-card code — regardless of
  subject.
- **Non-test source under a test/flake subject.** A "flake fix" or "test" PR whose diff includes
  **non-test product files** is a behavior change wearing a test-fix label. Read the non-test files.

**Genuine noise — skip only when the *diff* confirms it, never on the subject:**

- Comment scrubs and rewording.
- Dependency upgrades (Electron/Node/Python/React/Vite/etc.) and lockfile refreshes.
- CI / build / release plumbing (release gating, telemetry-key injection, apt-get hardening, CI concurrency, pyre-cache ignore).
- **Test-only** changes — the diff touches *nothing but* tests / test infra (`*_test.py`, `test_*.py`,
  `*.test.ts(x)`, fixtures). (Exception: a test-only PR can still move a `scenario_coverage.md` status
  — see Step 6.)
- Style-guide / review-rule / internal-doc edits, version bumps, frozen-schema regeneration.

**For everything not cleanly noise, apply the inclusion test** from the spec's scope discipline:

> Would a user **see**, **name**, or **configure** this? If yes, it likely belongs in the product docs.

New capabilities, new settings, new panels/screens, changed defaults, changed keybindings, new CLI
flags, changed error/reliability behavior a user would notice, and removed features all qualify.

**Keep implementation detail OUT of the product docs.** Internal services, the task/Environment
substrate, WebSocket/HTTP transport, Alembic/DB migrations, schema regen, and similar plumbing are
impl-only — they belong (if anywhere) in `requirements.md` as a contract, never as product narrative.

The signal-to-noise ratio is typically ~10:1 (≈15 product features out of ≈80 PRs). Treat that as an
**observation to sanity-check against, not a quota to prune toward** — classify each PR by its effect
and let the count land where it lands. A list far *larger* than that means impl detail is probably
leaking in; far *smaller* means you're likely trusting subjects over diffs. When a call is genuinely
uncertain, bias toward **reading the diff**, not toward skipping.

## Step 4: Understand each product change

Branch names embed ticket IDs (`scu-NNNN`) and squashed subjects are descriptive, but **do not write
spec text from the subject line alone** — it describes the fix, not the resulting behavior. Step 3
already gave you each PR's file list; now read the **real change** for everything you kept (and for any
escalation-trigger PR you're still unsure about):

```bash
git log <merge-sha>^1..<merge-sha>^2 --format='%s'   # the PR's own commits
git diff <merge-sha>^1..<merge-sha> -- <relevant paths>   # the real change → the resulting behavior
```

**Group related PRs into one feature** before editing (e.g. a dozen plugin-system PRs are one new
product surface, not a dozen edits). Decide, per feature, the *current* user-visible behavior — what
the product does now, on main — because that is what the spec must describe.

## Step 5: Plan the edits

For each feature, decide which docs are affected and what each edit is. This is mostly a straight
translation from "what the commits changed" to "what the product now does" — **don't check in with the
user for routine edits.** Make the changes and let the user review the diff at the end (Step 9).

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

## Step 7: Verify the docs against the code — every claim, baseline-independent

Steps 2–6 are *changelog-driven*: they translate the new commits into edits. That has a structural
blind spot — a claim **already in the docs** can be silently invalidated by a change you correctly
filtered out as noise in Step 3 (most often a **deletion or rename** buried in a "cleanup" / "build"
PR). The changelog will never surface it, because as a *commit* it isn't a product change; only its
*effect* on a standing claim is. (This is exactly how a deleted helper script lived on in
`requirements.md` for multiple runs.)

So this step ignores the commit history entirely. It treats the docs as a set of **standing
assertions** and confirms each one is true of the code **as it is right now**. It is **not scoped by
the baseline** and **not limited to the sections you edited** — a claim you didn't touch this run is
exactly where rot hides. **Every factual statement in all four docs is a claim to confirm true.**

Claim categories, and how to verify each:

- **Existence** — a named file, module, function, class, test, script, binary, env var, CLI command,
  setting, registration, or flag. → Confirm it still exists in the tree. This is the cheap backstop;
  always run it:
  ```bash
  # Pull backtick-quoted paths/symbols from the prose docs; report any with no match in the tree.
  for d in docs/specs/SPEC.md docs/specs/requirements.md; do grep -oE '`[^`]+`' "$d"; done \
    | tr -d '`' \
    | grep -oE '[A-Za-z0-9_./-]+\.(py|ts|tsx|toml|json|sh|plist)|[A-Za-z_][A-Za-z0-9_]{4,}' \
    | sort -u > /tmp/spec-refs.txt
  while read -r r; do
    git grep -qI -- "$r" -- sculptor tools 2>/dev/null || ls "$r" >/dev/null 2>&1 || echo "UNVERIFIED: $r"
  done < /tmp/spec-refs.txt
  ```
  Triage: runtime/on-disk paths (`~/.sculptor/internal/…`) and doc-internal IDs (`AREA-NNN`,
  `REQ-…`, `SECURITY.md`) are false positives; a real code path/symbol that's gone is a stale claim.
- **Value** — a number, limit, default, version/platform bar, timeout, keybinding, enum value, or
  exact UI label/string. → Grep the authoritative source and confirm the value matches: the version
  window in `managed_tools.py`, a size limit in the `*Utils.ts` constant, a default in
  `user_config.py`, a button's literal text in its component. A doc that pins `20 MB` must equal the
  constant.
- **Behavior** — "clicking X does Y", every scenario's **Then**, every "the product does Z" sentence.
  → Find the implementing code and confirm it still does that. This is the expensive part — fan it out
  (below).
- **Contract / guarantee** — persistence & migration survival, platform support, integration failure
  modes, isolation/security boundaries. → Confirm the mechanism still exists and behaves as stated.
- **Absence / scoping** — "only when …", "not gated on …", "removed", "no longer offered". These rot
  silently after a refactor. → Confirm the negative actually holds: the gate is where the doc says it
  is, and a thing described as removed is really gone *everywhere*.

**Make it tractable by fanning out.** You cannot deeply re-derive ~4700 lines of claims inline. Slice
the doc set into coherent units (by SPEC subsection, requirements section, and scenario area) and
dispatch a **read-only** agent per slice (the `Explore` agent fits) — in parallel. Hand each agent its
slice verbatim and require it to return, per claim, only a verdict:

- **confirmed** — with the `file:line` that proves it,
- **refuted** — with the contradicting code, or
- **uncertain** — implementation not found.

Bias the agents toward skepticism: *confirmed* requires finding the code and seeing it match, not that
the claim merely sounds plausible. Don't let an agent infer behavior from the doc itself.

**Act on the verdicts:**

- **Refuted** → fix the doc like any other edit (Step 6 rules: describe what *is*, no changelog
  wording). A refuted claim usually means a feature was removed, a default moved, or a label changed
  with no product-flagged PR.
- **Uncertain** → investigate yourself; if still unresolved, **flag it in the handback** (Step 9). Never
  silently leave a claim you could not confirm.

## Step 8: Verify internal consistency, then record the new baseline

Cross-check that the docs still agree **with each other**:

- Every new/changed `scenarios.md` ID has a matching `scenario_coverage.md` row, and the per-area and
  total summary counts add up (sum the area rows; they must equal the totals).
- A feature added to `SPEC.md` is referenced consistently wherever else it's mentioned (CLI table,
  settings list, experimental section, etc.) — grep the doc for the feature's name.
- No implementation-only detail leaked into the product narrative.

Then **update the baseline pointer** so the next run's *changelog review* starts here:

```bash
git rev-parse origin/main > docs/specs/.spec-baseline
```

## Step 9: Hand back, don't commit

Leave the working tree dirty for the user to review — do **not** commit or push (matching the other
doc-update skills). Summarize what you changed: the baseline range reviewed (`<baseline>..<tip>`, with
counts), the features that drove edits, the docs touched, the new baseline SHA recorded, and anything
you intentionally skipped. Report the **claim-verification pass (Step 7)** separately: roughly how many
claims you checked, every **refuted** claim you fixed (with what was wrong), and every **uncertain**
claim you could not confirm — the user needs the uncertains called out explicitly, not buried.

## Notes for recurring runs

- `.spec-baseline` scopes the **changelog review** (Steps 2–6) so each run only re-reads *new*
  commits. It does **not** scope the **claim-verification pass** (Step 7) — that re-confirms the whole
  doc set every run, on purpose. Don't "optimize" Step 7 down to only the touched sections or the
  baseline range; the rot it catches (a claim invalidated by a filtered-out deletion) is invisible to
  the changelog by definition. If cost is a concern, parallelize the fan-out — don't shrink the scope.
- Scale the *changelog* effort to the range: a week of commits is a quick pass; a multi-month gap
  (like the first run) is a large review — work through it feature-group by feature-group. The Step 7
  verification cost is roughly constant regardless of range, and usually dominates a small run.
- This skill reviews and edits docs; it never changes product code or tests.
