---
name: code-review-checklist
description: |
  Review a set of code changes against Sculptor's review categories and produce
  a markdown findings table. Use when reviewing code (your own or others').
---

# Code Review Checklist

Review a set of code changes against the categories below and produce a
markdown findings table.

## Inputs

- **Working directory** — where to run `git` commands. Default: the current repo.
- **Diff range** — preferred form is `<base>...<head>` (three dots). Default if
  not specified: `git diff origin/main...HEAD`.
- **Stated goal** (optional) — a description of what the change is meant to
  accomplish (e.g. an MR/PR description, a spec, a ticket). Used for the
  "Consistency with stated goal" category. Skip that category if no goal was
  provided.

## Steps

### 1. Read the stated goal (if any)

Read it before reading the diff so the goal is fresh while you're reviewing.

### 2. Read the diff

Run `git diff <base>...<head>` in the working directory and read the full
output. For very large diffs, also list changed files
(`git diff --stat <base>...<head>`) and prioritize files most relevant to the
stated goal.

Also read the commit messages in the range (`git log <base>..<head>`) — they
are part of what you review (see "Public-facing text" and "Git hygiene").

### 3. Walk every category

For each category below, look for issues in the diff. Be exhaustive — a single
file can have multiple issues of the same type. Don't skip categories that
look empty at a glance; spend a moment confirming.

For frontend (`.tsx`) changes, you MUST read `docs/development/review/react.md`
(generic React rules), `docs/development/review/sculptor.md` (Sculptor-specific
conventions: backend data hooks, Jotai atoms, component invariants), and
`docs/development/review/design.md` (design-system usage, existing patterns,
UI copy) in full and apply every rule in them. Do not skip this step. Do not
rely on summaries elsewhere in this checklist or on prior knowledge — the docs
are the source of truth and are updated independently.

For integration test changes (under `sculptor/tests/integration/`), you MUST
read the file `docs/development/review/integration_tests.md` in full and apply every rule
in it. Same reasoning as above.

### 4. Produce findings broken down by category

Output one section per category in the order they appear under "Categories"
below. Every category must have a section in your output — including ones
where you found no issues. This forces you to confirm you actually reviewed
each category rather than letting empty ones slip past unnoticed.

For each category, write a heading with the category name, then either prose
findings or an explicit "no issues" line.

Write each finding as a short paragraph, not as a table row. Lead with the
severity tag in bold, then the file path and line numbers, then a one- to
three-sentence explanation of what's wrong and why it matters. Multiple
findings in the same category go as separate paragraphs, blank-line separated.

Example output:

```
### Correctness

**HIGH** — `path/foo.py:42-48`. `bar()` is called with `None` when `x` is
empty, and `bar` does not guard against that. This will raise an
`AttributeError` at runtime on the empty-list path, which the new tests
don't cover.

**MEDIUM** — `path/baz.py:101`. The loop runs `range(len(items) - 1)`, so
the last item is silently skipped. Likely an off-by-one introduced when the
slice was removed in this change.

### Consistency with stated goal

No stated goal provided — section skipped.

### Test coverage

No issues found.
```

Each section must be one of:
- One or more prose findings (each a paragraph led by a bolded severity tag), OR
- The literal line `No issues found.`, OR
- For "Consistency with stated goal" only, when no goal was provided:
  `No stated goal provided — section skipped.`

Do NOT collapse multiple empty categories into a single "no issues" note.
Do NOT omit a category section. If you do, it signals you didn't review it.
Do NOT use markdown tables — prose only.

Severity:
- **CRITICAL** — crashes, data loss, security holes, silently wrong behavior
- **HIGH** — likely bugs, broken edge cases, missing tests for risky paths,
  breaking API/schema changes
- **MEDIUM** — maintainability issues, scope creep, style guide violations,
  unclear code that will lead to bugs
- **LOW** — nits, minor cleanup, naming, comments

### 5. Summarize

After the per-category sections, write a short summary (2–4 bullets):

- Whether the change accomplishes the stated goal (if a goal was provided)
- Top 1–3 things to address before merging
- Anything that should block the change
- "No issues found" is a valid summary if the diff is clean

## Categories

### Correctness
- Logic errors: off-by-one, wrong operator, inverted conditions
- Edge cases: `None`/empty/zero/negative inputs, boundary values
- Race conditions, ordering bugs in async/concurrent code
- Resource lifecycle: file handles, sockets, subscriptions, listeners,
  subprocesses cleaned up on all paths (including error paths)
- State invariants: any path that leaves an object in an inconsistent state

### Consistency with stated goal
- Does the implementation match the stated intent?
- Are there functional changes not mentioned in the goal (scope creep)?
- Is anything described in the goal missing from the diff?
- Are there obvious follow-ups the goal implies but the diff doesn't deliver?
- **Does the fix exercise the full user flow described in the goal, not just the narrow symptom?** If the goal describes a multi-step user flow (e.g. "background subagent renders as 0.0s") and the fix only addresses one moment in that flow, that's a partial fix — flag it. The bar is: a reviewer should be able to follow the original repro and confirm the *whole* flow works, not just that the literal symptom no longer appears.

### Test coverage
- New behavior has tests
- Bug fixes include a regression test that fails without the fix
- Tests are focused — one logical assertion per test
- Critical paths covered: error paths and edge cases, not just the happy path
- No tests skipped/`xfail`/disabled without justification
- No flaky patterns introduced (sleeps, real network, time-of-day deps)

### Proof of work completeness
This category applies when the stated goal is an MR/PR body produced by an autonomous workflow (e.g. `/sculptor-workflow:fix-bug`). Skip the category if no stated goal was provided, or if the stated goal is a spec/ticket rather than an MR body.

- **UI-visible bugs MUST have before/after screenshots.** If the diff touches any frontend file (`sculptor/frontend/`, any `.tsx`, `.css`, or other UI surface) and the MR body's "Before" or "After" slots lack an embedded image (e.g. `<img src="...">` or a markdown image link), flag it as HIGH. Test output is not a substitute.
- **Non-UI bugs MUST have failing-then-passing test output.** If the diff has no UI surface and the MR body's "Before" or "After" slots lack a fenced code block with test output, flag it as HIGH.
- **Test commit hashes MUST be present** in the Test block. If the body says "Failing-test commit: `<hash>`" with a placeholder or empty hash, flag it.
- **Root cause and Fix blocks MUST be substantive.** Single-sentence "fixed the bug" entries are not acceptable; flag any block under two sentences.
- **Repro steps MUST be exact.** Vague repro steps ("open the app, click around") that a reviewer cannot follow verbatim are not acceptable.

### Dead code & leftover artifacts
- Unused imports, variables, functions, types, components
- Commented-out code
- New `TODO`/`FIXME`/`XXX` comments without an owner or ticket
- Debug statements: `console.log`, `print(...)`, `pdb`, `breakpoint()`,
  `debugger`
- Unused feature flags, config knobs, env vars
- Stale code paths replaced by the change but not deleted

### Comments
- Comments describe the code and explain *why*; they are not narration.
- No incidental history or defensive justification — strip comments that explain
  today's bug fix, argue for the code's correctness, or narrate how the code
  used to work. The comment should help a future maintainer, not relitigate
  the change that introduced it.
- No restating volatile facts from the surrounding code (a count of subclasses,
  a list of variants/enum cases, the call sites of a function). These pin the
  comment to a moment in time and rot quickly — follow DRY.
- No ASCII-art banners or box-drawing section dividers. They add visual noise
  without conveying anything a plain one-line comment does not.
- No editorializing — strip frustration, jokes, hedging-as-mood, and
  exaggeration, keeping any underlying fact.
- No pointers to throwaway docs, tickets, or plan phases — `agent_docs/...`
  paths, `REQ-*` requirement IDs, or implementation-plan phase references.
  The comment must stand on its own.
- No real people's names in comments, docstrings, or test strings. Reword
  (e.g. "check with the team"), and use a generic placeholder (`dev`, `foo`,
  `alice`) for usernames in `/Users/<name>/` paths or example branch names.

### Error handling
- No bare `except:` or unconditional `except Exception:`
- Errors carry context (custom exception types where appropriate)
- No silently swallowed errors (`except: pass` etc.)
- User-facing errors are actionable
- External I/O has timeouts and reasonable retry/backoff where appropriate

### Security & secrets
- No secrets, tokens, API keys, or credentials in code or configs
- Input validated at trust boundaries
- Auth/permission checks present where required
- No untrusted input fed to subprocess/eval/SQL/template without sanitization
- Sensitive values not logged

### Type safety
- Type hints on new/changed public functions
- No new `Any` types unless justified
- Pydantic models for structured data, not ad-hoc dicts
- No new Pyrefly errors; suppressions justified with a comment
- For frontend: TypeScript types up to date; if `ElementIDs` changed, run
  `just generate-api`

### Backwards compatibility
- API/schema/config changes are documented and have migration paths
- Persisted data formats: forward-compatible reads if format changes
- Public CLI flags / env vars: deprecation considered before removal
- Frontend↔backend contract changes shipped together

### Frontend issues (for `.tsx` changes)
**Required:** Read `docs/development/review/react.md` (generic React rules),
`docs/development/review/sculptor.md` (Sculptor-specific frontend conventions), and
`docs/development/review/design.md` (design-system usage, existing patterns, UI copy)
in full with the Read tool, and apply every rule in them. The rules cover effects,
state, refs, render purity, performance, props, lists, backend data hooks,
Jotai atom usage, component-level invariants, design-token and component-reuse
conventions, and UI copy — detailed enough that summarizing them here would lose
information, so this section intentionally does not list them. If you find
yourself reviewing a `.tsx` change without having opened all three docs in the
current session, stop and read them.

Beyond the docs: `IconButton` in a `Flex` uses `gap="2"` (per CLAUDE.md).

### Integration test issues (for changes under `sculptor/tests/integration/`)
**Required:** Read `docs/development/review/integration_tests.md` in full with the Read
tool and apply every rule in it. The rules cover Playwright assertion
patterns, test isolation, and POM usage — they're detailed enough that
summarizing them here would lose information, so this section intentionally
does not list them. If you find yourself reviewing an integration test change
without having opened that doc in the current session, stop and read it.

### Style guide & ratchets
- All imports at top of file (no inline imports unless `# noqa: E402`)
- No relative imports
- No nested/inline function definitions (except simple lambdas)
- Boolean variables prefixed with `is_`/`has_`/`should_`/etc.
- No `num_` prefix (use `count_` or `_idx` suffix)
- Early-exit pattern preferred over deep nesting
- No magic numbers — use named constants
- No mutable default arguments
- Comments follow the **Comments** category above
- Run `just ratchets` if you suspect any counts changed; flag any increases

### Git hygiene
- Commit messages explain the "why"
- Commits are atomic — one logical change each
- No unrelated changes mixed in

### Public-facing text (commit messages & PR/MR description)
Commit messages and the PR/MR title and description are published to a public
repository — review them as **permanently, world-readable** artifacts. Read the
commit messages in the range (`git log <base>..<head>`) as well as the stated
goal (the PR/MR body, when one was provided). Flag any of the following:

- **CRITICAL** — secrets, tokens, credentials, or private keys in a commit
  message or PR/MR body.
- **PII** — real people's full names, personal email addresses, individual
  usernames, or local filesystem paths embedding a username (`/Users/<name>/`).
  These should be reworded to roles or generic placeholders (`dev`, `<user>`).
- **Internal-only leakage** — internal hostnames/URLs, internal
  service/tool/infra names, internal dashboards, customer names or
  customer-specific data, or verbatim private ticket/chat discussion. A bare
  ticket ID reference (e.g. `SCU-1447`) is fine; pasting the ticket's private
  contents is not.
- **Security-sensitive detail** — exploit steps or descriptions of internal
  security mechanisms written in a way that would aid an attacker. Security
  fixes should be described at a safe altitude, not as a reproduction recipe.
- **Candid internal commentary** — business strategy, unreleased plans,
  speculation about competitors, or remarks about individuals.

This is the same standard as the **Comments** category, extended from code
comments to the commit/PR prose. See also CLAUDE.md, "Public Visibility:
Commit Messages and PR Descriptions".
