"""Best-effort sweep of legacy on-disk MRU files.

Runs idempotently on every server startup; once the files are gone the
sweep is a no-op. The previous implementation persisted the most
recently used workspace and per-workspace agent ids to text files under
~/.sculptor/. After the move to localStorage on the frontend, those
files are unused and would otherwise sit on disk forever.
"""

from loguru import logger

from sculptor.utils.build import get_internal_folder
from sculptor.utils.build import get_workspaces_folder

_LEGACY_WORKSPACE_MRU_FILENAME = "most_recently_used_workspace.txt"
_LEGACY_AGENT_MRU_GLOB = "most_recently_used_agent_*.txt"


def cleanup_obsolete_mru_files() -> None:
    """Remove the obsolete MRU text files left over from before the localStorage migration."""
    workspace_mru = get_internal_folder() / _LEGACY_WORKSPACE_MRU_FILENAME
    try:
        workspace_mru.unlink(missing_ok=True)
        for path in get_workspaces_folder().glob(_LEGACY_AGENT_MRU_GLOB):
            path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to remove one or more legacy MRU files: {}", exc)
