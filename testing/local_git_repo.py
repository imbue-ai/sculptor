"""Synchronous version of LocalGitRepo in imbue_core"""

from __future__ import annotations

import contextlib
import shlex
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from threading import Lock
from typing import Any
from typing import Generator
from typing import IO
from typing import Self
from typing import Sequence
from typing import TYPE_CHECKING
from typing import TextIO

import anyio
import attr
from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.computing_environment.data_types import AnyPath
from imbue_core.computing_environment.data_types import RunCommandError
from imbue_core.constants import ExceptionPriority
from sculptor.testing.computing_environment import assert_repo_is_clean
from sculptor.testing.computing_environment import get_head_hash
from sculptor.testing.computing_environment import run_command_with_retry_on_git_lock_error
from sculptor.utils.file_utils import copy_dir

if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryMode
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextMode
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting

PYTHON_EXTENSION = ".py"


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


def get_git_repo_root_from_path(path: Path) -> Path:
    """Gets a Path to the git repo root for the given path."""
    if path.is_file():
        path = path.parent
    completed_process = subprocess.run(
        ["git", "-C", path, "rev-parse", "--show-toplevel"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    root_dir = Path(completed_process.stdout.decode().strip())
    assert root_dir.is_dir(), f"{root_dir} must be a directory"
    return root_dir


REPO_LOCKS: dict[Path, Lock] = {}


@attr.s(auto_attribs=True, frozen=True)
class LocalGitRepo:
    base_path: Path

    @classmethod
    def build_from_cwd(cls) -> Self:
        """Create a `LocalGitRepo` instance from the current working directory."""
        return cls(get_git_repo_root())

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
        # TODO: check for whether hooks should actually be run when we call this function
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
                f"Command {command_string} failed to decode stdout, replacing any invalid bytes which could lead to problems later",
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

    def read_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
        mode: OpenTextModeReading | OpenBinaryModeReading = "r",
        mkdir_if_missing: bool = True,
    ) -> str | bytes:
        with self._open_file(relative_path, cwd=cwd, mode=mode, mkdir_if_missing=mkdir_if_missing) as f:
            logger.trace("reading file {} in cwd {} with mode {}", relative_path, cwd, mode)
            content = f.read()
            assert isinstance(content, str) or isinstance(content, bytes)
            return content

    def head_hash(self) -> str:
        """Get the hash of the current HEAD commit."""
        return get_head_hash(self)

    def is_git_repo(self) -> bool:
        """Check that repo is valid git repo."""
        return Path(self.base_path / ".git").exists()

    def assert_clean(self) -> None:
        assert_repo_is_clean(self)

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
        # TODO: mjr doesn't think we need these quotes anymore but should be done in standalone MR
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

    @contextlib.contextmanager
    def temporary_commit(
        self, tag_prefix: str, commit_message: str, raise_on_head_hash_change: bool = False
    ) -> Generator[str, None, None]:
        """Context manager to make a temporary commit and tag in the repo."""
        self.run_git(("commit", "-am", commit_message, "--allow-empty", "--no-verify"))
        head_hash = self.head_hash()
        tag = f"{tag_prefix}/{head_hash}"
        self.run_git(("tag", tag))
        self.run_git(("push", "origin", tag, "--no-verify"))
        try:
            yield head_hash
        finally:
            # This is susceptible to a race condition (if the user makes a commit between the time we check the head hash and the time we reset the state).
            # So it's important to keep any block that uses this context manager short - make the commit, copy it to the controller, and work there. Don't hold the repo hostage.
            current_head_hash = self.head_hash()
            if current_head_hash != head_hash and raise_on_head_hash_change:
                raise AssertionError(
                    f"Head hash has changed from {head_hash} to {current_head_hash} since the temporary commit was made. Giving up on resetting git state, please address this manually."
                )
            else:
                self.run_git(("reset", "HEAD~"))

    def copy_repo(self, new_repo_path: Path, exists_ok: bool = True) -> "LocalGitRepo":
        """Make a full copy of this repo in a new directory.

        Note, this will copy all the files in the repo into a new local directory, but will not handle
        configuring the new directory as a git repo.
        """
        if Path(new_repo_path).exists():
            if not exists_ok:
                raise FileExistsError(
                    f"New repo path '{new_repo_path} already exists. Set `exists_ok=True` if you are happy overwriting it, otherwise select new path."
                )
            shutil.rmtree(new_repo_path)
        copy_dir(
            self.base_path,
            new_repo_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".gitsecret"),
        )
        return LocalGitRepo(new_repo_path)

    def clone_repo(self, target_path: Path, flags: tuple[str, ...] = tuple()) -> LocalGitRepo:
        target_path.mkdir(parents=True, exist_ok=True)
        target_repo = LocalGitRepo(target_path)
        target_repo.run_git(["clone", *flags, str(self.base_path), str(target_path)])
        return target_repo

    def is_path_in_repo(self, file_path: str | Path | anyio.Path) -> bool:
        """Check whether a given file path is within this repo.

        FIXME: It doesn't seem entirely necessary to enumerate all of the files with a particular extension
               just to check if a single file (whose path we know) is in the repo.
        """
        if isinstance(file_path, (str, Path)):
            file_path = anyio.Path(file_path)
        extension = file_path.suffix
        return file_path in self.get_all_files_by_extension(extension=extension)

    def _get_file_path(self, file_path: str | Path) -> Path:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(self.base_path / path)
        assert path.exists(), f"File {path} does not exist."
        return path

    def safely_read_file_from_repo(self, file_path: str | Path) -> str:
        """Safely read file from repo."""
        path = self._get_file_path(file_path)
        assert self.is_path_in_repo(path), f"File {path} is not in repo."
        return path.read_text()

    def get_all_files_by_extension(self, extension: str = PYTHON_EXTENSION) -> tuple[Path, ...]:
        """Get absolute path of all files in the repo with given extension."""
        paths: list[Path] = []
        for path in Path(self.base_path).rglob(f"*{extension}"):
            paths.append(Path(path))
        return tuple(paths)


