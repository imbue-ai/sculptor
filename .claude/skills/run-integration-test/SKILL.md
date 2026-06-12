---
name: run-integration-test
description: |
  Run Sculptor integration tests. MUST be used whenever:
  - Running tests in sculptor/tests/integration/
  - User asks to "run integration tests" or "run the tests" for integration test files
  - Using pytest on integration test files

  DO NOT run pytest directly for integration tests - use this skill instead.
  Tests must run as background processes with a Monitor watchdog.
---

# Sculptor Integration Test Runner

## What NOT To Do

- `uv run pytest` directly — use `just test-integration` so the test harness wraps it correctly.
- `TaskOutput` on the test task — returns all cumulative output and can blow context. Use `tail` on the log file at the end instead.
- Polling with repeated `sleep N && tail` — let Monitor wake you on completion or timeout.

## The Pattern

Run the test in the background with a completion marker appended to its log. Arm a `Monitor` with an until-loop that trips on the marker, with `timeout_ms` sized from the ladder below. On each Monitor timeout, check the log: if still progressing, re-arm with the next rung; if stale, kill.

### Step 1: Create a unique log file

```bash
mktemp -t integration-test
```

Note the returned path. The rest of the steps reference it as `<LOG>`.

### Step 2: Launch the test in background with a completion marker

```json
{
  "command": "( just test-integration sculptor/tests/integration/path/to/test.py 2>&1; echo \"JUST_COMPLETED: $?\" ) > <LOG> 2>&1",
  "run_in_background": true,
  "description": "Run integration test in background"
}
```

The subshell + `echo "JUST_COMPLETED: $?"` guarantees the log ends with a marker on any exit. Monitor watches for that marker. Note the returned **task_id** — you need it to kill a real hang.

**Multiple test files must be quoted as a single argument** to `just test-integration`:

```
( just test-integration "sculptor/tests/integration/a.py sculptor/tests/integration/b.py" 2>&1; echo "JUST_COMPLETED: $?" ) > <LOG> 2>&1
```

### Step 3: Arm the Monitor watchdog at rung 1

```json
{
  "command": "until grep -q \"JUST_COMPLETED:\" <LOG> 2>/dev/null; do sleep 3; done; echo \"TEST_COMPLETED\"",
  "description": "integration test completion watcher",
  "timeout_ms": <RUNG_1_MS>,
  "persistent": false
}
```

### Step 4: On Monitor event

**`TEST_COMPLETED` (or the test task's completion notification)** → go to Step 5.

**`[Monitor timed out — re-arm if needed.]`** → NOT necessarily a hang. Tail the log:

```bash
tail -30 <LOG>
```

Note: the tee'd `<LOG>` shows the `just` wrapper output, which prints the `.just-logs/test-integration-*.log` path — tail that file for actual pytest progress.

- **Fresh output** — new lines since your last look, or recent timestamps — the test is progressing. Re-arm Monitor with the **next rung** in the ladder and wait again.
- **Stale** — no new content since last check → genuine hang. `TaskStop` the task from Step 2, then go to Step 5 to inspect partial output.

If you exhaust the ladder (rung 3 trips) without completion, treat it as hung regardless of apparent progress — something is consuming the budget. `TaskStop` and report.

### Step 4b: Timeout ladder

Start small, grow up. Each rung's wake-up is both a hang backstop and a progress check.

| Scope                      | Rung 1   | Rung 2   | Rung 3     |
|----------------------------|----------|----------|------------|
| Single test function       | 60_000   | 180_000  | 600_000    |
| Single test file (default) | 120_000  | 300_000  | 900_000    |
| Multi-file suite           | 300_000  | 600_000  | 1_800_000  |

Why a ladder? Most runs complete at rung 1, giving you a fast wake-up. Slow tests get more time only when they've earned it by showing progress. A single giant timeout hides all of this.

### Step 5: Read results

`just` writes pytest output to `.just-logs/test-integration-<timestamp>.log`. Tail the newest:

```
Bash: ls -t .just-logs/test-integration-*.log | head -1 | xargs tail -30
```

Look for the `N passed` / `N failed` summary. The tee'd `<LOG>` only contains wrapper output and the `JUST_COMPLETED:` marker — useful for the exit code, not pytest details.

## Example (normal completion)

```
1. Bash: mktemp -t integration-test
   → /var/folders/.../integration-test.b5N49YB3VL

2. Bash (run_in_background: true):
     ( just test-integration sculptor/tests/integration/frontend/test_homepage.py 2>&1; echo "JUST_COMPLETED: $?" ) > /var/folders/.../integration-test.b5N49YB3VL 2>&1
   → task_id="b7q6lny77"

3. Monitor (timeout_ms: 120000):
     until grep -q "JUST_COMPLETED:" /var/folders/.../integration-test.b5N49YB3VL 2>/dev/null; do sleep 3; done; echo "TEST_COMPLETED"
   → task_id="bl7ca3bqd"

4. Event "TEST_COMPLETED" arrives at ~90s.

5. Bash: ls -t .just-logs/test-integration-*.log | head -1 | xargs tail -30
   → "============================= 10 passed in 27.40s =============================="
```

## Example (slow test — ladder climb)

```
3.  Monitor rung 1 (120000ms). Times out.
4.  Tail .just-logs — latest file mtime 4s ago, new lines since last check.
    → progressing. Re-arm Monitor rung 2 (300000ms).
4b. Event "TEST_COMPLETED" arrives at ~240s.
5.  Tail summary.
```

## Example (true hang)

```
3.  Monitor rung 1 (120000ms). Times out.
4.  Tail .just-logs — latest file mtime 2m ago, no new content.
    → hang. TaskStop task_id="b7q6lny77".
5.  Tail partial log for diagnosis.
```

## Why this shape

- `run_in_background` keeps the conversation unblocked.
- The `JUST_COMPLETED:` marker is a file-level signal that works uniformly across test files, independent of pytest config.
- `Monitor`'s `timeout_ms` is the single source of truth for each rung's ceiling. No external `gtimeout`/`timeout` needed.
- The ladder gives you early wake-ups (fast feedback when the test finishes quickly) AND a generous final ceiling (avoids killing legitimately slow tests), with a progress check between rungs to distinguish slow from stuck.
- One `tail` at the end keeps context clean.
