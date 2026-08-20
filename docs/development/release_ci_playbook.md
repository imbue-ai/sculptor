# Release CI Playbook

Shared operational knowledge for cutting and promoting Sculptor releases. The
`cut-release` and `promote-release` skills both point here so the hard-won
recovery lore lives in one place.

> **This is a living playbook.** Everyone who runs these skills can commit to
> this repo. When you hit a new failure mode, a new flake, or a better recovery
> step, **add it here in the same change** and commit it. A fix you keep in your
> head helps nobody; a fix you write down here helps the next person cutting a
> release. Prefer appending a short, dated bullet under "Field notes" over
> rewriting sections wholesale.

## The version model

`sculptor/pyproject.toml` `[project].version` drives everything. The builder CLI
(`uv run --project sculptor builder ...`, wrapped by `just` recipes in the root
`justfile`) does the arithmetic in `sculptor/sculptor/version.py`.

| State | Version shape | Where |
| --- | --- | --- |
| Active development | `X.Y.0.dev0` | `main` |
| Release candidate | `X.Y.0rcN` | `release/sculptor-vX.Y.0` |
| Promoted release | `X.Y.0` | `release/sculptor-vX.Y.0` (tagged) |
| Hotfix | `X.Y.(Z+1)` | `release/sculptor-vX.Y.(Z+1)` |

The `just` recipes and what they do:

