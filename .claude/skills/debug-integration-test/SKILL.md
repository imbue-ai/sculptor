---
name: debug-integration-test
description: |
  Debug failing Sculptor frontend integration tests.
  Use when integration tests fail and you need to diagnose the root cause.
  Covers common failure modes, how to read test logs, and investigation strategies.
---

# Debugging Sculptor Integration Tests

Use this skill when an integration test fails and you need to find the root cause.

## Common Failure Modes

### 1. Playwright TimeoutError on Disabled/Missing Element

**Symptom:** Test fails with `playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded` and the call log shows the element was found but remained **disabled** or **not visible**.

**Example error output:**
```
E  playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
E  Call log:
E    - waiting for get_by_test_id("TASK_STARTER").get_by_test_id("BRANCH_SELECTOR")
E      - locator resolved to <button disabled dir="ltr" type="button" ...>
E    - attempting click action
E      2 × waiting for element to be visible, enabled and stable
E        - element is not enabled
E      - retrying click action
E      ...
E      49 × waiting for element to be visible, enabled and stable
E        - element is not enabled
```

**Root cause:** The UI element exists in the DOM but never reaches the expected state. Common reasons:
- A prerequisite API call failed or never returned (e.g., branch list not fetched)
- The frontend is waiting on data that the backend never provided
- A timing issue where the test interacts with the UI before initialization completes

**How to investigate:**
1. Look at the Playwright call log in the traceback — it tells you the exact element state (`element is not enabled`, `element is not visible`, etc.)
2. Check the backend API logs in the test output for errors or missing API calls
3. **View the failure screenshot** (`test-failed-1.png`) — in CI this is always present and shows the page state at the moment of failure. See "Playwright Test Artifacts" below for how to find it. This is often enough to diagnose the issue.
4. **Inspect the Playwright trace** if the screenshot and logs aren't sufficient. The trace contains full DOM snapshots at each action, so you can:
   - Read `frame-snapshot` entries in `trace.trace` to see the complete DOM tree at the moment of timeout, including all `data-testid` attributes and element states
   - Read `trace.network` to check whether the expected API calls were made before the timeout
5. Compare what API calls were made (visible as HTTP log lines in `Captured stdout` and in `trace.network`) against what the frontend needs

### 2. "File not found" in Electron Window (DEV_ELECTRON mode)

**Symptom:** The Electron window shows `{"detail":"File not found: "}` as plain JSON text instead of the React app. Tests using the `sculptor_instance_` shared fixture fail with `ERROR at setup` and the traceback shows `expect(home_page.get_sidebar_toggle_button()).to_be_visible()` timing out at `resources.py`. The test log shows `"GET / HTTP/1.1" 404`.

**Root cause:** In `DEV_ELECTRON` mode (the default), the React frontend is served by the Vite dev server, **not** the backend. The backend's catch-all route `@APP.get("/{filename:path}")` in `app.py` tries to serve static files from `frontend-dist/` or `frontend/dist/`, but those directories don't contain built files in dev mode. If code navigates the Playwright page to the backend URL (e.g., `page.goto(http://127.0.0.1:{backend_port})`), the backend returns a 404 with the "File not found" JSON detail.

**How to identify:**
- Search the log for `"GET / HTTP/1.1" 404` — confirms the backend received a root request and returned 404
- Search for `ERR_ABORTED (-3)` — Electron's error when a page navigation is aborted
- The error occurs during fixture **setup**, not during the test itself

**How to fix:** Ensure that test infrastructure code does not navigate to the backend URL in `DEV_ELECTRON` mode. The Electron window already loads the React app from the Vite dev server. For the shared `sculptor_instance_` fixture, `_get_or_create_shared_instance` in `resources.py` should skip `navigate_to_frontend` and just wrap the existing page in `PlaywrightHomePage`.

**Key file:** `sculptor/sculptor/testing/resources.py` — the `_get_or_create_shared_instance` function.

### 3. FakeClaude Command Parsing Errors

**Symptom:** Task enters `ERROR` state immediately after creation, or FakeClaude returns an unexpected response. The test log may contain JSON parsing errors from the FakeClaude command handler.

**Root cause:** The `fake_claude:` command string has malformed JSON — e.g., missing backticks, unescaped quotes, or incorrect nesting.

**How to identify:** Search the test log for `json.JSONDecodeError` or `FakeClaude` error messages.

**How to fix:** Check the command string formatting. FakeClaude commands must follow this format:
```
fake_claude:<command> `<json_args>`
```
The JSON must be wrapped in backticks. Use multiline strings for complex JSON to avoid formatting mistakes.

## Playwright Test Artifacts

