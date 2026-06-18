## Overview

### High-level idea

Keep most code functional, immutable and stateless.

Pure (side-effect free) functions are easy to reason about, easy to test and naturally minimize coupling.

### Primitives

Avoid using primitive types directly. Create domain-specific classes that inherit from builtins.

The point is to create *meaningful* data types such that when a reader looks at the type signature of a function or object, it is obvious what type of data is being passed in, and that data should be guaranteed to be of the correct form.

If creating a primitive class, put it in `primitives.py`. If `primitives.py` becomes too large (> 500 lines), split it into a `primitives` module with separate files for different categories (e.g., `ids.py`, `strings.py`, `times.py`).

#### IDs

Always create a specific ID class for each type of object that has an ID by inheriting from the `ObjectID` class:

```python
from sculptor.primitives.ids import ObjectID


class TaskId(ObjectID):
    """Unique identifier for an agent task."""

    tag: str = "tsk"
```

#### File Paths

Always use `pathlib.Path` instead of `str` for file paths and directory paths:

```python
from pathlib import Path

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel


class EnvironmentConfig(FrozenModel):
    """Configuration for an agent environment."""

    workspace_directory: Path = Field(description="Directory for agent workspace")
    log_directory: Path = Field(description="Directory for agent logs")


def read_task_file(file_path: Path) -> str:
    """Read a task file and return its contents."""
    return file_path.read_text()
```

Using `Path` instead of `str` provides better type safety, clearer intent, and makes path operations more explicit and less error-prone.

#### Secrets

Always use `SecretStr` for any secret data:

```python
from pydantic import Field
from pydantic import SecretStr

from sculptor.foundation.pydantic_serialization import FrozenModel


class AgentCredentials(FrozenModel):
    """Credentials for authenticating an agent."""

    api_key: SecretStr = Field(description="API key for authentication")
    access_token: SecretStr = Field(description="Access token for services")
```

Unless otherwise stated, assume that secret data (API keys, tokens, passwords, etc.) will be accessible via `os.environ`.

### Exhaustive Pattern Matching

When branching on a finite set of cases, all possibilities must be handled explicitly with no implicit defaults.

**For enums, always use match statements.** The type checker can verify exhaustiveness at compile time.

**For complex conditions where match doesn't make sense,** use if/elif/else chains. All if/elif chains must end with an else clause. If the else case should never happen, raise an exception.

#### Match statements with assert_never (for enums)

Always use match statements when branching on enum values. Use `assert_never` from typing to enable the type checker to catch missing cases:

```python
from typing import assert_never


def get_status_message(status: TaskStatus) -> str:
    """Return a human-readable message for a task status."""
    match status:
        case TaskStatus.PENDING:
            return "Task is waiting to start"
        case TaskStatus.RUNNING:
            return "Task is in progress"
        case TaskStatus.COMPLETED:
            return "Task finished successfully"
        case TaskStatus.FAILED:
            return "Task encountered an error"
        case _ as unreachable:
            assert_never(unreachable)
```

If a new enum value is added, the type checker will report an error at every location where the enum is matched, forcing the developer to handle the new case.

#### If/elif/else with mandatory else clause

When you need complex conditional logic that cannot be expressed with match statements, use if/elif/else chains. The else clause is mandatory:

```python
from sculptor.foundation.errors import ImbueError


def categorize_task_urgency(task: Task, current_time: datetime) -> str:
    """Categorize a task based on multiple conditions."""
    age_hours = (current_time - task.created_at).total_seconds() / 3600

    if task.priority == TaskPriority.HIGH and age_hours > 24:
        return "critical_overdue"
    elif task.priority == TaskPriority.HIGH and age_hours <= 24:
        return "urgent_recent"
    elif task.priority == TaskPriority.MEDIUM and task.status == TaskStatus.RUNNING:
        return "in_progress"
    elif task.priority == TaskPriority.LOW and age_hours > 168:
        return "stale"
    else:
        raise ImbueError(
            f"Unhandled categorization case: priority={task.priority}, "
            f"age_hours={age_hours}, status={task.status}"
        )
```

