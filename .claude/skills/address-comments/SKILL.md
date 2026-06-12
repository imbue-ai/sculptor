---
name: address-comments
description: Apply CLAUDE:-prefixed comments from a merge/pull request
disable-model-invocation: true
allowed-tools: Bash(glab:*), Bash(gh:*), Bash(git:*), Glob, Grep, Read, Edit, Write
argument-hint: [request-number]
---

# Apply MR/PR Comments

Fetch comments from a merge/pull request and apply all comments that are prefixed with "CLAUDE:".

## Instructions

1. Detect the hosting provider from `origin` and fetch the request's comments — see the `git-provider` skill. If a request number is provided, use it. Otherwise, use the current branch.

2. Parse the output to find all comments (including discussion notes and inline code comments) that start with "CLAUDE:" (case-insensitive).

3. For each CLAUDE: comment found:
   - Read the referenced file (if it's an inline comment on a specific line)
   - Understand what change is being requested
   - Apply the requested change to the local codebase

4. **Important restrictions:**
   - Do NOT push any code
   - Do NOT reply to the comments on the provider
   - Only make local changes

## Fetching comments

Fetch the request's comments — both inline review comments and general discussion. See the `git-provider` skill for the per-host command and the JSON fields (comment body, file path, line, and whether a resolved flag is available). If a request number was provided, use it; otherwise use the current branch.

**Important:** the comment JSON can be large and may get truncated — save it to a temp file first, then parse with `jq` in a **separate** command (not chained with `&&`) to avoid shell-parsing issues with the jq expression.

From the fetched comments, select those whose body starts with "CLAUDE:" (case-insensitive). For each, capture the body and — for inline comments — the file path and line. When the host exposes a resolved flag (see `git-provider`), skip resolved comments; they're assumed already applied. Otherwise rely on the diff to see what's already done.

## Applying Changes

For each CLAUDE: comment:
1. Extract the instruction (everything after "CLAUDE:")
2. If it's an inline comment, note the file path and line number for context
3. Read the relevant file(s)
4. Apply the requested change
5. Move on to the next comment

Summarize all changes made at the end.
