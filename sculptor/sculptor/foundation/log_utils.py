from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import loguru

from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.constants import HIGH_PRIORITY_LEVEL
from sculptor.foundation.constants import LOW_PRIORITY_LEVEL
from sculptor.foundation.constants import MEDIUM_PRIORITY_LEVEL

LOCATION_WIDTH = 60
TRACE = "TRACE"

# between DEBUG and INFO:  https://loguru.readthedocs.io/en/stable/api/logger.html
DETAIL = "DETAIL"
DETAIL_LEVEL = 15

# the first 4 chars are used for "tsk_" and the next ~7 bytes are used for the timestamp
# thus we need at least a few extra characters to make sure task IDs remain distinguishable when two tasks are created
# very close in time
TASK_ID_MESSAGE_WIDTH = 16

LOG_LEVEL_NO_COLOR_TUPLES = [
    (DETAIL, DETAIL_LEVEL, "<fg 128,128,128>"),
    (ExceptionPriority.LOW_PRIORITY.value, LOW_PRIORITY_LEVEL, "<yellow>"),
    (ExceptionPriority.MEDIUM_PRIORITY.value, MEDIUM_PRIORITY_LEVEL, "<fg 255,127,0>"),
    (ExceptionPriority.HIGH_PRIORITY.value, HIGH_PRIORITY_LEVEL, "<red>"),
]


def fix_full_location(record: "loguru.Record") -> str:
    """
    One goal of this function is to format the location in an IDE-friendly way,
    so that control-clicking on the logged location opens the correct file
    and puts the cursor at the correct line.

    `record` looks like this:
    ```
    {
        "elapsed": datetime.timedelta(seconds=5, microseconds=152312),
        "exception": None,
        "extra": {
            "machine": "32de5bcafaa8",
            "user": "user",
            "agent_type": None,
            "agent_id": None,
            "parent_id": None,
            "async_task_id": None,
            "formatted_task_id": "",
            "formatted_agent_id": "",
            "sandbox_id": None,
            "formatted_sandbox_id": "",
        },
        "file": (
            name="error_dump_utils.py",
            path="/home/user/src/sculptor/sculptor.foundation/sculptor.foundation/error_dump_utils.py",
        ),
        "function": "write_exception",
        "level": (name="INFO", no=20, icon="ℹ️"),
        "line": 214,
        "message": "Full traceback for  is available at http://example-host:7777/exceptions/user__notebook_2025_01_28/1000__2025_01_28_17_47_19_170102__P000_W0000/C0000__user_10.0.0.1_5045/2025_03_06_09_59_10_188008_KeyboardInterrupt_traceback.txt",
        "module": "error_dump_utils",
        "name": "sculptor.foundation.error_dump_utils",
        "process": (id=3099015, name="MainProcess"),
        "thread": (id=140434013706048, name="MainThread"),
        "time": datetime(
            2025, 3, 6, 9, 59, 10, 920101, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=57600), "PST")
        ),
    }
    ```
    """
    log_path = Path(record["file"].path)
    try:
        cwd = Path.cwd()
    except FileNotFoundError:
        cwd = Path("/")

    if log_path.is_relative_to(cwd):
        log_path = log_path.relative_to(cwd)
    location: str = record["extra"].get("full_location", f"{str(log_path)}:{record['line']}:{record['function']}")
    while len(location) > LOCATION_WIDTH and "/" in location:
        location = location[location.find("/") + 1 :]
    return location[-LOCATION_WIDTH:].rjust(LOCATION_WIDTH)


def format_task_id(async_task_id: str) -> str:
    """Right-justify a task ID to a fixed width so log columns stay aligned."""
    return async_task_id[:TASK_ID_MESSAGE_WIDTH].rjust(TASK_ID_MESSAGE_WIDTH)


def ensure_core_log_levels_configured(additional_log_levels: Mapping[str, int] | None = None) -> None:
    """Register the DETAIL and ExceptionPriority log levels, plus any additional levels, idempotently."""
    loguru.logger.trace("configuring detail and ExceptionPriority log levels")
    for level, no, color in LOG_LEVEL_NO_COLOR_TUPLES:
        try:
            loguru.logger.level(level, no=no, color=color)
        except (TypeError, ValueError) as e:
            is_level_already_set_thus_ok = "already exists, you can't update its severity no" in str(e)
            if not is_level_already_set_thus_ok:
                raise

    if additional_log_levels is None:
        return

    loguru.logger.trace("configuring additional log levels {}", additional_log_levels)
    for level_name, level_no in additional_log_levels.items():
        try:
            loguru.logger.level(level_name, no=level_no)
        except (TypeError, ValueError) as e:
            is_level_already_set_thus_ok = "already exists, you can't update its severity no" in str(e)
            if not is_level_already_set_thus_ok:
                raise


def log_and_exit_program(exit_code: int, final_message: str) -> None:
    """Log a final message and then immediately exit the program.

    We enforce the final message so that the last line that the user sees is relevant to the shutdown.
    """
    loguru.logger.info(final_message)
    os._exit(exit_code)
