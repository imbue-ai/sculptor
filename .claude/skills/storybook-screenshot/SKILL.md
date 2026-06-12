---
name: storybook-screenshot
description: |
  Launch the Storybook dev server and use Playwright to take screenshots of
  component stories. Use when you need visual verification of UI component
  designs or want to iterate on a component's appearance.
---

# Storybook Screenshot

This skill describes how to start the Storybook dev server, then use Playwright
to navigate to specific component stories and take screenshots.

## CRITICAL: What NOT To Do

**DO NOT** use any of these approaches:
- Running `npm run storybook` as a foreground Bash command — it runs forever
  and will block Claude indefinitely
- Using shell backgrounding (`&`) with `$!` — PID tracking is unreliable
  across Bash tool calls

## Prerequisites

- `node_modules/` must exist in `sculptor/frontend/`
- The `src/api/` generated types must exist (Storybook strips the
  `generate-types` vite plugin, so they must be pre-generated)

If `node_modules/` doesn't exist, install dependencies first:

```bash
cd sculptor/frontend
npm install
```

If `src/api/` doesn't exist, generate it first:

```bash
cd sculptor/frontend
npm run generate-api
```

## Step 1: Set up environment

Create a unique log file and determine the workspace screenshots directory.
The workspace root is the parent of `code/` (which is your current working
directory). Screenshots go in `attachments/screenshots/` within that workspace
root.

```bash
LOG_FILE=$(mktemp)
WORKSPACE_ROOT=$(cd "$(pwd)/.." && pwd)
SCREENSHOTS_DIR="$WORKSPACE_ROOT/attachments/screenshots"
mkdir -p "$SCREENSHOTS_DIR"
echo "Log file: $LOG_FILE"
echo "Screenshots will be saved to $SCREENSHOTS_DIR"
```

Note the `LOG_FILE` and `SCREENSHOTS_DIR` paths for the next steps.

**Why mktemp?** Variable expansion like `$$` behaves unreliably in background
shell execution. Using a separate foreground `mktemp` call is more robust.

## Step 2: Start Storybook as a background process

Use the Bash tool with **`run_in_background: true`**, using the log file from
Step 1:

```json
{
  "command": "cd sculptor/frontend && npm run storybook:headless 2>&1 | tee <LOG_FILE>",
  "run_in_background": true,
  "description": "Start Storybook dev server in background"
}
```

This returns a **task_id** that you need for killing the server later.

## Step 3: Wait for readiness and extract the port

Wait **5 seconds**, then check the log file for the "ready" message:

```bash
tail -10 <LOG_FILE>
```

Look for output containing the local URL (e.g., `http://localhost:6006/`).
If not ready yet, wait another 5 seconds and check again. Repeat up to
6 times (30 seconds total). Storybook typically starts within 10–15 seconds.

**Extract the port from the log output.** Storybook defaults to port 6006 but
will pick a different port if 6006 is busy. Parse the actual port from the URL
in the log (e.g., `Local: http://localhost:6007/`) and use it as
`STORYBOOK_PORT` in all subsequent steps. Do NOT hardcode port 6006.

If the log shows an error (e.g., compilation failure), stop the background
process with `TaskStop` using the task_id and investigate.

**IMPORTANT**: Do NOT use `TaskOutput` for monitoring — it returns all
cumulative output and will fill your context. Always use `tail` to see only
recent output.

## Step 4: Write a Playwright screenshot script

Save all screenshots and videos to `$SCREENSHOTS_DIR` (set up in Step 1).
This is the `attachments/screenshots/` directory inside the workspace root.

Write a Python script to `/tmp/storybook_screenshots.py` that navigates to
story iframe URLs and takes screenshots:

```python
"""Take screenshots of Storybook component stories."""

import time
from playwright.sync_api import sync_playwright

STORYBOOK_URL = "http://localhost:<STORYBOOK_PORT from step 3>"
SCREENSHOTS_DIR = "<SCREENSHOTS_DIR from step 1>"

def story_iframe_url(story_id: str, theme: str = "light") -> str:
    """
    Build the iframe URL for a story.

    story_id format: "{kebab-title}--{kebab-variant}"
    e.g., "custom-askuserquestion--single-question"
         "radix-button--default"
    """
    return f"{STORYBOOK_URL}/iframe.html?id={story_id}&globals=theme:{theme}&viewMode=story"

def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        page.goto(story_iframe_url("custom-askuserquestion--single-question", theme="dark"))
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/askuserquestion_dark.png")

        browser.close()

if __name__ == "__main__":
    main()
```

