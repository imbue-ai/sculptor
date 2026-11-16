"""What colocating a repository with jj would run into, read without changing anything in the repository."""

from pathlib import Path

from sculptor.services.workspace_service.vcs.data_types import VcsCommandResult
from sculptor.services.workspace_service.vcs.errors import VcsCommandExitError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_repo_queries import is_jj_colocated
from sculptor.web.data_types import JjColocationBlocker
from sculptor.web.data_types import JjColocationPreflight
from sculptor.web.data_types import JjColocationWarning
from sculptor.web.data_types import JjReadiness

# What git leaves in its directory while a merge, rebase, cherry-pick or revert is stopped.
_OPERATION_IN_PROGRESS_MARKERS = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD")
_SUBMODULE_INDEX_MODE = "160000"
_SAMPLE_HOOK_SUFFIX = ".sample"
_HOOK_FRAMEWORK_PATHS = (".husky", ".pre-commit-config.yaml")


def read_colocation_preflight(
    git: GitCli, jj: JjCli, repo_path: Path, jj_readiness: JjReadiness
) -> JjColocationPreflight:
    """What stops, or changes, colocating the git repository at `repo_path` with jj.

    A `.jj` already there is checked only while jj is available, since only jj can read it.
    Raises `VcsCommandError` when git cannot read the repository.
    """
    git_dir, git_common_dir = _read_git_dirs(git, repo_path)
    blockers: list[JjColocationBlocker] = []
    if jj_readiness.blocker is not None:
        blockers.append(JjColocationBlocker.JJ_UNAVAILABLE)
    elif (repo_path / ".jj").exists() and not is_jj_colocated(jj, repo_path):
        blockers.append(JjColocationBlocker.JJ_REPOSITORY_NOT_COLOCATED)
    if _has_submodules(git, repo_path):
        blockers.append(JjColocationBlocker.SUBMODULES)
    if _uses_lfs(git, repo_path):
        blockers.append(JjColocationBlocker.LFS)
    if any((git_dir / marker).exists() for marker in _OPERATION_IN_PROGRESS_MARKERS):
        blockers.append(JjColocationBlocker.GIT_OPERATION_IN_PROGRESS)

    warnings: list[JjColocationWarning] = []
    if _has_hooks(git, repo_path, git_common_dir):
        warnings.append(JjColocationWarning.HOOKS)
    if _read_config_value(git, repo_path, "core.sparseCheckout", is_bool=True) == "true":
        warnings.append(JjColocationWarning.SPARSE_CHECKOUT)

    return JjColocationPreflight(
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        has_uncommitted_changes=_has_uncommitted_changes(git, repo_path),
    )


def _read_git_dirs(git: GitCli, repo_path: Path) -> tuple[Path, Path]:
    """The repository's own git directory, where operation state lives, and its common one, where hooks live."""
    output = git.run_git(
        ["rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"], repo_path, is_read_only=True
    ).stdout
    git_dir, git_common_dir = output.splitlines()
    return Path(git_dir), Path(git_common_dir)


def _has_submodules(git: GitCli, repo_path: Path) -> bool:
    if (repo_path / ".gitmodules").exists():
        return True
    output = git.run_git(["ls-files", "--stage"], repo_path, is_read_only=True).stdout
    return any(line.startswith(f"{_SUBMODULE_INDEX_MODE} ") for line in output.splitlines())


def _uses_lfs(git: GitCli, repo_path: Path) -> bool:
    """Whether a tracked `.gitattributes`, at any depth, routes files through the LFS filter."""
    result = git.run_git(
        ["grep", "--cached", "--quiet", "--fixed-strings", "-e", "filter=lfs"],
        repo_path,
        is_read_only=True,
        paths=[":(glob)**/.gitattributes"],
        is_checked=False,
    )
    # `git grep` exits 1 exactly when nothing matches.
    if result.returncode in (0, 1):
        return result.returncode == 0
    raise _unexpected_exit_error(result)


def _has_hooks(git: GitCli, repo_path: Path, git_common_dir: Path) -> bool:
    if _read_config_value(git, repo_path, "core.hooksPath", is_bool=False) is not None:
        return True
    try:
        hook_paths = tuple((git_common_dir / "hooks").iterdir())
    except FileNotFoundError:
        hook_paths = ()
    if any(path.is_file() and not path.name.endswith(_SAMPLE_HOOK_SUFFIX) for path in hook_paths):
        return True
    return any((repo_path / path).exists() for path in _HOOK_FRAMEWORK_PATHS)


def _has_uncommitted_changes(git: GitCli, repo_path: Path) -> bool:
    # Without `--no-optional-locks`, `git status` refreshes the index and so writes it.
    output = git.run_git(["--no-optional-locks", "status", "--porcelain"], repo_path, is_read_only=True).stdout
    return output != ""


def _read_config_value(git: GitCli, repo_path: Path, key: str, *, is_bool: bool) -> str | None:
    """The value of `key`, normalized to `true` or `false` when `is_bool`; None when it is unset."""
    type_options = ["--type=bool"] if is_bool else []
    result = git.run_git(["config", *type_options, "--get", key], repo_path, is_read_only=True, is_checked=False)
    # `git config --get` exits 1 exactly when the key is unset.
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise _unexpected_exit_error(result)
    return result.stdout.strip()


def _unexpected_exit_error(result: VcsCommandResult) -> VcsCommandExitError:
    return VcsCommandExitError(
        f"Error running {result.command}\nstderr: {result.stderr}",
        command=result.command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
