---
name: cut-release
description: |
  Cut a new Sculptor release candidate from main: run `just cut-release` (which
  creates the release/sculptor-vX.Y.0 branch at X.Y.0rc1, pushes the tag that
  triggers the RC build, and opens a PR bumping main to the next .dev0), then
  land the version-bump PR and babysit the RC build up to its manual approval
  gate. Handles the colocated jj + git working-copy setup and the CI
  flake/outage/zombie recovery playbook. Stops AT the approval gate — never
  approves it for you. Use when asked to "cut a release", "cut an RC", or start
  a new Sculptor release.
argument-hint: "(no args; operates on main's current .dev0 version)"
---

# Cut a Sculptor Release

Turn `main`'s current `X.Y.0.dev0` into a published release candidate and reset
`main` for the next cycle. Read **`docs/development/release_ci_playbook.md`**
first — it holds the shared version model, the approval-gate policy, the
flake-vs-outage triage, zombie-run recovery, and the jj working-copy rules that
this skill leans on. That playbook is a **living document**: if you learn
something new during a cut, add it there and commit it in the same change.

The end state of a successful cut:

- `release/sculptor-vX.Y.0` exists at `X.Y.0rc1`, tag `sculptor-vX.Y.0rc1`
  pushed, RC build running and **parked at its approval gate** for the user.
- `main` bumped to `X.(Y+1).0.dev0` via a merged version-bump PR.

## Step 1 — Preflight

Confirm the ground is clean before touching anything (see the playbook's
"Working in this colocated jj + git repo" section):

```bash
jj st                                   # working copy should be clean/empty
git fetch origin main --tags
git rev-parse origin/main               # note the tip
cd sculptor && python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"; cd ..
```

- The version must be a `.dev0` (e.g. `0.44.0.dev0`). If it isn't, someone
  forgot to bump after the last release — stop and sort that out first.
- `cut-release` refuses a **detached HEAD** (the normal jj state). If `jj st` is
  clean/empty, `git checkout main`. If the working copy has unrelated changes,
  **preserve them first** — bookmark + `jj new` per the playbook — then
  `git checkout main`.

## Step 2 — Run the cut

```bash
just cut-release
```

This creates and pushes `release/sculptor-vX.Y.0` at `X.Y.0rc1`, pushes tag
`sculptor-vX.Y.0rc1` (triggering the RC build), and opens the `main`-bump PR to
`X.(Y+1).0.dev0` with squash auto-merge enabled. Capture the release version,
the RC tag, and the bump PR number from the output.

`cut-release` leaves git on the transient `automated/bump-sculptor-v*` branch.
Return to a sane state: `git checkout main` and let jj re-import.

## Step 3 — Land the version-bump PR

The bump PR has auto-merge armed; your job is to get it green (never to force
it). Follow the playbook's **flake-vs-outage triage** and **zombie-run**
sections:

- Check its required checks: `gh pr checks <bump_pr>`.
- Infra flake → `gh run rerun <run_id> --failed`, then let auto-merge land it.
- Several checks red at setup/infra steps at once → check `githubstatus.com`; if
  Actions is down, **back off and wait**, don't retry into an outage.
- Checks wedged as zombies after an outage → close/reopen the PR to get fresh
  runs (`gh pr close <n> && sleep 3 && gh pr reopen <n>`, then re-arm auto-merge).
- **Never admin-merge past a failing required check.** If it genuinely needs a
  bypass, refuse and hand it to the user.

`main` merges through a **merge queue**, so green checks are not the last step:
the PR still has to be enqueued, the queue re-runs the required workflows against
`main`, and a failure there **ejects** the PR silently — it goes back to looking
open and green. An enqueue can also be swallowed with no error at all when a
wedged `merge_group` run is still alive. Don't assume; check:

```bash
gh api repos/imbue-ai/sculptor/issues/<bump_pr>/timeline --paginate \
  -q '.[] | select(.event | test("queue")) | .event + " @ " + .created_at'
```

See the playbook's **"Merging through the merge queue"** for the queue-state
query and how to spot and clear a wedged run.

Confirm it landed and `origin/main` advanced to `X.(Y+1).0.dev0`:

```bash
gh pr view <bump_pr> --json state -q '.state'          # MERGED
git fetch origin main && git show origin/main:sculptor/pyproject.toml | grep -m1 '^version'
```

## Step 4 — Babysit the RC build to the approval gate

Find the run for the RC tag and poll it (playbook: "Polling a build"):

```bash
gh run list --workflow=build-desktop.yml --limit 5   # find the sculptor-vX.Y.0rcN run
```

Poll in a bounded background loop, breaking when the run **completes** or a
**pending deployment** appears:

```bash
gh run view <run_id> --json status,conclusion -q '.status + " / " + (.conclusion // "running")'
gh api repos/imbue-ai/sculptor/actions/runs/<run_id>/pending_deployments -q 'length'
```

- Build fails on an **infra flake / cancellation** → retry (`gh run rerun
  <run_id> --failed`, or a full `gh run rerun <run_id>` if a cancellation left
  partial artifacts).
- A red `linux-arm64` won't sink the RC: it is `allow-failure: true`, and the
  publisher skips a non-blocking target whose artifacts are missing. The RC just
  ships without that architecture — rerun the job if QA needs an arm64 build.
- Build is **wedged as a zombie** after an outage → don't fight it: cut a fresh
  RC with `just fixup-release` (bumps `rcN → rc(N+1)`) from the release branch.
  (To run it you must `git checkout release/sculptor-vX.Y.0` on a clean tree —
  preserve any stray working-copy work first, per the playbook.)
- Build reaches the **approval gate** (`pending_deployments` ≥ 1, job
  `release desktop (S3 publish + gh release)` = `waiting`) → **stop here.**

## Step 5 — Hand off at the gate

First **check what will ship** — `allow-failure` jobs report success to `needs`, so
the gate can open with a red `linux-arm64`:

```bash
gh run view <run_id> --json jobs -q '.jobs[] | .name + " -> " + (.conclusion // "—")'
```

Then report that the RC build is green and parked at the `release` environment
approval gate, and **do not approve it**. Per the playbook's approval policy:
surface it, show the user how to approve (UI **Review deployments**, or the
`gh api ... pending_deployments ... state=approved` command with the env id from
`pending_deployments`), and if they ask you to approve, gently push back once,
then comply if they insist.

After they approve, the RC publishes (S3 + a `prerelease` GitHub release). Next
in the release process: **QA the RC**, then `promote-release` (see the
`promote-release` skill).

## Before you finish

If this cut taught you anything the playbook didn't already cover — a new flake
signature, a new recovery step, a sharper command — **add it to
`docs/development/release_ci_playbook.md` (Field notes) and commit it.** You have
write access; the next person cutting a release inherits what you write down.
