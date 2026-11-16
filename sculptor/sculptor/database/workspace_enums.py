"""Workspace-related enums."""

from enum import auto
from typing import Literal

from sculptor.foundation.upper_case_str_enum import UpperCaseStrEnum


class WorkspaceInitializationStrategy(UpperCaseStrEnum):
    """Strategy for workspace initialization.

    IN_PLACE: Work directly in the user's repository.
    CLONE: Work in an isolated clone of the repository.
    WORKTREE: Work in a git worktree off the user's repository (shared `.git`).
    """

    IN_PLACE = auto()
    CLONE = auto()
    WORKTREE = auto()


# The kinds whose checkout is a git checkout.
GitInitializationStrategy = Literal[
    WorkspaceInitializationStrategy.IN_PLACE,
    WorkspaceInitializationStrategy.CLONE,
    WorkspaceInitializationStrategy.WORKTREE,
]


class DiffStatus(UpperCaseStrEnum):
    """Status of workspace diff generation."""

    NONE = auto()
    GENERATING = auto()
    READY = auto()
