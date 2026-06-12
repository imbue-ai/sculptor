from __future__ import annotations

from enum import StrEnum


class TaskState(StrEnum):
    """The possible states of a server task."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"
    SUCCEEDED = "SUCCEEDED"
