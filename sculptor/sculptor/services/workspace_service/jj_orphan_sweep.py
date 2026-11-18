"""Forgetting the jj workspaces Sculptor created whose Sculptor workspace and directory are both gone.

A jj workspace's directory can be deleted without its repository being told,
and the repository then keeps recording the workspace and its working-copy commit.
"""

from collections.abc import Set as AbstractSet
from pathlib import Path

import typeid.errors
from loguru import logger

from sculptor.primitives.ids import TypeIDPrefixMismatchError
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_workspaces


def forget_orphaned_jj_workspaces(jj: JjCli, repo_path: Path, live_workspace_ids: AbstractSet[str]) -> list[str]:
    """Forget each workspace of the repository named by a Sculptor workspace id that is not live and has no directory.

    A workspace whose directory exists is never forgotten: it may belong to
    another Sculptor instance on the same repository. Returns the names forgotten.
    """
    orphaned_names = [
        entry.name
        for entry in list_workspaces(jj, repo_path)
        if _is_workspace_id(entry.name) and entry.name not in live_workspace_ids and not entry.root.exists()
    ]
    for name in orphaned_names:
        logger.debug(
            "Forgetting jj workspace {} in {}: its Sculptor workspace and directory are gone", name, repo_path
        )
        forget_workspace(jj, repo_path, name)
    return orphaned_names


def _is_workspace_id(name: str) -> bool:
    try:
        WorkspaceID(name)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError):
        return False
    return True
