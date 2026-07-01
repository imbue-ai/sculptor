# Integration Test Review Rules

Review rules for evaluating Sculptor integration tests. The goal is to catch flaky patterns before they're merged — most flakes stem from tests that implicitly assume fast execution, clean environments, or synchronous rendering.

For each issue found, note the issue type, file/line, and a brief description of what is wrong and how to fix it.

---

## Playwright Assertions

### `use_expect_not_assert`

**Question:** Is this test using Python `assert` or a manual loop to check UI state instead of Playwright's `expect()`?

Playwright's `expect()` auto-retries until the condition is met or the timeout expires. Python `assert` checks once and fails immediately if the DOM hasn't settled. Manual polling loops (while/for + sleep) are verbose, error-prone, and hide the intent.

**What to look for:**
- `assert element.is_visible()` or `assert element.inner_text() == ...`
- `assert is_element_focused(...)` or any helper that reads DOM state once
- `while` / `for` loops with `time.sleep()` polling for element state

```python
# Bad: checks once, fails if DOM hasn't settled
assert is_element_focused(name_input), "Expected name input to be focused"

# Good: retries until focused or timeout
expect(name_input).to_be_focused()
```

---

### `no_sleep_then_assert`

**Question:** Is this test using `wait_for_timeout()` followed by a non-retrying assertion?

This is the most common flake pattern. `page.wait_for_timeout(N)` is a fixed delay — it may be enough on fast machines but too short under load. Combining it with a snapshot assertion (`assert`, `.is_visible()`, `is_element_focused()`) means the test guesses how long the UI needs, rather than observing when it's ready.

**What to look for:**
- `page.wait_for_timeout(...)` immediately followed by `assert`
- `page.wait_for_timeout(...)` followed by `.inner_text()`, `.is_visible()`, or `is_element_focused()`
- Any pattern where a fixed sleep substitutes for waiting on a condition

```python
# Bad: sleep then snapshot
blur_page(page)
page.wait_for_timeout(200)
page.keyboard.press(f"{mod_key}+i")
page.wait_for_timeout(500)
assert is_element_focused(name_input)

# Good: expect() auto-retries both the precondition and the result
blur_page(page)
expect(name_input).not_to_be_focused()
page.keyboard.press(f"{mod_key}+i")
expect(name_input).to_be_focused()
```

When you need to wait for a structural condition that `expect()` can't express (e.g., a specific number of DOM nodes inside a virtual list), use `page.wait_for_function()`:

```python
# Bad: arbitrary sleep before interacting with a virtual list
alpha_view.click()
page.wait_for_timeout(500)

# Good: wait for the virtual list to render the expected items
alpha_view.click()
page.wait_for_function(
    """() => document.querySelectorAll('[data-testid="ALPHA_CHAT_VIEW"] [data-index]').length >= 6"""
)
```

---

### `no_snapshot_iteration`

**Question:** Is this test calling `.all()` or `.inner_text()` to find or filter elements from a list?

`.all()` returns a frozen snapshot of the current DOM. If elements are still rendering (e.g., dropdown options, virtual list items), the snapshot is incomplete or empty. Use Playwright's locator filtering (`.filter()`, `.get_by_text()`) which auto-retries until matching elements appear.

**What to look for:**
- `locator.all()` followed by a loop or list comprehension filtering on `.inner_text()`
- `only([x for x in locator.all() if x.inner_text() == ...])` — races on slow renders
- Any pattern that takes a DOM snapshot and then searches through it in Python

```python
# Bad: .all() captures a point-in-time snapshot that may be incomplete
options = chat_panel.get_model_options()
expect(options.first).to_be_visible()
target = only([opt for opt in options.all() if opt.inner_text().strip() == model_name])
target.click()

# Good: locator filtering auto-retries until the match appears
options = chat_panel.get_model_options()
target = options.filter(has=page.get_by_text(model_name, exact=True))
expect(target).to_be_visible()
target.click()
```

