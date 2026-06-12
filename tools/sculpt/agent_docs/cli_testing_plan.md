# Sculpt CLI Testing Plan

## Overview

Two testing layers:
1. **Unit tests** - Mock HTTP client, test CLI logic in isolation
2. **VCR tests** - Record/replay HTTP interactions for realistic integration testing

## Directory Structure

```
sculpt/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_client_up_to_date.py  # Existing
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_create_task.py
│   │   ├── test_create_project.py
│   │   ├── test_list.py
│   │   ├── test_show.py
│   │   └── test_projects.py
│   └── vcr/
│       ├── __init__.py
│       ├── cassettes/           # Recorded HTTP interactions
│       │   ├── test_list_tasks.yaml
│       │   ├── test_show_task.yaml
│       │   └── ...
│       ├── conftest.py          # VCR configuration
│       ├── test_list.py
│       ├── test_show.py
│       └── README.md            # Instructions for re-recording
```

## Unit Tests

### Approach

Use `typer.testing.CliRunner` with mocked HTTP responses via `respx` (httpx mock library).

### Fixtures (`tests/conftest.py`)

```python
import pytest
from typer.testing import CliRunner

@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()

@pytest.fixture
def mock_session_token() -> str:
    return "test-session-token-12345"

@pytest.fixture
def mock_project() -> dict:
    return {
        "objectId": "prj_test123",
        "name": "test-project",
        "userGitRepoUrl": "https://github.com/test/repo",
    }

@pytest.fixture
def mock_task() -> dict:
    return {
        "id": "tsk_abc123def456",
        "title": "Test task",
        "titleOrSomethingLikeIt": "Test task title",
        "status": "RUNNING",
        "taskStatus": "RUNNING",
        "model": "CLAUDE_4_SONNET",
        "interface": "TERMINAL",
        "createdAt": "2024-01-15T10:30:00Z",
        "updatedAt": "2024-01-15T10:35:00Z",
        "projectId": "prj_test123",
        "parentId": None,
        "isArchived": False,
        "isDeleted": False,
        "artifactNames": [],
    }
```

### Test Cases per Command

**`create-task`**
- Success case
- Invalid model name
- Connection error
- No projects found
- Validation error from server

**`create-project`**
- Success case (table output)
- Success case (JSON output)
- Connection error
- Validation error (invalid path)

**`list`**
- Success with tasks
- Success with no tasks
- Filter by status
- Include archived
- JSON output
- Invalid status filter
- Connection error

**`show`**
- Success case
- Task not found
- Ambiguous task ID (prefix matches multiple)
- JSON output

**`projects`**
- Success with projects
- Success with no projects
- JSON output
- Connection error

### Example Unit Test

```python
# tests/unit/test_list.py
import respx
from httpx import Response
from typer.testing import CliRunner

from sculpt.main import app

@respx.mock
def test_list_tasks_success(cli_runner: CliRunner, mock_project: dict, mock_task: dict):
    # Mock session token endpoint
    respx.get("http://localhost:5050/api/v1/session-token").mock(
        return_value=Response(204, headers={"set-cookie": "x-session-token=test123"})
    )
    # Mock projects endpoint
    respx.get("http://localhost:5050/api/v1/projects").mock(
        return_value=Response(200, json=[mock_project])
    )
    # Mock tasks endpoint
    respx.get(f"http://localhost:5050/api/v1/projects/{mock_project['objectId']}/tasks").mock(
        return_value=Response(200, json=[mock_task])
    )

    result = cli_runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "tsk_abc123d" in result.output  # Truncated ID
    assert "RUNNING" in result.output

@respx.mock
def test_list_tasks_connection_error(cli_runner: CliRunner):
    respx.get("http://localhost:5050/api/v1/session-token").mock(side_effect=Exception("Connection refused"))

    result = cli_runner.invoke(app, ["list"])

    assert result.exit_code == 1
    assert "Error" in result.output
```

## VCR Tests

### Setup

Add `pytest-recording` (or `vcrpy` with `pytest-vcr`) to dev dependencies:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-recording>=0.13.0",  # VCR for pytest
    "respx>=0.21.0",             # For unit test mocking
]
```

### VCR Configuration (`tests/vcr/conftest.py`)

```python
import pytest

@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [
            ("x-session-token", "REDACTED"),
            ("cookie", "REDACTED"),
            ("set-cookie", "x-session-token=REDACTED"),
        ],
        "record_mode": "none",  # Default: replay only, fail if no cassette
        "cassette_library_dir": "tests/vcr/cassettes",
        "match_on": ["method", "path", "query"],
    }
```

### Recording Cassettes

Create a script or document the process:

```bash
# tests/vcr/README.md content:

# Re-recording VCR Cassettes

To re-record all cassettes:

1. Start a local Sculptor server:
   cd sculptor && just start

2. Create test fixtures (project, tasks) via UI or CLI

3. Run tests in record mode:
   cd sculpt
   VCR_RECORD_MODE=all uv run pytest tests/vcr/ -v

4. Review and commit updated cassettes

Note: Cassettes are sanitized to remove session tokens.
```

### Example VCR Test

```python
# tests/vcr/test_list.py
import pytest
from typer.testing import CliRunner

from sculpt.main import app

@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()

@pytest.mark.vcr()
def test_list_tasks_recorded(cli_runner: CliRunner):
    """Test list command against recorded HTTP responses."""
    result = cli_runner.invoke(app, ["list", "--base-url", "http://localhost:5050"])

    assert result.exit_code == 0
    # Assertions based on recorded data

@pytest.mark.vcr()
def test_list_tasks_json_recorded(cli_runner: CliRunner):
    """Test list --json against recorded HTTP responses."""
    result = cli_runner.invoke(app, ["list", "--json", "--base-url", "http://localhost:5050"])

    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert isinstance(data, list)
```

## Running Tests

```bash
# All tests
cd sculpt && uv run pytest

# Unit tests only
uv run pytest tests/unit/

# VCR tests only
uv run pytest tests/vcr/

# Re-record VCR cassettes
VCR_RECORD_MODE=all uv run pytest tests/vcr/ -v
```

## Implementation Order

1. Add `respx` and `pytest-recording` to dev dependencies in `pyproject.toml`
2. Create `tests/conftest.py` with shared fixtures
3. Create `tests/unit/` directory with unit tests for each command
4. Create `tests/vcr/` directory with VCR configuration
5. Create `tests/vcr/README.md` with re-recording instructions
6. Record initial cassettes against local server
7. Add VCR tests

## Success Criteria

- All unit tests pass without network access
- VCR tests pass in replay mode
- `just check` passes from sculptor/
- Clear instructions exist for re-recording cassettes
