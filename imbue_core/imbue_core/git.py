"""Utility abstractions for interacting with git repositories."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from typing import AsyncGenerator
from typing import Sequence
from typing import TYPE_CHECKING
from typing import TextIO

import anyio
import attr
from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.async_utils import sync
from imbue_core.computing_environment.computing_environment import run_command_with_retry_on_git_lock_error
from imbue_core.computing_environment.data_types import AnyPath
from imbue_core.computing_environment.data_types import RunCommandError

if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryMode
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextMode
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


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


@attr.s(auto_attribs=True, frozen=True)
class LocalGitRepo:
    """Async interface for interacting with a local git repository.

    Implements the ComputingEnvironment protocol for use with computing_environment.py functions.
    """

    base_path: Path

    async def run_git(
        self,
        command: Sequence[str],
        check: bool = True,
        cwd: AnyPath | None = None,
        is_error_logged: bool = True,
        is_stripped: bool = True,
        retry_on_git_lock_error: bool = True,
    ) -> str:
        """Run a git command in the repo.

        Example:
        ```
        git_repo.run_git("status")
        ```
        """
        # Note: this used to be within an asyncio lock to prevent the program from concurrently running git commands.
        # This lock was removed since it was within global state, a dangerous pattern, and wasn't preventing other users from interacting with the git repo.
        command = ["git"] + list(command)
        if not retry_on_git_lock_error:
            result = await self.run_command(command, check=check, is_error_logged=is_error_logged, cwd=cwd)
        else:
            result = await run_command_with_retry_on_git_lock_error(
                self, command, check=check, is_error_logged=is_error_logged, cwd=cwd
            )
        if is_stripped:
            return result.strip()
        return result

    async def run_command(
        self,
        command: Sequence[str],
        check: bool = True,
        secrets: dict[str, str] | None = None,
        cwd: AnyPath | None = None,
        is_error_logged: bool = True,
    ) -> str:
        """Run a command in the repo.

        Note, this can be used to run any command, not just git.
        """
        command_string = shlex.join(command)
        logger.trace(
            f"Running command: {command_string=} from cwd={cwd or self.base_path} with {secrets=} {check=} {is_error_logged=}"
        )
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd or self.base_path,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=secrets,
        )
        # note, need to be carefull not to strip() lines since whitespace may be important (e.g. for diffs)
        # return joined lines since mostly we only use the output for logging, and this way we arn't
        # passing around lots of lists. Also it's easy to parse by lines if needed
        stdout_bytes, stderr_bytes = await proc.communicate()
        try:
            stdout = stdout_bytes.decode("UTF-8")
        except UnicodeDecodeError as e:
            # If we don't encounter this, it likely means something was fixed upstream and we can safely delete
            log_exception(
                e,
                "Command {command_string} failed to decode stdout, replacing any invalid bytes which could lead to problems later",
                command_string=command_string,
            )
            stdout = stdout_bytes.decode("UTF-8", errors="replace")
        stderr = stderr_bytes.decode("UTF-8")
        if check and proc.returncode != 0:
            error_message = f"command run from cwd={self.base_path} failed with exit code {proc.returncode} and stdout:\n{stdout}\nstderr:\n{stderr}"
            if is_error_logged:
                logger.error(
                    f"command attempted: '{command_string}' from cwd={self.base_path}\nerror message: {error_message}"
                )
            # this should not be None, but do this to satisfy type checker, int or None we throw the same error
            returncode = proc.returncode or -1
            raise RunCommandError(
                cmd=command_string,
                stderr=stderr,
                returncode=returncode,
                cwd=cwd or self.base_path,
            )
        return stdout

    @contextlib.asynccontextmanager
    async def _open_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
        mode: OpenTextMode | OpenBinaryMode = "r",
        mkdir_if_missing: bool = True,
    ) -> AsyncGenerator[anyio.AsyncFile[Any], None]:
        logger.trace("opening file {} in cwd {} with mode {}", relative_path, cwd, mode)
        if cwd is not None:
            sb_file_path = str(Path(cwd) / relative_path)
        else:
            sb_file_path = str(self.base_path / relative_path)

        if mkdir_if_missing:
            parent_dir = anyio.Path(sb_file_path).parent
            await parent_dir.mkdir(parents=True, exist_ok=True)

        f: anyio.AsyncFile[Any] | None = None
        try:
            f = await anyio.Path(sb_file_path).open(mode=mode)  # type: ignore
            yield f
        finally:
            if f is not None:
                await f.aclose()

    async def write_file(
        self,
        relative_path: AnyPath,
        content: str | bytes | None,
        cwd: AnyPath | None = None,
        mode: OpenTextModeWriting | OpenBinaryModeWriting = "w",
        mkdir_if_missing: bool = True,
    ) -> None:
        if content is None:
            await self.delete_file(relative_path, cwd=cwd)
            return

        async with self._open_file(relative_path, cwd=cwd, mode=mode, mkdir_if_missing=mkdir_if_missing) as f:
            logger.trace("writing to file {} in cwd {} with mode {}", relative_path, cwd, mode)
            await f.write(content)

    async def delete_file(self, relative_path: AnyPath, cwd: AnyPath | None = None) -> None:
        logger.trace("deleting the file {} in cwd {}", relative_path, cwd)
        if cwd is not None:
            sb_file_path = str(Path(cwd) / relative_path)
        else:
            sb_file_path = str(self.base_path / relative_path)
        await anyio.Path(sb_file_path).unlink()

    async def read_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
        mode: OpenTextModeReading | OpenBinaryModeReading = "r",
        mkdir_if_missing: bool = True,
    ) -> str | bytes:
        async with self._open_file(relative_path, cwd=cwd, mode=mode, mkdir_if_missing=mkdir_if_missing) as f:
            logger.trace("reading file {} in cwd {} with mode {}", relative_path, cwd, mode)
            content = await f.read()
            assert isinstance(content, str) or isinstance(content, bytes)
            return content

    async def is_git_repo(self) -> bool:
        """Check that repo is valid git repo."""
        return await anyio.Path(self.base_path / ".git").exists()

    async def configure_git(
        self,
        git_user_name: str | None = None,
        git_user_email: str | None = None,
        initial_commit_message: str = "initial commit",
        is_recreating: bool = False,
    ) -> None:
        """Configure git repo with user name and email."""
        if is_recreating:
            if await self.is_git_repo():
                await asyncio.to_thread(shutil.rmtree, self.base_path / ".git")

        # order here is important
        # ref https://stackoverflow.com/questions/11656761/git-please-tell-me-who-you-are-error?noredirect=1
        await self.run_git(("init",))
        if git_user_name:
            await self.run_git(("config", "user.name", f"'{git_user_name}'"))
        if git_user_email:
            await self.run_git(("config", "user.email", f"'{git_user_email}'"))
        await self.run_git(("add", "."))
        await self.run_git(("commit", "-m", f"'{initial_commit_message}'"))
        branch_name = await self.run_git(("symbolic-ref", "HEAD"))
        if not branch_name == "refs/heads/main":
            # rename master to main for consistency
            await self.run_git(("branch", "-m", "master", "main"))

    sync_configure_git = sync(configure_git)

    async def copy_repo(self, new_repo_path: Path, exists_ok: bool = True) -> "LocalGitRepo":
        """Make a full copy of this repo in a new directory.

        Note, this will copy all the files in the repo into a new local directory, but will not handle
        configuring the new directory as a git repo.
        """
        if await anyio.Path(new_repo_path).exists():
            if not exists_ok:
                raise FileExistsError(
                    f"New repo path '{new_repo_path} already exists. Set `exists_ok=True` if you are happy overwriting it, otherwise select new path."
                )
            await asyncio.to_thread(shutil.rmtree, new_repo_path)
        await asyncio.to_thread(
            shutil.copytree,
            self.base_path,
            new_repo_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".gitsecret"),
        )
        return LocalGitRepo(new_repo_path)

    sync_copy_repo = sync(copy_repo)


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
