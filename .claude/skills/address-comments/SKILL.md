---
name: address-comments
description: Apply CLAUDE:-prefixed comments from a pull request
disable-model-invocation: true
allowed-tools: Bash(gh:*), Bash(git:*), Glob, Grep, Read, Edit, Write
argument-hint: [pr-number]
---

# Apply PR Comments

Fetch comments from a pull request and apply all comments that are prefixed with "CLAUDE:".

## Instructions

1. Fetch the PR's comments via `gh` (see "Fetching comments" below). If a PR number is provided, use it. Otherwise, resolve the current branch's PR with `gh pr view --json number`.

2. Parse the output to find all comments (including discussion notes and inline code comments) that start with "CLAUDE:" (case-insensitive).

3. For each CLAUDE: comment found:
   - Read the referenced file (if it's an inline comment on a specific line)
   - Understand what change is being requested
   - Apply the requested change to the local codebase

4. **Important restrictions:**
   - Do NOT push any code
   - Do NOT reply to the comments on GitHub
   - Only make local changes

## Fetching comments

Fetch the PR's comments — both inline review comments and general discussion — with `gh`:

- Inline review comments: `gh api --paginate "repos/{owner}/{repo}/pulls/<N>/comments"` — each has `.body`, `.path`, and `.line` (or `.original_line`). `gh` substitutes `{owner}`/`{repo}` for the current repo.
- General discussion: `gh api --paginate "repos/{owner}/{repo}/issues/<N>/comments"`.

If a PR number was provided, use it; otherwise resolve the current branch's PR with `gh pr view --json number`.

**Important:** the comment JSON can be large and may get truncated — save it to a temp file first, then parse with `jq` in a **separate** command (not chained with `&&`) to avoid shell-parsing issues with the jq expression.

From the fetched comments, select those whose body starts with "CLAUDE:" (case-insensitive). For each, capture the body and — for inline comments — the file path and line. GitHub's REST comments have no resolved flag, so rely on the diff to see what's already done.

## Applying Changes

For each CLAUDE: comment:
1. Extract the instruction (everything after "CLAUDE:")
2. If it's an inline comment, note the file path and line number for context
3. Read the relevant file(s)
4. Apply the requested change
5. Move on to the next comment

Summarize all changes made at the end.
