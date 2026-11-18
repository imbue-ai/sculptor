"""Where each workspace kind's checkout lives, from the kind and the directories around it."""

from pathlib import Path
from typing import assert_never

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy

_CHECKOUT_DIRECTORY_NAME = "code"


def is_isolated_checkout(initialization_strategy: WorkspaceInitializationStrategy) -> bool:
    """Whether a workspace of this kind gets a fresh checkout of its own, rather than working in the user's repository."""
    match initialization_strategy:
        case WorkspaceInitializationStrategy.IN_PLACE:
            return False
        case (
            WorkspaceInitializationStrategy.CLONE
            | WorkspaceInitializationStrategy.WORKTREE
            | WorkspaceInitializationStrategy.JJ_WORKSPACE
        ):
            return True
        case _ as unreachable:
            assert_never(unreachable)


def checkout_path_for_strategy(
    initialization_strategy: WorkspaceInitializationStrategy,
    repo_path: Path | None,
    environment_path: Path | None,
) -> Path | None:
    """Where a checkout of this kind lives, or None when the directory it lives under is unknown.

    `repo_path` is the user's repository and `environment_path` the workspace's
    environment directory. The path is not checked for existence.
    """
    if not is_isolated_checkout(initialization_strategy):
        return repo_path
    if environment_path is None:
        return None
    return environment_path / _CHECKOUT_DIRECTORY_NAME
