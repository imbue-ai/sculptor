from pathlib import Path

from sculptor.database.models import Workspace
from sculptor.services.workspace_service.vcs.checkout_layout import checkout_path_for_strategy


def workspace_checkout_path(workspace: Workspace, repo_path: Path) -> Path | None:
    """Where a workspace's checkout lives, computed without resuming its environment.

    A clone or worktree checkout is None until the workspace has an environment.
    """
    environment_path = None if workspace.environment_id is None else Path(workspace.environment_id)
    return checkout_path_for_strategy(workspace.initialization_strategy, repo_path, environment_path)