- **`just cut-release`** — from `main` (or any branch at `origin/main`'s tip):
  creates `release/sculptor-vX.Y.0` at `X.Y.0rc1`, pushes tag
  `sculptor-vX.Y.0rc1` (this triggers the release build), and opens a PR bumping
  `main` to `X.(Y+1).0.dev0` with squash auto-merge enabled.
- **`just fixup-release`** — from the release branch: bumps `rcN → rc(N+1)`,
  commits, pushes tag `sculptor-vX.Y.0rc(N+1)` → a fresh RC build. This is the
  "the last RC build was bad / wedged, cut another" button.
- **`just promote-release`** — from the release branch: strips the `rcN` suffix
  (`X.Y.0rcN → X.Y.0`), commits, pushes tag `sculptor-vX.Y.0` → the production
  release build.
- **`just hotfix-release`** — from an already-promoted release branch: bumps the
  patch component to `X.Y.(Z+1)` and starts a new release branch for it.
- **`just bump-version`** — opens a manual `.dev0` version-bump PR on `main`.

A tag push matching `sculptor-v*` is what triggers `build-desktop.yml`. That
workflow runs under the `release-build` GitHub Environment for tag builds and
ends in a **manual approval gate** (the `release` environment) before it
publishes artifacts.

## The GitHub Actions approval gate

The final `release desktop (S3 publish + gh release)` job waits on the `release`
environment's required-reviewer rule. Polling shows up as a pending deployment:

```bash
# Is the run parked at the gate?
gh api repos/imbue-ai/sculptor/actions/runs/<run_id>/pending_deployments -q 'length'   # 0 = no gate / already approved
# Which environment, and can I approve?
gh api repos/imbue-ai/sculptor/actions/runs/<run_id>/pending_deployments \
  -q '.[] | "env=" + .environment.name + " id=" + (.environment.id|tostring) + " can_approve=" + (.current_user_can_approve|tostring)'
```

**Approval policy — do not approve the gate on the user's behalf.** Approving is
a human sign-off that the RC/release is good to publish. When running as a skill:

- **Never offer to auto-approve.** Surface that the gate is reached, then stop.
- If the user explicitly asks you to approve, **don't refuse** — but gently push
  back first (it's a real sign-off, not a rubber stamp; the artifacts go out).
  If they still want it, proceed.
- Show them how to do it themselves:
  - **UI:** open the run, click **Review deployments**, check `release`, **Approve and deploy**.
  - **CLI:** `gh api --method POST repos/imbue-ai/sculptor/actions/runs/<run_id>/pending_deployments -f 'environment_ids[]=<env_id>' -f state=approved -f comment='...'`

### Before you approve: check what will actually ship

`allow-failure` jobs report success to `needs`, so a run can reach the gate with a
red `linux-arm64` build. That doesn't break the publish — the publisher skips a
non-blocking target whose artifacts are missing — but it does mean that
architecture sits out the release. Look before handing the gate to a human:

```bash
# Every job's real conclusion (allow-failure reds show up here, not in `needs`)
gh run view <run_id> --json jobs -q '.jobs[] | .name + " -> " + (.conclusion // "—")'
```

If arm64 is red and you want it included, `gh run rerun <run_id> --failed` first —
otherwise say plainly which architectures the release will contain when you hand
off.

## Polling a build

```bash
# Find the run for a freshly pushed tag:
gh run list --workflow=build-desktop.yml --limit 5
# Status of a run:
gh run view <run_id> --json status,conclusion -q '.status + " / " + (.conclusion // "running")'
# Per-job breakdown (find the failing job + step):
gh run view <run_id> --json jobs -q '.jobs[] | .name + " -> " + .status + "/" + (.conclusion // "—")'
gh run view <run_id> --json jobs -q '.jobs[] | select(.conclusion=="failure") | .name + " :: " + ((.steps[]? | select(.conclusion=="failure") | .name) // "?")'
```

Poll in a bounded background loop (60s cadence), breaking when the run completes
**or** a pending deployment appears. `build-desktop.yml` sets
`cancel-in-progress: false`, so builds are never auto-cancelled — a stuck run is
stuck, not racing. Expect roughly **20–25 minutes** from tag push to the gate.

Ready-made loop — run it in the background rather than blocking on it:

```bash
RUN=<run_id>
for i in $(seq 1 70); do
  st=$(gh run view $RUN --json status,conclusion -q '.status + " / " + (.conclusion // "running")')
  pd=$(gh api repos/imbue-ai/sculptor/actions/runs/$RUN/pending_deployments -q 'length' 2>/dev/null || echo 0)
  echo "[$i] $(date -u +%H:%M:%S) status=$st pending=$pd"
  case "$st" in completed*) echo "RUN COMPLETED"; break;; esac
  [ "${pd:-0}" -ge 1 ] && { echo "GATE REACHED"; break; }
  sleep 60
done
```

When a run parks at the gate its `status` becomes `waiting` (not `completed`) —
that, plus `pending_deployments >= 1`, is the signal. Note also that a rerun of
only the failed jobs is much faster than the original build, because GitHub reuses
the already-green jobs instead of re-running them.

Finding your run: stale zombie runs can sit in `gh run list` as `queued`
indefinitely (one wedged RC run was still listed a week later). Match on the
tag/branch column, not on list position.

`linux-arm64` is non-blocking end to end: it is `allow-failure: true` in the build
and packaged-test matrices, and `publish-build-artifacts` skips any non-blocking
target whose artifacts are absent (`NON_BLOCKING_TARGETS` in
`sculptor/builder/artifacts.py`). A red arm64 build costs that one architecture and
nothing else — its previous artifacts stay in place, so arm64 Linux simply isn't
offered this update. Rerun the job if you want arm64 in the release. `linux-x64`
and `macos-arm64` are required and fail the run outright.

## Flake vs. outage: triage before you retry

When a required check fails, decide which world you're in **before** hammering
retries:

1. **Look at the failing step.** A failure in `Set up job`, runner acquisition
   ("job was not acquired by Runner of type hosted"), `Export AWS credentials`,
   `Export Modal credentials`, `Download build artifacts`, or a cache
   save/restore error is **infrastructure**, not your code — especially on a
   diff (like a version bump) that can't affect tests.
2. **When several independent required checks fail at once at setup/infra
   steps, suspect a platform incident.** Check GitHub's status:
   ```bash
   curl -s https://www.githubstatus.com/api/v2/components.json | \
     python3 -c "import sys,json; d=json.load(sys.stdin); [print(c['name'],'->',c['status']) for c in d['components'] if c['name']=='Actions']"
   curl -s https://www.githubstatus.com/api/v2/incidents/unresolved.json | \
     python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['incidents']),'unresolved'); [print('-',i['name'],'::',i['status']) for i in d['incidents']]"
   ```
   The status **page lags real recovery** — trust an empirical signal (a
   `Set up job` step actually succeeding) over the component color.

**Then act:**

- **Isolated flake** → retry to green, then let auto-merge take over:
  `gh run rerun <run_id> --failed` (or a full `gh run rerun <run_id>` when a
  cancellation left partial/inconsistent artifacts).
- **Active outage** → **back off and wait.** Retrying into an outage just burns
  attempts and muddies history; queued runs pick up on their own once capacity
  returns. Retry cadence during recovery can still hit residual infra flakes, so
  bound your retries and re-check that the failing step is still infra (and that
  another arch/job is passing) rather than assuming one retry restores green.
- **Genuine, reproducing failure on a non-infra step** → stop and escalate. Do
  not paper over a real red.

**Never admin-merge / force past a failing *required* check.** (Aspirational but
firm: we should never *need* to.) If a merge genuinely requires bypassing a
required check, **refuse and hand it back to the user to do by hand** — don't do
it for them.

Required checks on `main` come from the repo ruleset (currently `checks + unit
tests` and `offload integration tests`); confirm with:
```bash
gh api repos/imbue-ai/sculptor/rules/branches/main -q '.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
```

## Zombie runs after an outage

Runs that were **queued during** an incident can wedge into a limbo state: GitHub
refuses to cancel them (`gh run cancel` → "Cannot cancel a workflow run that is
completed") **and** refuses to rerun them (`gh run rerun` → "already running"),
and `gh run view` may disagree with itself about the status. They will not
self-heal. Don't fight them — **supersede** them:

- **`pull_request` checks (e.g. the version-bump PR):** close and reopen the PR
  to retrigger fresh runs with new IDs:
  ```bash
  gh pr close <n> && sleep 3 && gh pr reopen <n>
  gh pr merge <n> --auto --squash   # re-arm auto-merge
  ```
  The "strategy set by the merge queue" notice is expected — see
  "Merging through the merge queue", and verify the enqueue registered.
- **Tag-triggered release build:** you can't cheaply re-dispatch a tag build.
  Cut a fresh RC instead — **`just fixup-release`** (`rcN → rc(N+1)`) pushes a new
  tag and a new, healthy build. It costs one RC number and sidesteps the zombie.

## Merging through the merge queue

`main` merges via a GitHub **merge queue**, so `gh pr merge <n>` does not merge
anything — it *enqueues*. Two consequences worth internalising:

- **Your strategy flag is ignored.** `gh` prints
  `! The merge strategy for main is set by the merge queue` and the queue decides.
  Passing `--merge` does not guarantee a merge commit (though in practice a
  multi-commit PR has landed as its individual commits plus a merge commit).
- **The queue re-runs the required workflows against `main` + your PR**, as
  `merge_group` events on `gh-readonly-queue/main/pr-<n>-<sha>` refs. So a PR
  whose own checks are green can still fail in the queue, and every queue attempt
  spends another full CI cycle.

```bash
# Where am I in the queue?
gh api graphql -f query='{repository(owner:"imbue-ai",name:"sculptor"){mergeQueue{entries(first:20){nodes{position state pullRequest{number}}}}}}' \
  -q '.data.repository.mergeQueue.entries.nodes[] | "#" + (.pullRequest.number|tostring) + " pos=" + ((.position//0)|tostring) + " " + .state'
# The queue's own check runs:
gh run list --event merge_group --limit 5
```

State goes `QUEUED` → `AWAITING_CHECKS` → merged. If a queue check fails or times
out, the PR is **ejected** (`removed_from_merge_queue` by `github-merge-queue[bot]`)
and simply sits there open and green — nothing tells you. Re-queue with another
`gh pr merge <n>`.

**Always verify that an enqueue actually registered.** An enqueue can be silently
swallowed — no error, no queue entry, no timeline event — when a wedged
`merge_group` run from a previous attempt is still alive:

```bash
gh api repos/imbue-ai/sculptor/issues/<n>/timeline --paginate \
  -q '.[] | select(.event | test("queue")) | .event + " @ " + .created_at'
```

If your `added_to_merge_queue` event isn't there, you are not queued, however
confidently the UI or CLI implied otherwise. Look for a wedged run
(`gh run list --event merge_group`): the signature is `in_progress` well past the
job timeout with `updatedAt` frozen at its start time. `gh run cancel` may report
success and be ignored; cancelling again and re-queuing has cleared it.

## Working in this colocated jj + git repo

This repo is **colocated** (`.jj/` and `.git/` both exist) and normally sits on a
**detached git HEAD** under jj. The release recipes run `git checkout` internally
and need a **real git branch** with a **clean working tree**:

- `cut-release` refuses a detached HEAD → `git checkout main` first (safe only
  when `jj st` shows the working copy clean/empty).
- `fixup-release`/`promote-release` need to be on `release/sculptor-vX.Y.0` →
  `git checkout release/sculptor-vX.Y.0`.

**Preserve unrelated working-copy work before checking out.** If `jj st` shows
changes that aren't part of the release, don't discard them — bookmark and step
off so the git tree goes clean:

```bash
jj bookmark create wip-<name> -r @   # pin the work at a findable name
jj new                               # empty change on top → advances git_head, working tree is now clean
git status --short                   # should be empty
git checkout <target-branch>         # now safe
# recover later with: jj edit wip-<name>
```

After a recipe finishes it may leave git on a transient branch (e.g.
`automated/bump-sculptor-v*`). Return to a sane state with `git checkout main`
(or the release branch) and let jj re-import. Never discard work you didn't
create — surface it.

## Field notes

Append dated, specific learnings here. Keep them short.

- **2026-08-06/07 — GitHub Actions major outage mid-cut.** Runner acquisition
  failed ("job was not acquired by Runner of type hosted"), credential-export
  and cache steps flaked, and jobs queued during the incident wedged into the
  uncancellable-and-un-rerunnable zombie state. Recovery: waited for
  `githubstatus.com` Actions to return to operational, then superseded the
  zombies — close/reopen for the version-bump PR, `just fixup-release` (`rc1 →
  rc2`) for the release build. Both went green on healthy runners. Lesson:
  triage flake-vs-outage before retrying; the status page lags; supersede, don't
  fight, zombie runs.
- **2026-08-14 — an arm64 build flake, and the publisher bug it exposed
  (promoting 0.44.0).** `build linux-arm64` died 76s in on a transient uv download
  (`Failed to download viztracer`, `stream error received: unspecific protocol
  error detected`), preceded by `Cache service responded with 400`. At the time
  `publish-build-artifacts` demanded all three targets, so the run reached the gate
  looking green, the human approved, and the publish then hard-failed on the
  missing `AppImage/arm64/*` artifacts. **Nothing was published** — verification
  runs before any `s3_copy`, so there was no partial release and no GitHub release
  object. Recovery was `gh run rerun <run_id> --failed`, which rebuilt arm64 only
  (~10 min, since the green x64/macOS packaged tests were reused), then a second
  approval published cleanly. The publisher now skips a non-blocking target whose
  artifacts are absent, so a flaky arm64 build can no longer waste an approval;
  what remains is that a red arm64 means that architecture sits out the release.
- **2026-08-14 — two alarming-but-normal outputs from `just promote-release`.**
  It prints `Releasing Sculptor <old rcN version> from git sha ...` — a stale
  `pyproject_version()` read taken before the bump; the version actually released
  is the stripped one. The tag push prints `Bypassed rule violations for
  refs/tags/sculptor-vX.Y.0: Cannot create ref due to creations being restricted`
  — also expected, but it reveals a real prerequisite: **you need tag-creation
  bypass on the repo ruleset**, or the promotion dies at the push.
- **2026-08-14 — release branches get abandoned; don't infer the target from the
  newest branch.** 0.41 and 0.43 were both cut and never promoted, so production
  went 0.42.0 → 0.44.0 directly. The reliable signal for "which RC is real" is a
  published `rcN` prerelease in `gh release list` — that means its build went green
  *and* a human approved its gate. This also sets the release-notes range: it
  starts at the prior **promoted** tag, which may be several minors back.
- **2026-08-20 — a wedged `merge_group` run silently swallowed an enqueue.** A PR
  was ejected from the merge queue after its queue checks hung, and the follow-up
  enqueue produced **no `added_to_merge_queue` timeline event and no error** — it
  simply never queued, while the PR sat open and `CLEAN`. The blocker was the
  previous attempt's `checks` run, still `in_progress` 2h30m later (job timeout is
  1h) with `updatedAt` frozen at its start time; `gh run cancel` returned success
  and the run ignored it. After cancelling it again and re-queuing, the same PR
  merged in ~9 minutes on the first try. Lesson: after any `gh pr merge`, confirm
  the enqueue registered before you start waiting on it.
- **2026-08-20 — `jj git push --deleted` is not scoped to the bookmark you just
  deleted.** It pushes *every* pending bookmark deletion, so cleaning up one
  merged branch also deleted an unrelated stale branch from the remote (harmless
  in that instance — already merged — but not intended). Push a specific deletion
  with `jj git push -b <bookmark>` instead, or check what is pending first.