---

### `no_lowered_timeouts`

**Question:** Is this test setting an explicit timeout lower than the default 30s?

Our test harness sets the default `expect()` timeout to 30s (`configure_expect_timeout` in `playwright_conftest.py`). This already accounts for backend round-trips, WebSocket delivery, page reloads, and virtual list rendering. Tests that override with `timeout=5_000` or `timeout=10_000` are opting into tighter timing that works on fast machines but flakes under load.

Only lower the timeout when you're intentionally asserting performance (e.g., "this element must appear within 2s of clicking").

**What to look for:**
- `expect(...).to_be_visible(timeout=5_000)` or similar explicit timeouts below 30s that aren't performance assertions
- `timeout=10_000` on operations that involve async round-trips (tab switch, rename, WebSocket push)

```python
# Bad: lowered timeout that flakes on slower runners
expect(messages).to_have_count(4, timeout=5_000)

# Good: use the default — it's already 30s
expect(messages).to_have_count(4)
```

**Exceptions:** Timeouts *above* the default are fine for operations known to be slow (e.g., initial SPA render, long streaming responses). Lowered timeouts are fine when the test is specifically verifying responsiveness.

---

### `confirm_side_effects_before_next_step`

**Question:** Does this test confirm that an async action's side effects have landed before asserting something that depends on them?

Playwright auto-waits for actionability before `.click()` and `.fill()`, so you don't need `expect(...).to_be_visible()` before every interaction. But Playwright can't know when the *side effects* of an action have propagated through the backend, WebSocket, and React state. If a test renames an agent and then immediately asserts the intro text updated, it races against the backend round-trip. Confirm the intermediate result (e.g., tab text changed) before asserting the downstream effect (e.g., intro text changed).

**What to look for:**
- An action with async side effects (rename, delete, mode switch, form submit) followed immediately by an assertion on a *different* element that depends on those side effects
- No confirmation that a dialog/input dismissed after submit — the test proceeds while the operation is still in-flight
- Reading shadow DOM content (e.g., Pierre diff viewer) without waiting for async internal rendering (Shiki tokenisation) to complete

```python
# Bad: asserts intro text immediately after rename — the rename hasn't
# round-tripped through the backend yet, so the intro atom is stale
_rename_via_context_menu(page, agent_tab, "Renamed Agent")
expect(intro).to_contain_text("Renamed Agent")

# Good: confirm the rename landed (tab text updated) before asserting
# the downstream effect (intro text, which reads from a different atom)
_rename_via_context_menu(page, agent_tab, "Renamed Agent")
expect(agent_tab).to_contain_text("Renamed Agent", timeout=15_000)
expect(intro).to_contain_text("Renamed Agent", timeout=15_000)
```

```python
# Bad: proceeds immediately after pressing Enter — rename may still be in-flight
rename_input.fill(new_name)
rename_input.press("Enter")
# next step assumes rename is done...

# Good: confirm the input dismissed (rename committed) before moving on
rename_input.fill(new_name)
rename_input.press("Enter")
expect(rename_input).not_to_be_visible()
```

---

### `wait_for_actual_target`

**Question:** Is this test waiting on a proxy element instead of the element it actually cares about?

Wait on the element whose state you're about to assert. Waiting on a proxy (e.g., a status pill disappearing as a signal for "operation complete") is fragile — the proxy may not render in all contexts (e.g., after a page reload or view switch), causing a timeout even though the actual condition you care about is already satisfied.

**What to look for:**
- A helper that waits on element A, followed by a separate assertion on element B
- Waiting for a status indicator to disappear as a proxy for "streaming finished" or "agent idle"
- The wait target was defined in a different rendering context (before a page reload, `switch_to_alpha_view`, or navigation)

