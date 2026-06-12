from __future__ import annotations

import asyncio
from typing import Protocol
from typing import Sequence
from typing import TYPE_CHECKING

from imbue_core.computing_environment.data_types import AnyPath
from imbue_core.computing_environment.data_types import RunCommandError

# Import the types needed for file modes
if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


class ComputingEnvironment(Protocol):
    """Protocol defining the interface for a computing environment.

    This protocol specifies the required methods for interacting with a computing
    environment, including running commands and file operations.
    """

    async def run_command(
        self,
        command: Sequence[str],
        check: bool = True,
        secrets: dict[str, str] | None = None,
        cwd: AnyPath | None = None,
        is_error_logged: bool = True,
    ) -> str: ...

    async def run_git(
        self,
        command: Sequence[str],
        check: bool = True,
        cwd: AnyPath | None = None,
        is_error_logged: bool = True,
        is_stripped: bool = True,
        retry_on_git_lock_error: bool = True,
    ) -> str: ...

    async def write_file(
        self,
        relative_path: AnyPath,
        content: str | bytes | None,
        cwd: AnyPath | None = None,
        mode: OpenTextModeWriting | OpenBinaryModeWriting = "w",
        mkdir_if_missing: bool = True,
    ) -> None: ...

    async def read_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
        mode: OpenTextModeReading | OpenBinaryModeReading = "r",
        mkdir_if_missing: bool = True,
    ) -> str | bytes: ...

    async def delete_file(
        self,
        relative_path: AnyPath,
        cwd: AnyPath | None = None,
    ) -> None: ...


async def run_command_with_retry_on_git_lock_error(
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
            return await computing_environment.run_command(
                command, check=check, is_error_logged=is_error_logged and retry_count >= max_retries, cwd=cwd
            )
        except RunCommandError as e:
            error_message = str(e)
            if "fatal: Unable to create" in error_message and ".git/index.lock': File exists" in error_message:
                if retry_count >= max_retries:
                    raise
                await asyncio.sleep(retry_delay)
                retry_count += 1
            else:
                raise
