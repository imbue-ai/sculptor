import datetime
import sys
import typing
from pathlib import Path
from typing import Callable

import loguru
from cachetools import LRUCache
from loguru import logger
from loguru._file_sink import FileSink

from imbue_core.common import is_running_within_a_pytest_tree
from sculptor.config.settings import TEST_LOG_PATH
from sculptor.utils.build import is_dev_build

if typing.TYPE_CHECKING:
    from loguru import Message

from imbue_core.log_utils import ensure_core_log_levels_configured
from imbue_core.log_utils import fix_full_location
from imbue_core.log_utils import format_task_id

FANCY_FORMAT = "{time:HH:mm:ss.SSS} |<level>{level: <7}</level>| <cyan>{extra[full_location]}</cyan><green>{extra[formatted_context]}</green>:{extra[route]} - <level>{message}</level>"

LOG_EXTENSION = "jsonl"
ZIPPED_LOG_EXTENSION = "gz"

# not quite sure what type that loguru callable expects, is undocumented
FileObject = typing.Any


def setup_default_test_logging() -> None:
    setup_loggers(
        log_file=TEST_LOG_PATH / "server" / "logs.jsonl",
        level="TRACE",
        deployer_branch_slug="_testing",
    )


def setup_loggers(
    log_file: Path,
    level: str,
    format: str = FANCY_FORMAT,
    deployer_branch_slug: str | None = None,
    is_rotation_enabled: bool = True,
    # these are straight from loguru, with our own defaults
    # see here for details: https://loguru.readthedocs.io/en/stable/api/logger.html#file
    # roughly our defaults correspond to "keep up to 1GB of uncompressed data, stored as up to 10 files, where the inactive files are commpressed"
    # (with the additional caveat that we keep 10x as much data if we're in dev mode)
    rotation: (
        int | datetime.time | datetime.timedelta | str | Callable[["Message", FileObject], bool] | None
    ) = "0.1 GB",
    retention: int | datetime.timedelta | str | Callable[[list[str]], None] | None = None,
    compression: str | Callable[[str | Path], None] | None = ZIPPED_LOG_EXTENSION,
) -> None:
    assert str(log_file).endswith(f".{LOG_EXTENSION}"), "log file must end with .jsonl"
    # Create logs directory if it doesn't exist (including parent directories)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    required_level = logger.level(level).no
    logger.configure(
        patcher=_patch_log_context_in_place,
        extra={
            "program": "sculptor",
            "deployer_branch_slug": deployer_branch_slug,
            "formatted_context": "",
            "route": "",
        },
    )

    # Store the default handler ID (loguru adds one by default on import)
    # The default handler has ID 0
    default_handler_id = 0

    # Remove only the default handler if it exists - do not remove other custom handlers
    # pyre-ignore[16]: Accessing private field _core
    if default_handler_id in logger._core.handlers:
        logger.remove(default_handler_id)

    # add the stderr handler
    _stderr_log_handler = logger.add(sys.__stderr__, level=required_level, format=format, diagnose=False)  # type: ignore

    # install internal log levels for exception reporting
    ensure_core_log_levels_configured()

    # retain extra logs if we are developers
    is_dev = is_dev_build() or is_running_within_a_pytest_tree()
    if retention is None:
        retention = (100 if is_dev else 10) if is_rotation_enabled else None
    # note that we write all lines to the main log file, and all task-specific logs are also written to their own files
    # add the structured local file logger
    log_writer = LogWriter(
        log_file,  # we save roughly 1GB of raw logs (in production)
        # make a new log file once the primary one reaches 0.5 GB
        rotation=rotation if is_rotation_enabled else None,
        # how many past log files to keep around
        retention=retention,
        # make sure we compress the older ones to save space
        compression=compression if is_rotation_enabled else None,
    )
    logger.add(
        log_writer,
        serialize=True,
        format=format,
        level="TRACE",
        diagnose=False,
    )


class LogWriter(FileSink):
    def __init__(
        self,
        path,
        *,
        rotation: int
        | datetime.time
        | datetime.timedelta
        | str
        | Callable[["Message", FileObject], bool]
        | None = None,
        retention: int | datetime.timedelta | str | Callable[[list[str]], None] | None = None,
        compression: str | Callable[[str | Path], None] | None = None,
        delay=False,
        watch=False,
        mode="a",
        buffering=1,
        encoding="utf8",
        **kwargs,
    ):
        assert watch is False, "watch=True is not supported in this wrapper"
        super().__init__(
            path,
            rotation=rotation,
            retention=retention,
            compression=compression,
            delay=delay,
            watch=watch,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            **kwargs,
        )
        self.log_file_path = Path(path)
        # LRU cache to store file handles for task-specific logs
        # so that we can close them when they are no longer needed
        # note that the 200 is a balance between the risk of running out of file handles
        # and the maximum number of concurrent tasks you can have before performance degrades
        self.task_file_cache = _LRUCacheThatClosesFiles(maxsize=200)

    def write(self, message: "Message") -> None:
        # write to the main log file
        super().write(message)
        # if there is a task_id in the message, write to the task-specific log file
        extra_data = message.record["extra"]
        if "task_id" in extra_data:
            task_id_str = str(extra_data["task_id"])

            # open a new file handle for this task_id if necessary
            if task_id_str not in self.task_file_cache:
                task_log_file = self.log_file_path.parent.parent / "tasks" / f"{task_id_str}.json"
                task_log_file.parent.mkdir(parents=True, exist_ok=True)
                self.task_file_cache[task_id_str] = task_log_file.open("a", encoding="utf-8")
            task_log_file = self.task_file_cache[task_id_str]

            # write to the task-specific log file
            task_log_file.write(message)


class _LRUCacheThatClosesFiles(LRUCache):
    def __delitem__(self, key: str) -> None:
        if key in self:
            value = self[key]
            value.close()
        super().__delitem__(key)


def _patch_log_context_in_place(
    record: "loguru.Record", format_task_id: Callable[[str], str] = format_task_id
) -> None:
    record["extra"]["full_location"] = fix_full_location(record)
    task_id: str | None = record["extra"].get("task_id", None)
    if task_id is None:
        request_id: str | None = record["extra"].get("request_id", "")
        # formatted_context = format_task_id(str(request_id) if request_id else "")
        formatted_context = str(request_id) if request_id else ""
        record["extra"]["formatted_context"] = f" [{formatted_context}]"
    else:
        formatted_context = format_task_id(str(task_id))
        record["extra"]["formatted_context"] = f" [{formatted_context}]"
