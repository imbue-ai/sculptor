"""Unit tests for :mod:`sculptor.web.repo_polling_manager`.

These cover the background branch/remote-branch pollers' behaviour when a
workspace's git repo is torn down out from under them. A workspace repo can
vanish two ways:

* the working directory is removed entirely (``FileNotFoundError``), or
* the directory survives but is no longer a git repo — e.g. a worktree whose
  gitdir was pruned — which makes git print ``fatal: not a git repository``.

In the orphaned-backend scenario from SCU-1429 neither poller ever gives up:
they keep invoking git every few seconds (and the remote-branches poller keeps
logging errors) until process shutdown, dragging the host. The pollers must
instead raise :class:`StopPolling` so their source stops.

The pollers are background-thread jobs with no UI trigger, so per the repo's
test strategy these are exercised with unit tests rather than Playwright.
"""

import shutil
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.threads import StopPolling
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.testing.local_git_repo import LocalGitRepo
from sculptor.web.derived import WorkspaceBranchInfo
from sculptor.web.derived import WorkspaceRemoteBranchesInfo
from sculptor.web.repo_polling_manager import _WorkspaceBranchPollingCallback
from sculptor.web.repo_polling_manager import _WorkspaceRemoteBranchesPollingCallback


def _make_base_repo(base: Path, cg: ConcurrencyGroup) -> None:
    base.mkdir(parents=True, exist_ok=True)
    repo = LocalWritableGitRepo.from_new_repository(
        repo_path=base, concurrency_group=cg, user_email="t@example.com", user_name="Tester"
    )
    (base / "f.txt").write_text("hi")
    repo.stage_all_files()
    repo.create_commit("init")


def _add_worktree(base: Path, worktree: Path) -> None:
    LocalGitRepo(base).run_git(["worktree", "add", str(worktree), "-b", "wsbranch"])


@pytest.fixture
def healthy_worktree(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> Generator[tuple[Path, Path], None, None]:
    """A base repo plus a checked-out worktree that stands in for a workspace."""
    base = tmp_path / "base"
    worktree = tmp_path / "workspace"
    _make_base_repo(base, test_root_concurrency_group)
    _add_worktree(base, worktree)
    yield base, worktree


def _branch_callback(worktree: Path, cg: ConcurrencyGroup) -> _WorkspaceBranchPollingCallback:
    return _WorkspaceBranchPollingCallback(
        workspace_id=WorkspaceID(),
        workspace_working_dir=worktree,
        concurrency_group=cg,
        services=MagicMock(spec=CompleteServiceCollection),
    )


def _remote_branches_callback(worktree: Path, cg: ConcurrencyGroup) -> _WorkspaceRemoteBranchesPollingCallback:
    return _WorkspaceRemoteBranchesPollingCallback(
        workspace_id=WorkspaceID(),
        workspace_working_dir=worktree,
        concurrency_group=cg,
    )


def test_branch_callback_returns_info_for_healthy_repo(
    healthy_worktree: tuple[Path, Path], test_root_concurrency_group: ConcurrencyGroup
) -> None:
    _base, worktree = healthy_worktree
    result = _branch_callback(worktree, test_root_concurrency_group)()
    assert isinstance(result, WorkspaceBranchInfo)
    assert result.current_branch == "wsbranch"


def test_remote_branches_callback_returns_info_for_healthy_repo(
    healthy_worktree: tuple[Path, Path], test_root_concurrency_group: ConcurrencyGroup
) -> None:
    _base, worktree = healthy_worktree
    result = _remote_branches_callback(worktree, test_root_concurrency_group)()
    assert isinstance(result, WorkspaceRemoteBranchesInfo)
    # A fresh local worktree has no remotes.
    assert result.remote_branches == ()


def test_branch_callback_raises_stop_polling_when_working_dir_deleted(
    healthy_worktree: tuple[Path, Path], test_root_concurrency_group: ConcurrencyGroup
) -> None:
    _base, worktree = healthy_worktree
    callback = _branch_callback(worktree, test_root_concurrency_group)
    shutil.rmtree(worktree)
    with pytest.raises(StopPolling):
        callback()


def test_branch_callback_raises_stop_polling_when_git_dir_dangling(
    healthy_worktree: tuple[Path, Path], test_root_concurrency_group: ConcurrencyGroup
) -> None:
    base, worktree = healthy_worktree
    callback = _branch_callback(worktree, test_root_concurrency_group)
    # The worktree dir survives, but its gitdir is gone, so git reports
    # "fatal: not a git repository" — the exact SCU-1429 symptom.
    shutil.rmtree(base / ".git")
    assert worktree.exists()
    with pytest.raises(StopPolling):
        callback()


def test_remote_branches_callback_raises_stop_polling_when_working_dir_deleted(
    healthy_worktree: tuple[Path, Path], test_root_concurrency_group: ConcurrencyGroup
) -> None:
    _base, worktree = healthy_worktree
    callback = _remote_branches_callback(worktree, test_root_concurrency_group)
    shutil.rmtree(worktree)
    with pytest.raises(StopPolling):
        callback()


def test_remote_branches_callback_raises_stop_polling_when_git_dir_dangling(
    healthy_worktree: tuple[Path, Path], test_root_concurrency_group: ConcurrencyGroup
) -> None:
    base, worktree = healthy_worktree
    callback = _remote_branches_callback(worktree, test_root_concurrency_group)
    shutil.rmtree(base / ".git")
    assert worktree.exists()
    with pytest.raises(StopPolling):
        callback()


def test_branch_callback_does_not_stop_for_repo_without_commits(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Guard: a valid repo that simply has no commits yet (unborn HEAD) is a
    transient state, not a missing repo. The poller must keep going (return
    ``None``), not raise ``StopPolling`` — otherwise a freshly-created workspace
    would stop being polled before its first commit lands."""
    empty_repo = tmp_path / "empty"
    empty_repo.mkdir()
    LocalGitRepo(empty_repo).run_git(["init"])
    result = _branch_callback(empty_repo, test_root_concurrency_group)()
    assert result is None