Never write if/elif chains without a final else clause.

### Pure Functions

Prefer pure functions (no side effects) wherever possible. Almost all functions should be pure:

```python
from collections.abc import Sequence


def filter_completed_tasks(tasks: Sequence[Task]) -> tuple[Task, ...]:
    """Return only tasks that have completed successfully."""
    return tuple(t for t in tasks if t.status == TaskStatus.COMPLETED)


def sort_tasks_by_priority(tasks: Sequence[Task]) -> tuple[Task, ...]:
    """Sort tasks by priority (high to low)."""
    priority_order = {TaskPriority.HIGH: 0, TaskPriority.MEDIUM: 1, TaskPriority.LOW: 2}
    return tuple(sorted(tasks, key=lambda t: priority_order[t.priority]))
```

### Naming

- Use literal, concrete names (ex: `find_overdue_incomplete_todos`)
- Longer names are okay (ex: `filter_todos_by_priority_and_status_within_date_range`)
- Only use single-letter variables for extremely common cases (ex: `for i in range(10):`)
- Use only extremely common abbreviations (ex: `max`, `min`, `idx`, `tmp`, etc.). Otherwise spell the word out fully (ex: `approximate` instead of `approx`).

Prefix names of private variables (those not intended to be imported or used outside of a module) with `_`.

Try to make public module-scope variables globally unique.

#### Classes

In our functional programs, there are three conceptual categories of classes:

1. **Data classes (FrozenModel)**: Domain objects that fundamentally ARE their data--the "nouns" of the program
2. **Interfaces (ABC only, NOT models)**: Behavior contracts that define WHAT operations exist, not HOW they work
3. **Implementations**: Concrete classes that fulfill interface contracts and choose their own internal structure

**The key principle: interfaces define contracts, not data structures.**

##### Class Naming

