# Testing

## Test Organization

| Type              | Location                       | Naming      |
|-------------------|--------------------------------|-------------|
| Unit tests        | Colocated with source          | `*_test.py` |
| Integration tests | `sculptor/tests/integration/`  | `test_*.py` |

## Running Tests

```bash
just test-unit              # All unit tests (backend, frontend, imbue_core, sculpt CLI)
just test-unit-backend      # Backend only
just test-unit-offload      # Backend on Offload/Modal — use when local CPU is busy or chasing local flakes (see .sculptor/testing.md)
just test-unit-frontend     # Frontend only
just test-integration       # All integration tests
```

For specific integration tests:

```bash
just test-integration "sculptor/tests/integration/frontend/test_task_page_chatting.py::test_send_multiple_messages"
just test-integration "sculptor/tests/integration/frontend/test_task_page_chatting.py" "--headed"  # with browser
XDIST_WORKERS=4 just test-integration "sculptor/tests/integration/"  # override parallel workers (default: -n auto, capped at 3)
```

## Integration Tests

Uses Playwright with a Page Object Model (POM) architecture.

### Key Concepts

- **Page classes** (`sculptor/sculptor/testing/pages/`): wrap Playwright's `Page`
- **Element classes** (`sculptor/sculptor/testing/elements/`): wrap Playwright's `Locator`
- **Test IDs**: centralized in `sculptor/sculptor/constants.py` (`ElementIDs` enum), used as `data-testid` attributes

### Rules

- Always access elements through POM hierarchy — never raw `get_by_test_id()` in tests
- Use `expect()` for assertions and waiting — not Python `assert` or manual loops
- Use `@user_story("...")` decorator to document what the test validates
- Use `wait_for_tasks_to_build()` / `wait_for_tasks_to_finish()` helpers
- One test, one feature

See [docs/development/review/integration_tests.md](review/integration_tests.md) for detailed anti-patterns with examples (flaky assertions, timeout rules, test isolation).
