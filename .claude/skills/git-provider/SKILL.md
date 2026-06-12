---
name: git-provider
description: |
  Reference for interacting with the git hosting provider (GitLab via `glab`
  or GitHub via `gh`) in a provider-agnostic way. Detect the provider from the
  `origin` remote, then use the matching CLI/API and field names. Consult this
  whenever a skill or task needs to view/create/diff a merge request or pull
  request, post review comments, or call the host's API.
user-invocable: false
---

# Git provider reference

Skills should not assume a specific git host. Detect the provider from the
`origin` remote and use the matching CLI. This skill is the single source of
truth for that mapping so individual skills don't hardcode provider specifics.

> **Scope:** this skill covers MR/PR operations and the host API. It does
> **not** cover CI/pipelines — that tooling is not yet provider-agnostic.

## Detect the provider from `origin`

```bash
ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
case "$ORIGIN_URL" in
  *gitlab*) PROVIDER="gitlab" ;;   # use glab
  *github*) PROVIDER="github" ;;   # use gh
  *)        PROVIDER="unknown" ;;  # e.g. a local filesystem path (Sculptor clone mode)
esac
```

Notes:
- **Self-hosted** GitLab / GitHub Enterprise may live on a custom host that does
  not contain `gitlab`/`github` in the URL. If detection returns `unknown` but a
  provider CLI is clearly authenticated, prefer asking the user rather than
  guessing.
- In some Sculptor workspaces `origin` points at a **local filesystem path**
  (clone mode), not a hosted URL. In that case `PROVIDER=unknown` and there is
  no MR/PR to act on — surface this to the user instead of erroring out.

## Derive host / owner / repo from the remote

Handles both SSH (`git@host:group/project.git`) and HTTPS
(`https://host/group/project.git`):

```bash
case "$ORIGIN_URL" in
  git@*)        HOST="${ORIGIN_URL#git@}"; HOST="${HOST%%:*}"
                REPO_PATH="${ORIGIN_URL#*:}"; REPO_PATH="${REPO_PATH%.git}" ;;
  http://*|https://*)
                REST="${ORIGIN_URL#*://}"; HOST="${REST%%/*}"
                REPO_PATH="${REST#*/}"; REPO_PATH="${REPO_PATH%.git}" ;;
esac
# REPO_PATH is "group/project" (GitLab) or "owner/repo" (GitHub).
```

Never hardcode the project path or a numeric project ID — derive them here.

Once you know the provider, use the matching section below. The two sections
share the same sub-headers so a consumer reads only the one for its host.

## GitLab (`glab`)

### Commands

- View MR as JSON: `glab mr view [N] -F json`
- Diff: `glab mr diff [N]`
- Create: `glab mr create --target-branch <B>`
- Edit title / body: `glab mr update --title <T> [--description <D>]`
- List: `glab mr list`
- Merge: `glab mr merge [N]`
- Raw API: `glab api <path>`
- Authenticated user: `glab api user`

### JSON fields

- Number / ID: `.iid`
- Title: `.title`
- Description: `.description`
- Target branch: `.target_branch`
- Source branch: `.source_branch`
- Head commit SHA: `.sha`
- Web URL: `.web_url`
- State: `.state` (`opened` / `merged` / `closed`)

### Pushed head ref

Fetch the exact pushed head from `merge-requests/<iid>/head`:

```bash
git fetch origin "merge-requests/${NUMBER}/head:refs/remotes/origin/mr/${NUMBER}"
```

### Fetching comments

`glab mr view [N] -c -F json --per-page 200` returns a `.Notes[]` array. Each
note has `.body` and a `.resolved` flag; inline comments also carry
`.position.new_path` and `.position.new_line`. Skip resolved notes — they're
assumed already addressed.

### Auth

`GITLAB_TOKEN` (the REST API expects `Authorization: Bearer <token>`). `glab`
commands use the CLI's own auth.

### Terminology

Merge requests (**MRs**), referenced as `!123`, keyed by `.iid`.

## GitHub (`gh`)

### Commands

- View PR as JSON: `gh pr view [N] --json number,title,body,baseRefName,headRefName,headRefOid,url,state`
- Diff: `gh pr diff [N]`
- Create: `gh pr create --base <B>`
- Edit title / body: `gh pr edit [N] --title <T> [--body <D>]`
- List: `gh pr list`
- Merge: `gh pr merge [N]`
- Raw API: `gh api <path>`
- Authenticated user: `gh api user`

### JSON fields

- Number / ID: `.number`
- Title: `.title`
- Description: `.body`
- Target branch: `.baseRefName`
- Source branch: `.headRefName`
- Head commit SHA: `.headRefOid`
- Web URL: `.url`
- State: `.state` (`OPEN` / `MERGED` / `CLOSED`)

### Pushed head ref

Fetch the exact pushed head from `pull/<number>/head`:

```bash
git fetch origin "pull/${NUMBER}/head:refs/remotes/origin/pr/${NUMBER}"
```

### Fetching comments

Inline review comments: `gh api --paginate "repos/{owner}/{repo}/pulls/<N>/comments"`
— each has `.body`, `.path`, and `.line` (or `.original_line`). General
discussion: `gh api --paginate "repos/{owner}/{repo}/issues/<N>/comments"`.
`gh` substitutes `{owner}`/`{repo}` for the current repo. REST comments have no
resolved flag — rely on the diff to see what's already addressed.

### Auth

`GH_TOKEN`, or an authenticated `gh auth login`. `gh` commands use the CLI's own
auth.

### Terminology

Pull requests (**PRs**), referenced as `#123`, keyed by `.number`.

## General notes

- **MR/PR titles, descriptions, and review comments are published — write them as world-readable.** Keep out PII, internal-only references, customer data, and security-sensitive detail (see CLAUDE.md, "Public Visibility: Commit Messages and PR Descriptions").
- Prefer the CLI (`glab` / `gh`) over raw `curl` — both pick up the CLI's own auth.
- Use the provider's own term (MR vs PR) in user-facing output.
- Comment/listing JSON can be large and may truncate — save it to a temp file, then parse with `jq`.
