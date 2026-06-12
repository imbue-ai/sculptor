import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest
from loguru import logger
from xdist import get_xdist_worker_id
from xdist import is_xdist_worker

from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import GitCommitSnapshot
from sculptor.testing.mock_repo import MockRepoState

INITIAL_REPO_CONTENTS = {
    ".gitignore": "node_modules\n",
    "README.md": "# Test Project\n\nThis is a test project\n",
}
FILE_CONTENTS_FOR_COMMIT_1 = {
    "data/something.txt": "some data\n",
    "src/main.py": "print('hello world')\nprint('goodbye')\n",
    # 75-line helper module used to create a two-hunk vs-target-branch diff in tests.
    # The file is long enough that after HEAD shortens it, Pierre's context-expansion
    # loop accesses indices beyond HEAD's length, triggering the renderHunks crash.
    "src/helpers.py": "# Helper utilities for the project.\n\n\ndef add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n\n\ndef multiply(a, b):\n    return a * b\n\n\ndef divide(a, b):\n    if b == 0:\n        return None\n    return a / b\n\n\ndef square(n):\n    return n * n\n\n\ndef cube(n):\n    return n * n * n\n\n\ndef is_even(n):\n    return n % 2 == 0\n\n\ndef is_odd(n):\n    return n % 2 != 0\n\n\ndef clamp(value, min_val, max_val):\n    return max(min_val, min(max_val, value))\n\n\ndef reverse_string(s):\n    return s[::-1]\n\n\ndef count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n\n\ndef flatten(nested):\n    return [item for sublist in nested for item in sublist]\n\n\ndef unique(lst):\n    seen = set()\n    result = []\n    for item in lst:\n        if item not in seen:\n            seen.add(item)\n            result.append(item)\n    return result\n\n\ndef chunk(lst, size):\n    return [lst[i:i + size] for i in range(0, len(lst), size)]\n\n\ndef format_name(first, last):\n    return f'{first} {last}'\n\n\ndef truncate(text, max_length):\n    if len(text) <= max_length:\n        return text\n    return text[:max_length - 3] + '...'\n",
}
NEW_REPO_BASE_BRANCH_NAME = "main"


def get_test_project_state() -> FullLocalGitRepo:
    return FullLocalGitRepo(
        # FIXME: currently our tests rely on this being the same as the user name so commit hashes are stable
        #  for tests the username is in ServerSettings and is product@imbue.com
        #  We need to fix this in the backend code so that the user's username is used for commits they make
        git_user_email="product@imbue.com",
        git_user_name="imbue",
        git_diff=None,
        git_branch=NEW_REPO_BASE_BRANCH_NAME,
        main_history=(
            GitCommitSnapshot(
                contents_by_path=INITIAL_REPO_CONTENTS,
                commit_message="initial commit",
                commit_time="2025-01-01T00:00:01",
            ),
            GitCommitSnapshot(
                contents_by_path=FILE_CONTENTS_FOR_COMMIT_1,
                commit_message="add some cool data",
                commit_time="2025-01-01T00:00:01",
            ),
        ),
    )


@contextmanager
def generate_test_project_repo(
    request: pytest.FixtureRequest, concurrency_group: ConcurrencyGroup
) -> Generator[MockRepoState, None, None]:
    """
    Faster test setup for local sync. Doesn't need to push to the remote repo, and so we can cache the repo more aggressively.
    """
    with tempfile.TemporaryDirectory() as tempdir:
        initial_state = get_test_project_state()
        test_project_name = (
            "test_project" if not is_xdist_worker(request) else "test_project_" + get_xdist_worker_id(request)
        )
        repo_dir = Path(tempdir) / test_project_name
        logger.info("Creating test project repo in {}", str(repo_dir))
        repo = MockRepoState.build_locally(
            state=initial_state, local_dir=repo_dir, concurrency_group=concurrency_group
        )
        subprocess.run(["git", "remote", "add", "origin", str(repo_dir)])
        yield repo