def copy_files_from_one_repo_to_another(
    src_repo_path: Path, dst_repo_path: Path, relative_file_paths: Sequence[str | Path]
) -> None:
    """Copies files from src to dst repo using the relative file paths."""
    for relative_path in relative_file_paths:
        src_file_path = src_repo_path / relative_path
        dst_file_path = Path(dst_repo_path / relative_path)
        # make sure necessary directories exist in destination
        dst_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file_path, dst_file_path)


def get_repo_url_from_folder(repo_path: Path) -> str:
    try:
        repo_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=repo_path, universal_newlines=True
        ).strip()
    except subprocess.CalledProcessError:
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
            raise UnableToFindRepoBase() from e


def _run_command_and_capture_output(args: Sequence[str], cwd: Path | None = None) -> str:
    arg_str = " ".join(shlex.quote(arg) for arg in args)
    print(f"Running command: {arg_str}", file=sys.stderr)
    with subprocess.Popen(args, text=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        with StringIO() as output:
            _handle_output(proc, output, sys.stderr)
            if proc.wait() != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd=args, output=output.getvalue())
            return output.getvalue()


class UnableToFindRepoBase(Exception):
    """Raised when the base of the repository cannot be found."""


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


def get_diff_without_index(diff: str) -> str:
    new_lines = []
    for line in diff.splitlines():
        if line.startswith("index "):
            # We replace index lines with "index 0000000..0000000 100644" because:
            # - `0000000..0000000` ensures no real object hashes are referenced, making the diff neutral.
            # - `100644` is the standard file mode for non-executable files in git diffs, ensuring compatibility.
            # - This keeps the diff format valid while removing specific index information.
            new_lines.append("index 0000000..0000000 100644")
        else:
            new_lines.append(line)
    return "\n".join(new_lines).strip()


def is_diffs_without_index_equal(diff_1: str, diff_2: str) -> bool:
    return get_diff_without_index(diff_1) == get_diff_without_index(diff_2)
