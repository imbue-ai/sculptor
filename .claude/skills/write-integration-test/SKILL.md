---
name: write-integration-test
description: |
  Instructions for writing new Sculptor frontend integration tests.
  Covers how to use FakeClaude for deterministic agent behavior,
  test file setup, and the available FakeClaude commands.
  Use when writing new integration tests or adding tests to existing files.
---

# Writing New Integration Tests

This skill explains how to write a new frontend integration test for Sculptor.

## First Decision: Default Response vs FakeClaude Commands

Before writing your test, decide whether you need to control the agent's behavior.

### Default response (prefer this when possible)

When the prompt has no `fake_claude:` prefix, FakeClaude returns a default response (`"[FakeClaude] Task completed."`) without making any LLM calls.

**Use the default response when:** the test doesn't depend on specific agent behavior — e.g., testing UI elements, task list rendering, settings pages, modals, branch switching, navigation, or any feature where it doesn't matter *what* the agent says, only that a task exists.

**Advantages:**
- Simplest possible test — no command strings to construct
- Fast — instant responses, no real LLM calls

**How:** Call `start_task_and_wait_for_ready()` with a plain prompt (no `fake_claude:` prefix) — or with no prompt at all when the test only needs the workspace UI shell.

### FakeClaude commands (for controlled agent behavior)

If your test needs the agent to perform specific actions — e.g., writing files, running bash commands, calling tools, or asking user questions — use FakeClaude commands. These give you **deterministic, repeatable** agent behavior without any LLM calls.

**Use FakeClaude commands when:** the test asserts on specific agent output, tool usage, file changes, or any behavior that requires controlling what the agent does.

**How:** Prefix the prompt (or a follow-up `send_chat_message`) with `fake_claude:<command>` followed by a JSON argument in backticks.

### Available FakeClaude commands

| Command | Description | Example |
|---------|-------------|---------|
| `text` | Emit a text response | `fake_claude:text \`{"text": "Hello"}\`` |
| `write_file` | Write a file to disk | `fake_claude:write_file \`{"file_path": "hello.py", "content": "..."}\`` |
| `edit_file` | Edit a file (old_string → new_string) | `fake_claude:edit_file \`{"file_path": "f.py", "old_string": "...", "new_string": "..."}\`` |
| `bash` | Run a shell command | `fake_claude:bash \`{"command": "echo hello"}\`` |
| `todo_write` | Update the todo/plan list | `fake_claude:todo_write \`{"todos": [...]}\`` |
| `ask_user_question` | Ask the user a question (Q&A panel) | `fake_claude:ask_user_question \`{"questions": [...]}\`` |
| `multi_step` | Execute multiple commands sequentially | `fake_claude:multi_step \`{"steps": [...]}\`` |
| `parallel_tools` | Execute multiple tools in parallel | `fake_claude:parallel_tools \`{"tools": [...]}\`` |
| `warning` | Surface a warning message | `fake_claude:warning \`{"message": "..."}\`` |
| `start_background_task` | Arm a background task; the arming turn ends and the process lingers | `fake_claude:start_background_task \`{"trigger_path": "...", "reaction_text": "..."}\`` |
| `complete_background_task` | Inside a borrowed turn, complete an armed task inline mid-cycle | `fake_claude:complete_background_task \`{"task_id": "..."}\`` |

**Test-timed background completions.** `start_background_task` arms a background
task without completing it — the arming turn ends (its `result` is emitted) and
the process lingers. Pass `trigger_path` from a `FakeClaudeTrigger`
(`sculptor/testing/fake_claude_pause.py`) and call `trigger.fire()` when the test
wants completion: FakeClaude then emits `task_updated` + `task_notification`
followed by a scripted reaction cycle (`reaction_text` / `reaction_steps`),
without any user frame prompting it. To complete a task *during* a follow-up turn
instead (so the notification interleaves mid-cycle), put a
`complete_background_task` step with the same `task_id` in that turn's
`multi_step` script; its reaction cycle then runs after the turn finishes.

## CRITICAL: Use `/run-integration-test` to Run Tests

**You MUST use the `/run-integration-test` skill to run integration tests.** Do not run `pytest` or `just test-integration` directly — the skill handles background execution and timeout monitoring, which is required because integration tests can hang indefinitely on failure. Running in foreground will block you with no way to recover.

The `just test-integration` commands shown below are for **human developers only**. As an agent, always use `/run-integration-test` instead.

## Step-by-Step: Writing a New Test

### Step 1: Write the test file

Create your test file in `sculptor/tests/integration/frontend/`. Follow the patterns in the existing README at `sculptor/tests/integration/frontend/README.md`.

Key conventions:
- Use `sculptor_instance_: SculptorInstance` fixture for tests using the shared instance
- Use `sculptor_instance_factory_: SculptorInstanceFactory` for tests that need multiple Sculptor instances (e.g., restart tests)
- Use `@user_story("...")` decorator
- Use Playwright `expect()` for all assertions (auto-retrying)
- Access elements through the POM hierarchy, never raw `get_by_test_id()` in test code
- Use `only()` from `sculptor.foundation.itertools` when expecting exactly one element
- Read `docs/development/review/integration_tests.md` to avoid common anti-patterns (flaky sleeps, snapshot races, missing waits)

#### Minimal example (default response — no commands needed):

```python
"""Integration tests for my new feature."""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to verify my new feature works")
def test_my_feature(sculptor_instance_: SculptorInstance) -> None:
    """Test that my feature works correctly."""
    # No fake_claude: prefix — FakeClaude returns the default response.
    # The helper creates the workspace, sends the prompt as the first chat
    # message, and (by default) waits for the agent to finish.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="Do something",
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_messages().last).to_contain_text("Task completed")

    # ... your assertions on UI elements here ...
```

#### Minimal example (FakeClaude command — controlled behavior):

```python
"""Integration tests that require controlled agent behavior."""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to verify agent creates files correctly")
def test_agent_creates_file(sculptor_instance_: SculptorInstance) -> None:
    """Test that the agent creates a file and it appears in changes."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "def hello_world():\\n    print('hello world')\\n"
}`""",
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # ... your assertions on file changes here ...
```

#### Multi-step example (sequential commands):

```python
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "hello.py",
        "content": "def hello():\\n    print('hello')\\n"
      }
    },
    {
      "command": "bash",
      "args": {"command": "git add hello.py && git commit -m 'Add hello'"}
    }
  ]
}`""",
    )
```

### Step 2: Run the test

Use `/run-integration-test` to run your test:

```
/run-integration-test sculptor/tests/integration/frontend/test_my_feature.py
```

FakeClaude tests require no special setup — no API keys, no snapshot generation. They run deterministically every time.

### Step 3: Commit the test

```bash
git add sculptor/tests/integration/frontend/test_my_feature.py
```

## JSON Formatting Convention

When FakeClaude commands have complex JSON arguments (nested objects, arrays), use multiline strings for readability:

```python
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
    )
```

For simple single-field JSON, inline is fine:

```python
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Hello from FakeClaude"}`',
    )
```

## Troubleshooting

If a test fails, use the `/debug-integration-test` skill. It covers common failure modes (Playwright timeouts, element state issues), how to read test logs, and investigation strategies.
