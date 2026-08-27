# CI Babysitter

The **CI Babysitter** watches your open pull requests and, when a PR's CI
pipeline fails or the PR develops a merge conflict, automatically asks an AI
agent to fix it — investigate the failure, make the change, commit, and push.
It's designed for leaving a batch of PRs to sort themselves out while you step
away: fire off some work, turn the babysitter on, and come back to find most of
them green.

The CI Babysitter is **experimental and off by default**. Turn it on in
[Settings](settings.md) → **CI**.

---

## What it does

Once enabled, the babysitter reacts to two things on each of your open PRs:

- **A failed pipeline** — when the PR's CI checks go red, it asks an agent to
  find the root cause, fix the code, and push the fix.
- **A merge conflict** — when the PR can no longer merge cleanly into its base
  branch, it asks an agent to rebase, resolve the conflicts, and force-push.

It keeps trying, up to a limit you set (the **retry cap**), until the pipeline
passes. PRs it can't rescue are simply left with their failing status for you to
pick up by hand — the babysitter never merges or closes a PR itself.

---

## How it works

You don't have to do anything once it's on. Behind the scenes:

1. **Sculptor watches your PRs.** It polls GitHub for each open PR's checks and
   merge status (roughly every 30 seconds), so it notices when a pipeline turns
   red or a conflict appears.
2. **It waits for a quiet moment.** The babysitter never interrupts an agent
   that's mid-task. If any agent in that workspace is busy or waiting on you, it
   holds off — the failure will come back around on the next push, and it'll act
   then.
3. **It opens a dedicated agent.** When the workspace is idle, the babysitter
   spawns its own agent in that workspace, shown as a **"CI Babysitter"** tab.
   This is a normal agent session — it's just started automatically and handed a
   prompt. The same tab is reused for every retry, so it reads as one ongoing
   conversation, and it sticks around across app restarts.
4. **The agent does the work.** It receives the fix prompt (see below), then
   investigates, edits, commits, and pushes just like an agent you'd drive
   yourself. The babysitter only sends the prompt; the agent makes and pushes the
   changes.
5. **It retries until green — or gives up.** Each attempt counts against the
   retry cap. When the pipeline finally passes, the counter resets, so a future
   failure gets a fresh set of attempts. Once the cap is reached, it stops
   prompting for that PR until the pipeline next passes on its own.

A couple of details worth knowing:

- It won't fire twice for the same failing run — only a **new** pipeline run that
  fails re-arms it. This also means a PR that's *already* red when you turn the
  babysitter on won't consume a retry until its next run fails.
- When a PR is **merged or closed**, the babysitter retires for that workspace
  and stops watching.

---

## Turning it on and configuring it

All of the babysitter's settings live in [Settings](settings.md) → **CI**, and
apply across every workspace:

- **Enable CI Babysitter** — the master switch. Off by default.
- **Babysitter agent** — which agent does the fixing:
  - **Most recently used** (the default) — matches whatever kind of agent you
    last used in that workspace.
  - **Claude** or **Pi** — always use that harness.
  - **A specific agent** — any registered agent that accepts automated prompts.
    Plain terminals and agents that don't opt in won't appear here.
- **Retry Cap** — how many times the babysitter will prompt for one PR before
  giving up (until the pipeline next passes). Default **3**; you can set anywhere
  from **1 to 10**.
- **Pipeline Failed Prompt** — the instruction sent when a pipeline fails. The
  default asks the agent to *"Investigate the failing pipeline for this PR,
  identify the root cause, fix the code, commit, and push."* Edit it to fit your
  project, or reset it to the default.
- **Merge Conflict Prompt** — the instruction sent when a conflict appears. The
  default asks the agent to fetch, rebase against the base branch, resolve the
  conflicts, and force-push. Also editable and resettable.

---

## Pausing it for one PR

You don't have to turn the whole feature off to stop it on a single PR. Open the
PR's status button (see [Pull Requests](pull_requests.md)) and use the
**pause/resume** switch there. Pausing is **per workspace** and is remembered
across restarts, so a PR you've paused stays paused until you resume it.

If the babysitter can't run for a workspace — for example, its chosen agent type
isn't available — the switch shows a short reason instead of a status.

---

## Requirements and limits

- **GitHub pull requests only.** PR status comes from the GitHub CLI (`gh`), so
  the babysitter only works in repos with a GitHub remote and a `gh` that's
  installed and signed in. See [Pull Requests](pull_requests.md) for setup.
- **Sculptor has to be running.** The babysitter is part of your local Sculptor
  app, not a cloud service. It only watches and fixes PRs while the app is open
  and your machine is on.
- **It shares your GitHub rate limit.** Status polling counts against your
  personal GitHub API budget across all your workspaces. If that budget runs low,
  Sculptor automatically slows its polling down, which means it may take longer to
  notice a new failure.
- **It respects your in-progress work.** Because it waits for the workspace to be
  idle, a failure that lands while you're actively working is skipped for now
  rather than queued — it re-arms on the next push.
- **It won't rescue everything.** Once a PR hits the retry cap, it's left flagged
  with its failing status for you to take over manually.
