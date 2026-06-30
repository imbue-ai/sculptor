---
name: auto-qa-changes
description: |
  Launch Sculptor in a headless browser and interact with the UI via an HTTP
  API. Send commands via curl, get screenshots back, and visually inspect the
  result — like a human QA tester. Use when you need visual verification of
  UI changes, manual testing of features, or end-to-end testing with real Claude.
---

# Manual Testing with Live Browser Control

This skill launches Sculptor's backend with a headless Chromium browser and
serves an HTTP API for interactive control. You send commands via `curl`,
get screenshots back, and reason about what to do next — like a human QA
tester with programmatic precision.

The browser starts on the home page. Navigate to whatever page you need by
clicking buttons — just like a real user.

## Prerequisites

- The venv must have `playwright` installed (it already does in this repo)
- Chromium browser for Playwright must be installed
- Node.js and npm (for the Vite dev server)

## Quick Start

### Step 1: Determine the screenshots directory

```bash
WORKSPACE_ROOT=$(cd "$(pwd)/.." && pwd)
SCREENSHOTS_DIR="$WORKSPACE_ROOT/attachments/screenshots"
mkdir -p "$SCREENSHOTS_DIR"
echo "Screenshots: $SCREENSHOTS_DIR"
```

### Step 2: Start the live browser server

Launch the server as a **background process**. The server auto-allocates
a free port for the HTTP control API and prints it to the log:

```bash
# IMPORTANT: Use nohup to fully detach the server process.
# Do NOT use run_in_background — its 10-minute timeout will kill the server.
SERVER_LOG="$SCREENSHOTS_DIR/manual-test-server.log"
SERVER_PIDFILE="$SCREENSHOTS_DIR/manual-test-server.pid"
nohup uv run --project sculptor python -m sculptor.testing.manual_test_server \
  --screenshots-dir "$SCREENSHOTS_DIR" > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$SERVER_PIDFILE"
echo "Server PID: $SERVER_PID (saved to $SERVER_PIDFILE)"
```

Wait for the server to start, then read the control port from the log:

```bash
# Poll until the control port is printed to the log
for i in $(seq 1 60); do
  PORT=$(grep -o 'MANUAL_TEST_CONTROL_PORT=[0-9]*' "$SERVER_LOG" | head -1 | cut -d= -f2)
  if [ -n "$PORT" ]; then
    echo "Control port: $PORT"
    break
  fi
  sleep 2
done

# Then poll until the server is ready
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:$PORT/status 2>/dev/null | grep -q '"success"'; then
    echo "Server ready!"
    break
  fi
  sleep 2
done
```

### Step 3: Dismiss onboarding (if visible)

A fresh Sculptor instance shows an onboarding modal that blocks the home
page. Take a screenshot first — if you see the onboarding modal, dismiss it:

```bash
# Check if onboarding is visible
RESULT=$(curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "locate", "selector": "[data-testid=ONBOARDING_WELCOME_STEP]"}')
ELEMENTS=$(echo "$RESULT" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('elements',[])))")

if [ "$ELEMENTS" -gt 0 ]; then
  # Click through: email input -> submit -> complete
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "locate", "selector": "[data-testid=ONBOARDING_EMAIL_INPUT]"}'
  # Click the email input and type a test email
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "click", "x": <x>, "y": <y>}'
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "type", "text": "test@test.com"}'
  # Locate and click "Get Started"
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "locate", "selector": "[data-testid=ONBOARDING_EMAIL_SUBMIT]"}'
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "click", "x": <x>, "y": <y>}'
  # Locate and click the final complete button
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "locate", "selector": "[data-testid=ONBOARDING_COMPLETE_BUTTON]"}'
  curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "click", "x": <x>, "y": <y>}'
  echo "Onboarding dismissed"
fi
```

Replace `<x>` and `<y>` with coordinates from each `locate` response.
If no onboarding modal appears, skip this step.

### Step 4: Interact with the browser

