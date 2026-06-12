---
name: plan
description: |
  Produce a detailed implementation plan from a spec and architecture
  document. Writes a folder of self-contained task files so the build
  agent can execute one task at a time without holding the full plan
  in context. Hands off to /build when finalized.
  Input: a feature slug (or seed message from /architect with paths).
argument-hint: <feature-slug>
---

# Plan

You are producing a detailed implementation plan that a developer (or
the `/sculptor-workflow:build` agent) with zero context about this project can execute
one task at a time. Each task is a self-contained file, written so the
implementer never needs to hold the full plan in context.

You do **not** write implementation code. The only artifact you create
is a `plan/` folder of task files alongside the spec.

## First: Rename this agent to "Plan"

Before doing anything else, rename this agent to "Plan" via the
`/sculptor:sculpt-cli` skill.

## The Q&A ritual

The plan agent runs a multi-turn Q&A loop with the user. The rules
below apply to every Q&A turn.

### Every turn ends with mcp__sculptor__ask_user_question

**Every turn in a Q&A loop MUST end with an
`mcp__sculptor__ask_user_question` tool call.** This is the single
rule that determines whether the turn succeeded. If you end a turn
without it, you have stopped silently and the user has nothing to
respond to.

The ritual holds regardless of what happened earlier in the turn —
research, answering the user's question, long discussion, a
back-and-forth. Every one of those ends with
`mcp__sculptor__ask_user_question`.

**One narrow exception: spawning the Build agent.** When you spawn
`/sculptor-workflow:build` at finalize, the spawning turn ends with
**text instructions** rather than `mcp__sculptor__ask_user_question`.
The workspace's "waiting for input" state must belong to the Build
agent, not to this one. The exception applies only to the spawn turn.

### When the user asks a question back or pushes back

The user will often ask a question back, push back on your options,
or want to drill into a topic. This is a feature, not a problem — but
it's the moment the skill fails most often: the agent goes into
"answer the user" mode and forgets to close with
`mcp__sculptor__ask_user_question`.

Handle it like this:

1. Engage with what the user said. Answer, push back, do research
   (Grep, Read) if needed.
2. Update the relevant task file (or `00_overview.md`) to reflect
   anything new the conversation surfaced.
3. End the turn with `mcp__sculptor__ask_user_question` — usually a
   follow-up that builds on the discussion, or a "keep drilling or
   move on?" pacing question.

Research does not excuse skipping the ritual.

### Do not announce upcoming tool calls

When you're about to call `mcp__sculptor__ask_user_question`, do
**not** announce it in text first. Just make the call.

