from pathlib import Path
from typing import Generator

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.testing.repo_resources import generate_test_project_repo


@pytest.fixture
def mock_repo_path(
    request: pytest.FixtureRequest, test_root_concurrency_group: ConcurrencyGroup
) -> Generator[Path, None, None]:
    with generate_test_project_repo(request, test_root_concurrency_group) as repo:
        yield repo.base_path


@pytest.fixture
def test_user_email() -> str:
    return "test@imbue.com"
