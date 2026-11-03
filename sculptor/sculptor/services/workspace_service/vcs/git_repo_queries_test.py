from pathlib import Path

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.workspace_service.vcs.data_types import GitHeadIdentity
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_repo_queries import does_ref_exist
from sculptor.services.workspace_service.vcs.git_repo_queries import read_head_identity
from sculptor.services.workspace_service.vcs.git_repo_queries import read_origin_url
from sculptor.services.workspace_service.vcs.git_repo_queries import resolve_main_repo_path


def test_read_head_identity_reports_the_checked_out_branch(git_cli: GitCli, git_repo: Path) -> None:
    assert read_head_identity(git_cli, git_repo) == GitHeadIdentity(branch_name="main")


def test_read_head_identity_reports_a_detached_head_explicitly(git_cli: GitCli, git_repo: Path) -> None:
    run_blocking(["git", "checkout", "-q", "--detach"], cwd=git_repo)

    identity = read_head_identity(git_cli, git_repo)

    assert identity.is_detached
    assert identity.branch_name is None


def test_read_head_identity_reports_the_branch_of_a_repository_with_no_commits(
    git_cli: GitCli, tmp_path: Path
) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    run_blocking(["git", "init", "-q", "-b", "trunk"], cwd=repo)

    assert read_head_identity(git_cli, repo) == GitHeadIdentity(branch_name="trunk")


def test_read_head_identity_raises_outside_a_repository(git_cli: GitCli, tmp_path: Path) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    with pytest.raises(VcsCommandError):
        read_head_identity(git_cli, not_a_repo)


def test_does_ref_exist_distinguishes_present_and_missing_refs(git_cli: GitCli, git_repo: Path) -> None:
    assert does_ref_exist(git_cli, git_repo, "refs/heads/main")
    assert not does_ref_exist(git_cli, git_repo, "refs/heads/missing")


def test_does_ref_exist_finds_remote_tracking_refs(git_cli: GitCli, git_repo: Path) -> None:
    run_blocking(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=git_repo)

    assert does_ref_exist(git_cli, git_repo, "refs/remotes/origin/main")


def test_resolve_main_repo_path_maps_a_worktree_to_its_repository(
    git_cli: GitCli, git_repo: Path, tmp_path: Path
) -> None:
    worktree = tmp_path / "worktree"
    run_blocking(["git", "worktree", "add", "-q", "-b", "feature", str(worktree), "main"], cwd=git_repo)

    assert resolve_main_repo_path(git_cli, worktree).resolve() == git_repo.resolve()


def test_resolve_main_repo_path_returns_a_main_repository_unchanged(git_cli: GitCli, git_repo: Path) -> None:
    assert resolve_main_repo_path(git_cli, git_repo) == git_repo


def test_read_origin_url_returns_the_origin_remote(git_cli: GitCli, git_repo: Path) -> None:
    run_blocking(["git", "remote", "add", "origin", "git@github.com:owner/repo.git"], cwd=git_repo)

    assert read_origin_url(git_cli, git_repo) == "git@github.com:owner/repo.git"


def test_read_origin_url_is_none_without_an_origin(git_cli: GitCli, git_repo: Path) -> None:
    assert read_origin_url(git_cli, git_repo) is None
