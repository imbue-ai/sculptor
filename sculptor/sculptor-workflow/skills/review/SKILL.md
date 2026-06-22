---
name: review
description: |
  Final review pass for a feature implementation. Verifies the diff
  satisfies the spec's requirements, that tests were written and pass,
  and invokes the repo's configured code-review skill. Writes review.md
  alongside the spec, then offers options for handling findings.
  Input: a feature slug (or seed message from /build with paths).
argument-hint: <feature-slug>
---

# Review

Final review pass. You read the spec, architecture, and plan; walk
the diff to verify requirements are addressed and tests were written;
re-run the test suite to confirm everything passes; invoke the repo's
configured code-review skill; and write `review.md` with the findings.

You do **not** fix anything yourself. The user decides what to do with
the findings.

## First: Rename this agent to "Review"

Before doing anything else, rename this agent to "Review" via the
`/sculptor:sculpt-cli` skill.

## The Q&A ritual

Most of this skill runs autonomously (Steps 1-8). A Q&A loop only
kicks in if the user picks **Address findings in this tab** at
Step 9's finalize. The rules below apply to that loop and to any
other turn where you ask the user a question with your question tool
(including the finalize question itself).

### Every turn ends by asking the user a question

**Every turn in a Q&A loop MUST end by asking the user a question with your question tool.**
This is the single
rule that determines whether the turn succeeded. If you end a turn
without it, you have stopped silently and the user has nothing to
respond to.

The ritual holds regardless of what happened earlier in the turn —
research, fixing a finding, answering the user's question, long
discussion. Every one of those ends by asking the user a question with your question tool.

**One narrow exception: spawning a fixer agent.** When the user
picks "Spawn a fixer agent" at finalize and you spawn it, the
spawning turn ends with **text instructions** rather than
by asking the user a question. The workspace's "waiting for
input" state must belong to the fixer agent, not to this one. The
exception applies only to the spawn turn.

### When the user asks a question back or pushes back

The user will often ask a question back, push back on a finding, or
want to drill into a topic. This is a feature, not a problem — but
it's the moment the skill fails most often: the agent goes into
"answer the user" mode and forgets to close by asking the user a
question with your question tool.

Handle it like this:

1. Engage with what the user said. Answer, push back, do research
   (Grep, Read) if needed.
2. Update `review.md` to reflect anything new the conversation
   surfaced — mark findings as resolved with commit references when
   a fix has landed.
3. End the turn by asking the user a question with your question tool — usually a
   follow-up that builds on the discussion, or a "address the next
   finding or stop?" pacing question.

Research does not excuse skipping the ritual.

### Do not announce upcoming tool calls

When you're about to ask the user a question, do
**not** announce it in text first. Just make the call.