Every command returns a JSON response with a `screenshot` field containing
the absolute path to a PNG. **Display the screenshot to the user with an
`<img>` tag** using the absolute file path as the `src`:

```
<img src="/absolute/path/to/screenshot.png" alt="Description of UI state">
```

This is the ONLY way to show images in the chat. The `<img>` tag must use
an absolute local file path as the `src` attribute. HTTP URLs will not render.

**Do not Read the screenshot yourself to inspect it — see "Context
management" below.** The `<img>` tag renders on the user's side without
loading the image into your context; the Read tool pulls the full PNG into
your context, and a few 2x retina screenshots will blow it out.

## Context management: never Read screenshots directly

Screenshots are 2x retina PNGs at viewport size — each one is large, and a
testing session produces dozens. **Never call the Read tool on a screenshot
yourself.** Reading even a handful of them will blow out your context
window long before the session ends.

Three rules:

1. **Display to the user via `<img>` tag.** This is free for your context —
   the tag renders on the user's side; no image data enters your context.
2. **Verify state programmatically when you can.** `locate`, `wait`,
   `wait_for_hidden`, and `/status` are enough to confirm "did the modal
   open?", "is the button there?", "is the agent done?" without any pixel
   inspection. Prefer them.
3. **When you genuinely need visual inspection** (alignment, what text
   appeared, whether a panel shows the expected content), **delegate to a
   subagent** with a narrow question:

   ```
   Agent(
     description="Describe screenshot",
     prompt="Read /path/to/screenshots/0012_get.png. Focus on the right
             panel: is the Agent Tasks panel open, are there at least two
             todo items visible, and does the first one show a green
             checkmark? Answer in 3-4 sentences."
   )
   ```

   The subagent's text response comes back to you; the image stays in the
   subagent's context and is discarded when it returns.

Describe-this-screenshot subagents are cheap. Use one per check. Never
batch a "look at all these screenshots" prompt — that just moves the
context blowout to the subagent.

## Available Actions

All actions interact with the browser the same way a real user would —
clicking, typing, scrolling, hovering, and dragging. There are no shortcuts
that bypass the UI.

### Take a screenshot

```bash
curl -s http://127.0.0.1:$PORT/screenshot | python3 -c "import json,sys; print(json.load(sys.stdin)['screenshot'])"
```

Display the screenshot to the user via an `<img>` tag. Do not Read it
yourself — delegate visual inspection to a subagent (see "Context
management" below).

### Click at coordinates

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "click", "x": 450, "y": 320}'
```

### Double-click

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "double_click", "x": 450, "y": 320}'
```

### Type text

Types into whatever element currently has focus:

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "type", "text": "Hello world"}'
```

### Press a key

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "press", "key": "Enter"}'
```

### Hover

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "hover", "x": 450, "y": 320}'
```

### Scroll

```bash
# Scroll down by 300px (negative delta_y = scroll down)
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "scroll", "delta_y": -300}'
```

### Drag

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "drag", "from_x": 100, "from_y": 200, "to_x": 300, "to_y": 200}'
```

### Restart the application

Stops and restarts the Sculptor backend and Vite dev server while preserving
the browser, database, config, and repository. Use this to test persistence-
related features — e.g., verifying that data survives a shutdown/restart cycle.

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "restart"}'
```

After restart, the browser navigates to the freshly started application. The
screenshot in the response shows the home page after the restart completes.
The database, config files, and git repo are preserved — only the backend
and frontend processes are recycled.

### Resize viewport

For testing responsive layouts at different screen sizes:

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "resize", "width": 800, "height": 600}'
```

### Locate an element

Find the coordinates of elements **without** bypassing the UI. Use this
instead of guessing coordinates from screenshots — screenshots may render
at a different size than the actual 1400x900 viewport.

By CSS selector:

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "locate", "selector": "[data-testid=SEND_BUTTON]"}'
```

By visible text:

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "locate", "text": "hello.txt"}'
```

Returns a list of matching elements with their center coordinates:

```json
{
  "success": true,
  "screenshot": "/path/to/screenshots/0005_locate.png",
  "elements": [
    {"x": 450, "y": 320, "width": 80, "height": 24, "text": "hello.txt"}
  ]
}
```

