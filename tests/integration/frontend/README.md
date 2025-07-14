# Frontend Integration Testing Guide

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
    return self.get_by_test_id(ElementTags.START_TASK_BUTTON)
```

The custom classes exist to:
- Group related functionality (e.g., all task starter operations in one place)
- Prevent raw `get_by_test_id()` calls in test code
- Provide a semantic interface for complex components

**Design Note**: POM classes should return locators or element objects, rather than perform actions themselves. Complex actions or wait logic should be implemented as helper functions or utilities, not as methods on Page or Element subclasses.

### Test ID Strategy

All test IDs are centralized in `sculptor/sculptor/testing/constants.py` in the `ElementTags` enum:

```python
class ElementTags(Serializable, StrEnum):
    # Home Page Elements
    TASK_STARTER = "TASK_STARTER"
    TASK_LIST = "TASK_LIST"
    TASK_INPUT = "TASK_INPUT"
    START_TASK_BUTTON = "START_TASK_BUTTON"

    # Chat Elements
    CHAT_PANEL = "CHAT_PANEL"
    CHAT_INPUT = "CHAT_INPUT"
    SEND_BUTTON = "SEND_BUTTON"
    # ... many more
```

Frontend components include these as `data-testid` attributes:
```tsx
// Example from a React component
<Button
    data-testid={ElementTags.START_TASK_BUTTON}
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

**Important**: Never access the internal locator attributes directly. Always call methods on the POM objects themselves - they will automatically route to the underlying locator. This maintains proper encapsulation and ensures the POM abstraction works correctly.

### Timeout Management

- **Default timeout**: Configured in `sculptor/conftest.py` - use this for all operations except task container building
- **BUILD_TIMEOUT_SECS**: Required when waiting for task container building:
  ```python
  expect(get_task_status_locator(task)).to_have_text("Ready", timeout=BUILD_TIMEOUT_SECS * 1000)
  ```
- Avoid defining custom and hardcoded timeouts unless absolutely necessary

### Element Access Hierarchy

**Important**: Always access elements through the POM hierarchy. Never use raw `get_by_test_id()` calls in test code - if you need access to an element that doesn't have a getter, add a method to the parent POM class (or create it):
```python
# Correct approach
home_page = PlaywrightHomePage(page=sculptor_page_)
task_starter = home_page.get_task_starter()
task_starter.get_task_input().type("Hello")

# Avoid direct access
home_page.get_by_test_id("TASK_INPUT").type("Hello")  # Don't do this
```

### Selecting Single Elements

When you expect exactly one element and need to work with it, use `only()` from `imbue_core.itertools` rather than `.first` or indexing. This makes the test's expectations explicit and will fail clearly if the assumption is violated.

## How to Write a New Integration Test

### Reference Patterns

You can see examples of different testing scenarios:
- `test_home_page.py::test_initial_load` - Verifies the home page starts with no tasks
- `test_chat_page.py::test_starting_text` - Tests that task text appears in chat after navigation
- `test_send_messages.py::test_send_multiple_messages` - Tests sending multiple messages in a conversation
- `test_chat_page.py::test_system_prompt` - Tests system prompt modification and its effect on responses

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
delete_menu_item = task.page.get_by_test_id(ElementTags.DELETE_MENU_ITEM)
```

This is handled in helper functions like `delete_task()` in `sculptor/testing/elements/task.py`.

## When to Extend the POM

Consider adding new element classes when you encounter major page components with multiple child elements (like the chat panel or task starter). For simple elements, returning raw Locators is fine.

Add new methods to page or element classes when you need to access an element that doesn't have a getter method.

## Key Principles

- **Semantic access**: Always go through page and element objects rather than raw selectors
- **Proper waits**: Use `expect()` for all waiting and assertions
- **Test isolation**: Each test should work independently
- **One test, one feature**: Each test should verify a single piece of functionality
- **Readability**: Tests should read like user stories

When writing new tests, try to match the existing patterns as closely as possible. If you deviate from any patterns that are held across existing tests, there should be a strong reason why you are doing so.
