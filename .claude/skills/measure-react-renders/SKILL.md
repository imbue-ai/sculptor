---
name: measure-react-renders
description: |
  Compare React component render counts between origin/main and the current
  branch during a user-defined UI scenario (e.g. panel resize, navigation).
  Use when verifying that performance changes actually reduced re-renders.
argument-hint: <scenario-file>
---

# Render Performance Comparison

## Step 1: Create the baseline worktree

```bash
git fetch origin main
git worktree add /tmp/sculptor_baseline origin/main
cd /tmp/sculptor_baseline/sculptor/frontend && npm install --silent
```

## Step 2: Write the scenario file

If the user provides one, use it. Otherwise write a Python file exporting:

- `DESCRIPTION: str` — what is being measured
- `TARGET_COMPONENTS: list[str]` — component names to highlight
- `setup(page, base_url, workspace_id, task_id)` — navigate + wait
- `action(page)` — perform the action to measure

Component names must be **unminified** source names (e.g. `AlphaChatInterfaceInner`
if the export is memo-wrapped, `AlphaChatInterface` if not).

See `scenarios/panel_resize.py` for an example.

## Step 3: Run the comparison

```bash
uv run --project sculptor python \
  .claude/skills/measure-react-renders/scripts/perf_compare.py \
  --baseline-dir /tmp/sculptor_baseline \
  --current-dir "$(pwd)" \
  --scenario path/to/scenario.py
```

Use `--skip-build` if frontends are already built.

The script builds both frontends with `--minify false` (preserves component
names), starts two isolated backends, injects `__REACT_DEVTOOLS_GLOBAL_HOOK__`
via Playwright's `addInitScript` before React loads, runs the scenario, and
prints a comparison table.

## Step 4: Cleanup

```bash
git worktree remove /tmp/sculptor_baseline
```

## Scenario example

```python
import time

DESCRIPTION = "Panel resize render cascade"
TARGET_COMPONENTS = ["AlphaChatInterface", "DiffSplitContainer", "ZoneContent"]

def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

def action(page):
    handles = page.locator('[role="separator"]').all()
    handle = handles[-1]
    handle.focus()
    time.sleep(0.3)
    for _ in range(5):
        page.keyboard.press("ArrowLeft")
        time.sleep(0.15)
    for _ in range(5):
        page.keyboard.press("ArrowRight")
        time.sleep(0.15)
```
