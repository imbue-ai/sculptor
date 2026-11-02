from pathlib import Path
from typing import assert_never

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy

_CHECKOUT_DIRECTORY_NAME = "code"


def workspace_checkout_path(workspace: Workspace, repo_path: Path) -> Path | None:
    """Where a workspace's checkout lives, computed without resuming its environment.

    `repo_path` is the user's repository, which an in-place workspace works in
    directly. A clone or worktree checkout lives in the `code` directory of the
    workspace's environment, so it is None until an environment exists. The path
    is not checked for existence.
    """
    match workspace.initialization_strategy:
        case WorkspaceInitializationStrategy.IN_PLACE:
            return repo_path
        case WorkspaceInitializationStrategy.CLONE | WorkspaceInitializationStrategy.WORKTREE:
            if workspace.environment_id is None:
                return None
            return Path(workspace.environment_id) / _CHECKOUT_DIRECTORY_NAME
        case _ as unreachable:
            assert_never(unreachable)
