from collections.abc import Mapping
from pathlib import Path

import attr

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.frozen_utils import empty_mapping
from sculptor.testing.computing_environment import apply_patch_via_git
from sculptor.testing.computing_environment import make_commit
from sculptor.testing.local_git_repo import LocalGitRepo


class RepoCreationError(Exception):
    """Raised when a repo cannot be created from a snapshot."""


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
        raise RepoCreationError(
            f"Destination for repo creation must be an empty directory. {destination_path} is not empty."
        )

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
    # Write each file on its own ConcurrencyGroup-tracked ObservableThread, then join them:
    # join() re-raises any exception the worker captured. File counts here are small
    # test-fixture sizes, so one thread per file is fine.
    threads = [
        concurrency_group.start_new_thread(
            target=repo.write_file, args=(file_path, file_content), name=f"write_file_{index}"
        )
        for index, (file_path, file_content) in enumerate(content.items())
    ]
    for thread in threads:
        thread.join()