When a test fails, Playwright records several artifacts that are invaluable for debugging. The available artifacts depend on the flags passed to pytest:

- **`test-failed-1.png`** — a full-page screenshot taken at the moment of failure (`--screenshot=only-on-failure`). **Start here** — it's small, fast to view, and often enough to diagnose UI issues.
- **`trace.zip`** — a full trace containing the action timeline, DOM snapshots at each step, network requests, console logs, and screencast frames (`--tracing=retain-on-failure`). Use this when the screenshot alone isn't enough.
- **`video.webm`** — a screen recording of the entire test run (`--video=retain-on-failure`).

`pytest.ini` only configures `--tracing=retain-on-failure`. The CI runner adds `--screenshot=only-on-failure` and `--video=retain-on-failure`. When running locally, add these flags yourself if you want the screenshot and video.

### Where to find artifacts

**Locally** — after a failed test run, look in:
```
sculptor/test-results/<test-file-stem>-<test-name>-<browser>/
```

For example, a failure in `test_task_page_chatting.py::test_starting_text` produces:
```
sculptor/test-results/test-task-page-chatting-test-starting-text-chromium/trace.zip
```

**In CI** — artifacts are uploaded as workflow artifacts. To download them:

1. Download the full artifacts archive for the failed run (find the run ID
   with `gh run list`):
   ```bash
   gh run download <RUN_ID> --dir /tmp/ci-artifacts/
   ```
   or download a single named artifact: `gh run download <RUN_ID> -n <artifact-name> --dir /tmp/ci-artifacts/`.

2. The download contains test artifacts organized under `test-results/<test-dir>/`, where `<test-dir>` is derived from the test file and test name. Depending on the test configuration, each directory may include failure screenshots (e.g. `test-failed-1.png`), Playwright traces, and video recordings. For example:
   ```
   test-results/tests-integration-frontend-test-ask-user-question-py-test-ask-user-question-dismiss/test-failed-1.png
   ```

3. List the downloaded files to find artifacts for a specific test:
   ```bash
   find /tmp/ci-artifacts -path '*test-results*' | grep <test-name>
   ```

### What's inside a trace zip

A `trace.zip` is a standard ZIP archive. Unzip it to access the contents:
```bash
unzip trace.zip -d /tmp/trace-contents/
```

Key files inside:

| File | Format | Contents |
|------|--------|----------|
| `trace.trace` | Newline-delimited JSON | The main event log. Contains action events (`before`/`after` pairs), `frame-snapshot` entries with **full DOM trees**, `screencast-frame` references, `console` messages, and `log` entries. |
| `trace.network` | Newline-delimited JSON | HAR-format entries for every HTTP request/response (URL, method, status, headers, timing). Response bodies stored in `resources/` by SHA1 hash. |
| `trace.stacks` | JSON | Stack traces mapping actions back to test source lines. Contains `files` (list of source paths) and `stacks` (list of frame references). |
| `resources/` | Directory | Screenshot JPEGs (named `page@<id>-<timestamp>.jpeg`), network response bodies (`<sha1>.json`), and source file snapshots (`src@<sha1>.txt`). |

### How to inspect a trace as an agent

The Playwright trace viewer is a GUI tool — agents should unzip the trace and read the files directly.

**Step 1: Unzip**
```bash
unzip /tmp/trace.zip -d /tmp/trace-contents/
```

**Step 2: Read `trace.trace` for the action timeline and DOM**

Each line is a JSON object. The key event types:

- **`before`** — Start of a Playwright action. Contains the `selector`, `method` (e.g., `click`, `expect`), `params`, and `startTime`. The `beforeSnapshot` field references the DOM snapshot taken *before* the action.
  ```json
  {"type":"before","callId":"call@42","title":"Expect \"to_have_attribute\"","method":"expect",
   "params":{"selector":"internal:testid=[data-testid=\"TASK_INPUT\"s]","timeout":30000},
   "beforeSnapshot":"before@call@42"}
  ```
- **`after`** — Completion of the action. Contains `result` (success/failure) and `endTime`. For timeouts, look for error results here.
- **`frame-snapshot`** — **Full DOM tree** captured at a specific action step. All fields are nested inside a `snapshot` sub-object: `snapshot.snapshotName`, `snapshot.callId`, `snapshot.html`, etc. The `snapshot.html` field contains the DOM as a nested array structure (`['TAG', {attrs}, ...children]`). All `data-testid` attributes are present, so you can search for specific elements and check their state (disabled, hidden, etc.). To find the DOM at the moment of failure, look for the `frame-snapshot` whose `snapshot.snapshotName` matches the `beforeSnapshot` or `afterSnapshot` of the failing action.
- **`screencast-frame`** — References a screenshot JPEG in `resources/` via the `sha1` field.
- **`log`** — Detailed log messages for each action (e.g., retry messages during `expect` waits).
- **`console`** — Browser console output.

