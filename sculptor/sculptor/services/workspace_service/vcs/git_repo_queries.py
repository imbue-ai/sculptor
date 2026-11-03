"""Read-only questions about a git repository or checkout."""

from pathlib import Path

from sculptor.services.workspace_service.vcs.data_types import GitHeadIdentity
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli

_REMOTE_QUERY_TIMEOUT_SECONDS = 10.0


def read_head_identity(git: GitCli, checkout_path: Path) -> GitHeadIdentity:
    """The branch checked out at `checkout_path`, with a detached HEAD reported explicitly.

    A branch with no commits yet still counts as checked out. Raises
    `VcsCommandError` when `checkout_path` is not a git checkout.
    """
    result = git.run_git(
        ["symbolic-ref", "--quiet", "--short", "HEAD"], checkout_path, is_read_only=True, is_checked=False
    )
    # `symbolic-ref --quiet` exits 1, silently, exactly when HEAD is not a symbolic ref.
    if result.returncode == 1:
        return GitHeadIdentity(branch_name=None)
    if result.returncode != 0:
        raise VcsCommandError(
            f"Cannot read HEAD in {checkout_path}: {result.stderr.strip()}",
            command=result.command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return GitHeadIdentity(branch_name=result.stdout.strip())


def does_ref_exist(git: GitCli, repo_path: Path, ref: str) -> bool:
    """Whether `ref` resolves in the repository; pass a full name such as `refs/heads/main` to be unambiguous."""
    result = git.run_git(
        ["rev-parse", "--verify", "--quiet"], repo_path, is_read_only=True, operands=[ref], is_checked=False
    )
    return result.returncode == 0


def resolve_main_repo_path(git: GitCli, checkout_path: Path) -> Path:
    """The main repository a linked worktree belongs to; any other path is returned unchanged."""
    if not (checkout_path / ".git").is_file():
        return checkout_path
    result = git.run_git(
        ["rev-parse", "--path-format=absolute", "--git-common-dir"], checkout_path, is_read_only=True, is_checked=False
    )
    if result.returncode != 0:
        return checkout_path
    main_repo_path = Path(result.stdout.strip()).parent
    if not main_repo_path.is_dir():
        return checkout_path
    return main_repo_path


def read_origin_url(git: GitCli, repo_path: Path) -> str | None:
    """The URL of the `origin` remote, or None when there is no such remote."""
    result = git.run_git(
        ["remote", "get-url", "origin"],
        repo_path,
        is_read_only=True,
        is_checked=False,
        timeout=_REMOTE_QUERY_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()
