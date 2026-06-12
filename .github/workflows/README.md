# Workflow security rules

Everything under `.github/` is owned by `@imbue-ai/sculptor-maintainers`
(CODEOWNERS) and `main` requires code-owner review, so a maintainer reviews
every change to these workflows. When you review or write one, enforce these
rules — they exist to stop a fork PR from exfiltrating secrets once the repo is
public.

## 1. Privileged triggers must not run PR-authored code

`pull_request_target`, `workflow_run`, and `issue_comment` workflows run in the
**base repo** with secrets and a read/write `GITHUB_TOKEN`. If such a workflow
checks out and runs code from the PR (build, test, install scripts, a published
action at the PR ref), the PR author's code runs **with our secrets** — the
classic "pwn request."

- **Do not** add `actions/checkout` of the PR branch/ref (or run PR scripts) in
  a `pull_request_target` / `workflow_run` workflow.
- These workflows should only do trusted, code-independent work: label, comment,
  open/close, gate. See [`pr-gate.yml`](pr-gate.yml) and
  [`approve-contributor.yml`](approve-contributor.yml) — both act purely through
  the API and check out nothing.
- If you genuinely need PR contents under a privileged trigger, check out a
  pinned base SHA only, never execute PR code, and get a second maintainer's
  review.

## 2. Fork PRs must never run on self-hosted runners

A forked PR runs untrusted code. On a `self-hosted` runner that code executes on
**our** hardware — reachable to Vault, the cloud metadata endpoint
(`169.254.169.254`), and our network — even though GitHub withholds secrets and
OIDC from forks.

- Any job on a self-hosted runner (e.g. `offload-runner`) that triggers on
  `pull_request` must guard against forks:
  ```yaml
  if: >-
    github.event_name != 'pull_request' ||
    github.event.pull_request.head.repo.full_name == github.repository
  ```
  See [`offload.yml`](offload.yml).

## 3. Don't rely on `pull_request` secret access for forks

Fork `pull_request` runs get a read-only token and **no secrets/OIDC** — that's
the safe default. Don't try to work around it (e.g. by moving secret-dependent
steps to `pull_request_target`). If a check needs secrets, it shouldn't run on
untrusted fork PRs at all.

## 4. Never interpolate `${{ }}` into a `run:` script body

`${{ }}` is substituted as raw text *before* the shell parses the line, so an
attacker-influenced value can inject shell commands — and unlike the rules
above, this fires even under trusted `push` / tag / `workflow_dispatch`
triggers. Risky values include `github.head_ref`, `github.ref_name`, an issue/PR
title or body, and commit author fields (git refnames legitimately allow
`` $ ; | & ( ) ` `` and quotes).

- Pass the value through `env:` and reference it as a quoted shell variable, so
  the runner hands it to the shell as data, never as script text:
  ```yaml
  - env:
      REF: ${{ github.ref_name }}   # data assignment — safe
    run: do-something "$REF"        # quoted shell variable — safe
  ```
- Do **not** write `run: do-something "${{ github.ref_name }}"` — the value is
  pasted into the script and evaluated by the shell.
- The hole reopens one layer down: a `just`/`make`/script wrapper that
  re-interpolates its arguments unquoted re-introduces it. Quote at every
  boundary (`just`'s `quote()`, shell `"$@"`).

## 5. approve-contributor needs Actions PR-creation enabled

[`approve-contributor.yml`](approve-contributor.yml) opens the allowlist PR
with the workflow's `GITHUB_TOKEN`. GitHub blocks Actions-created PRs by
default, so enable **Settings → Actions → General → "Allow GitHub Actions to
create and approve pull requests"** — without it the `pulls.create` call fails
with HTTP 403. (Repos can also enable it via
`PUT /repos/{owner}/{repo}/actions/permissions/workflow` with
`can_approve_pull_request_reviews: true`.)

## 6. Repo-level backstop (set at the public flip)

Turn on **Settings → Actions → General → "Require approval for all outside
collaborators"** so no fork-PR workflow runs until a maintainer clicks
"Approve and run." This is only configurable once the repo is public; track it
with the public-flip settings mirror (SCU-1391).