Then click the element using the returned coordinates:

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "click", "x": 450, "y": 320}'
```

### Wait for an element to appear

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "wait", "id": "CHAT_PANEL", "timeout": 15000}'
```

### Wait for an element to disappear

```bash
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "wait_for_hidden", "id": "THINKING_INDICATOR", "timeout": 30000}'
```

### Get page status

```bash
curl -s http://127.0.0.1:$PORT/status
```

## Waiting for the agent to finish

After submitting a prompt, the agent may take seconds to minutes to complete.
**Do NOT guess when it's done.** Use `wait_for_hidden` with the
`THINKING_INDICATOR` test ID:

```bash
# Wait up to 6 minutes for the agent to finish
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "wait_for_hidden", "id": "THINKING_INDICATOR", "timeout": 360000}'
```

If you need to poll with progress updates instead of a single blocking call:

```bash
for i in $(seq 1 120); do
  RESULT=$(curl -s -X POST http://127.0.0.1:$PORT/execute \
    -d '{"action": "wait_for_hidden", "id": "THINKING_INDICATOR", "timeout": 3000}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('success','false'))")
  if [ "$RESULT" = "True" ] || [ "$RESULT" = "true" ]; then
    echo "Agent finished!"
    break
  fi
  echo "Still thinking... ($i)"
done
```

**Agent state test IDs** (useful for `wait` and `wait_for_hidden`):

| Test ID | When visible |
|---------|-------------|
| `THINKING_INDICATOR` | Agent is running (thinking, streaming, or calling tools) |
| `STOP_BUTTON` | Agent is running (click to interrupt) |
| `STATUS_PILL_LABEL` | Shows current state text: "Thinking...", "Streaming...", "Calling tools...", or "" when idle |

## Testing Workflow

### How to navigate

Navigate the UI the same way a user would — by clicking buttons:

1. Use `locate` to find elements by their visible text or CSS selector
2. Use `click` with the returned coordinates
3. Use `wait` if you need to wait for a page transition to complete
4. Repeat

For example, to navigate to settings: locate the settings icon, click it,
and wait for the settings page to load.

### CRITICAL: Narrated visual walkthrough protocol

**Every visual testing session MUST be narrated as a step-by-step walkthrough
that the user can follow along with.** This serves three purposes:

1. The user can watch your progress in real-time and intervene if needed
2. The screenshots + narration become proof-of-work for MR descriptions
3. The narration forces careful visual inspection at each step

**For EVERY screenshot you take, you MUST:**

1. **Display the screenshot** to the user with an HTML `<img>` tag using the
   absolute file path as `src`. This is the ONLY way the user can see images.
   Example: `<img src="/path/to/screenshots/0001_get.png" alt="Home page">`