```python
# Bad: STATUS_PILL may never render after switch_to_alpha_view's page reload,
# so this times out even though streaming already finished
def _wait_for_agent_idle_alpha(page, *, timeout=60000):
    status_pill = page.get_by_test_id(ElementIDs.STATUS_PILL)
    expect(status_pill).not_to_be_visible(timeout=timeout)

_wait_for_agent_idle_alpha(page)
expect(cursor).to_have_count(0)

# Good: wait directly on the element you care about
expect(cursor).to_have_count(0, timeout=120_000)
```

---

### `no_wall_clock_in_fake_claude`

**Question:** Is this test using `fake_claude:sleep` (or any other wall-clock pause inside fake_claude) to keep the agent busy through a sequence of UI actions?

The agent must outlast all the UI overhead between "agent starts" and "test finishes its assertions." Any wall-clock window — even a generous one — is asymptotically racy under CI load: when the runner is slow, the agent finishes before the test's assertions land, and the test exercises the wrong code path (or fails outright). Bumping the sleep is a treadmill — SCU-845 hit this three times in the same file before being fixed properly. The same applies to *any* sleep inside fake_claude that the test relies on to expose a transient state (e.g. a pause embedded inside a multi-step handler like `background_subagent`).

**What to look for:**
- `fake_claude:sleep` in a prompt where the agent needs to stay busy until the test does something
- Any `*_seconds` / `*_ms` arg passed to a fake_claude command that the test relies on to observe a transient state
- Comments like "sized generously so a slower runner can still…" — these are warning signs that a wall-clock is being asked to absorb arbitrary CI latency

```python
# Bad: a 12-second wall-clock sleep to keep the agent busy until the test is
# ready. Asymptotically racy under CI load; "increase the timeout" is the same
# trap SCU-845 hit three times.
SLOW_COMMAND = 'fake_claude:sleep `{"seconds": 12}`'

# Good: a sentinel file the test touches when it's ready for the agent to
# proceed. No wall-clock — the agent stays busy until release() is called.
from sculptor.testing.fake_claude_pause import FakeClaudePause

pause = FakeClaudePause()
bg_command = "fake_claude:background_subagent `" + json.dumps({
    "description": "Find Python files",
    "pause_path": str(pause.release_path),
}) + "`"
# ... start the agent with bg_command, assert mid-state ...
pause.release()  # agent's next poll sees the sentinel; turn finishes naturally
```

**Fix:** Use the `FakeClaudePause` helper (`sculptor/sculptor/testing/fake_claude_pause.py`) — it generates a per-test sentinel path under `/tmp/` and exposes both `prompt` (for the simple "pause the whole turn" case via `fake_claude:wait_for_file`) and `release_path` (for embedding the same sentinel into other fake_claude commands that support a `pause_path` arg). If you need a brand-new pause point inside an existing fake_claude command, add a `pause_path` arg there and use `_wait_until(..., done=sentinel.exists)` rather than `handle_sleep`. The change that introduced `FakeClaudePause` (SCU-845) converted the existing tests and is the canonical example.

---

## Test Isolation

### `isolate_from_host_filesystem`

**Question:** Does this test depend on state outside its temporary directories — home directory, global caches, system PATH, or state shared with other xdist workers?

Tests must not rely on the host machine's home directory, global caches (`~/.cache/`), or globally installed binaries. On persistent CI runners, state from previous runs bleeds through. On ephemeral runners, the state may be absent. Tests also run concurrently across multiple xdist workers on the same machine — any shared mutable state (files, directories, ports) becomes a race condition between workers.

**What to look for:**
- A test that depends on a binary being on PATH without stubbing it (e.g., expects `claude` to be installed and version-compatible)
- Reading or writing to `~/.cache/`, `~/.config/`, or other home-directory paths not controlled by the test
- Fixtures that don't redirect `SCULPTOR_USER_DATA_DIR`, cache paths, or equivalent to per-worker temp directories
- Missing `@stub_dependency` for external binaries the test interacts with
- Writing to a fixed path (e.g., `/tmp/sculptor_test.db`) instead of a worker-scoped temp directory — concurrent workers will clobber each other

```python
# Bad: assumes the real claude binary is installed and version-compatible.
# Works on developer machines, breaks on CI where the installed version drifts.

