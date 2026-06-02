from datetime import datetime
from pathlib import Path
from typing import Self

import attr
from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.git_data_types import CommitTimestamp
from sculptor.testing.computing_environment import create_reset_and_checkout_branch
from sculptor.testing.computing_environment import get_branch_name
from sculptor.testing.computing_environment import make_commit
from sculptor.testing.computing_environment import switch_branch
from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import create_repo_from_snapshot
from sculptor.testing.local_git_repo import LocalGitRepo


@attr.s(auto_attribs=True)
class MockRepoState:
    """A thin wrapper around LocalGitRepo making relevant operations readily visible.
    Feel free to use any of the other LocalGitRepo methods directly if needed.
    """

    repo: LocalGitRepo

    @classmethod
    def build_locally(cls, state: FullLocalGitRepo, local_dir: Path, concurrency_group: ConcurrencyGroup) -> Self:
        assert state.git_diff is None
        repo = create_repo_from_snapshot(
            full_repo=state, destination_path=local_dir, concurrency_group=concurrency_group
        )
        return cls(repo=repo)

    @property
    def base_path(self) -> Path:
        return self.repo.base_path

    def write_file(self, path: Path | str, content: str | None) -> None:
        logger.info("Writing file {} with content {}", path, content)
        if content is None:
            Path(self.repo.base_path / path).unlink()
        else:
            Path(self.repo.base_path / path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.repo.base_path / path).write_text(content)
        logger.info("Wrote file {} with content {}", path, content)

    def commit(self, message: str, commit_time: str | datetime | CommitTimestamp | None = None) -> None:
        make_commit(self.repo, commit_message=message, allow_empty=True, commit_time=commit_time)

    def stage_all_changes(self) -> None:
        self.repo.run_git(("add", "."))

    def create_reset_and_checkout_branch(self, branch_name: str) -> None:
        create_reset_and_checkout_branch(self.repo, branch_name)

    def get_current_branch_name(self):
        return get_branch_name(self.repo)

    def checkout_branch(self, branch_name: str) -> None:
        """Switch to an existing branch."""
        switch_branch(self.repo, branch_name)

    def get_branches(self) -> list[str]:
        return self.repo.run_git(("branch", "--list", "--format=%(refname:short)")).splitlines()
