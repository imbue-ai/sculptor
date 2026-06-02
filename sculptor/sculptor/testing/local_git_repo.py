"""Synchronous version of LocalGitRepo in sculptor.foundation"""

from __future__ import annotations

import contextlib
import shlex
import shutil
import subprocess
from pathlib import Path
from threading import Lock
from typing import Any
from typing import Generator
from typing import IO
from typing import Sequence
from typing import TYPE_CHECKING

import attr
from loguru import logger

from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.constants import ExceptionPriority
from sculptor.testing.computing_environment import run_command_with_retry_on_git_lock_error
from sculptor.testing.computing_environment_types import AnyPath
from sculptor.testing.computing_environment_types import RunCommandError

if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryMode
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextMode
    from _typeshed import OpenTextModeWriting


REPO_LOCKS: dict[Path, Lock] = {}


@attr.s(auto_attribs=True, frozen=True)
class LocalGitRepo:
    base_path: Path

    def run_git(
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
        absolute_path = self.base_path.absolute()
        if absolute_path not in REPO_LOCKS:
            REPO_LOCKS[absolute_path] = Lock()
        with REPO_LOCKS[absolute_path]:
            command = ["git"] + list(command)
            if not retry_on_git_lock_error:
                result = self.run_command(command, check=check, is_error_logged=is_error_logged, cwd=cwd)
            else:
                result = run_command_with_retry_on_git_lock_error(
                    self, command, check=check, is_error_logged=is_error_logged, cwd=cwd
                )
            if is_stripped:
                return result.strip()
            return result

    def run_command(
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
            "Running command: command_string={} from cwd={} with secrets={} check={} is_error_logged={}",
            command_string,
            cwd or self.base_path,
            secrets,
            check,
            is_error_logged,
        )
        proc = subprocess.Popen(
            command,
            cwd=cwd or self.base_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=secrets,
        )
        # note, need to be careful not to strip() lines since whitespace may be important (e.g. for diffs)
        # return joined lines since mostly we only use the output for logging, and this way we arn't
        # passing around lots of lists. Also it's easy to parse by lines if needed
        stdout_bytes, stderr_bytes = proc.communicate()
        try:
            stdout = stdout_bytes.decode("UTF-8")
        except UnicodeDecodeError as e:
            # If we don't encounter this, it likely means something was fixed upstream and we can safely delete
            log_exception(
                e,
                "Command {command_string} failed to decode stdout, replacing any invalid bytes which could lead to problems later",
                command_string=command_string,
                priority=ExceptionPriority.MEDIUM_PRIORITY,
            )
            stdout = stdout_bytes.decode("UTF-8", errors="replace")
        stderr = stderr_bytes.decode("UTF-8")
        if check and proc.returncode != 0:
            error_message = f"command run from cwd={self.base_path} failed with exit code {proc.returncode} and stdout:\n{stdout}\nstderr:\n{stderr}"
            if is_error_logged:
                logger.error(
                    "command attempted: '{}' from cwd={}\nerror message: {}",
                    command_string,
                    self.base_path,
                    error_message,
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

    @contextlib.contextmanager
    def _open_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
        mode: OpenTextMode | OpenBinaryMode = "r",
        mkdir_if_missing: bool = True,
    ) -> Generator[IO[Any], None, None]:
        logger.trace("opening file {} in cwd {} with mode {}", relative_path, cwd, mode)
        if cwd is not None:
            sb_file_path = str(Path(cwd) / relative_path)
        else:
            sb_file_path = str(self.base_path / relative_path)

        if mkdir_if_missing:
            parent_dir = Path(sb_file_path).parent
            parent_dir.mkdir(parents=True, exist_ok=True)

        f: IO[Any] | None = None
        try:
            f = Path(sb_file_path).open(mode=mode)  # type: ignore
            yield f
        finally:
            if f is not None:
                f.close()

    def write_file(
        self,
        relative_path: AnyPath,
        content: str | bytes | None,
        cwd: AnyPath | None = None,
        mode: OpenTextModeWriting | OpenBinaryModeWriting = "w",
        mkdir_if_missing: bool = True,
    ) -> None:
        if content is None:
            self.delete_file(relative_path, cwd=cwd)
            return

        with self._open_file(relative_path, cwd=cwd, mode=mode, mkdir_if_missing=mkdir_if_missing) as f:
            logger.trace("writing to file {} in cwd {} with mode {}", relative_path, cwd, mode)
            f.write(content)

    def delete_file(self, relative_path: AnyPath, cwd: AnyPath | None = None) -> None:
        logger.trace("deleting the file {} in cwd {}", relative_path, cwd)
        if cwd is not None:
            sb_file_path = str(Path(cwd) / relative_path)
        else:
            sb_file_path = str(self.base_path / relative_path)
        Path(sb_file_path).unlink()

    def is_git_repo(self) -> bool:
        """Check that repo is valid git repo."""
        return Path(self.base_path / ".git").exists()

    def configure_git(
        self,
        git_user_name: str | None = None,
        git_user_email: str | None = None,
        initial_commit_message: str = "initial commit",
        is_recreating: bool = False,
    ) -> None:
        """Configure git repo with user name and email."""
        if is_recreating:
            if self.is_git_repo():
                shutil.rmtree(self.base_path / ".git")

        # order here is important
        # ref https://stackoverflow.com/questions/11656761/git-please-tell-me-who-you-are-error?noredirect=1
        self.run_git(("init",))
        if git_user_name:
            self.run_git(("config", "user.name", f"'{git_user_name}'"))
        if git_user_email:
            self.run_git(("config", "user.email", f"'{git_user_email}'"))
        self.run_git(("add", "."))
        self.run_git(("commit", "-m", f"'{initial_commit_message}'"))
        branch_name = self.run_git(("symbolic-ref", "HEAD"))
        if not branch_name == "refs/heads/main":
            # rename master to main for consistency
            self.run_git(("branch", "-m", "master", "main"))
