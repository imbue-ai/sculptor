# Frontend Integration Testing Guide

This is a very important guide on rules to follow when writing tests. You should read over this carefully before writing any tests.

## Core Architecture: Page Object Model (POM)

Our integration testing structure uses a POM: HTML pages and elements are represented using classes that **subclass Playwright's native `Page` and `Locator` objects**. This inheritance gives you full access to Playwright's methods while providing our semantic abstractions.

### Key Classes and Structure

**Page Classes** (found in `sculptor/sculptor/testing/pages/`):
- Base class: `PlaywrightIntegrationTestPage` - Wraps Playwright's `Page`
- Concrete implementations provide semantic access to page elements

**Element Classes** (found in `sculptor/sculptor/testing/elements/`):
- Base class: `PlaywrightIntegrationTestElement` - Wraps Playwright's `Locator`
- Concrete implementations group related functionality for complex UI components

**Simple Elements**: Many methods return raw `Locator` objects for basic elements:
```python
def get_start_button(self) -> Locator:
    return self.get_by_test_id(ElementIDs.START_TASK_BUTTON)
```

The custom classes exist to:
- Group related functionality (e.g., all task starter operations in one place)
- Prevent raw `get_by_test_id()` calls in test code
- Provide a semantic interface for complex components

### Test IDs

All test IDs are centralized in `sculptor/sculptor/constants.py` in the `ElementIDs` enum (a `StrEnum`):

Frontend components include these as `data-testid` attributes:
```tsx
// Example from a React component
<Button
    data-testid="START_TASK_BUTTON"
    onClick={handleStart}
>
    Start Task
</Button>
```

**Warning**: Be careful where you place the `data-testid` attribute. If it's on a component that doesn't directly render HTML (like a higher-level React component), the test ID might not appear in the final HTML.

## Critical Testing Patterns

### Fixture Imports

Import fixtures explicitly with `# noqa: F401` comments. This helps with IDE navigation since some setups don't automatically recognize fixtures from conftest files.

### Use `expect()` for Assertions and Waits

The `expect()` pattern is the standard way to handle assertions and waiting:

```python
# Always use expect
expect(tasks).to_have_count(1)
expect(chat_input).to_have_text("")
expect(user_messages.nth(0)).to_have_text("Hello")
expect(last_message).to_contain_text(signal_word)
```

Avoid using Python's `assert` statements or manual wait loops unless there's an exceptional reason. Both `PlaywrightIntegrationTestElement` and `PlaywrightIntegrationTestPage` inherit from Playwright's classes, so all Playwright methods work seamlessly.

### Timeout Management

- **Default `expect()` timeout**: Configured in `sculptor/tests/integration/frontend/conftest.py` via the `configure_expect_timeout` autouse fixture — 30 seconds by default.
- **Task/agent wait helpers**: Use `start_task_and_wait_for_ready()` from `sculptor.testing.playwright_utils` to create a workspace + agent and wait until the chat panel is ready, then `wait_for_completed_message_count()` from `sculptor.testing.elements.chat_panel` to wait for the agent's turn to finish — instead of writing manual timeout logic. `start_task_and_wait_for_ready` uses generous explicit timeouts (60s) for the slow workspace-clone / environment-setup steps; `wait_for_completed_message_count` uses the default 30s `expect()` timeout (overridable per call for long multi-step prompts).
- Avoid defining custom and hardcoded timeouts unless absolutely necessary.

### Element Access Hierarchy

**Important**: Always access elements through the POM hierarchy. Never use raw `get_by_test_id()` calls in test code - if you need access to an element that doesn't have a getter, add a method to the parent POM class (or create it):
```python
# Correct approach
task_starter = sculptor_instance_.get_task_starter()
task_starter.get_task_input().type("Hello")

# Avoid direct access
sculptor_instance_.page.get_by_test_id("TASK_INPUT").type("Hello")  # Don't do this
```

### User Story Decorator

Tests should use the `@user_story("...")` decorator to document what user-facing behavior the test validates:
```python
from sculptor.testing.user_stories import user_story

@user_story("to see changes in the agent's code")
def test_artifact_panel_diff_tab_basic(sculptor_instance_: SculptorInstance) -> None:
    ...
```


## How to Write a New Integration Test

### Reference Patterns

You can see examples of different testing scenarios:
- `test_homepage_task_list.py::test_initial_load` - Verifies the home page starts with no tasks
- `test_task_page_chatting.py::test_starting_text` - Tests that task text appears in chat after navigation
- `test_task_page_chatting.py::test_send_multiple_messages` - Tests sending multiple messages in a conversation
- `test_homepage_system_prompt.py::test_system_prompt_from_home_page` - Tests system prompt modification and its effect on responses
- `test_settings_integration.py` - Tests that don't require the agent (no snapshot needed)

## Important Implementation Details

### Lazy Locator Evaluation

Playwright locators are lazy - they don't search the DOM until you interact with them. This means you can create locators once and reuse them throughout your test:

```python
tasks = task_list.get_tasks()  # Creates locator, doesn't search yet
expect(tasks).to_have_count(0)  # First DOM search
# ... user creates a task ...
expect(tasks).to_have_count(1)  # Same locator, fresh search
```

### Elements Outside Their Parent

Some elements (dropdowns, dialogs, modals) render at the page level, not within their parent component:
```python
# Note: using task.page instead of task
delete_menu_item = task.page.get_by_test_id(ElementIDs.DELETE_MENU_ITEM)
```

## When to Extend the POM

Consider adding new element classes when you encounter major page components with multiple child elements (like the chat panel or task starter). For simple elements, returning raw Locators is fine.

Add new methods to page or element classes when you need to access an element that doesn't have a getter method.

## Key Principles

- **Proper waits**: Use `expect()` for all waiting and assertions
- **One test, one feature**: Each test should verify a single piece of functionality
- **Readability**: Tests should read like user stories
- **POM encapsulation**: Never access internal locator attributes directly — call methods on POM objects, which auto-route to the underlying locator
- **POM returns data, helpers perform actions**: POM classes should return locators or element objects. Complex actions or wait logic should be helper functions or utilities, not methods on Page or Element subclasses
- **Minimal code changes**: Avoid modifying frontend or backend code in ways that could affect actual functionality. Changes should be isolated to the testing setup as much as possible
- **Use `only()`**: When you expect exactly one element and need to work with it, use `only()` from `imbue_core.itertools` rather than `.first` or indexing. This makes the test's expectations explicit and will fail clearly if the assumption is violated
- **Match existing patterns**: When writing new tests, try to match the existing patterns as closely as possible. If you deviate, there should be a strong reason why

## Running Tests

**CRITICAL: If you are a Claude/Sculptor agent, you MUST use the `/run-integration-test` skill to run integration tests.** Do not run `pytest` or `just test-integration` directly — the skill handles background execution and timeout monitoring, which is required because integration tests can hang indefinitely on failure. Running in foreground will block you with no way to recover.

The Justfile contains the default flags for integration testing as part of the `test-integration` command. Here are some custom arguments you can include:
- `--headed`: Runs the tests with a browser window open. This is the same browser window the test itself interfaces with.
- `-n <N>`: Runs tests with N parallel workers (uses pytest-xdist). By default, tests run sequentially.

Here are some example test commands:
```bash
# Run a specific test with browser visible
just test-integration "sculptor/tests/integration/frontend/test_task_page_chatting.py::test_send_multiple_messages" "--headed"

# Run all tests with no parallelism (default behavior)
just test-integration

# Run with 4 parallel workers
just test-integration "sculptor/tests/integration/" "-n 4"
```