## Step 5: Run the Playwright script

Run the script as a **foreground** command (it completes quickly, unlike the
server):

```bash
.venv/bin/python3 /tmp/storybook_screenshots.py
```

The `.venv/` is at the repo root (`code/.venv/`), not under `sculptor/`.

## Step 6: Display results in chat

After taking a screenshot or recording a video, display it inline in the chat
by outputting an `<img>` or `<video>` tag with the absolute path. Only absolute
local file paths (starting with `/`) are supported — HTTP URLs will not be
rendered.

Examples:
```
<img src="/absolute/path/to/attachments/screenshots/component.png" alt="component screenshot">
```

```
<video src="/absolute/path/to/attachments/screenshots/recording.webm" controls></video>
```

## Step 7: Clean up

Kill the Storybook background process using `TaskStop` with the task_id from
Step 2.

**Always clean up**, even if the screenshot step failed.

## Story ID format

Story IDs are derived from the `title` and export name in the `.stories.tsx`
file. The conversion is: lowercase, slashes and spaces become hyphens, two
hyphens separate the story title from the variant name.

| Story file title | Export name | Story ID |
|---|---|---|
| `Custom/AskUserQuestion` | `SingleQuestion` | `custom-askuserquestion--single-question` |
| `Custom/AskUserQuestion` | `MultiSelect` | `custom-askuserquestion--multi-select` |
| `Custom/AskUserQuestion` | `MultipleQuestions` | `custom-askuserquestion--multiple-questions` |
| `Custom/AskUserQuestion` | `NoDismiss` | `custom-askuserquestion--no-dismiss` |
| `Custom/Panels/DockingLayout` | `Default` | `custom-panels-dockinglayout--default` |
| `Custom/Tabs/TabBar` | `Default` | `custom-tabs-tabbar--default` |
| `Radix/Button` | `Default` | `radix-button--default` |
| `Radix/Dialog` | `Default` | `radix-dialog--default` |

To discover all available story IDs, fetch the Storybook index (use the port
from Step 3):

```bash
curl -s http://localhost:<STORYBOOK_PORT>/index.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for story_id in sorted(data['entries'].keys()):
    entry = data['entries'][story_id]
    if entry['type'] == 'story':
        print(story_id)
"
```

## Common patterns

### Screenshot all variants of a component

```python
VARIANTS = [
    "custom-askuserquestion--single-question",
    "custom-askuserquestion--multi-select",
    "custom-askuserquestion--multiple-questions",
    "custom-askuserquestion--minimal",
    "custom-askuserquestion--no-dismiss",
]

for variant in VARIANTS:
    for theme in ["light", "dark"]:
        page.goto(story_iframe_url(variant, theme=theme))
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        name = variant.split("--")[1]
        page.screenshot(path=f"{SCREENSHOTS_DIR}/{name}_{theme}.png")
```

### Clip to just the component (no surrounding padding)

```python
page.goto(story_iframe_url("custom-askuserquestion--single-question"))
page.wait_for_load_state("networkidle")
# Find the story root element and clip to its bounding box
element = page.locator("#storybook-root").first
element.screenshot(path=f"{SCREENSHOTS_DIR}/component_only.png")
```

### Screenshot at a specific viewport size

```python
context = browser.new_context(viewport={"width": 800, "height": 600})
```

### Video recording

```python
context = browser.new_context(
    viewport={"width": 800, "height": 700},
    record_video_dir=SCREENSHOTS_DIR,
    record_video_size={"width": 800, "height": 700},
)
page = context.new_page()
# ... navigate and interact ...
context.close()  # Video is finalized when context closes
```

## Gotchas

- **Use the iframe URL, not the full Storybook shell**: The iframe URL
  (`/iframe.html?id=...`) renders just the component without the Storybook
  chrome (sidebar, toolbar). This gives cleaner screenshots. The full shell
  URL is `/?path=/story/{id}` but it includes the Storybook UI.

- **`src/api/` must be pre-generated**: The Storybook vite config explicitly
  strips the `generate-types` plugin to avoid needing the Python backend.
  If the `src/api/` directory is missing, stories that import from `~/api`
  will fail to compile. Run `npm run generate-api` from `sculptor/frontend/`.

- **Wait after `networkidle`**: Some components use CSS transitions or async
  rendering. Add a `time.sleep(1)` after `wait_for_load_state("networkidle")`
  to let animations settle before screenshotting.

- **Always kill the server when done**: The Storybook process runs
  indefinitely. Always use `TaskStop` to clean up, even if the script fails.
