# Implement Task

You are implementing a single task from an implementation plan. Read
the task file, do the work it describes, verify, self-review, and
commit. Then move on to the next task.

This file describes the per-task process. It is re-applied to every
task in the plan, so you re-read it at the start of every task.

## CRITICAL: No pre-existing failures

There is no such thing as a "pre-existing failure." If the configured
pre-commit checks (per `.sculptor/code.md`'s *Pre-commit Verification*
section) or any end-to-end test fails, you MUST fix it before
committing — even if you believe the failure existed before your
changes. ALL failures are your responsibility.

## Steps

1. **Read the task file** at `$TASK_FILE`. This file is
   self-contained — it has everything you need: goal, requirements
   addressed, background, files to modify, implementation details,
   testing suggestions, gotchas, and verification checklist.

2. **Read the files listed** in the task's *Files to modify/create*
   and *Background* sections. Understand the existing code before
   making changes.

3. **Implement the task** following the implementation details in the
   task file. Key rules:
   - Follow the patterns and conventions described in the task file.
   - All imports at the top of the file, no inline imports, no
     relative imports.
   - Complete type hints on all public functions.
   - Do not add unnecessary comments, docstrings, or abstractions
     beyond what the task requires.
   - Some tasks may not produce code changes (e.g. tasks that spawn
     another agent or run verification only). The task file will say
     so explicitly. Follow what it says.

4. **Run verification** — mandatory, not optional. Use the commands
   listed in `.sculptor/code.md`'s *Pre-commit Verification* section:
   - Run the check command (whatever combination of format, lint,
     typecheck, and project-specific static checks the config
     lists). If it fails, fix and re-run. Keep iterating until it
     passes.
   - Run the unit-test command. Fix failures. Iterate until green.
   - Run any specific end-to-end tests listed in the task's
     verification checklist. If `.sculptor/testing.md` names a skill
     for running end-to-end tests (in *Test Writing* or *Test
     Debugging*), use it — don't run end-to-end tests directly when
     a skill exists. Iterate until green.
   - Keep fixing and re-running until everything passes. Only report
     failure if you hit a hard blocker that you genuinely cannot
     resolve (e.g. a missing dependency, a fundamental design
     contradiction).

5. **Walk through the verification checklist** in the task file.
   Confirm each item passes.

6. **Self-review your diff** before committing:
   - Run `git diff` to see all your staged and unstaged changes.
   - Check for: missed requirements from the task, bugs, security
     issues (injection, XSS, hardcoded secrets), dead code, leftover
     debug statements.
   - Fix anything you find and re-run the pre-commit verification.

7. **Commit the changes** with a descriptive message. If the task
   produced no changes (e.g. a task that spawns an agent, or
   verification passed with no code edits needed), **do not make an
   empty commit** — skip the commit and report success without one.

   ```bash
   git add -A  # stage everything from this task
   # Skip the commit if nothing is staged:
   if git diff --cached --quiet; then
     echo "Task <task #>: no changes to commit"
   else
     git commit -m "$(cat <<'EOF'
   Task <task #>: <one-line of what this task accomplished>

   <detailed report of what this task accomplished>

   Co-authored-by: Sculptor <sculptor@imbue.com>
   EOF
   )"
   fi
   ```

## Reporting back

When you're done with the task, report one of:

- **Success (committed):** `Task <X.Y> completed. Commit: <hash>. All verification passed.`
- **Success (no commit):** `Task <X.Y> completed. No changes to commit. All verification passed.` — use this when the task was about spawning an agent, running verification, or otherwise didn't produce code changes.
- **Failure:** Use your question tool — `mcp__sculptor__ask_user_question` if it's available, otherwise the built-in `AskUserQuestion` — to surface the failure (it raises the "waiting for input" status that alerts the user): what went wrong, what you tried, and options for the user.

Do not include full test output in your report — just summarize the
result.

## Do not

- Modify files outside the scope of this task.
- Skip any verification steps.
- Commit if verification is failing.
- **Make an empty commit.** If `git diff --cached` is empty after
  staging, do not commit.
- Make architectural decisions that contradict the task file — if
  something seems wrong, surface it to the user with your question tool rather than improvising.