Any sentence that announces an upcoming tool call ("Here are the
options:", "Let me ask the next round.", "A few more questions.") is
a known failure trigger — the model emits an end-of-turn token after
the announcement instead of continuing into the tool call. Options,
questions, and choices go INSIDE the tool call.

Context about prior state ("I marked REQ-XYZ-3 as resolved in
`review.md` after commit abc1234.") is fine. Announcements about the
next action are not.

### How to ask

Provide 1-4 concrete options per question. Sculptor's UI shows a
free-text field alongside options, so you don't need an "Other"
option. For genuinely open-ended questions, omit options entirely.

One sharp question beats four padded ones.

## Step 1: Load configs

Check for `.sculptor/code.md`, `.sculptor/testing.md`, and
`.sculptor/docs.md`. If any is missing, invoke `/sculptor-workflow:setup-repo`
immediately.

Read them. Key sections:

- **`.sculptor/code.md`** — pre-commit verification commands, branch
  conventions.
- **`.sculptor/testing.md`** — test framework, end-to-end test
  command/skill, test strategy.
- **`.sculptor/docs.md`** — spec location pattern (for resolving the
  slug into paths) and the *Code Review* section, which names the
  skill to invoke for the code-review pass.

## Step 2: Parse the input

`$ARGUMENTS` may contain a bare slug or seed markers from `/sculptor-workflow:build`:

- `Slug:` feature slug
- `Spec path:` absolute or repo-relative
- `Architecture path:` absolute or repo-relative
- `Plan folder:` absolute or repo-relative
- `Diff range:` git diff range, defaults to `origin/main...HEAD`

If no slug is provided, ask with your question tool, offering glob-discovered slugs.

Resolve all paths from the slug + docs config if any are missing
from the seed.

If `origin/main` doesn't exist, or no commits are ahead of it, use
your question tool to ask the user what base reference to compare against.

## Step 3: Read upstream artifacts

1. The spec — every `REQ-*` ID and every User Scenario.
2. The architecture — every component decision and the
   *Files to Modify / Create / Delete* appendix.
3. The plan's `00_overview.md` — the task index and phase rationale.
4. (Optional) skim individual task files for verification checklists.

## Step 4: Read the diff

Run `git diff <base>...<head>` to see the full diff. For large diffs,
also run `git diff --stat <base>...<head>` to list changed files,
and prioritise files most relevant to the spec.

## Step 5: Verify requirements coverage

For each `REQ-*` in the spec (or each Requirement bullet, if not
numbered):

- Locate the code in the diff that implements it. Cite
  `path/to/file.py:line-range`.
- Mark the requirement as **Covered**, **Partial**, **Gap**, or
  **Not addressed**.
- Note any deviations from the architecture's design.

For each User Scenario:

- Verify the corresponding code paths exist.
- Where testable, confirm tests cover the scenario.

For each architectural decision in `architecture.md`:

- Verify the diff reflects it (e.g. files in *Files to Modify*
  actually got modified; new components actually exist).

Capture all of this in structured notes — you'll write it to
`review.md` in Step 8.

## Step 6: Verify tests

1. List the tests added in the diff. Run
   `git diff --stat <base>...<head>` and filter to test paths
   (using the `Test location:` field inside `.sculptor/testing.md`'s
   *Test Framework* section).
2. Run the full test suite using the configured pre-commit
   verification command from `.sculptor/code.md`. Iterate until it
   passes or until you have a concrete failure to report.
3. Run end-to-end tests called out in the plan's overview using the
   testing config's command or skill (named in `.sculptor/testing.md`'s
   *Test Writing* or *Test Debugging* sections, if present).
4. Fail loudly in `review.md` if any tests are skipped, marked
   `xfail`, or pending without justification.

Do NOT block on a failing test by stopping the review. Capture the
failure in `review.md` and continue.

## Step 7: Run the code-review skill

Read the *Code Review* section of `.sculptor/docs.md`.

- **If it names a skill** (e.g. `Skill: /code-review-checklist`):
  Invoke that skill via the Skill tool. Pass the diff range and the
  spec path (as the stated goal). Capture its output.
- **If empty:** Skip this step. Note in `review.md` that no
  code-review skill is configured for this repo.

## Step 8: Write `review.md`

Path: same directory as the spec.

- **Directory-per-spec:** `<spec-dir>/review.md`
- **Flat:** `<spec-dir>/<slug>.review.md`

Structure:

```markdown
# <Feature> — Review

## Summary

<2-4 bullets: did the implementation meet the spec? top 1-3 things to
address before merging? anything that should block? "No issues found"
is valid if the diff is clean>

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-XXX-1   | Covered | `path/to/file.py:42-58` |
| REQ-XXX-2   | Partial | <what's missing> |
| REQ-XXX-3   | Gap     | <what's missing> |
| REQ-XXX-4   | Not addressed | <why> |

## User Scenarios

For each User Scenario in the spec, one paragraph: did the diff
deliver it? Was it covered by a test?

## Test Coverage

- Tests added: <list>
- Test suite status: <pass / specific failure>
- Integration tests run: <list + status>
- Anything skipped / `xfail` / pending: <list, with justification or
  flag>

## Code Review Findings

<If a code-review skill ran, paste its output here verbatim. If no
skill is configured, write: "No code-review skill configured in
.sculptor/docs.md — section skipped. Consider authoring a repo
review skill and configuring it.">

## Overall Assessment

<short, plain summary. Is this ready to merge? What's the biggest
risk? What needs follow-up?>
```

Show the path in a code block.

## Step 9: Finalize

Emit the finalizing question on its own turn
with these options:

- **Address findings in this tab** — switch into a Q&A loop where
  you help the user resolve specific items from `review.md`. You
  can edit code in this tab, run tests, commit fixes. Each fix
  references a specific finding from `review.md`.
- **Spawn a fixer agent** — spawn a fresh agent (renamed `Fix`)
  seeded with `review.md` and the list of findings to address. Use
  `/sculptor:sculpt-cli` to spawn; end the spawn turn with text
  instructions (no question).
- **Done** — stop cleanly.

Act on the user's choice.

### If the user picks "Address findings in this tab"

Enter a Q&A loop following the ritual at the top of this skill.
Each turn:

1. Pick a finding to address (in order of severity, unless the user
   has already directed otherwise).
2. Fix the code, run verification, commit per fix (one commit per
   logical change).
3. Update `review.md` to mark the finding as **Resolved** with a
   reference to the commit hash.
4. End the turn by asking the user, with your question tool, whether to
   address the next finding, hand off to a fixer agent, or stop.

## Rules

- Do NOT fix anything automatically without user direction. Review
  surfaces issues; the user decides what to do.
- Do NOT skip the code-review skill invocation if one is configured —
  even if the diff looks clean.
- Do NOT block on a failing test by halting Review. Capture the
  failure in `review.md`, continue, and surface it in the Summary.
- **Ask every question with your question tool** — `mcp__sculptor__ask_user_question` if it's available, otherwise the built-in `AskUserQuestion`. Never ask in plain text: only the tool call puts the workspace into the "waiting for input" state that alerts the user.
- The finalize question is its own turn.
- When spawning a fixer agent, end the spawn turn with **text
  instructions** rather than by asking the user a question.
- Re-run the test suite even if Build already did — Review is the
  one phase that re-verifies; other phases trust prior phases'
  verification.
