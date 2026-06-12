from concurrent.futures import as_completed
from pathlib import Path
from typing import Mapping

import attr

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.frozen_utils import empty_mapping
from sculptor.primitives.executor import ObservableThreadPoolExecutor
from sculptor.testing.computing_environment import apply_patch_via_git
from sculptor.testing.computing_environment import make_commit
from sculptor.testing.local_git_repo import LocalGitRepo


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class GitCommitSnapshot:
    contents_by_path: Mapping[str, str]
    commit_message: str
    # ex: "2023-05-15T14:30:00"
    # used for GIT_AUTHOR_DATE and GIT_COMMITTER_DATE
    commit_time: str


@attr.s(auto_attribs=True, frozen=True, kw_only=True)
class FullLocalGitRepo:
    git_user_name: str
    git_user_email: str
    main_history: tuple[GitCommitSnapshot, ...]
    # the relative paths of any currently untracked files in the repo, and their content
    untracked_file_content_by_path: Mapping[str, str] = attr.ib(factory=empty_mapping)
    git_branch: str = "main"
    git_diff: str | None = None


def create_repo_from_snapshot(
    full_repo: FullLocalGitRepo,
    destination_path: Path,
    concurrency_group: ConcurrencyGroup,
) -> LocalGitRepo:
    """Creates an entire repo history locally from scratch. Much faster and more reliable than checking from remote."""
    if not destination_path.exists():
        destination_path.mkdir(parents=True)
    assert destination_path.is_dir(), (
        f"Destination for repo checkout must be a directory. {destination_path} is not a directory."
    )

    if any(destination_path.iterdir()):
        raise Exception(f"Destination for repo creation must be an empty directory. {destination_path} is not empty.")

    # create the empty repo
    new_repo = LocalGitRepo(destination_path)
    new_repo.run_git(("init",))
    new_repo.run_git(("checkout", "-b", "main"))
    if full_repo.git_branch != "main":
        new_repo.run_git(("branch", "-m", "main", full_repo.git_branch))
    new_repo.run_git(("config", "user.name", f"'{full_repo.git_user_name}'"))
    new_repo.run_git(("config", "user.email", f"'{full_repo.git_user_email}'"))

    # put the history in
    for commit in full_repo.main_history:
        _write_files_in_parallel(new_repo, commit.contents_by_path, concurrency_group)
        make_commit(new_repo, commit.commit_message, commit_time=commit.commit_time)

    if full_repo.git_diff:
        # apply any diffs from between git_hash and repo snapshot state of repo being checked out
        apply_patch_via_git(new_repo, full_repo.git_diff, is_error_logged=True)

    if full_repo.untracked_file_content_by_path:
        # make sure the untracked file contents are there
        _write_files_in_parallel(new_repo, full_repo.untracked_file_content_by_path, concurrency_group)

    return new_repo


def _write_files_in_parallel(
    repo: LocalGitRepo, content: Mapping[str, str], concurrency_group: ConcurrencyGroup
) -> None:
    def write_file(file_path: str, file_content: str) -> None:
        repo.write_file(file_path, file_content)

    with ObservableThreadPoolExecutor(concurrency_group) as executor:
        futures = [executor.submit(write_file, file_path, file_content) for file_path, file_content in content.items()]
        for future in as_completed(futures):
            future.result()  # This will raise any exceptions that occurred