# Good: factory fixture stubs the binary in its isolated fake_bin_dir
from sculptor.testing.dependency_stubs import DependencyState, create_disabled_dependency_stub

create_disabled_dependency_stub(fake_bin_dir, "claude", DependencyState.INSTALLED_STUB)
```

**Fix:** Use `@stub_dependency("claude", state=...)` for tests that interact with external binaries. For cache paths, redirect them into the test's temp directory (e.g., Electron's `app.setPath("cache", temp_dir)`). All mutable state must be scoped to the worker's temp directories, never to fixed paths that concurrent workers share.

---

### `no_user_config_coupled_assertions`

**Question:** Does this test invoke a user-configurable tool or environment (a shell, `git`, an editor, locale, `$TERM`, any rc-driven CLI) and then assert on output or behaviour that the user's configuration can perturb — coupling a config-independent assertion to per-developer settings?

Many tools read configuration the test does not control: a login shell sources the user's rc chain (themes, plugins, syntax highlighting, bracketed-paste); `git` reads `~/.gitconfig` (aliases, `init.defaultBranch`, signing, hooks); CLIs read dotfiles; output formatting and parsing depend on `$LANG`/`$LC_*` and `$TERM`. When a test invokes such a tool and asserts on what comes back, that configuration becomes uncontrolled input — a clean CI runner behaves nothing like a heavily-customised laptop, so the test passes in one place and flakes or fails in the other. The deeper smell is the coupling itself: the property under test (an env var is propagated, a path is built, a commit is created) is usually produced by code whose behaviour does not depend on those settings at all, yet it is being observed through a config-dependent channel. (This is the assertion-coupling counterpart to `isolate_from_host_filesystem`: that rule is about not depending on host *state*; this one is about not coupling an *assertion* to host *configuration*.)

**What to look for:**
- A process built from `$SHELL` / `os.environ["SHELL"]`, or a shell run with `-l`, without pinning the shell's environment
- Invoking `git`, an editor, a package manager, or any rc-driven CLI without neutralising the user's global config (`HOME`, `ZDOTDIR`, `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_NOSYSTEM`, `EDITOR`, `LANG`/`LC_ALL`, `TERM`)
- Matching on a tool's output with ANSI/escape-stripping, locale-tolerant parsing, or `errors="replace"` decoding added to cope with config-driven noise
- Fixed sleeps or generous timeouts added so a slow, heavily-configured tool (e.g. a themed shell with an async prompt) has "enough" time before the test interacts with it
- An assertion about logic (env handling, argument building, path construction) verified *only* end-to-end through such a tool, with no direct test of the function that implements it

**Fix:**
- Neutralise the configuration so every run gets a vanilla, deterministic tool: point `HOME`/`ZDOTDIR` at an empty directory for shells, set `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_NOSYSTEM` for git, pin `LANG`/`LC_ALL` and `TERM`, and pass an explicit tool rather than inheriting `$SHELL`/`$EDITOR` when the test does not specifically need the user's. An autouse fixture is a good home for this. Removing the variability usually lets you delete the escape-stripping / timeout band-aids too.
- Push the real assertion down a layer: unit-test the pure function that produces the behaviour (env scrub/merge, arg building, path construction) directly with controlled inputs, and keep at most a thin end-to-end test that the value reaches the real tool.

**Exceptions:** Tests that genuinely exercise the tool integration itself — that a login shell honours SIGHUP and exits, that a git hook fires — legitimately invoke the real tool, but should still pin its configuration so the behaviour under test is the only variable.

---

## Test Placement

### `correct_launch_mode_markers`

**Question:** Does this test carry the launch-mode marker that matches the runtime it actually needs?

The default integration run uses headless Chromium (`--sculptor-launch-mode=browser`). A test that needs a real Electron renderer or main process must opt into a different launch mode via a marker. Without a marker, the test runs only in browser mode; with the wrong marker, the test is silently skipped in the run where it would have provided coverage. The marker is what `pytest_collection_modifyitems` in `sculptor/conftest.py` reads to decide which run each test participates in.

The launch-mode markers (defined in `sculptor/pytest.ini`):

- *(no marker)* — runs only in **browser** mode. The default for most tests.
- `@pytest.mark.electron` — runs only in **electron** mode (Electron dev server via CDP). Use for behaviour that requires a real Electron renderer or main process: native clipboard, native file dialogs, auto-update, dock badge, drag-and-drop with real paths.
- `@pytest.mark.browser_and_electron` — runs in **both** browser and electron modes. Use when the same assertion should hold across both runtimes (rare; usually one or the other suffices).
- `@pytest.mark.electron_custom_command` — runs only in `electron-custom-command` mode (Electron started with `SCULPTOR_CUSTOM_BACKEND_CMD`; file uploads go over HTTP instead of Electron IPC). Today the only consumer is `test_image_upload.py`, where the upload tests are marked `@browser_and_electron` (several also `@electron_custom_command`) to lock in upload behaviour across the browser/HTTP, Electron-IPC, and custom-command transport paths. Add this marker only if your test exercises a code path that switches on whether Electron starts the backend itself or hands off to a custom command.
- `@pytest.mark.packaged_electron` — runs only in `packaged-electron` mode (the *launch mode*, not the CI pipeline). It is the packaged-build analogue of `@electron` and must always be combined with `@release` — the harness rejects `@packaged_electron` without `@release` at collection time.

**What to look for:**
- A test asserting on Electron-only behaviour (clipboard read-back, native menu, dock badge) with no marker → silently skipped in CI (browser mode cannot satisfy it; the electron run will not pick it up either).
- `@pytest.mark.electron` on a test whose assertions do not depend on Electron at all → runs only in the slower Electron job and adds no coverage over an unmarked version.
- `@pytest.mark.electron_custom_command` added alone, without `@electron` → loses coverage in the standard Electron job, where the IPC path also matters.
- `@pytest.mark.packaged_electron` without `@release` → collection fails loudly. Add `@release` (the CI gate) alongside the launch-mode filter, or drop `@packaged_electron`.

**Fix:** Match the marker to the runtime the test actually depends on. If the test can pass headless, leave it unmarked.

---

### `release_marker_requires_release_safe_setup`

**Question:** Does this test's `@pytest.mark.release` setup match what the packaged build can actually provide?

`@pytest.mark.release` adds the test to the release pipeline, where it runs against the **packaged** Sculptor build. By default a release-marked test runs in both `packaged-electron` (Linux AppImage) and `packaged-backend` (macOS, headless backend) modes. The packaged build ships without Fake Claude. Two failure modes show up only in the release run, which makes them easy to miss in review:

1. **Fake Claude dependency** — the test calls `start_task_and_wait_for_ready(...)` and lets the helper take its default `model_name=FAKE_CLAUDE_MODEL_NAME`. In packaged mode the Fake Claude `MODEL_OPTION` never appears; the helper hangs for 30s and fails. The test passes in regular CI (where Fake Claude exists), so the regression is invisible until the release job runs.
2. **The `packaged-backend` mode cannot satisfy the test** — the test asserts on behaviour that requires a real Electron main process (auto-update wiring, native menus, dock badge, real file dialogs, IPC-mediated behaviour). `@release` alone runs in `packaged-backend` too, where there is no Electron process, and the test fails there even though it would pass on Linux. The fix is to add `@pytest.mark.packaged_electron` alongside `@release` so the test is narrowed to `packaged-electron` only — the packaged-build analogue of marking an Electron-only test with `@electron` in the regular suite.

**What to look for:**
- `@pytest.mark.release` on a test that calls `start_task_and_wait_for_ready(...)` and relies on its default model selection (Fake Claude).
- `@pytest.mark.release` on a test whose assertions require Electron main-process behaviour without also carrying `@pytest.mark.packaged_electron` — will fail in `packaged-backend` mode on macOS.
- A new release-marked test added alongside a feature that has not been verified end-to-end against the packaged artifact.

**Fix:**
- If the test does not need to exercise the agent itself, drop `@pytest.mark.release` — it still runs in the regular integration suite. Routing it through real Claude (so it works against the packaged build) is a separate, heavier exercise.
- If the test legitimately needs a fully packaged Electron host (so `packaged-backend` cannot satisfy it), add `@pytest.mark.packaged_electron` alongside `@release` so it is skipped in the headless-backend variant.

**Exceptions:** Tests that exercise functionality available in any packaged build without spinning up an agent (UI shell, navigation, settings) are fine to mark `@release` as long as their setup does not reach for Fake Claude.

---

## Test Scope

### `no_layout_only_tests`

**Question:** Does this test verify behaviour, or only layout?

Integration tests exist to verify user-visible behaviour. They are not the right tool for verifying visual layout — that is what before/after screenshots are for. A test whose only assertions read CSS dimensions, line-clamp counts, clipping, `getBoundingClientRect()`, `getComputedStyle()`, or anything else that reflects rendering rather than behaviour is a layout-only test. These tests provide weak coverage (small rendering changes break them without any underlying bug), and they cost the same to run as a real e2e test.

If a bug is "purely visual" — the only failure mode is that something doesn't look right — `.sculptor/testing.md` already says you MUST NOT write an integration test for it. This rule catches the inverse case: a behavioural bug whose test, as written, only validates layout.

**What to look for:**
- Assertions that read element width/height, `clientWidth`/`clientHeight`, or `getBoundingClientRect()`
- `page.evaluate()` calls that read computed style (`getComputedStyle()`, `style.lineClamp`, `style.overflow`, etc.) and assert on the value
- Comparing screenshots dimensions or pixel counts as the only assertion
- Tests whose name describes a visual outcome ("renders truncated," "is clipped," "fits on one line") with no behavioural assertion alongside

```python
# Bad: only verifies the element's rendered width
button = create_workspace_button(page)
width = button.evaluate("el => el.getBoundingClientRect().width")
assert width < 200, "button should not overflow"

