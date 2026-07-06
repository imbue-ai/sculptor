# Skills

Sculptor bundles **skills** — reusable agent capabilities you invoke as slash
commands inside any agent session. Type `/` in the chat input to open the
picker. Skills run as full agents with their own tools, so they can read your
codebase, spawn parallel subagents, and adapt to your repo.

Two skill bundles ship with Sculptor:

- **`sculptor-workflow`** — an opinionated, end-to-end engineering pipeline that
  takes a feature from idea to reviewed code.
- **`sculptor-experimental`** — newer skills for moving work between agents and
  workspaces.

(There are also three `sculptor:*` helpers — `/sculptor:help` to ask questions
about Sculptor, `/sculptor:sculpt-cli` to drive Sculptor from the `sculpt`
CLI, and `/sculptor:build-sculptor-plugin` to build an
[extension](extensions.md). They're listed in
[Slash commands](chat.md#slash-commands).)

---

## The engineering workflow (`sculptor-workflow`)

`sculptor-workflow` breaks feature work into focused stages. Each stage is its
own skill, runs as its own agent (renamed to match the stage — "Spec",
"Architect", and so on, so you can tell the tabs apart), and produces a durable
artifact the next stage reads from disk.

The pipeline:

> **spec → mock → architect → plan → build → review**

You don't have to run the whole thing. Every stage takes a feature *slug* and
finds the earlier artifacts on disk, so you can start at any stage or stop after
one. When a stage finishes it offers to hand off to the next.

| Stage | Skill | Produces |
| --- | --- | --- |
| Spec | `/sculptor-workflow:spec` | the implementation spec |
| Mock | `/sculptor-workflow:mock` | `mocks.html` + `mocks.context.md` |
| Architect | `/sculptor-workflow:architect` | `architecture.md` |
| Plan | `/sculptor-workflow:plan` | a `plan/` folder of task files |
| Build | `/sculptor-workflow:build` | the implementation (commits) |
| Review | `/sculptor-workflow:review` | `review.md` |

Two more skills stand on their own: `setup-repo` (configure a repo for the
workflow) and `fix-bug` (a self-contained TDD bug fix).

### `/sculptor-workflow:setup-repo`

Run this once in a new repo. It creates three config files under `.sculptor/`
that teach the other skills how your codebase works:

- **`.sculptor/code.md`** — structure, branch naming, build/run commands, and
  the checks to run before committing.
- **`.sculptor/testing.md`** — test framework and strategy, bug tracking, and
  manual/visual testing.
- **`.sculptor/docs.md`** — where specs and their docs live, which UI to imitate
  for mocks, and which code-review skill the review stage should call.

The other workflow skills read these configs. If they're missing when you start
a stage, that skill invokes `setup-repo` for you.

### `/sculptor-workflow:spec`

Write an implementation spec through guided Q&A **before** any code is written.
It scaffolds the spec file, clarifies your goals, explores the codebase, and
refines the spec turn by turn — you watch it take shape in Sculptor's diff
viewer as you answer. For UI-heavy features it can spawn `/sculptor-workflow:mock`
to produce visual mocks as input to the spec. The only artifact is the spec
itself; no implementation code is written.

Input: a description of the feature or change.

### `/sculptor-workflow:mock`

Iterate on interactive HTML mocks of a feature. **Exploration mode** generates
several end-to-end variants so you can compare directions side by side;
**confirmation mode** refines a single coherent mock to visually verify a design
that's already specified. It can run standalone or be spawned by `/spec`. The
only artifacts are `mocks.html` and `mocks.context.md` — it never commits or
writes production code.

### `/sculptor-workflow:architect`

Produce an `architecture.md` for a feature whose spec already exists. It reads
the spec (and mocks, if any), analyses the codebase deeply, and refines the
design through Q&A — again visible live in the diff viewer. On finalize it
offers to hand off to `/plan`. It writes only `architecture.md`.

Input: a feature slug.

### `/sculptor-workflow:plan`

Turn the spec and architecture into a detailed implementation plan: a `plan/`
folder of **self-contained task files**, each written so the build agent can
execute it one task at a time without holding the whole plan in context. On
finalize it offers to hand off to `/build`.

Input: a feature slug.

### `/sculptor-workflow:build`

Execute the plan one task at a time. Build is mostly autonomous — it works
through each task file in order, re-reading its per-task instructions every time
so it doesn't drift (skip verification, forget to commit, or jump ahead), and
commits after each task. The plan's final tasks run a full test pass and spawn
the Review agent. Build is normally launched by `/plan` rather than invoked
directly.

Input: a feature slug.

### `/sculptor-workflow:review`

A final review pass. It reads the spec, architecture, and plan; walks the diff
to confirm the requirements are met and tests were written; re-runs the suite;
invokes the repo's configured code-review skill; and writes the findings to
`review.md`. It doesn't fix anything — you decide what to do with the findings.

Input: a feature slug.

### `/sculptor-workflow:fix-bug`

Fix a bug with strict test-driven development: understand the bug, prove it with
a failing test, fix the code, verify. It has two modes:

- **Interactive (default)** — asks you to confirm the reproduction and approach
  before writing code.
- **Autonomous** — prefix the input with `--autonomous` to run end-to-end with
  no questions. It explores the codebase, classifies the bug (reproduced, stale,
  already-fixed, or unreproducible), fixes proven bugs, and — if the repo's
  config allows it — opens a pull request.

Input: a bug description or a bug ticket ID.

---

## Experimental skills (`sculptor-experimental`)

> **Experimental.** These skills are built on the `sculpt` CLI and their
> behaviour may change.

Both skills move the current work to a **fresh agent** seeded with a summary of
where you are — useful when the context window is large, or when you want a clean
checkout to continue or branch off from.

### `/sculptor-experimental:handoff`

Hand the current work off to a fresh agent. You choose where it lands:

- **New agent, same workspace** — shares this workspace's branch and files
  (including uncommitted changes), so it picks up exactly where you left off.
- **New workspace** — a fresh, isolated workspace on its own auto-named branch
  cut from the current branch. Before creating it, the skill offers to commit
  any uncommitted work, since the new workspace only sees committed history.

Either way it composes a self-contained context summary so the new agent can
continue without your current conversation, then reports the new agent (and
workspace) ID so you can switch to it.

Input (optional): what the new agent should focus on next. If omitted, it's
inferred from the recent conversation.

### `/sculptor-experimental:stack`

Stack a new workspace **on top of** the current branch — a handoff into a new
workspace whose branch is both *based off* and *targets* the current branch. That
scopes the new workspace's diff and any pull request to just the changes
made on top of your current work, rather than against the repo's default target
(e.g. `main`). Use it to spin off a dependent follow-up while keeping the current
agent focused.

Stacking is only supported from **worktree** workspaces (the stacked workspace
needs to resolve your current branch as a local ref). From other workspace types,
use `/sculptor-experimental:handoff` instead.

---

## Your own skills and commands

Sculptor also surfaces any skills or commands you've installed under
`~/.claude/skills/` or `~/.claude/commands/`, as well as any under the current
repo's `.claude/` directory. They appear in the `/` picker alongside the
built-ins, sorted alphabetically. For everything else, see the
[Claude Code commands reference](https://code.claude.com/docs/en/commands).
