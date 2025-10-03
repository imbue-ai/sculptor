from enum import Enum

from imbue_core.agents.data_types.ids import TaskID
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeUnion
from sculptor.services.local_sync_service.local_sync_errors import LocalSyncError

# Local Sync Exceptions


class OtherSyncTransitionInProgressError(LocalSyncError):
    """Exception raised when sync startup fails for a task."""

    def __init__(self, action: str, new_task_id: TaskID) -> None:
        self.task_id = new_task_id
        self.action = action
        message = f"Cannot {action} {new_task_id}: Another sync state transition is in progress"
        super().__init__(message)


class NewNoticesInSyncHandlingError(LocalSyncError):
    def __init__(self, notices: tuple[LocalSyncNoticeUnion, ...]) -> None:
        super().__init__(", AND ".join([n.reason for n in notices]))
        self.notices = notices


class SyncStartupError(LocalSyncError):
    """Exception raised when sync startup fails for a task."""

    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        task_branch: str | None = None,
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.task_branch = task_branch

    def __str__(self) -> str:
        details = [super().__str__()]
        if self.task_id:
            details.append(f"Task ID: {self.task_id}")
        if self.task_branch:
            details.append(f"Task branch: {self.task_branch}")
        return "\n".join(details)


class ExpectedStartupBlocker(Enum):
    USER_GIT_STATE_DIRTY = "USER_GIT_STATE_DIRTY"
    USER_BRANCH_AHEAD_OF_AGENT = "USER_BRANCH_AHEAD_OF_AGENT"
    BRANCHES_DIVERGED = "BRANCHES_DIVERGED"


class ExpectedSyncStartupError(SyncStartupError):
    def __init__(
        self,
        message: str,
        blockers: list[ExpectedStartupBlocker],
        task_id: str | None = None,
        task_branch: str | None = None,
    ) -> None:
        super().__init__(message, task_id, task_branch)
        self.message = message
        self.blockers = blockers

    def __str__(self) -> str:
        details = [super().__str__()]
        details.append(f"Expected blockers: {self.blockers}")
        return "\n".join(details)


class SyncCleanupError(LocalSyncError):
    """Exception raised when sync cleanup fails."""

    def __init__(
        self,
        message: str,
        task_id: TaskID | None = None,
        cleanup_step: str | None = None,
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.cleanup_step = cleanup_step

    def __str__(self) -> str:
        details = [super().__str__()]
        if self.task_id:
            details.append(f"Task ID: {self.task_id}")
        if self.cleanup_step:
            details.append(f"Cleanup step: {self.cleanup_step}")
        return "\n".join(details)


class SyncStateError(LocalSyncError):
    """Exception raised when sync state management fails."""

    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        current_state: str | None = None,
        expected_state: str | None = None,
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.current_state = current_state
        self.expected_state = expected_state

    def __str__(self) -> str:
        details = [super().__str__()]
        if self.task_id:
            details.append(f"Task ID: {self.task_id}")
        if self.current_state:
            details.append(f"Current state: {self.current_state}")
        if self.expected_state:
            details.append(f"Expected state: {self.expected_state}")
        return "\n".join(details)
