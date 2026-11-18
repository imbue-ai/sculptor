import threading

from sculptor.primitives.ids import WorkspaceID


class StaleWorkingCopyRegistry:
    """The jj workspaces whose working copy the last snapshot found stale.

    A snapshot that fails as stale marks a workspace; a snapshot or an update
    that succeeds clears it. Recovery is the user's choice, so nothing here
    updates a working copy.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stale_workspace_ids: set[WorkspaceID] = set()

    def mark_stale(self, workspace_id: WorkspaceID) -> None:
        with self._lock:
            self._stale_workspace_ids.add(workspace_id)

    def mark_fresh(self, workspace_id: WorkspaceID) -> None:
        with self._lock:
            self._stale_workspace_ids.discard(workspace_id)

    def is_stale(self, workspace_id: WorkspaceID) -> bool:
        with self._lock:
            return workspace_id in self._stale_workspace_ids