# Bad: only verifies CSS line-clamp
text = prompt_navigator_popover(page)
clamp = text.evaluate("el => getComputedStyle(el).webkitLineClamp")
assert clamp == "2"

# Good (for a behavioural bug): assert what the user can DO, not how it looks
button = create_workspace_button(page)
button.click()
expect(workspace_dialog).to_be_visible()
```

**Fix:** If the bug is purely visual, delete the test and verify with a before/after screenshot instead (see `.sculptor/testing.md` and the fix-bug skill's screenshot mandate). If the bug has behavioural impact (e.g. a button overflows AND becomes unclickable), test the behaviour (clickability), not the layout.

---

## Test Structure

### `use_pom_hierarchy`

**Question:** Is this test accessing UI elements directly via `page.get_by_test_id()` instead of through the Page Object Model?

Access elements through the POM class hierarchy (`pages/` → `elements/`). Raw `page.get_by_test_id()` in test functions bypasses the abstraction, making tests brittle when element structure changes and duplicating access logic across tests.

**What to look for:**
- `page.get_by_test_id(ElementIDs....)` in test functions — should be accessed via a POM method
- Repeated element-access patterns across multiple tests that should be a single POM method

**Exceptions:** Quick one-off checks in test helpers or conftest fixtures where introducing a POM method would be over-abstraction.
