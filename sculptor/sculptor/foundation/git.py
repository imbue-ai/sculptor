"""Utility abstractions for interacting with git repositories."""

from __future__ import annotations

import shlex
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Sequence
from typing import TextIO


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


def get_git_repo_root() -> Path:
    """Gets a Path to the current git repo root, assuming that our cwd is somewhere inside the repo."""
    completed_process = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    root_dir = Path(completed_process.stdout.decode().strip())
    assert root_dir.is_dir(), f"{root_dir} must be a directory"
    return root_dir


def get_repo_url_from_folder(repo_path: Path) -> str:
    try:
        repo_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=repo_path, universal_newlines=True
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        raise
    else:
        if repo_url.startswith("git@"):
            # convert ssh url to https
            repo_url = repo_url.replace(":", "/")
            repo_url = f"https://{repo_url[4:]}"
        if "https://oauth2:" in repo_url:
            # remove the oauth2 prefix
            # repo_url is something like https://oauth2:{token}@gitlab.com/.../.git
            # change it to https://gitlab.com/.../.git
            # This will happen if repo was originallycloned using oauth2
            suffix = repo_url.split("@")[-1]
            repo_url = "https://" + suffix
        return repo_url


def get_repo_base_path() -> Path:
    working_directory = Path(__file__).parent
    try:
        return Path(
            _run_command_and_capture_output(["git", "rev-parse", "--show-toplevel"], cwd=working_directory).strip()
        )
    except subprocess.CalledProcessError as e:
        try:
            return working_directory.parents[1]
        except IndexError:
            raise RuntimeError("Unable to find repo base") from e


def _run_command_and_capture_output(args: Sequence[str], cwd: Path | None = None) -> str:
    arg_str = " ".join(shlex.quote(arg) for arg in args)
    print(f"Running command: {arg_str}", file=sys.stderr)
    with subprocess.Popen(args, text=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        with StringIO() as output:
            _handle_output(proc, output, sys.stderr)
            if proc.wait() != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd=args, output=output.getvalue())
            return output.getvalue()


def _handle_output(process: subprocess.Popen[str], *files: TextIO) -> None:
    process_stdout = process.stdout
    assert process_stdout is not None
    while True:
        output = process_stdout.read(1)
        if output:
            for f in files:
                f.write(output)
        elif process.poll() is not None:
            break
