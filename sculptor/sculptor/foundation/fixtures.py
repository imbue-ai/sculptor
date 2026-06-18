"""These fixtures make it easy to mock out the loguru logger and git repos in tests"""

import tempfile
from pathlib import Path
from typing import Any
from typing import AsyncGenerator
from typing import Generator
from unittest.mock import Mock

import pygit2
import pytest
from pygit2 import Repository
from pytest_mock import MockerFixture


@pytest.fixture
def mock_loguru_log(mocker: MockerFixture) -> Generator[Mock, None, None]:
    """Mock out the loguru logger for testing.

    The returned mock exposes a get_errors() helper for retrieving error-level log lines.
    """
    mock = mocker.patch("loguru.logger._log")
    mock.get_errors = lambda: get_loglines_at_level(mock, "error")
    yield mock


@pytest.fixture
async def empty_temp_git_repo() -> AsyncGenerator[Path, None]:
    """Create an empty temporary git repository with user config."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "git_repo"
        repo_path.mkdir()

        # Initialize git repo
        repo = pygit2.init_repository(str(repo_path))

        # Configure git user
        config = repo.config
        config["user.name"] = "Test User"
        config["user.email"] = "test@example.com"

        yield repo_path


@pytest.fixture
async def initial_commit_repo(empty_temp_git_repo: Path) -> AsyncGenerator[tuple[Path, str], None]:
    """Add an initial commit to an empty git repository."""
    repo_path = empty_temp_git_repo
    repo = Repository(str(repo_path))

    # Force HEAD to track "main"
    repo.set_head("refs/heads/main")

    first_file = repo_path / "file1.txt"
    first_file.write_text("Content 1")

    repo.index.add("file1.txt")
    repo.index.write()
    tree = repo.index.write_tree()

    signature = pygit2.Signature("Test User", "test@example.com")
    first_commit = repo.create_commit("HEAD", signature, signature, "First commit", tree, [])
    first_commit_hash = str(first_commit)

    yield repo_path, first_commit_hash


def get_loglines_at_level(mock_loguru_log: Mock, level: str) -> list[Any]:
    return [call for call in mock_loguru_log.mock_calls if len(call.args) > 1 and str(call.args[0]).lower() == level]
