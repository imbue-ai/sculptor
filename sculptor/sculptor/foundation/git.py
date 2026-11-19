"""Utility abstractions for interacting with git repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path


def is_path_in_git_repo(path: Path) -> bool:
    """Check if a path is in a git repository."""
    if path.is_file():
        path = path.parent
    completed_process = subprocess.run(
        ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed_process.returncode != 0:
        return False
    result = completed_process.stdout.decode().strip()
    assert result in ("true", "false"), result
    return result == "true"


def resolve_worktree_to_main_repo(path: Path) -> Path:
    """Return the main repo's working tree if ``path`` is a git worktree, else ``path`` unchanged.

    A git worktree's ``.git`` is a file containing ``gitdir: <main>/.git/worktrees/<name>``;
    its object store lives in the main repo. Operations like ``git clone --reference``
    refuse worktrees ("reference repository ... as a linked checkout is not supported yet"),
    so any caller that needs the canonical repository should resolve through this helper
    before doing anything path-shaped with ``path``.

    Returns ``path`` unchanged if it is not a worktree, if git fails to report the
    common dir, or if the resolved parent directory does not exist on disk.
    """
    if not (path / ".git").is_file():
        return path
    completed_process = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed_process.returncode != 0:
        return path
    common_dir = Path(completed_process.stdout.decode().strip())
    main_repo = common_dir.parent
    if not main_repo.is_dir():
        return path
    return main_repo


class RepoRootNotFoundError(Exception):
    """Raised when no directory from the working directory up holds ``.git`` or ``.jj``."""


def find_repo_root(start_directory: Path) -> Path | None:
    """Find the repository root: the nearest directory, from ``start_directory`` up, holding ``.git`` or ``.jj``.

    A jj workspace of a repository has ``.jj`` and no ``.git``, and it can sit
    inside another checkout (a from-source Sculptor keeps its workspaces in the
    checkout's ``.dev_sculptor``), whose root a search for ``.git`` alone, or
    ``git rev-parse``, would find instead. Returns None if no directory holds
    either.
    """
    for directory in (start_directory, *start_directory.parents):
        if (directory / ".git").exists() or (directory / ".jj").is_dir():
            return directory
    return None


def get_repo_root() -> Path:
    """Return the root of the git checkout or jj workspace that holds the working directory."""
    working_directory = Path.cwd()
    repo_root = find_repo_root(working_directory)
    if repo_root is None:
        raise RepoRootNotFoundError(f"{working_directory} is not inside a git checkout or a jj workspace")
    return repo_root


def get_repo_url_from_folder(repo_path: Path) -> str:
    """Return the ``origin`` remote URL for ``repo_path``, normalized to an https URL."""
    repo_url = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=repo_path, universal_newlines=True
    ).strip()
    if repo_url.startswith("git@"):
        # convert ssh url to https
        repo_url = repo_url.replace(":", "/")
        repo_url = f"https://{repo_url[4:]}"
    if "https://oauth2:" in repo_url:
        # strip the oauth2 credentials left over from an oauth2 clone,
        # e.g. https://oauth2:{token}@github.com/.../.git -> https://github.com/.../.git
        suffix = repo_url.split("@")[-1]
        repo_url = "https://" + suffix
    return repo_url


def get_repo_base_path() -> Path:
    """Return the repo root containing this module, falling back to its grandparent directory."""
    module_directory = Path(__file__).parent
    repo_root = find_repo_root(module_directory)
    if repo_root is None:
        return module_directory.parents[1]
    return repo_root
