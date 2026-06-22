---
name: build
description: |
  Execute an implementation plan by working through each task file in
  order. Reads the plan's 00_overview.md, builds a TODO from the task
  index, then for each task re-reads implement_task.md and follows it
  end-to-end. The plan's final two tasks handle global test
  verification and spawning the Review agent.
  Input: a feature slug (or seed message from /plan with paths).
disable-model-invocation: true
argument-hint: <feature-slug>
---

# Build

Execute the implementation plan one task at a time. You are mostly
autonomous — you don't run a Q&A loop. For each task file you re-read
`implement_task.md` (alongside this SKILL.md) and follow it
end-to-end: read the task, do the work, verify, commit (or skip the
commit if there are no changes).

Per-task discipline is critical — agents that drift from this rhythm
tend to forget to run verification, forget to commit, or skip ahead.
Re-reading `implement_task.md` at the start of every task is the
structural defense.

## First: Rename this agent to "Build"

Before doing anything else, rename this agent to "Build" via the
`/sculptor:sculpt-cli` skill.

## Step 1: Load configs

Check for `.sculptor/code.md` and `.sculptor/testing.md`. If either
is missing, invoke `/sculptor-workflow:setup-repo` immediately. Then
read both — they drive verification and testing commands.

Check for `.sculptor/docs.md` (for spec / plan paths). Same rule.

## Step 2: Parse the input

`$ARGUMENTS` may contain a bare slug or seed markers from
`/sculptor-workflow:plan`:

- `Slug:` feature slug
- `Spec path:` absolute or repo-relative
- `Architecture path:` absolute or repo-relative
- `Plan folder:` absolute or repo-relative path to the `plan/` folder

If no slug is provided, ask with your question tool — `mcp__sculptor__ask_user_question` if it's available, otherwise the built-in `AskUserQuestion` — offering glob-discovered slugs. (The tool call raises the "waiting for input" status that alerts the user; don't ask in plain text.)

Verify the plan folder exists at the resolved path. If not, stop and
ask the user how to proceed with your question tool.

## Step 3: Read the overview and implement_task.md

Read these two files now, before any task work:

1. `<plan-folder>/00_overview.md` — for the task index. Do NOT read
   any individual task files yet.
2. `implement_task.md` (next to this SKILL.md in the plugin) — the
   per-task process. You will re-read this at the start of every
   task in Step 5.

## Step 4: Build the TODO list

From the Task Index table in `00_overview.md`, build a TODO entry
for every row. Each TODO has this exact format:

```
Read and execute <plan-folder>/<filename>
```

Mark every TODO as `pending`.

The last two entries in the plan are always:

- a verification task that runs all tests added during the plan and
  iterates until they pass
- a hand-off task that spawns the Review agent

You treat these like any other task — read the task file, follow
`implement_task.md`, mark completed. They are intentionally part of
the TODO list (not separate post-loop steps) so they're impossible
to forget.

## Step 5: Execute each task in order

For each TODO entry, in order:

1. Mark the TODO as `in_progress`.
2. **Re-read `implement_task.md`** (the per-task process file). Do
   this even if you read it in Step 3 — re-reading keeps the
   discipline visible.
3. Read the task file specified in the TODO.
4. Follow `implement_task.md` end-to-end against this task.
5. Mark the TODO as `completed`.
6. Move to the next TODO.

If a task hard-fails with a blocker you cannot resolve, stop and ask the user how to proceed with your question tool.
Do NOT skip the task.

## When the TODO list is empty

All tasks are done, including the final verification and Review
hand-off (the plan's last two tasks already took care of those). The
Review agent is now running in another tab; the user's focus belongs
there.

If the final task did its job correctly, the spawn turn already
ended with text instructions pointing the user to the Review tab —
nothing else for you to do. If for some reason the Review agent was
not spawned (e.g. a task failed earlier and the user told you to
skip it), report that clearly so the user can spawn Review manually.

## Rules

- Do NOT modify files outside the scope of the current task.
- Do NOT skip any verification steps.
- Do NOT commit if verification is failing.
- Do NOT make empty commits — `implement_task.md` covers when to
  skip the commit step.
- Do NOT make architectural decisions that contradict the task
  file — if something seems wrong, surface it to the user with your question tool rather than improvising.
- Do NOT read task files ahead of time — only read each task file
  when you start working on it.
- Do NOT proceed past a failed task without asking the user.
- Do NOT skip the re-read of `implement_task.md` at the start of
  each task. The re-read is the structural defense against drift.
