from pathlib import Path

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.vcs.errors import GitCommandInJjWorkspaceError
from sculptor.services.workspace_service.vcs.errors import VcsBinaryNotFoundError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.errors import VcsCommandExitError
from sculptor.services.workspace_service.vcs.errors import VcsCommandTimeoutError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_cli import find_jj_workspace_root


def _use_dependency_paths(dependency_paths: DependencyPaths) -> None:
    config = get_default_user_config_instance().model_copy(update={"dependency_paths": dependency_paths})
    set_user_config_instance(config)


def _write_script(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/bash\n{body}\n")
    path.chmod(0o755)
    return path


def _make_jj_only_workspace(path: Path) -> Path:
    (path / ".jj").mkdir(parents=True)
    return path


def test_run_git_runs_in_the_given_directory(git_cli: GitCli, git_repo: Path) -> None:
    result = git_cli.run_git(["rev-parse", "--show-toplevel"], git_repo, is_read_only=True)

    assert Path(result.stdout.strip()).resolve() == git_repo.resolve()


def test_tripwire_raises_for_a_directory_with_jj_and_no_git(git_cli: GitCli, tmp_path: Path) -> None:
    workspace = _make_jj_only_workspace(tmp_path / "jj_workspace")

    with pytest.raises(GitCommandInJjWorkspaceError) as error_info:
        git_cli.run_git(["status"], workspace, is_read_only=True)

    assert error_info.value.workspace_root == workspace


def test_tripwire_raises_for_a_subdirectory_of_a_jj_workspace(git_cli: GitCli, tmp_path: Path) -> None:
    workspace = _make_jj_only_workspace(tmp_path / "jj_workspace")
    subdirectory = workspace / "src" / "deep"
    subdirectory.mkdir(parents=True)

    with pytest.raises(GitCommandInJjWorkspaceError):
        git_cli.run_git(["status"], subdirectory, is_read_only=True)


def test_tripwire_does_not_raise_in_a_git_worktree(git_cli: GitCli, git_repo: Path, tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    run_blocking(["git", "worktree", "add", "-q", "-b", "feature", str(worktree), "main"], cwd=git_repo)
    assert (worktree / ".git").is_file()

    result = git_cli.run_git(["symbolic-ref", "--short", "HEAD"], worktree, is_read_only=True)

    assert result.stdout.strip() == "feature"


def test_tripwire_does_not_raise_in_a_colocated_jj_repository(git_cli: GitCli, git_repo: Path) -> None:
    (git_repo / ".jj").mkdir()

    result = git_cli.run_git(["rev-parse", "--is-inside-work-tree"], git_repo, is_read_only=True)

    assert result.stdout.strip() == "true"


def test_tripwire_is_not_a_vcs_command_error_so_graceful_handlers_cannot_swallow_it() -> None:
    assert not issubclass(GitCommandInJjWorkspaceError, VcsCommandError)


def test_find_jj_workspace_root_stops_at_the_nearest_git_directory(tmp_path: Path) -> None:
    outer_jj = _make_jj_only_workspace(tmp_path / "outer")
    inner_git = outer_jj / "inner"
    (inner_git / ".git").mkdir(parents=True)

    assert find_jj_workspace_root(inner_git) is None
    assert find_jj_workspace_root(outer_jj) == outer_jj


def test_run_gh_uses_the_configured_binary_and_runs_in_a_jj_workspace(git_cli: GitCli, tmp_path: Path) -> None:
    fake_gh = _write_script(tmp_path / "gh", 'echo "gh:$GH_REPO:$*"')
    _use_dependency_paths(DependencyPaths(gh=str(fake_gh)))
    workspace = _make_jj_only_workspace(tmp_path / "jj_workspace")

    result = git_cli.run_gh(
        ["pr", "list"], workspace, is_read_only=True, extra_env={"GH_REPO": "github.com/owner/name"}
    )

    assert result.stdout.strip() == "gh:github.com/owner/name:pr list"


def test_run_git_uses_the_configured_git_binary_and_places_operands_and_paths(git_cli: GitCli, tmp_path: Path) -> None:
    fake_git = _write_script(tmp_path / "fake-git", 'printf "%s\\n" "$@"')
    _use_dependency_paths(DependencyPaths(git=str(fake_git)))

    result = git_cli.run_git(["show", "--stat"], tmp_path, is_read_only=True, operands=["-HEAD"], paths=["-file.txt"])

    assert result.stdout.splitlines() == ["show", "--stat", "--end-of-options", "-HEAD", "--", "-file.txt"]


def test_run_git_does_not_set_git_ssh_command(
    git_cli: GitCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    fake_git = _write_script(tmp_path / "fake-git", 'echo "${GIT_SSH_COMMAND-unset}"')
    _use_dependency_paths(DependencyPaths(git=str(fake_git)))

    result = git_cli.run_git(["fetch"], tmp_path, is_read_only=False)

    assert result.stdout.strip() == "unset"


def test_run_git_passes_each_operand_and_path_to_git_as_one_argument(git_cli: GitCli, tmp_path: Path) -> None:
    fake_git = _write_script(tmp_path / "fake-git", "printf '[%s]' \"$@\"")
    _use_dependency_paths(DependencyPaths(git=str(fake_git)))

    result = git_cli.run_git(["show"], tmp_path, is_read_only=True, operands=["", "HEAD\nmain"], paths=["a\nb"])

    assert result.stdout == "[show][--end-of-options][][HEAD\nmain][--][a\nb]"


def test_run_git_reports_an_argument_containing_nul_as_a_vcs_command_error(git_cli: GitCli, git_repo: Path) -> None:
    with pytest.raises(VcsCommandError):
        git_cli.run_git(["rev-parse"], git_repo, is_read_only=True, operands=["HEAD\0main"])


def test_checked_non_zero_exit_raises_vcs_command_exit_error(git_cli: GitCli, git_repo: Path) -> None:
    with pytest.raises(VcsCommandExitError) as error_info:
        git_cli.run_git(["checkout", "-q"], git_repo, is_read_only=False, operands=["no-such-branch"])

    assert error_info.value.returncode != 0
    assert "no-such-branch" in error_info.value.stderr


def test_unchecked_non_zero_exit_returns_the_finished_process(git_cli: GitCli, git_repo: Path) -> None:
    result = git_cli.run_git(
        ["rev-parse", "--verify", "--quiet"], git_repo, is_read_only=True, operands=["no-such-ref"], is_checked=False
    )

    assert result.returncode == 1


def test_timeout_is_part_of_the_vcs_command_error_family(git_cli: GitCli, tmp_path: Path) -> None:
    hanging_git = _write_script(tmp_path / "hanging-git", "exec sleep 30")
    _use_dependency_paths(DependencyPaths(git=str(hanging_git)))

    with pytest.raises(VcsCommandError) as error_info:
        git_cli.run_git(["status"], tmp_path, is_read_only=True, timeout=0.2)

    assert isinstance(error_info.value, VcsCommandTimeoutError)


def test_a_directory_that_does_not_exist_raises_vcs_command_error(git_cli: GitCli, tmp_path: Path) -> None:
    with pytest.raises(VcsCommandError):
        git_cli.run_git(["status"], tmp_path / "missing", is_read_only=True)


def test_an_unresolvable_git_binary_raises_vcs_binary_not_found(
    git_cli: GitCli, git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")

    with pytest.raises(VcsBinaryNotFoundError):
        git_cli.run_git(["status"], git_repo, is_read_only=True)


def test_read_only_command_is_retried_after_a_failure(git_cli: GitCli, tmp_path: Path) -> None:
    attempts_file = tmp_path / "attempts"
    flaky_git = _write_script(
        tmp_path / "flaky-git",
        f'echo attempt >> "{attempts_file}"\n[ "$(wc -l < "{attempts_file}")" -ge 2 ] || exit 1\necho ok',
    )
    _use_dependency_paths(DependencyPaths(git=str(flaky_git)))

    result = git_cli.run_git(["status"], tmp_path, is_read_only=True)

    assert result.stdout.strip() == "ok"
    assert len(attempts_file.read_text().splitlines()) == 2


def test_read_only_command_that_times_out_is_not_retried(git_cli: GitCli, tmp_path: Path) -> None:
    attempts_file = tmp_path / "attempts"
    hanging_git = _write_script(tmp_path / "hanging-git", f'echo attempt >> "{attempts_file}"\nexec sleep 30')
    _use_dependency_paths(DependencyPaths(git=str(hanging_git)))

    with pytest.raises(VcsCommandTimeoutError):
        git_cli.run_git(["status"], tmp_path, is_read_only=True, timeout=2.0)

    assert len(attempts_file.read_text().splitlines()) == 1


def test_mutating_command_is_not_retried(git_cli: GitCli, tmp_path: Path) -> None:
    attempts_file = tmp_path / "attempts"
    failing_git = _write_script(tmp_path / "failing-git", f'echo attempt >> "{attempts_file}"\nexit 1')
    _use_dependency_paths(DependencyPaths(git=str(failing_git)))

    with pytest.raises(VcsCommandError):
        git_cli.run_git(["commit"], tmp_path, is_read_only=False)

    assert len(attempts_file.read_text().splitlines()) == 1
