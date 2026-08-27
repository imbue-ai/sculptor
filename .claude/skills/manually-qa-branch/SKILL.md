---
name: manually-qa-branch
description: |
  Test a pull request by creating a shallow clone at the PR's commit and launching Sculptor.
  Use when you need to test changes from a specific PR in isolation.
---

# Test Pull Request

This skill allows you to test a pull request by creating a shallow clone of the repository at the PR's commit and launching the Sculptor app. It uses the `gh` CLI to fetch the PR's details (requires authenticated `gh` — `gh auth login` or `GH_TOKEN`).

## Usage

```
/manually-qa-branch <NUMBER>
```

Examples:
- `/manually-qa-branch 1234` - Test pull request 1234

## What This Skill Does

1. Fetches the PR details via `gh`
2. Gets the source branch and latest commit SHA from the request
3. Clones/updates the repository in a well-known cache directory at that specific commit
4. Runs `uv sync` to sync dependencies
5. Runs `just install` to install the project (reuses build cache from previous PR tests)
6. Launches `just start` **in the background** so the user can manually test the app
7. **Immediately** runs an automatic code review of the PR diff via the
   `/code-review-checklist` skill — in parallel with the user's manual testing —
   and presents findings as a markdown table

## Implementation Steps

When this skill is invoked, follow these steps:

### Step 1: Parse the PR number
Extract the PR number from the argument, removing any leading "#" if present.

### Step 2: Fetch the PR details
Fetch the PR as JSON:

```bash
gh pr view <NUMBER> --json number,title,body,baseRefName,headRefName,headRefOid,url,state
```

From it you need:

- source branch — `.headRefName`
- head commit SHA — `.headRefOid`
- target branch — `.baseRefName`
- title — `.title`
- description — `.body`
- PR URL — `.url`

Compute the **diff base** for the post-test review locally as
`git merge-base <TARGET_BRANCH> <SHA>` after Step 7 fetches the target branch.

### Step 3: Use a well-known cache directory
Use a consistent cache directory to preserve build artifacts across PR tests:
```bash
CACHE_DIR="$HOME/.cache/sculptor-mr-testing"
```

This directory will be reused for all PR tests, keeping the build cache warm.

### Step 4: Clone or update the repository at the specific commit
If the cache directory doesn't exist, create it and do an initial clone. Derive
the clone URL from the current repo's `origin` rather than hardcoding a host:
```bash
if [ ! -d "$CACHE_DIR" ]; then
  git clone "$(git remote get-url origin)" "$CACHE_DIR"
fi
```

Then fetch and checkout the specific commit:
```bash
cd "$CACHE_DIR"
git fetch origin "+refs/heads/<SOURCE_BRANCH>:refs/remotes/origin/<SOURCE_BRANCH>"
git checkout <SHA>
```

Note: This approach reuses the same directory, so `just install` can reuse build caches from previous PR tests.

### Step 5: Setup the environment
Run the following commands in sequence:
```bash
cd "$CACHE_DIR"
uv sync
just install
```

### Step 6: Launch Sculptor in the background

**CRITICAL**: Launch `just start` as a **background** process (`run_in_background: true`
on the Bash tool). Do NOT block on it. The whole point of this skill is for
the agent to run a code review **in parallel** with the user's manual testing —
if you wait for `just start` to exit, the user will be stuck waiting for the
review until they stop the app.

You MUST also unset several environment variables before launching to avoid
port conflicts and authentication issues:

```bash
env -u SESSION_TOKEN -u SCULPTOR_API_PORT -u SCULPTOR_FRONTEND_PORT just start
```

> **Testing the onboarding flow?** Plain `just start` seeds a dev config and
> skips the welcome flow, landing straight in the app — ideal for QAing the PR's
> feature. To walk the full first-run/onboarding flow instead, swap `just start`
> for `just start-onboard` (alias `just source`) in the command above. Both exist
> only on branches that include the fast-QA `just start` change; on older
> branches `just start` still shows onboarding.

Run that command via the Bash tool with `run_in_background: true`. Note the
shell ID returned — you'll use it later to check on the app if needed.

After launching, briefly tell the user the app is starting up and that you're
beginning the code review in parallel. Then proceed immediately to Step 7 — do
NOT poll, sleep, or ask the user to confirm anything.

Why these env vars must be unset:
- **SESSION_TOKEN**: The tmux backend starts without SESSION_TOKEN (no auth required). The Electron app generates its own SESSION_TOKEN. If SESSION_TOKEN is inherited from the parent shell, it causes a mismatch and 403 errors.
- **SCULPTOR_API_PORT / SCULPTOR_FRONTEND_PORT**: The parent Sculptor process sets these to the ports it's currently using (e.g. 49325). If they leak into the PR's `just start`, the PR's backend will try to bind to the same port as the production app, fail with "address already in use", and the Electron app will connect to the wrong (production) backend — causing CORS and auth errors. Unsetting them lets the justfile use its own defaults (1224 / 5173), which won't conflict.

### Step 7: Run the code review in parallel

Immediately after launching the app in the background, run a code review of
the PR diff while the user is manually testing.

1. Make sure the target branch is fetched in the cache directory so the diff
   base is available locally:
   ```bash
   cd "$CACHE_DIR"
   git fetch origin "+refs/heads/<TARGET_BRANCH>:refs/remotes/origin/<TARGET_BRANCH>"
   ```

2. Invoke the `/code-review-checklist` skill via the Skill tool. Pass the
   following context to it:
   - **Working directory**: `$CACHE_DIR` (the cloned request checkout)
   - **Diff range**: `<BASE_SHA>...<SHA>` where `<BASE_SHA>` is
     `git merge-base <TARGET_BRANCH> <SHA>` and `<SHA>` is the request head SHA
   - **Stated goal**: the request title and description, plus the request URL
     for reference

   Example invocation message to the skill:
   ```
   Please review this PR.

   - PR: <NUMBER> — <TITLE>
   - URL: <URL>
   - Working directory: <CACHE_DIR>
   - Diff: git diff <BASE_SHA>...<SHA>

   Request description:
   <DESCRIPTION>
   ```

3. The skill will produce a markdown findings table followed by a short
   summary. Present its output directly to the user — do not edit or
   summarize it further.

4. After presenting the review, tell the user:
   - The Sculptor app is still running in the background for them to keep testing
   - The request checkout is at `$CACHE_DIR` if they want to dig deeper
   - They can stop the app whenever they're done

## Important Notes

- This skill requires authenticated `gh` access (`gh auth login` or `GH_TOKEN`)
- The clone is created in `$HOME/.cache/sculptor-mr-testing` and reused across PR tests for fast build times
- The `just start` command will block until the user stops the app (Ctrl+C)
- After the app is stopped, inform the user that they can find the PR code at `$HOME/.cache/sculptor-mr-testing`
- The cached directory can be manually deleted with `rm -rf ~/.cache/sculptor-mr-testing` if needed


## Error Handling

- If `gh` is not authenticated, tell the user to set it up with `gh auth login`
- If the PR number is not found, display a helpful error message
- If fetching the PR fails, show the error and suggest checking the PR number and network connection
- If `origin` is not a hosted remote (e.g. a local filesystem path), there is no PR to fetch — tell the user this skill needs a hosted remote
- If git clone fails, it might be because the branch was deleted - inform the user
