from datetime import datetime
from pathlib import Path
from typing import Self

import attr
from loguru import logger

from imbue_core.git_data_types import CommitTimestamp
from sculptor.testing.computing_environment import apply_patch_via_git
from sculptor.testing.computing_environment import create_reset_and_checkout_branch
from sculptor.testing.computing_environment import get_branch_name
from sculptor.testing.computing_environment import git_push
from sculptor.testing.computing_environment import make_commit
from sculptor.testing.computing_environment import switch_branch
from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import RemoteGitRepoSnapshot
from sculptor.testing.git_snapshot import checkout_repo_from_snapshot
from sculptor.testing.git_snapshot import create_repo_from_snapshot
from sculptor.testing.local_git_repo import LocalGitRepo


@attr.s(auto_attribs=True)
class MockRepoState:
    """A thin wrapper around LocalGitRepo making relevant operations readily visible.
    Feel free to use any of the other LocalGitRepo methods directly if needed.
    """

    repo: LocalGitRepo

    @classmethod
    def build_from_remote(cls, state: RemoteGitRepoSnapshot, local_dir: Path) -> Self:
        assert state.git_diff is None
        repo = checkout_repo_from_snapshot(repo_snapshot=state, destination_path=local_dir)
        repo.run_git(("fetch", "--unshallow"))
        switch_branch(repo, state.git_branch)
        return cls(repo=repo)

    @classmethod
    def build_locally(cls, state: FullLocalGitRepo, local_dir: Path) -> Self:
        assert state.git_diff is None
        repo = create_repo_from_snapshot(full_repo=state, destination_path=local_dir)
        return cls(repo=repo)

    @property
    def base_path(self) -> Path:
        return self.repo.base_path

    def write_secrets_file(self, secrets: dict[str, str]) -> None:
        """write secrets to .env file"""
        secrets_str = "\n".join(f"{k}='{v}'" for k, v in secrets.items())
        Path(self.repo.base_path / ".env").write_text(secrets_str)

    def write_file(self, path: Path | str, content: str | None) -> None:
        logger.info("Writing file {} with content {}", path, content)
        if content is None:
            Path(self.repo.base_path / path).unlink()
        else:
            Path(self.repo.base_path / path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.repo.base_path / path).write_text(content)
        logger.info("Wrote file {} with content {}", path, content)

    def apply_patch(self, patch: str) -> None:
        apply_patch_via_git(self.repo, git_diff=patch, is_error_logged=True)

    def commit(self, message: str, commit_time: str | datetime | CommitTimestamp | None = None) -> None:
        make_commit(self.repo, commit_message=message, allow_empty=True, commit_time=commit_time)

    def reset(self) -> None:
        self.repo.run_git(("reset", "--hard"), cwd=self.base_path)

    def clean(self) -> None:
        """Remove untracked files and directories."""
        self.repo.run_git(("clean", "-fd"), cwd=self.base_path)

    def stage_all_changes(self) -> None:
        self.repo.run_git(("add", "."))

    def push_to_remote(self) -> None:
        git_push(self.repo, branch_name=get_branch_name(self.repo))

    def create_reset_and_checkout_branch(self, branch_name: str) -> None:
        create_reset_and_checkout_branch(self.repo, branch_name)

    def get_current_branch_name(self):
        return get_branch_name(self.repo)

    def checkout_branch(self, branch_name: str) -> None:
        """Switch to an existing branch."""
        switch_branch(self.repo, branch_name)

    def pull(self, remote: str, branch: str | None = None) -> None:
        """Pull from a remote repository."""
        if branch:
            self.repo.run_git(("pull", remote, branch))
        else:
            self.repo.run_git(("pull", remote))

    def push(self, remote: str, branch: str | None = None) -> None:
        """Push to a remote repository."""
        if branch:
            self.repo.run_git(("push", remote, branch))
        else:
            self.repo.run_git(("push", remote))

    def delete_branch(self, branch_name: str, force: bool = False) -> None:
        """Delete a local branch."""
        if force:
            self.repo.run_git(("branch", "-D", branch_name))
        else:
            self.repo.run_git(("branch", "-d", branch_name))

    def get_project_name(self) -> str:
        return self.repo.base_path.name

    def read_file(self, file_path: Path) -> str:
        file_content = (self.repo.base_path / file_path).read_text()
        return file_content

    def get_branches(self) -> list[str]:
        return self.repo.run_git(("branch", "--list", "--format=%(refname:short)")).splitlines()