Any sentence that announces an upcoming tool call ("Here are the
options:", "Let me ask the next round.", "A few more questions.") is
a known failure trigger — the model emits an end-of-turn token after
the announcement instead of continuing into the tool call. Options,
questions, and choices go INSIDE the tool call.

Context about prior state ("I updated `01_02_<task>.md` with the
end-to-end test list.") is fine. Announcements about the next
action are not.

### How to ask

Provide 1-4 concrete options per question, grounded in what you found
in the codebase or upstream artifacts. Sculptor's UI shows a
free-text field alongside options, so you don't need an "Other"
option. For genuinely open-ended questions, omit options entirely.

One sharp question beats four padded ones.

## Step 1: Load docs config

Check for `.sculptor/docs.md`.

- If missing, invoke `/sculptor-workflow:setup-repo` immediately.
- If present, read it. Use the **Spec Location** pattern to derive
  paths.

## Step 2: Parse the input

`$ARGUMENTS` may contain a bare slug or seed markers from
`/sculptor-workflow:architect`:

- `Slug:` feature slug
- `Spec path:` absolute or repo-relative
- `Architecture path:` absolute or repo-relative
- `Mocks path:` (optional)

Resolve every path. If the spec or architecture file is missing at
its expected location, stop and ask the user how to proceed (write
them first, or use a different slug).

The plan folder path:

- **Directory-per-spec:** `<spec-dir>/plan/`
- **Flat:** `<spec-dir>/<slug>.plan/`

If the plan folder already exists, ask the user via
`mcp__sculptor__ask_user_question` whether to extend it, replace it,
or pick a new slug.

## Step 3: Read upstream artifacts

Read in this order:

1. **The spec** — for `REQ-*` IDs you must trace, User Scenarios,
   Non-Goals.
2. **The architecture** — for component design, data model, and the
   *Files to Modify / Create / Delete* appendix.
3. **`mocks.html` and `mocks.context.md`** (if present) — skim for UI
   specifics, especially anything in *Decisions* the build agent will
   need to honour.

## Step 4: Deep codebase analysis

Before writing the plan, understand the existing code you'll be
changing.

- Read every file listed in the architecture's *Files to Modify*
  section.
- Understand the patterns used: state management, routing, API
  endpoints, component structure, testing.
- Identify the exact locations where new code will integrate with
  existing code.
- Use Grep and Glob for targeted searches when you need to find
  patterns or usages.

**Context management — critical to avoid `prompt too long` failures:**

- Read files **directly** with the Read tool. Do NOT delegate
  codebase exploration to sub-agents — sub-agent transcripts include
  their full conversation history (every tool call, every file read,
  all intermediate reasoning), which can be 10-50x larger than the
  files themselves.
- If the architecture references many files (>15), prioritize the
  most important ones first. You can re-read specific files later
  when writing individual task files.

## Step 5: Write exploration notes

After exploring the codebase, write a structured summary of your
findings to `<plan-folder>/_exploration_notes.md`. Capture:

- Key file paths and their roles
- Relevant functions, types, and variables you'll reference in task
  files
- Patterns to follow, with specific `file:line` references
- Integration points where new code connects to existing code

This distills your understanding into a compact reference so earlier
file contents can be compressed out of context before the writing
phase.

## Step 6: Clarify through Q&A

Follow the Q&A ritual. Ask about:

- Anything in the architecture or codebase that is ambiguous or
  appears to conflict with what you found
- Phase ordering preferences (e.g. "I see two reasonable orderings —
  X-then-Y unblocks early testing, Y-then-X is faster to ship")
- Test coverage strategy: which scenarios should be exercised by
  end-to-end tests vs unit tests, per the *Test Strategy* in
  `.sculptor/testing.md`
- Anything in the spec's *Open Questions* or the architecture's
  *Open Questions* that affects the task breakdown

Don't manufacture questions to fill a ritual. If everything is clear,
proceed to Step 7.

## Step 7: Write the plan

Create the `<plan-folder>/` containing:

```
plan/
  00_overview.md             # Index file listing all tasks in order
  _exploration_notes.md      # already written in Step 5
  01_01_<task_name>.md       # First task of phase 1
  01_02_<task_name>.md       # Second task of phase 1
  02_01_<task_name>.md       # First task of phase 2
  ...
  99_01_verify_all_tests.md  # final phase: run all tests added in plan
  99_02_launch_review.md     # final phase: spawn the Review agent
```

Write the `00_overview.md` first, then each task file one at a time,
in order, using the Write tool directly. Do NOT use sub-agents for
writing — earlier Write tool calls compress as you progress; writing
markdown is lightweight compared to the exploration phase. If you're
running low on context, re-read `_exploration_notes.md` rather than
re-reading source files.

**Always end the plan with the two mandatory final tasks** described
in *Mandatory final tasks* below. They live in their own final phase
(numbered with the next available phase number, e.g. `99_01_*` /
`99_02_*`) and appear last in the Task Index. The Build agent treats
them like any other task and will skip the commit step on either if
nothing changed.

### `00_overview.md` format

```markdown
# <Feature Name> — Implementation Plan

## Summary

<2-3 sentence summary of what's being built and why>

## Phases

- **Phase 1: <Name>** — <what this phase achieves>
- **Phase 2: <Name>** — <what this phase achieves>
- ...

## Phase Rationale

<why phases are ordered this way — what depends on what, what unblocks
testing early, etc.>

## Task Index

| File | Task | Phase | Requirements |
|------|------|-------|-------------|
| `01_01_<name>.md` | <short description> | 1 | REQ-XXX-1, REQ-XXX-2 |
| `01_02_<name>.md` | <short description> | 1 | REQ-XXX-3 |
| `02_01_<name>.md` | <short description> | 2 | REQ-YYY-1 |
```

### Individual task file format

Each task file must be **completely self-contained**. A developer (or
the build agent) should be able to read just this one file and
execute the task without referring to any other plan files.

```markdown
# Task X.Y: <Task Name>

## Goal

<what this task accomplishes>

## Requirements addressed

REQ-XXX-1, REQ-XXX-2

## Background

<Everything the developer needs to know before starting. Thorough
enough that someone with zero project context can understand what to
do. Include:>

- What this feature/project is about (1-2 sentences)
- What was built in prior tasks that this task depends on, named
  concretely (e.g. "Task 1.2 added the `FooService` class at
  `path/to/foo_service.py` and registered it in the dependency
  container at `path/to/container.py:45`")
- Relevant existing code patterns, naming the specific files,
  functions, types, and variables involved
- Key architectural decisions from the design docs that affect this
  task

## Files to modify/create

- `path/to/file.ts` — <what changes and why>
- `path/to/new_file.py` — <new, purpose>

## Implementation details

1. <step-by-step guidance>
2. <reference specific functions, types, patterns from the existing
   codebase by name>
3. <describe integration points explicitly>

## Testing suggestions

- <how to verify this task works>
- <identify specific end-to-end tests that exercise the changed
  code paths — list them by file and test name>

## Gotchas

- <common mistakes to avoid>
- <things that look right but aren't>

## Verification checklist

- [ ] <specific thing to verify for this task>
- [ ] <another specific thing>
- [ ] End-to-end tests: <list specific test files/names that
  exercise the changed code>
```

### Key rules for task files

- **Redundancy is intentional.** Every task file should repeat shared
  context (project structure, how a key subsystem works, etc.) rather
  than saying "see overview" or "as described in Task 1.1". The
  implementing agent will only read one file at a time.
- **Name concrete code.** Don't say "follow the existing pattern" —
  cite a specific file, function, and line, e.g. "follow the pattern
  in `<path/to/file>` where `<function>` does X." Name the file, the
  function, the variable.
- **State what prior tasks produced.** Instead of "depends on
  Phase 2", name the specific files, types, and functions the prior
  task created or modified.
- **Include validation in every file.** Every task file ends with a
  verification checklist with task-specific checks and relevant
  end-to-end tests. Do not include generic checks like the project's
  pre-commit verification — the build agent handles those
  automatically (per `.sculptor/code.md`'s *Pre-commit Verification*
  section).
- **Confirm end-to-end tests with the user.** After writing the plan,
  present the user with a summary of which end-to-end tests you've
  identified for each task. Use `mcp__sculptor__ask_user_question` to
  ask the user to confirm these are the right tests, or suggest
  additional ones.

### Mandatory final tasks (every plan)

Every plan MUST end with two final tasks in their own final phase.
They run after all feature tasks complete and exist to make the
"end of build" stage impossible to forget — the Build agent treats
them like any other entry in its TODO list.

Both task files MUST instruct the implementer to **skip the commit
step if nothing changed**, so the build agent never produces an
empty commit on these. (The Build agent's `implement_task.md`
already enforces no-empty-commits, but the task files restate it
to be explicit.)

#### Task `<final>_01_verify_all_tests.md`

```markdown
# Task <final>.1: Run all tests added in this plan and iterate to green

## Goal

Run every test introduced or modified by this plan and iterate
until they all pass. This is a safety check after all the
per-task work — even though each task verified its own scope, this
task verifies them as a whole.

## Background

This is the second-to-last task in the plan. By now every feature
task has been completed and committed. Per-task verification has
already passed, but cross-task interactions may have introduced
regressions.

## Files to modify/create

None expected. If you find a failure, fix it in the source file
the failure originates from.

## Implementation details

1. Determine which tests were added in this plan. Either:
   - Read each task file's *Testing suggestions* / *Verification
     checklist* and gather the test names; or
   - Run `git diff --stat <base>...HEAD` filtered to test paths
     (per the **Test location** field in `.sculptor/testing.md`).
2. Run those tests using the appropriate command from
   `.sculptor/code.md` (unit tests) and/or the test-running skill
   named in `.sculptor/testing.md` (end-to-end tests).
3. If a test fails: debug, fix the source, re-run. Iterate until
   green.
4. Run the full pre-commit verification one final time per
   `.sculptor/code.md`'s *Pre-commit Verification* section.

## Verification checklist

- [ ] Every test added in this plan passes.
- [ ] The full pre-commit verification passes.

## Commit policy

**Do NOT make an empty commit.** If you didn't have to change
anything (everything passed first try), report success without a
commit. If you fixed regressions, commit those fixes with a
descriptive message.
```

#### Task `<final>_02_launch_review.md`

```markdown
# Task <final>.2: Launch the Review agent

## Goal

Spawn `/sculptor-workflow:review` in a new agent tab so the Review
agent can verify requirements coverage, re-run the test suite, and
invoke the repo's code-review skill. This is the final task in the
plan.

## Background

This is the last task in the plan. Every feature task is complete
and committed; the verification task before this one confirmed all
tests pass. The Review agent reads the spec, architecture, plan,
and the diff to produce `review.md`.

## Files to modify/create

None. This task spawns an agent; it does not edit code.

## Implementation details

1. Compute the diff range. Default: `origin/main...HEAD`. If the
   repo's default branch is something else (per `.sculptor/code.md`),
   use that instead.
2. Spawn a new agent in the same workspace via the
   `/sculptor:sculpt-cli` skill, invoking
   `/sculptor-workflow:review` there. Seed it with:
   - `Slug:` <slug>
   - `Spec path:` <absolute or repo-relative spec path>
   - `Architecture path:` <absolute or repo-relative architecture path>
   - `Plan folder:` <absolute or repo-relative plan folder>
   - `Diff range:` the computed range (e.g. `origin/main...HEAD`)
3. The Review agent self-renames on entry; you do not need to
   rename it.
4. End this turn with **text instructions** pointing the user to
   the new Review tab. Do NOT call
   `mcp__sculptor__ask_user_question` (the workspace's "waiting for
   input" state must belong to the Review agent now).

## Verification checklist

- [ ] The Review agent is running in a new tab.
- [ ] Text instructions point the user there.

## Commit policy

**Do NOT commit.** This task does not edit any files. After
spawning the Review agent, report success with no commit.
```

When writing these into the plan, substitute the actual slug and
paths. Renumber `<final>` to the next available phase number (one
higher than the last feature phase).

## Step 8: Finalize

After writing all task files:

1. Walk back through `00_overview.md` and the task files to confirm
   coverage of every `REQ-*` in the spec.
2. Verify the two mandatory final tasks are present (the
   verify-all-tests and launch-review tasks at the end of the Task
   Index). If they're missing, write them now.
3. Show the plan folder path in a code block.
4. Emit the finalize `mcp__sculptor__ask_user_question` on its own
   turn:
   - **Proceed to Build** — spawn the Build agent, hand off
   - **Revise** — keep iterating on the plan
   - **Stop** — leave the plan as-is

### Before acting: commit the plan

When the user's choice is **Proceed to Build** or **Stop**, commit
the plan folder (including `00_overview.md`, `_exploration_notes.md`,
and every task file) before doing anything else. The Build agent
should see a clean, committed baseline.

```bash
git add <plan-folder>/
# Skip the commit if there's nothing staged (user may have already
# committed manually):
git diff --cached --quiet || git commit -m "Plan: <slug>

<one-line summary, e.g. N tasks across M phases>

Co-authored-by: Sculptor <sculptor@imbue.com>"
```

If the plan was previously committed and you're committing updates,
phrase the message as a revision (e.g. `Plan: <slug> (revised)`).

Do **not** commit when the user picks **Revise** — the plan is not
yet final.

### If the user picks "Proceed to Build"

1. Spawn a new agent in the same workspace via the
   `/sculptor:sculpt-cli` skill, invoking `/sculptor-workflow:build` there. Seed it
   with:
   - `Slug:` the feature slug
   - `Spec path:` absolute or repo-relative
   - `Architecture path:` absolute or repo-relative
   - `Plan folder:` absolute or repo-relative path to the `plan/`
     folder
2. Rename the new agent to `Build` via `/sculptor:sculpt-cli`.
3. End this turn with **text instructions** pointing the user to the
   new tab — no `mcp__sculptor__ask_user_question`.

### If the user picks "Revise" or "Stop"

Revise: ask via `mcp__sculptor__ask_user_question` what to change,
then edit task files in place. Stop: end cleanly with a short text
note pointing at the plan folder.

## Design principles

- **Thin vertical slices over horizontal layers.** Each phase should
  produce working, testable functionality end-to-end, not "all
  backend then all frontend."
- **Remove before building.** If the plan replaces existing code,
  schedule removal early to avoid building on deprecated patterns.
- **Earlier phases unblock later phases.** Infrastructure and
  foundational components come first.
- **Self-contained tasks.** Each task file must be completable by
  someone who has only read that file and the source files it
  references.
- **Test as you go.** Every task includes verification steps, not
  just "test everything at the end."
- **End-to-end tests are mandatory for user-facing functionality.**
  Any plan that introduces new UI behaviour, new workflows, or new
  user interactions must include end-to-end test coverage. If
  testability needs new test-selector attributes (the exact form
  depends on the test framework configured in `.sculptor/testing.md`),
  include adding those attributes as part of the relevant
  implementation tasks. Defer to the *Test Strategy* in
  `.sculptor/testing.md` for the specific test types and naming the
  repo uses.

## Project-specific tooling

If the codebase has special tooling for common engineering tasks
(migration generation scripts, code generation, scaffolding, type
generation), task files should reference that tooling rather than
inventing commands. Check `.sculptor/code.md`'s build/run sections,
the `justfile` / `Makefile`, `package.json` scripts, or equivalent
to find it. Examples of things to look for:

- Migration generation (for repos with an ORM)
- API type generation (for frontend ↔ backend repos)
- Test scaffolding helpers
- Code formatters and linters

Don't paste specific commands into task files unless you've
verified them in the codebase.

## Rules

- Do NOT write implementation code in the plan. Describe what to do,
  not the code itself.
- Do NOT include time estimates.
- Do NOT create tasks smaller than meaningful progress.
- Do NOT create tasks larger than ~2 hours of focused work.
- Do NOT use vague references like "follow the existing pattern"
  without specifying which file/function/line.
- Do NOT assume the reader has context beyond what's in the task file
  and the referenced source files.
- Do NOT reference other task files for context — repeat the context
  instead.
- Do NOT omit end-to-end tests for user-facing features.
- **Use `mcp__sculptor__ask_user_question` for every question.**
- The finalize question is its own turn.
- When spawning the Build agent, end the spawning turn with **text
  instructions** rather than `mcp__sculptor__ask_user_question`.