**Step 3 (optional): Read `trace.network` for HTTP requests**

Each line is a HAR-format `resource-snapshot` with full request/response details. Useful for checking whether expected API calls (e.g., `/api/v1/tasks`, branch fetching) were made and what status codes were returned. Response bodies are stored in `resources/<sha1>.json`.

**Step 4 (optional): View screenshots from `resources/`**

The JPEG files in `resources/` are screencast frames captured throughout the test. They are named `page@<page_id>-<timestamp>.jpeg`. To find the screenshot closest to the failure, sort by timestamp (the numeric suffix) and view the last few images. These give you a visual snapshot of what the page looked like.

### Trace limitations

Traces only record Playwright-level actions (clicks, expects, navigations, etc.). Python-side assertions (`assert ...`) that fail after all Playwright interactions have completed will **not** appear as errors in the trace. If every action in `trace.trace` succeeded but the test still failed, the failure is in a Python assertion outside of Playwright.

### When traces are most useful

- **TimeoutError on a locator** — the trace shows the DOM state at the moment of timeout, so you can see whether the element existed but was disabled/hidden, or was missing entirely
- **Unexpected UI state** — compare the DOM snapshots against what the test expected
- **Flaky tests** — trace timing reveals race conditions between UI updates and test assertions
- **Missing API calls** — the network log shows whether expected backend requests were made

## How to Read Test Logs

Test output from `just test-integration` contains several interleaved log streams. Here's how to parse them.

### Log Structure

The test output contains these sections in order:

1. **Test collection** — pytest finds and lists tests
2. **Captured stdout call** — Interleaved logs from the test runtime, including:
   - Backend server logs (prefixed with timestamps like `15:13:11.060`)
   - Electron stdout (prefixed with `[Electron stdout]`)
   - Test framework logs (from `sculptor/testing/` modules)
3. **FAILURES section** — The pytest traceback with the actual error
4. **Captured stdout setup/teardown** — Server startup and shutdown logs
5. **Short test summary** — One-line PASSED/FAILED per test

### Key Patterns to Search For

When diagnosing a failure, search the log output for these patterns (using `grep`):

| Pattern | What it reveals |
|---------|----------------|
| `FAILED` | Which tests failed and where in the output the failure occurred |
| `TimeoutError` | Playwright timeout — element never reached expected state |
| `error:` (lowercase) | Git errors, backend errors, or general error messages |
| `Error` (capitalized) | Python exceptions, proxy errors |
| `element is not enabled` | Playwright retrying on a disabled element |
| `element is not visible` | Playwright retrying on a hidden element |
| `"GET / HTTP/1.1" 404` | Backend received root request and returned 404 — likely a DEV_ELECTRON navigation bug |
| `File not found:` | Backend's catch-all static file route can't find frontend files (expected in DEV_ELECTRON mode) |
| `json.JSONDecodeError` | Malformed JSON in a FakeClaude command string |

### Timeline Reconstruction

To understand what happened during a test:

1. **Find the failure**: Search for `FAILED` or `TimeoutError` to locate the error
2. **Read the traceback**: The `FAILURES` section shows the exact line and Playwright call log
3. **Trace API calls**: Backend HTTP logs show every API call made. Look for patterns:
   - Successful flow: `OPTIONS` → `GET/POST` → `200` responses
   - Failed flow: Missing expected API calls, or `4xx`/`5xx` responses
4. **Check for gaps**: If there's a long gap (30+ seconds) between the last API call and `FAILED`, the test was stuck waiting on an element that never became ready

### Example: Diagnosing a Disabled Branch Selector

Real failure from `test_changes_reflected_from_branch_with_commits`:

```
# 1. Error shows branch selector button is disabled
E  - locator resolved to <button disabled ... data-testid="BRANCH_SELECTOR">
E  49 × waiting for element to be visible, enabled and stable
E    - element is not enabled

# 2. Backend logs show these were the last API calls:
15:13:18.007 - "GET /api/v1/auth/me HTTP/1.1" 200
15:13:18.023 - "POST .../set-most-recently-used HTTP/1.1" 200

# 3. Then 26 seconds of silence until:
FAILED [100%] 15:13:43.965

# 4. Diagnosis: No branch-fetching API call was ever made.
#    The frontend homepage loaded, but the branch selector
#    never received its branch list data, so it stayed disabled.
```