2. **Describe what you see** — layout, visible elements, state of the UI.
   **Do not Read the image yourself to get this description.** Either infer
   state from the `locate`/`wait`/`status` responses you already have, or —
   when you need pixel-level detail — delegate to a subagent (see "Context
   management" above) and paraphrase its answer.
3. **Call out any issues** — visual bugs, misalignments, unexpected states
4. **Announce your next action** — what you're about to click/type and why

**WARNING:** The `<img>` tag is the only way the user sees images. Do not
substitute a Read call for it — Read pulls the PNG into your context (bad)
without showing anything to the user (also bad).

**Format each step like this:**

```
<img src="/absolute/path/to/screenshots/0001_screenshot.png" alt="Home page - empty state">

**Step 1: Home page (empty state)**
I see the home page with "No workspaces yet" centered in the content area.
The top bar shows the home icon, "+" button, search, settings gear, and help
icon. Spacing and alignment look correct. The dark theme renders cleanly with
no visual artifacts.

No issues found.

**Next:** I'll click the "+" button to open the workspace creation form.
```

**Do NOT skip screenshots.** Do NOT batch multiple actions without showing
the result of each one. The user should be able to reconstruct your entire
testing session from the output alone.

### Naming screenshots for MR reuse

Give screenshots descriptive `alt` text so they're useful when attached to
MRs later. Good alt text describes the page state, not the action:

- Good: `alt="Workspace creation form with prompt filled in"`
- Good: `alt="Settings page - keybindings section at 800px viewport"`
- Bad: `alt="screenshot"` or `alt="step 3"`

### What to look for

Prioritize in this order — a functionality bug always trumps a cosmetic nit.

#### Tier 1: Functionality

Does the feature actually work?

- **Actions produce results**: Clicking buttons, submitting forms, navigating
  links — does the expected thing happen?
- **Data appears correctly**: Are lists populated? Do values match what was
  entered? Are counts accurate?
- **Error handling**: What happens with invalid input, empty fields, or network
  errors? Does the UI show a helpful message or silently fail?
- **State transitions**: After an action, does the UI update? (e.g., after
  creating a workspace, does it appear in the list? After agent finishes,
  does "Thinking..." disappear?)
- **Navigation**: Can you get to every page? Does the back button work?
  Do deep links load the right view?

#### Tier 2: Visual correctness

Does it look right?

- **Alignment**: Are controls lined up? Are labels aligned with their inputs?
  Are icons vertically centered with adjacent text?
- **Spacing**: Is padding/margin consistent between similar elements? Compare
  spacing in repeated items (e.g., list rows, card grids) — inconsistency
  is easy to spot.
- **Text rendering**: Is any text clipped, truncated unexpectedly, or
  overflowing its container? Are long values (filenames, commit messages)
  handled gracefully with ellipsis or wrapping?
- **Color & contrast**: Do colors match the dark theme? Is text readable
  against its background? Are selected/active states visually distinct from
  unselected?
- **Borders & dividers**: Are section boundaries clear? Are there missing or
  extra separator lines?
- **Responsive layout**: Use the `resize` action to test at smaller viewports
  (e.g., 800x600). Do panels collapse or stack correctly? Does anything
  overflow or become unreachable?
- **Overlapping elements**: Are any controls hidden behind other elements?
  Check especially around dropdowns, modals, and floating panels.

#### Tier 3: Polish & edge cases

The difference between "it works" and "it's good."

- **Hover & focus states**: Do interactive elements change appearance on hover?
  Is focus visible for keyboard navigation? Use the `hover` action to test.
- **Empty states**: Do empty lists, panels, or search results show a helpful
  message instead of blank space?
- **Loading states**: Are spinners or skeletons shown during async operations?
  Or does the UI feel frozen?
- **Transitions & animations**: Do elements appear/disappear smoothly, or do
  they pop in jarringly?
- **Keyboard interaction**: Can you Tab through controls? Does Enter submit
  forms? Do keyboard shortcuts work?
- **Scroll behavior**: Does content scroll when it should? Is scroll contained
  to the right panel, or does the whole page scroll unexpectedly?

You do not need to check every item on every screenshot — focus on what's
relevant to the current view. But always describe what you see before moving
on. When reporting issues, note the tier so the reader can prioritize.

### Example: Full narrated visual test session

Here's how a visual test session should look in the chat output. Each step
shows the screenshot, describes the UI, and announces the next action.

**Step 1:** Take the initial screenshot.

```bash
curl -s http://127.0.0.1:$PORT/screenshot
```

Then display it with an `<img>` tag (if you need a description beyond what
`locate`/`status` already told you, delegate to a subagent per "Context
management"):

```
<img src="/path/to/screenshots/0001_get.png" alt="Home page - no workspaces">

**Step 1: Home page (empty state)**
The home page shows "No workspaces yet" with a folder icon. The top bar has
the home icon (active), "+" button, and right-side icons (search, settings,
help). Layout is centered and clean.

**Next:** I'll locate and click the "+" button to create a new workspace.
```

**Step 2:** Locate the "+" button and click it.

```bash
# Find the button's coordinates
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "locate", "selector": "[data-testid=ADD_WORKSPACE_BUTTON]"}'
# Click at the returned coordinates
curl -s -X POST http://127.0.0.1:$PORT/execute \
  -d '{"action": "click", "x": 72, "y": 52}'
```

Then display it with an `<img>` tag (if you need a description beyond what
`locate`/`status` already told you, delegate to a subagent per "Context
management"):

```
<img src="/path/to/screenshots/0003_click_72_52.png" alt="Workspace creation form">

**Step 2: Workspace creation form**
The "Create new workspace" form is showing. I can see:
- Workspace name input (placeholder: "Untitled workspace (optional)...")
- Prompt input area (placeholder: "Enter a prompt (optional)...")
- Repo selector showing "manual_test_repo"
- Branch selector showing "testing"
- Model dropdown showing "Opus"
- Blue submit arrow button at bottom right

Form layout looks correct. All controls are visible and properly spaced.

**Next:** I'll click the workspace name input and type a name.
```

**Step 3:** Continue with the next action, and so on for every step.

### Summary at the end

After completing your visual testing, write a brief summary:

```
## Visual Testing Summary

**Pages tested:** Home page, workspace creation form, settings page
**Viewport sizes tested:** 1400x900 (default), 800x600
**Issues found:**
- [Issue description, with screenshot reference]
- None found (if clean)

**Screenshots saved to:** /path/to/screenshots/
These screenshots can be attached to the MR description.
```

## Displaying screenshots to the user

**CRITICAL:** To show a screenshot to the user, you MUST output an HTML
`<img>` tag in your text response. This is the ONLY method that works:

```
<img src="/absolute/path/to/attachments/screenshots/0001_get.png" alt="Home page - empty workspace list">
```

- The `src` MUST be an **absolute local file path** (starting with `/`)
- HTTP URLs will NOT render
- Do NOT Read the image to inspect it — that pulls a large PNG into your
  context and does not show anything to the user. Delegate inspection to a
  subagent (see "Context management") if `locate`/`status` isn't enough.
- Always include descriptive `alt` text for reuse when sharing

Screenshots are saved to `$SCREENSHOTS_DIR`.

## Useful test IDs

These `data-testid` attributes can be used with `locate` and `wait`/`wait_for_hidden`.
Use `locate` to find coordinates, then `click` to interact:

| Test ID | Element |
|---------|---------|
| `TASK_BUTTON` | Task item in the sidebar |
| `TASK_INPUT` | New task prompt input on home page |
| `START_TASK_BUTTON` | Create task button |
| `WORKSPACE_NAME_INPUT` | Workspace name input field |
| `CHAT_INPUT` | Message input in chat |
| `SEND_BUTTON` | Send message button |
| `CHAT_PANEL` | The chat message area |
| `ADD_WORKSPACE_BUTTON` | "+" button to create new workspace |
| `WORKSPACE_TAB` | Workspace tab in tab bar |
| `WORKSPACE_ROW` | Workspace row in home list |
| `MODEL_SELECTOR` | Model dropdown selector |
| `HOME_BUTTON` | Home navigation button |
| `SETTINGS_SIDEBAR` | Settings page sidebar |
| `COMPACTION_BAR` | Context remaining bar at bottom |
| `COMPACTION_PANEL` | The popover from the context bar |
| `CLEAR_CONTEXT_BUTTON` | Clear Context button in popover |
| `CONTEXT_SUMMARY` | Collapsed context summary message |
| `CONTEXT_SUMMARY_HEADER` | Clickable header to expand summary |
| `ONBOARDING_WELCOME_STEP` | Onboarding modal (if visible) |
| `ONBOARDING_EMAIL_INPUT` | Email field in onboarding |
| `ONBOARDING_EMAIL_SUBMIT` | "Get Started" button |
| `ONBOARDING_COMPLETE_BUTTON` | Final onboarding button |
| `THINKING_INDICATOR` | Pulsing dot + "Thinking..." (visible while agent runs) |
| `STOP_BUTTON` | Stop button (visible while agent runs) |
| `STATUS_PILL_LABEL` | Agent state label (alpha view): "Thinking...", "Streaming...", "" |

Full list of test IDs is in `sculptor/sculptor/constants.py` (the `ElementIDs` enum).

## Additional options

### `--project-path /path/to/repo`

By default the server creates a small test git repository. Pass
`--project-path` to point Sculptor at a real repository instead.

## Gotchas

- **Use real Claude, not Fake Claude**: The manual test server passes through
  your local API keys, so real Claude models work out of the box. Use whatever
  model is selected by default (typically Claude Opus). Do NOT switch to
  "Fake Claude" — the whole point of manual testing is to exercise the real
  end-to-end flow that integration tests cannot cover.

- **Wait for server readiness**: The backend takes ~20-30 seconds to start.
  Always poll `/status` before sending commands.

- **Screenshots are numbered**: Files are named `0001_step.png`,
  `0002_click_100_200.png`, etc. The counter increments for each action.

- **`time.sleep` in actions**: Each action has a short built-in delay after
  execution to let animations settle. For longer waits, use `wait` or
  `wait_for_hidden`.

- **Finding element coordinates**: Do NOT estimate coordinates by eyeballing
  screenshots — the screenshot image may render at a different size than the
  actual 1400x900 viewport, leading to completely wrong click targets. Always
  use `locate` to find precise coordinates first, then `click`.

- **Port allocation**: All ports (backend, Vite, control API) are
  auto-allocated via `PortManager`, which coordinates across processes
  using a file lock. No port conflicts with other agents or `just start`.

- **Hot reload**: The harness uses the Vite dev server, so CSS and component
  changes appear in the next screenshot without restarting. If you edit a
  `.tsx` or `.scss` file, just take another screenshot to see the change.

## Reading backend logs (when something fails)

The server log you started with `nohup` (`$SERVER_LOG`) only captures the
backend's **startup** output. Once the server is ready, the backend's runtime
logs — request handling, git commands, and the full traceback + stderr of any
backend error (e.g. a `WorktreeError` from `git worktree add`) — go **only** to
the backend's own structured log file under its temp data folder, not to
`$SERVER_LOG`. If the UI shows an error but `$SERVER_LOG` looks empty after
startup, that's expected; look here instead.

Find the backend's data folder (printed at startup) and read its JSONL log:

```bash
# The temp sculptor folder is printed once at startup, e.g. in the "Using DB:" line.
SCULPTOR_FOLDER=$(grep -oE '/[^ ]*sculptor_manual_test_[A-Za-z0-9_]+' "$SERVER_LOG" | head -1)
BACKEND_LOG="$SCULPTOR_FOLDER/internal/logs/server/logs.jsonl"
echo "Backend log: $BACKEND_LOG"

# Pull out errors / a specific failure (each line is a JSON record; print the message):
grep -aE '\|ERROR|Traceback|fatal:|WorktreeError' "$BACKEND_LOG" | python3 -c "
import json,sys
for line in sys.stdin:
    try: print(json.loads(line).get('text',''))
    except Exception: print(line.rstrip())
" | tail -40
```

This is the authoritative place to find *why* a workspace, agent, or git
operation failed — the agent panel truncates the message and `$SERVER_LOG`
won't have it.

## Cleanup

**IMPORTANT:** The server runs as a detached `nohup` process — it will keep
running even after your conversation ends. Always clean up when done:

```bash
# Kill the server using the PID file (survives conversation compaction)
kill $(cat "$SCREENSHOTS_DIR/manual-test-server.pid") 2>/dev/null
```

The server's signal handler automatically cleans up temp directories and
the Sculptor backend process when it receives SIGTERM.

The PID file is saved inside `$SCREENSHOTS_DIR` so it stays local to this
workspace and won't interfere with other agents' servers.

**NEVER delete screenshot files.** They are referenced by `<img>` tags in the
user's chat history. Deleting them turns those into broken image links that
cannot be recovered. Leave all screenshots in `$SCREENSHOTS_DIR` — they are
small and the user may want to attach them to MRs later.
