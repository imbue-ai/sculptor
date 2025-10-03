import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest
from loguru import logger
from xdist import get_xdist_worker_id
from xdist import is_xdist_worker

from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import GitCommitSnapshot
from sculptor.testing.git_snapshot import RemoteGitRepoSnapshot
from sculptor.testing.mock_repo import MockRepoState

INITIAL_REPO_CONTENTS = {
    ".gitignore": "node_modules\n",
    "README.md": "# Test Project\n\nThis is a test project\n",
}
FILE_CONTENTS_FOR_COMMIT_1 = {
    "data/something.txt": "some data\n",
    "src/main.py": "print('hello world')\nprint('goodbye')\n",
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
def generate_test_project_repo(request: pytest.FixtureRequest) -> Generator[MockRepoState, None, None]:
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
        repo = MockRepoState.build_locally(state=initial_state, local_dir=repo_dir)
        subprocess.run(["git", "remote", "add", "origin", str(repo_dir)])
        yield repo


# REMOTE REPO: clones a remote repo. It takes longer, and by default you should use the
# local one above instead (though that won't work with sandboxed commands until we've fixed that part up)
@contextmanager
def test_project_repo() -> Generator[MockRepoState, None, None]:
    with tempfile.TemporaryDirectory() as tempdir:
        logger.info("Creating test project repo in {}", str(tempdir))
        initial_state = RemoteGitRepoSnapshot(
            git_repo_url="https://gitlab.com/generally-intelligent/blackberry-projects/test_project",
            git_branch="main",
            git_hash="6aa65979bf0dae50b8417e8ba7df584cb2a65a09",
            git_user_email="imbue@imbue.com",
            git_user_name="imbue",
            git_diff=None,
        )
        repo = MockRepoState.build_from_remote(state=initial_state, local_dir=Path(tempdir))
        yield repo
