import shutil
from collections.abc import Callable
from collections.abc import Sequence
from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.jj_availability import describe_jj_unavailability
from sculptor.services.project_jj_state_service.colocation_preflight import read_colocation_preflight
from sculptor.services.workspace_service.vcs.vcs_runners import VcsRunners
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import run_jj
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjColocationBlocker
from sculptor.web.data_types import JjColocationPreflight
from sculptor.web.data_types import JjColocationWarning
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNotInstalled

_JJ_AVAILABLE = JjAvailable(blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL))
_NOTHING_TO_REPORT = JjColocationPreflight(
    blockers=(), warnings=(), has_uncommitted_changes=False, jj_unavailable_reason=None
)


@pytest.fixture
def runners(test_root_concurrency_group: ConcurrencyGroup, jj_binary: JjBinary) -> VcsRunners:
    git_path = shutil.which("git")

    def resolve_binary(tool: Dependency) -> str | None:
        if tool is Dependency.JJ:
            return str(jj_binary.path)
        if tool is Dependency.GIT:
            return git_path
        return None

    return build_vcs_runners(test_root_concurrency_group, resolve_binary)


@pytest.fixture
def git_repo(jj_isolated_env: JjIsolatedEnv, tmp_path: Path) -> Path:
    """A plain git repository on `main` whose one commit holds `file.txt`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, ("init", "-q", "-b", "main"))
    _commit_file(repo, "file.txt", "first\n", "init")
    return repo


def _git(repo: Path, args: Sequence[str], is_checked: bool = True) -> None:
    run_blocking(["git", *args], cwd=repo, is_checked=is_checked)


def _commit_file(repo: Path, relative_path: str, content: str, message: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _git(repo, ("add", relative_path))
    _git(repo, ("commit", "-q", "-m", message))


def _read_preflight(runners: VcsRunners, repo: Path) -> JjColocationPreflight:
    return read_colocation_preflight(runners.git, runners.jj, repo, _JJ_AVAILABLE)


def test_a_clean_git_repository_has_nothing_to_report(runners: VcsRunners, git_repo: Path) -> None:
    assert _read_preflight(runners, git_repo) == _NOTHING_TO_REPORT


def test_an_already_colocated_repository_has_nothing_to_report(
    runners: VcsRunners, jj_colocated_repo: JjColocatedRepo
) -> None:
    assert _read_preflight(runners, jj_colocated_repo.path) == _NOTHING_TO_REPORT


def test_jj_being_unavailable_blocks_colocation(runners: VcsRunners, git_repo: Path) -> None:
    jj_not_installed = JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED)

    preflight = read_colocation_preflight(runners.git, runners.jj, git_repo, jj_not_installed)

    assert preflight.blockers == (JjColocationBlocker.JJ_UNAVAILABLE,)
    assert preflight.jj_unavailable_reason == describe_jj_unavailability(jj_not_installed)


def test_a_jj_repository_with_its_own_git_store_blocks_colocation(
    runners: VcsRunners, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv, tmp_path: Path
) -> None:
    repo = tmp_path / "split"
    repo.mkdir()
    # jj refuses to start a repository of its own in a directory that already holds a git repository.
    run_jj(jj_binary, ("git", "init", "--no-colocate"), cwd=repo)
    _git(repo, ("init", "-q", "-b", "main"))
    _commit_file(repo, "file.txt", "first\n", "init")

    assert _read_preflight(runners, repo).blockers == (JjColocationBlocker.JJ_REPOSITORY_NOT_COLOCATED,)


def test_a_gitmodules_file_blocks_colocation(runners: VcsRunners, git_repo: Path) -> None:
    _commit_file(git_repo, ".gitmodules", '[submodule "vendor"]\n\tpath = vendor\n\turl = ../vendor\n', "modules")

    assert _read_preflight(runners, git_repo).blockers == (JjColocationBlocker.SUBMODULES,)


def test_a_submodule_in_the_index_without_a_gitmodules_file_blocks_colocation(
    runners: VcsRunners, git_repo: Path
) -> None:
    commit_id = run_blocking(["git", "rev-parse", "HEAD"], cwd=git_repo).stdout.strip()
    _git(git_repo, ("update-index", "--add", "--cacheinfo", f"160000,{commit_id},vendor"))

    assert _read_preflight(runners, git_repo).blockers == (JjColocationBlocker.SUBMODULES,)


def test_an_lfs_filter_in_a_nested_tracked_gitattributes_blocks_colocation(
    runners: VcsRunners, git_repo: Path
) -> None:
    _commit_file(git_repo, "assets/.gitattributes", "*.bin filter=lfs diff=lfs merge=lfs -text\n", "lfs")

    assert _read_preflight(runners, git_repo).blockers == (JjColocationBlocker.LFS,)


def test_an_lfs_filter_in_an_untracked_gitattributes_does_not_block_colocation(
    runners: VcsRunners, git_repo: Path
) -> None:
    (git_repo / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")

    assert _read_preflight(runners, git_repo).blockers == ()


def _diverge_from_side_branch(repo: Path) -> None:
    """`main` and `side` each change the same line of `file.txt` in their own commit."""
    _git(repo, ("checkout", "-q", "-b", "side"))
    _commit_file(repo, "file.txt", "side\n", "side change")
    _git(repo, ("checkout", "-q", "main"))
    _commit_file(repo, "file.txt", "main\n", "main change")


def _stop_in_a_merge(repo: Path) -> None:
    _diverge_from_side_branch(repo)
    _git(repo, ("merge", "side"), is_checked=False)


def _stop_in_a_rebase(repo: Path) -> None:
    _diverge_from_side_branch(repo)
    _git(repo, ("rebase", "side"), is_checked=False)


def _stop_in_a_cherry_pick(repo: Path) -> None:
    _diverge_from_side_branch(repo)
    _git(repo, ("cherry-pick", "side"), is_checked=False)


def _stop_in_a_revert(repo: Path) -> None:
    _commit_file(repo, "file.txt", "second\n", "second")
    _commit_file(repo, "file.txt", "third\n", "third")
    _git(repo, ("revert", "--no-edit", "HEAD~1"), is_checked=False)


@pytest.mark.parametrize(
    "stop_in_an_operation",
    [_stop_in_a_merge, _stop_in_a_rebase, _stop_in_a_cherry_pick, _stop_in_a_revert],
    ids=["merge", "rebase", "cherry_pick", "revert"],
)
def test_a_git_operation_in_progress_blocks_colocation(
    runners: VcsRunners, git_repo: Path, stop_in_an_operation: Callable[[Path], None]
) -> None:
    stop_in_an_operation(git_repo)

    assert _read_preflight(runners, git_repo).blockers == (JjColocationBlocker.GIT_OPERATION_IN_PROGRESS,)


def _install_a_git_hook(repo: Path) -> None:
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)


def _configure_a_hooks_path(repo: Path) -> None:
    _git(repo, ("config", "core.hooksPath", "tools/hooks"))


def _add_husky(repo: Path) -> None:
    (repo / ".husky").mkdir()


def _add_a_pre_commit_config(repo: Path) -> None:
    _commit_file(repo, ".pre-commit-config.yaml", "repos: []\n", "pre-commit")


@pytest.mark.parametrize(
    "add_hooks",
    [_install_a_git_hook, _configure_a_hooks_path, _add_husky, _add_a_pre_commit_config],
    ids=["git_hooks_directory", "core_hooks_path", "husky", "pre_commit"],
)
def test_hooks_are_a_warning(runners: VcsRunners, git_repo: Path, add_hooks: Callable[[Path], None]) -> None:
    add_hooks(git_repo)

    preflight = _read_preflight(runners, git_repo)

    assert (preflight.blockers, preflight.warnings) == ((), (JjColocationWarning.HOOKS,))


def test_a_sparse_checkout_is_a_warning(runners: VcsRunners, git_repo: Path) -> None:
    _commit_file(git_repo, "docs/guide.md", "guide\n", "docs")
    _git(git_repo, ("sparse-checkout", "set", "docs"))

    preflight = _read_preflight(runners, git_repo)

    assert (preflight.blockers, preflight.warnings) == ((), (JjColocationWarning.SPARSE_CHECKOUT,))


def test_a_modified_file_is_reported_as_uncommitted_changes_only(runners: VcsRunners, git_repo: Path) -> None:
    (git_repo / "file.txt").write_text("edited\n")

    assert _read_preflight(runners, git_repo) == JjColocationPreflight(
        blockers=(), warnings=(), has_uncommitted_changes=True, jj_unavailable_reason=None
    )


def test_an_untracked_file_is_reported_as_uncommitted_changes(runners: VcsRunners, git_repo: Path) -> None:
    (git_repo / "notes.txt").write_text("notes\n")

    assert _read_preflight(runners, git_repo).has_uncommitted_changes is True


def _read_every_file(root: Path) -> dict[Path, tuple[bytes, int]]:
    """Every file under `root` with its content and modification time."""
    return {
        path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_the_preflight_of_a_git_repository_changes_no_file(runners: VcsRunners, git_repo: Path) -> None:
    _install_a_git_hook(git_repo)
    _commit_file(git_repo, ".gitmodules", '[submodule "vendor"]\n\tpath = vendor\n\turl = ../vendor\n', "modules")
    (git_repo / "file.txt").write_text("edited\n")
    (git_repo / "notes.txt").write_text("notes\n")
    files_before = _read_every_file(git_repo)

    preflight = _read_preflight(runners, git_repo)

    assert preflight.blockers == (JjColocationBlocker.SUBMODULES,)
    assert _read_every_file(git_repo) == files_before


def test_the_preflight_of_a_colocated_repository_changes_no_file(
    runners: VcsRunners, jj_colocated_repo: JjColocatedRepo
) -> None:
    (jj_colocated_repo.path / "README.md").write_text("edited\n")
    files_before = _read_every_file(jj_colocated_repo.path)

    preflight = _read_preflight(runners, jj_colocated_repo.path)

    assert preflight.has_uncommitted_changes is True
    assert _read_every_file(jj_colocated_repo.path) == files_before
