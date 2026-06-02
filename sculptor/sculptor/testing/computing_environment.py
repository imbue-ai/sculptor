from __future__ import annotations

import shlex
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol
from typing import Sequence
from typing import TYPE_CHECKING
from uuid import uuid4

import anyio
from loguru import logger

from sculptor.foundation.computing_environment.data_types import AnyPath
from sculptor.foundation.computing_environment.data_types import FailedToMakeCommitError
from sculptor.foundation.computing_environment.data_types import PatchApplicationError
from sculptor.foundation.computing_environment.data_types import RunCommandError
from sculptor.foundation.git_data_types import CommitTimestamp
from sculptor.foundation.section import Section
from sculptor.foundation.time_utils import get_current_time

# Import the types needed for file modes
if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeWriting


class ComputingEnvironment(Protocol):
    """Protocol defining the interface for a computing environment.

    This protocol specifies the required methods for interacting with a computing
    environment, including running commands and file operations.
    """

    def run_command(
        self,
        command: Sequence[str],
        check: bool = True,
        secrets: dict[str, str] | None = None,
        cwd: AnyPath | None = None,
        is_error_logged: bool = True,
    ) -> str: ...

    def run_git(
        self,
        command: Sequence[str],
        check: bool = True,
        cwd: AnyPath | None = None,
        is_error_logged: bool = True,
        is_stripped: bool = True,
        retry_on_git_lock_error: bool = True,
    ) -> str: ...

    def write_file(
        self,
        relative_path: AnyPath,
        content: str | bytes | None,
        cwd: AnyPath | None = None,
        mode: OpenTextModeWriting | OpenBinaryModeWriting = "w",
        mkdir_if_missing: bool = True,
    ) -> None: ...

    def delete_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
    ) -> None: ...


def _get_temp_patch_file() -> anyio.Path:
    # this triggers the file watcher
    # patch_file = (self.base_path / str(uuid4())).with_suffix(".patch")
    patch_file = (Path("/tmp") / uuid4().hex).with_suffix(".patch")
    return anyio.Path(patch_file)


def run_command_with_retry_on_git_lock_error(
    computing_environment: ComputingEnvironment,
    command: Sequence[str],
    check: bool = True,
    is_error_logged: bool = True,
    cwd: AnyPath | None = None,
) -> str:
    max_retries = 50
    retry_count = 0
    retry_delay = 0.1  # seconds
    while True:
        try:
            return computing_environment.run_command(
                command, check=check, is_error_logged=is_error_logged and retry_count >= max_retries, cwd=cwd
            )
        except RunCommandError as e:
            error_message = str(e)
            is_potentially_transient_lock_error = (
                "fatal: Unable to create" in error_message and ".git/index.lock': File exists" in error_message
            )
            is_retry_limit_reached = retry_count >= max_retries
            if is_retry_limit_reached or (not is_potentially_transient_lock_error):
                raise
            retry_count += 1
            logger.trace(
                "{} failed due to git lock error, retrying (attempt {}/{}, error: {})",
                command,
                retry_count + 1,
                max_retries,
                error_message,
            )
            time.sleep(retry_delay)


def get_branch_name(computing_environment: ComputingEnvironment, is_error_logged: bool = True) -> str:
    """Get the name of the current branch."""
    return computing_environment.run_git(("symbolic-ref", "--short", "HEAD"), is_error_logged=is_error_logged)


def create_reset_and_checkout_branch(computing_environment: ComputingEnvironment, branch_name: str) -> str:
    """Create new branch with given name."""
    return computing_environment.run_git(("switch", "-C", branch_name))


def switch_branch(computing_environment: ComputingEnvironment, branch_name: str) -> str:
    """Switch to branch with given name."""
    return computing_environment.run_git(("switch", branch_name))


def convert_datetime_to_git_timestamp(dt: datetime) -> str:
    return datetime.isoformat(dt)


def get_commit_ts_for_current_time() -> CommitTimestamp:
    """Get the commit timestamp for the current time."""
    current_time = get_current_time()
    return CommitTimestamp(
        author_ts=convert_datetime_to_git_timestamp(current_time),
        committer_ts=convert_datetime_to_git_timestamp(current_time),
    )


def _convert_time_to_commit_ts(time: str | datetime | CommitTimestamp | None) -> CommitTimestamp:
    if time is None:
        return get_commit_ts_for_current_time()
    elif isinstance(time, datetime):
        return CommitTimestamp(
            author_ts=convert_datetime_to_git_timestamp(time), committer_ts=convert_datetime_to_git_timestamp(time)
        )
    elif isinstance(time, CommitTimestamp):
        return time
    else:
        # assume it's a git timestamp
        return CommitTimestamp(author_ts=time, committer_ts=time)


def make_commit(
    computing_environment: ComputingEnvironment,
    commit_message: str,
    allow_empty: bool = False,
    amend: bool = False,
    commit_time: str | datetime | CommitTimestamp | None = None,
) -> str:
    if commit_message.strip() == "":
        commit_message = "No commit message provided"

    commit_ts = _convert_time_to_commit_ts(commit_time)
    time_args = f'GIT_AUTHOR_DATE="{commit_ts.author_ts}" GIT_COMMITTER_DATE="{commit_ts.committer_ts}" '

    commit_message = shlex.quote(commit_message)
    no_changes_message = "No changes to commit"
    amend_args = "--amend " if amend else ""
    if allow_empty or amend:
        bash_command = f"""git add . && {time_args}git commit {amend_args}--allow-empty -m {commit_message} > /dev/null && git rev-parse HEAD"""
    else:
        bash_command = f"""git add . && ( git status | grep -q "nothing to commit" && echo "{no_changes_message}" ) || ( {time_args}git commit {amend_args}-m {commit_message} > /dev/null && git rev-parse HEAD )"""

    with Section(f"committing changes with message: '{commit_message}'", log_level="DEBUG"):
        stdout = run_command_with_retry_on_git_lock_error(
            computing_environment,
            ["bash", "-c", bash_command],
        )
        stdout = stdout.strip()
        if stdout == no_changes_message:
            raise FailedToMakeCommitError(f"Failed to make commit with message: {commit_message}. {bash_command=}")
        new_git_hash = stdout
        return new_git_hash


def apply_patch_via_git(computing_environment: ComputingEnvironment, git_diff: str, is_error_logged: bool) -> None:
    """Apply a diff to repo."""
    if git_diff.strip() == "":
        return
    patch_file = _get_temp_patch_file()
    computing_environment.write_file(patch_file, git_diff)
    # NOTE: --allow-empty is necessary because the patch may be empty, or result in no changes,
    #  but it isn't available in older git versions we still need to support, so we fall back
    #  to the error check below.
    try:
        computing_environment.run_git(("apply", "--verbose", str(patch_file)), is_error_logged=is_error_logged)
    except RunCommandError as e:
        raise PatchApplicationError(f"Failed to apply patch: {e}") from e
    finally:
        computing_environment.delete_file(patch_file)