* Name classes in [CamelCase](https://en.wikipedia.org/wiki/Camel_case). E.g. `TaskExecutor`.
  Acronyms can be fully capitalized: `HTTPClient`, not `HttpClient`.
* Don't use `__` prefixes ever (except for dunder methods).
  Python mangles `__*` names unexpectedly; use `_` prefix for private symbols instead.

##### Data Classes (FrozenModel)

Use `FrozenModel` for classes that fundamentally ARE their data. These are immutable domain objects:

```python
from functools import cached_property

from pydantic import Field
from pydantic import computed_field

from sculptor.foundation.pydantic_serialization import FrozenModel


class TaskResult(FrozenModel):
    """Result of executing an agent task."""

    task_id: TaskId = Field(description="Unique identifier for the task")
    status: TaskStatus = Field(description="Final status of the task")
    output: str = Field(description="Output produced by the task")
    error_message: str | None = Field(default=None, description="Error message if failed")

    @computed_field
    @cached_property
    def is_successful(self) -> bool:
        """Whether the task completed successfully."""
        return self.status == TaskStatus.COMPLETED

    def with_error(self, message: str) -> "TaskResult":
        """Return a copy with an error message."""
        return self.model_copy(update={"error_message": message, "status": TaskStatus.FAILED})
```

Instead of using `BaseModel` directly, use one of our canonical base classes:

* `sculptor.foundation.pydantic_serialization.SerializableModel`: Use by default. Serializable to/from JSON and immutable.
* `sculptor.foundation.pydantic_serialization.FrozenModel`: Use when data cannot fit into JSON (e.g., dict with non-string keys).

Always prefer immutable classes--they're much easier and safer to work with. You can "change" an immutable class with `model_copy(update={...})`.

Frozen objects should be contained in a file named `data_types.py` at the root of the package (helps avoid circular imports). If the file gets too large (> 500 lines), convert it to a `data_types` module.

**Import rules for `data_types.py`**: These files should only import from:
- The standard library
- Third-party libraries (such as `pydantic`)
- Other `data_types.py` files

##### Interface Classes

Interfaces define behavior contracts. They should inherit from `ABC` only.

```python
from abc import ABC
from abc import abstractmethod


class TaskExecutorInterface(ABC):
    """Contract for executing agent tasks."""

    @abstractmethod
    def execute(self, task: Task) -> TaskResult:
        """Execute a task and return the result."""

    @abstractmethod
    def cancel(self, task_id: TaskId) -> None:
        """Cancel a running task."""
```

If serialization is part of the contract, define it explicitly:

```python
from abc import ABC
from abc import abstractmethod
from typing import Self


class SerializableExecutorInterface(ABC):
    """Contract for a serializable task executor."""

    @abstractmethod
    def execute(self, task: Task) -> TaskResult:
        """Execute a task and return the result."""

    @abstractmethod
    def to_serializable(self) -> FrozenModel:
        """Return a serializable snapshot of this executor's state."""

    @classmethod
    @abstractmethod
    def from_serializable(cls, state: FrozenModel) -> Self:
        """Reconstruct an executor from serialized state."""
```

When possible, create "paired" method names in interfaces (e.g., if there's a `start` method, there should be a `stop` method). Use natural opposites (`start`/`stop` instead of `start`/`shutdown`).

Interface classes should be contained in a file named `interfaces.py` at the root of the package.

**Import rules for `interfaces.py`**: These files should only import from:
- The standard library
- Third-party libraries
- `data_types.py` files
- Other `interfaces.py` files

##### Implementation Classes

Implementations fulfill interface contracts. If convenient, inherit from a model class.

**Option A: Simple case where the class IS its serializable state**

```python
class SimpleTaskExecutor(FrozenModel, TaskExecutorInterface):
    """A simple executor where the class IS its serializable state."""

    config: ExecutorConfig = Field(description="Executor configuration")

    def execute(self, task: Task) -> TaskResult:
        """Execute the task using the configured settings."""
        return _run_task(task, self.config)

    def cancel(self, task_id: TaskId) -> None:
        """Cancel is not supported for simple executor."""
        raise NotImplementedError("Simple executor does not support cancellation")
```

**Option B: Complex case with transient state that shouldn't be serialized**

```python
class CachingTaskExecutor(TaskExecutorInterface):
    """An executor with caches and connections that shouldn't be serialized."""

    def __init__(self, config: ExecutorConfig) -> None:
        self._config = config
        self._cache: dict[TaskId, TaskResult] = {}
        self._connection = _create_connection(config)

    def execute(self, task: Task) -> TaskResult:
        """Execute the task, using cache if available."""
        if task.task_id in self._cache:
            return self._cache[task.task_id]
        result = _run_task(task, self._config)
        self._cache[task.task_id] = result
        return result

    def cancel(self, task_id: TaskId) -> None:
        """Cancel a running task."""
        self._connection.send_cancel(task_id)
```

Implementation classes should be contained within their own named module off of the root of the package (e.g., if the package is `agent` and the interface is `ExecutorInterface`, implementations go in `agent.executor`).

##### Additional Class Guidelines

* Use `@classmethod` only for factory functions (e.g. alternate constructors).
* Use `@staticmethod` only for satisfying a `Protocol` with a class object.
* *Don't* use `pydantic.BaseModel` for Exceptions--it's a footgun
* *Don't* use `pydantic.BaseSettings` unless loading values from environment variables
* *Don't* use `NamedTuple` or `dataclasses`--use pydantic models instead

#### Modules

Name modules using "snake_case".

Always prefix private modules with "_".

Never put any code in `__init__.py` files.

Always use absolute imports from the original definition.

### Comments

Prefer clear naming and semantically meaningful types over comments.

Create docstrings for public members; keep docstrings short. Never put type information in docstrings, use type annotations and function signatures.

For commonly used helpers, use doctests to document proper usage.

### Code Layout

Use `ruff` for formatting.

Avoid implicit string concatenation.

### Control Flow

Use early returns, `break` and `continue` to avoid deeply nested code.

* Prefer early exit over single return / deep nesting style. I.e.: prefer this
```python
for thing in things:
    if whatever:
        break
    if other:
        break
    thing.do_stuff()
```

over this:

```python
def thing(x):
    if not x.thing:
        if not x.other_thing:
            x.do_thing()

```

#### Exceptions

##### Handling Exceptions

Prefer "asking forgiveness" over "looking before you leap".

GOOD:
```python
def read_items(path: Path) -> list[Item]:
    try:
        f = path.open()
    except FileNotFoundError:
        return []
    with f:
        return [Item.parse(line) for line in f]
```

BAD:
```python
def read_items(path: Path) -> list[Item]:
    if not path.exists():
        return []
    with path.open() as f:
        return [Item.parse(line) for line in f]
```

Be conservative with which exceptions are caught. Prefer to crash instead of catching errors that you don't know what to do with.

Never swallow exceptions (i.e. just `pass` on them).
For example, do *not* do stuff like this:

BAD:
```python
try:
    os.unlink("file.txt")
    # raised when file does not exist
except OSError:
    pass
```

All sorts of crazy things could have happened in the above example, some of which you may actually want or need to deal with in a separate and well-defined way.

There are many reasons the `os.unlink` call might fail.
You might need to understand and handle them differently.
But at least, handle them in some way.
Just passing is generally lazy and unhelpful.
A permission error might indicate that the user should be
prompted so they can react differently than if the file is simply missing.
Permission errors, though, might manifest as a specific error code, rather than
a generic `OSError` exception.

*Never* use bare `except:` clauses! These are absolutely the worst.
Always name the exceptions being caught, ideally with extremely specific `except` clauses.

##### Defining and Raising Exceptions

**You should strongly consider defining custom exceptions pretty much whenever you want to raise an error.**

Think carefully about the exceptions you raise, and follow these guidelines:

* *Don't* raise builtin errors just because the name feels appropriate if the context doesn't fit (i.e. raising a `ReferenceError` or a `KeyError` from some database API).
* *Never* raise any builtin that might be handled further up the callstack, like `FileNotFoundError`.
* It's ok to inherit from builtins like `ValueError`, `KeyError`, or `IndexError` when the context makes sense.
  * "when it makes sense" does **not** mean "whenever you feel like it", but rather, if you are making a special type of dictionary, it's fine to raise some exception type that inherits from `KeyError` when a key is not found.
* *Avoid* raising or reraising 3rd party errors to avoid coupling. ie:
```python
  # good: calling code doesn't have to worry about 3rd party implementation detail
  except anthropic.APIConnectionError as e:
    raise TransientLanguageModelError() from e
```
* *Do* define custom exceptions whenever is sensible.
  Many `ValueErrors` and `RuntimeErrors` are good candidates.

Create a custom exception is easy:
```python
class ConfigValidationError(ValueError):
    pass
```

This makes interpreting and debugging errors much easier, and avoids builtin overuse.
Situations to almost certainly use a custom exception:
1. When the exception **should ever be caught**.
   This avoids requiring the handler to be overly broad.
2. When the exception type can be used to **convey more useful semantic information than a builtin type** (as in the above example).
3. When the exception **helps model the problem domain**.

As you can see, there are very good reasons to use custom exceptions.
They help us model problem domains, guarantee we catch the right error, and have nice decoupling properties.
It is highly unlikely that you will define too many of them.

##### Exception Chaining

**IMPORTANT**: Within an `except` clause, always use `raise ... from err` or `raise ... from None` when raising exceptions. Never use a bare `raise SomeException()` inside an except block.

Use `raise ... from e` to preserve the exception chain when the original exception is relevant:

```python
def load_task_config(config_path: Path) -> TaskConfig:
    """Load task configuration from a file."""
    try:
        raw_data = config_path.read_text()
    except OSError as e:
        raise TaskConfigError(f"Cannot read config file: {config_path}") from e
    try:
        parsed_data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        raise TaskConfigError(f"Invalid JSON in config file: {config_path}") from e
    return TaskConfig.model_validate(parsed_data)
```

Use `raise ... from None` to suppress the original exception when it's not relevant to the caller (e.g., implementation details):

```python
def parse_task_status(user_input: str) -> TaskStatus:
    """Parse a task status from user input."""
    try:
        return TaskStatus(user_input.upper())
    except ValueError:
        raise InvalidTaskStatusError(f"Invalid status: {user_input}") from None
```

### Typing

Include complete type hints.

Never use `dict` unless the keys are dynamic.

#### Immutable Input Types

Function *inputs* should be typed using immutable abstract types rather than mutable concrete types. This allows the type checker to catch accidental mutations of input data, which is almost always a mistake.

Use these immutable types for parameters:
- `Sequence[T]` instead of `list[T]`
- `Mapping[K, V]` instead of `dict[K, V]`
- `AbstractSet[T]` instead of `set[T]`

Return types should use concrete mutable types like `list` or `dict`, since the caller owns the returned value and may need to modify it.

```python
from collections.abc import Mapping
from collections.abc import Sequence


def find_tasks_by_status(
    tasks: Sequence[Task],  # Immutable input
    priority_by_status: Mapping[TaskStatus, int],  # Immutable input
) -> list[Task]:  # Concrete return type
    """Find tasks and sort by status priority."""
    return sorted(
        [t for t in tasks if t.status in priority_by_status],
        key=lambda t: priority_by_status[t.status],
    )
```

If something needs to be changed, return an updated copy instead of mutating the input.

Return types (that are not retained) should use concrete mutable types like `list` or `dict` since the caller now owns the returned value and may want to modify it.

When "modifying" input arguments return an updated copy instead of mutating the input.

### Frontend Style Guide

The detailed [Frontend Style Guide](./frontend.md) builds on the concepts within this document and describes some modifications and refinements suited for our frontend codebases. If you will be editing frontend code, please read that document as well.

### Markdown

Write documentation in Markdown format.

### Bash

Use bash _only_ for simple cases or when we do not yet have a python environment set up.

### Logging

Always use `loguru` for loggging.

#### Log Levels

Always use the right log level for your statement:

- logger.exception: use this to capture all unexpected exceptions. After calling this, just call "raise" to continue propagating the exception (since it is unexpected)
- logger.error: use this for unexpected error situations (where there is no Exception, otherwise use)
- logger.warning: use this for things that seem suspicious, but not worth crashing over (or you are in a part of the code that should not crash). These should be purged aggressively if ever seen in a log
- logger.info: Use this to describe what the application is doing at a high level. These messages are ideally something that would make sense to a user of the program. Info logs belong in CLI/user-facing code, not in library/API code
- logger.debug: Use this to describe how the application is doing it. These messages ideally make sense to the developer of the program. This is the primary level for library/API code
- logger.trace: Use this for detailed parameter values and state. These messages are disabled by default, and will generally only be used when debugging a specific problem

#### Log Placement Guidelines

The purpose of log statements is to tell a story to the reader about what is happening in the program. They help us understand program execution and debug issues.

**Log before actions, not after.** Place log statements immediately before the action they describe, not after. This ensures the log appears even if the action fails:

```python
from loguru import logger


def execute_task(executor: TaskExecutorInterface, task: Task) -> TaskResult:
    """Execute a task and return the result."""
    # Log BEFORE the action
    logger.debug("Executing task")
    result = executor.execute(task)
    logger.trace("Task completed with status={}", result.status)
    return result
```

**Do not log at function entry points.** Since logs are placed at the call site (before calling a function), the function itself should not log its own entry. The caller's log already describes what's about to happen.

**Reserve `logger.info` for CLI/user-facing code.** Library and API code should use `logger.debug` for normal operations:

```python
# In CLI code - info is appropriate
def cli_run_task(task_id: str) -> None:
    task = load_task(TaskId(task_id))
    result = execute_task(task)
    logger.info("Task {} completed with status {}", task_id, result.status)


# In library/API code - use debug instead
def execute_task(task: Task) -> TaskResult:
    logger.debug("Executing task")
    result = _run_task(task)
    logger.trace("Task id={} status={}", task.task_id, result.status)
    return result
```

**Do not log in tight loops or frequently-called functions.** Functions called very frequently should not log, even at TRACE level.

**No logs while idle.** Do not emit logs when nothing is happening. Logs should only appear when the program is actively doing something.

### Misc

* Never use `eval` or `exec` unless explicitly instructed to do so.
* Never use dataclasses or named tuples.
* Never use `async` or `asyncio`.

## Testing

Always use `pytest` for testing.

### Test File Organization

Tests are organized by scope, with low-level tests colocated with source code and higher-level tests in the `tests/` directory.

#### Colocated Tests (same directory as code under test)

1. **Unit tests** (`*_test.py`): Fast, isolated tests for single functions/methods
   - Example: `task_utils.py` -> `task_utils_test.py`

2. **Integration tests** (`test_*.py`): Tests for interactions within a component
   - Example: `test_task_execution.py` in the same directory as the task execution code

#### Higher-Level Tests (`tests/` directory at project root)

3. **End-to-end / Acceptance tests** (`tests/`): Full system tests organized by category
   - `tests/integration/` - Cross-component integration tests
   - `tests/acceptance/` - Full system tests, may make live requests
   - Example: `tests/acceptance/test_full_workflow.py`

### Test Function Naming

NEVER make classes just to contain test functions. Instead, create test functions with long, unique, descriptive names:

```python
def test_filter_completed_tasks_returns_only_tasks_with_completed_status() -> None:
    """Test that filter_completed_tasks returns only completed tasks."""
    tasks = (
        Task(task_id=TaskId.generate(), status=TaskStatus.COMPLETED),
        Task(task_id=TaskId.generate(), status=TaskStatus.PENDING),
        Task(task_id=TaskId.generate(), status=TaskStatus.COMPLETED),
    )

    result = filter_completed_tasks(tasks)

    assert len(result) == 2
    assert all(t.status == TaskStatus.COMPLETED for t in result)
```

### Test Quality Guidelines

- NEVER use `time.sleep()` in tests or production code. Use polling with timeouts instead. Better yet, use explicit communication (`queue.Queue`, `threading.Event`) if possible.
- ALWAYS use `uuid4().hex` to generate unique IDs for test data.
- NEVER use mocks unless explicitly instructed to do so--they make tests brittle.
- NEVER allow flaky or non-deterministic tests. Fix them until reliable.
- Unit tests must run quickly (< 5 seconds each, < 120 seconds total for suite).
- Integration tests should complete in < 120 seconds each.

### Snapshot Testing

Use "snapshot testing" with `inline-snapshot` to verify complex outputs:

```python
from inline_snapshot import snapshot


def test_format_task_output_shows_status_and_title() -> None:
    task = Task(
        task_id=TaskId.generate(),
        title="Complete documentation",
        status=TaskStatus.COMPLETED,
    )

    formatted = format_task_for_display(task)

    assert formatted == snapshot("[x] Complete documentation")
```

For large outputs that don't fit inline, save to a file and compare the hash:

```python
import hashlib

from inline_snapshot import snapshot


def test_export_tasks_to_json_produces_expected_output() -> None:
    tasks = create_large_task_list()
    exported_json = export_tasks_to_json(tasks)

    # Save snapshot for manual review
    snapshot_path = Path(__file__).parent / "snapshots" / "exported_tasks.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(exported_json)

    # Compare hash instead of full content
    content_hash = hashlib.sha256(exported_json.encode()).hexdigest()
    assert content_hash == snapshot(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
```
