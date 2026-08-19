---
name: promote-release
description: |
  Promote a QA'd Sculptor release candidate to a full production release: verify
  the RC build is green and has been QA'd, then from the release branch run
  `just promote-release` (which strips the rcN suffix, commits X.Y.0, and pushes
  the sculptor-vX.Y.0 tag that triggers the production build) and babysit that
  build up to its manual approval gate. Handles the colocated jj + git working
  copy and the CI flake/outage/zombie recovery playbook. Stops AT the approval
  gate — never approves it for you. Use when asked to "promote a release",
  "ship the release", or turn an RC into the real release.
argument-hint: "[release-version, e.g. 0.44] (optional; inferred from the release branch)"
---

# Promote a Sculptor Release

Turn a release candidate on `release/sculptor-vX.Y.0` into the promoted `X.Y.0`
release. Read **`docs/development/release_ci_playbook.md`** first — the version
model, approval-gate policy, flake-vs-outage triage, zombie recovery, and jj
working-copy rules all live there and this skill depends on them. That playbook
is a **living document**: anything new you learn promoting a release goes back
into it in the same change.

**Gate before you start:** promotion publishes the real thing. Confirm the RC
build for the current `rcN` went **green and was actually QA'd** before running
anything here. If it wasn't QA'd, stop and get that done first.

## Step 0 — Work out what to promote

Don't assume the newest release branch is the one to ship. Branches get cut and
abandoned: 0.41 and 0.43 were both cut and never promoted, so production went
0.42.0 → 0.44.0 directly.

```bash
git fetch origin --tags --prune
git branch -r --list 'origin/release/*' | sort -V | tail -5    # candidate branches
git tag -l 'sculptor-v*' --sort=-v:refname | head              # rcN tags
gh release list --limit 10                                     # what actually shipped
```

Read those together:

- The branch to promote is the one whose **`rcN` prerelease appears in
  `gh release list`**. That publication is proof the RC build went green *and* a
  human approved its gate — stronger evidence than "the build was green".
- The newest non-prerelease (`Latest`) entry is what production runs today.
- A release branch with no published prerelease was abandoned; leave it alone.

## Step 1 — Get onto the release branch, clean

`promote-release` runs `git checkout`-based checks and needs a **real git
branch** (`release/sculptor-vX.Y.0`) with a **clean tree** — not the usual jj
detached HEAD.

```bash
jj st                                   # working copy clean/empty?
git fetch origin release/sculptor-vX.Y.0
git checkout release/sculptor-vX.Y.0
cd sculptor && python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"; cd ..   # expect X.Y.0rcN
```

If `jj st` shows unrelated working-copy work, **preserve it first** (bookmark +
`jj new`, per the playbook) before the checkout — never discard it.

Sanity checks the recipe also enforces, worth confirming yourself:

- You're on `release/sculptor-vX.Y.0` and the version is an `rcN` pre-release.
- The branch is **not behind** its upstream:
  ```bash
  git fetch --prune && git status --porcelain=2 --branch | grep '^# branch.ab'
  ```
  If behind, pull/rebase before promoting.

## Step 2 — Promote

```bash
just promote-release
```

This strips the pre-release suffix (`X.Y.0rcN → X.Y.0`), commits the version on
the release branch, and pushes tag `sculptor-vX.Y.0` — which triggers the
production release build. Capture the release version and tag from the output.

Two outputs look wrong but are normal (playbook field notes, 2026-08-14):

- `Releasing Sculptor <old rcN version> from git sha ...` — a stale
  `pyproject_version()` echo. The version actually released is the stripped one.
- `Bypassed rule violations for refs/tags/... creations being restricted` on the
  tag push. Expected — but it means you need **tag-creation bypass** on the repo
  ruleset; without it the promotion fails right here.

## Step 3 — Babysit the production build to the approval gate

Same polling and recovery as an RC build (playbook: "Polling a build",
"Flake vs. outage", "Zombie runs"):

```bash
gh run list --workflow=build-desktop.yml --limit 5    # find the sculptor-vX.Y.0 run
gh run view <run_id> --json status,conclusion -q '.status + " / " + (.conclusion // "running")'
gh api repos/imbue-ai/sculptor/actions/runs/<run_id>/pending_deployments -q 'length'
```

- Infra flake / cancellation → retry (`gh run rerun <run_id> --failed`, or a
  full rerun after a cancellation).
- A red `linux-arm64` is survivable: it is `allow-failure: true`, and the publisher
  skips a non-blocking target whose artifacts are missing. The release ships
  without that architecture — rerun the job if you want arm64 included.
- Outage → check `githubstatus.com`, back off, don't retry into it.
- **Never admin-merge / force a bad required check.** Refuse and hand back.
- Gate reached (`pending_deployments` ≥ 1, run `status` = `waiting`, `release
  desktop (S3 publish + gh release)` = `waiting`) → verify, then **stop.**

Note: if the production build is unrecoverable but the RC was fine, promotion
isn't the place to cut a new RC — that's `fixup-release` on the RC side. A
promoted release that later needs patching uses `just hotfix-release` (see the
playbook's version model).

## Step 4 — Verify at the gate, then hand off

Check what will actually ship before handing it over — `allow-failure` jobs report
success to `needs`, so the gate can open with a red `linux-arm64`:

```bash
gh run view <run_id> --json jobs -q '.jobs[] | .name + " -> " + (.conclusion // "—")'
```

Then report that the build is parked at the `release` environment approval gate,
and **do not approve it.** Per the playbook: surface it, give the user the run URL
plus the env id, show them how to approve themselves (UI **Review deployments**, or
the `gh api ... pending_deployments ... state=approved` command), and if asked to
approve, push back gently once, then comply if they insist.

If arm64 is red, rerun it first when you want that architecture in the release —
and either way, tell the user which architectures this release will contain.

## Step 5 — After they approve

Confirm the publish actually landed; don't trust the job status alone:

```bash
gh run view <run_id> --json conclusion -q .conclusion             # success
gh release view sculptor-vX.Y.0 --json isPrerelease,isDraft       # false / false
curl -s https://imbue-sculptor-releases.s3.amazonaws.com/slim/AppImage/x64/latest-linux.yml | grep '^version:'
```

That last one matters most — the auto-update manifests are the channel that
actually reaches users. (A release with **0 assets is normal**: artifacts live in
S3 and the release body just links them.)

Follow-ups this skill does **not** do:

- **Release notes** (`write-release-notes`). The range starts at the prior
  *promoted* tag, which may be several minors back — 0.44.0's notes had to cover
  0.42.0 → 0.44.0 because 0.43 never shipped. Scoping to the previous release
  *branch* silently drops half of what users are receiving. The release body is
  pipeline boilerplate (title + `## Assets`); splice notes in **above** `## Assets`
  and preserve that block verbatim, via
  `gh release edit <tag> --notes-file <file>`. Do **not** sign a published product
  changelog `(Sent by Claude)` — CLAUDE.md's transparency rule targets PR, issue,
  and chat messages, not user-facing release copy.
- **`update-help-docs`** for the release (run it from the release branch).
- **Linear** hygiene for the tickets that shipped.
- Slack needs nothing: the pipeline posts to `#sculptor-release` automatically on
  a successful publish.

## Before you finish

Learned something the playbook doesn't cover? **Add it to
`docs/development/release_ci_playbook.md` (Field notes) and commit it** in the
same change. You have write access — write it down for the next promoter.
