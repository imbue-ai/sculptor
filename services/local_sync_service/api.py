import abc
import datetime
from enum import StrEnum
from typing import Optional

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.pydantic_serialization import FrozenModel
from imbue_core.pydantic_serialization import MutableModel
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import LocalSyncMessageUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdateMessage
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import ObserverLifecycle
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import SlightlySaferObserver
from sculptor.services.local_sync_service.path_batch_scheduler import LocalSyncPathBatchSchedulerStatus


class SyncSessionInfo(MutableModel):
    """Represents an active sync process for a task."""

    task_id: TaskID
    project_id: ProjectID
    sync_name: str
    sync_branch: str
    original_branch: str

    @property
    def is_switching_branches(self) -> bool:
        return self.original_branch != self.sync_branch


class LocalSyncHighLevelStatus(StrEnum):
    """This rolls intermediate, transient, and granular states into the simple high-level status"""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"

    @property
    def is_paused(self) -> bool:
        return self == LocalSyncHighLevelStatus.PAUSED


class LocalSyncSessionState(FrozenModel):
    info: SyncSessionInfo
    scheduler_status: LocalSyncPathBatchSchedulerStatus
    observer_lifecycle: ObserverLifecycle
    start_time: datetime.datetime
    stop_time: datetime.datetime | None
    last_sent_message: LocalSyncMessageUnion | None = None

    @property
    def notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        if isinstance(self.last_sent_message, LocalSyncUpdateMessage):
            return self.last_sent_message.all_notices
        return ()

    @classmethod
    def build_if_sensible(
        cls,
        info: SyncSessionInfo,
        observer: SlightlySaferObserver,
        last_sent_message: LocalSyncMessageUnion | None,
        scheduler_status: LocalSyncPathBatchSchedulerStatus,
    ) -> Optional["LocalSyncSessionState"]:
        start_time = observer.start_time
        if observer.lifecycle == ObserverLifecycle.INITIALIZED or start_time is None:
            logger.debug("surprising: reconciler state requested before observer started")
            return None

        return cls(
            info=info,
            scheduler_status=scheduler_status,
            observer_lifecycle=observer.lifecycle,
            start_time=start_time,
            stop_time=observer.stop_time,
            last_sent_message=last_sent_message,
        )

    @property
    def high_level_status(self) -> LocalSyncHighLevelStatus:
        if self.observer_lifecycle in (ObserverLifecycle.STOPPED, ObserverLifecycle.STOPPING):
            return LocalSyncHighLevelStatus.STOPPED
        if self.scheduler_status == LocalSyncPathBatchSchedulerStatus.STOPPING:
            return LocalSyncHighLevelStatus.STOPPED
        elif self.scheduler_status.is_paused:
            return LocalSyncHighLevelStatus.PAUSED

        assert self.scheduler_status.is_active, f"Impossible: Unexpected reconciler status: {self.scheduler_status}"
        return LocalSyncHighLevelStatus.ACTIVE


class LocalSyncService(Service, abc.ABC):
    """Manages bidirectional sync between local development environment and task containers"""

    @abc.abstractmethod
    def get_session_state(self) -> LocalSyncSessionState | None: ...

    @abc.abstractmethod
    def sync_to_task(self, task_id: TaskID, transaction: DataModelTransaction, task: Task | None = None) -> None:
        """Start bidirectional working tree + unidirectional git sync for a task."""

    @abc.abstractmethod
    def unsync_from_task(
        self, task_id: TaskID, transaction: DataModelTransaction, switching_to_task: bool = False
    ) -> None:
        """Stop sync and restore original state.

        Args:
            task_id: The task to disable sync for
            switching_to_task: If True, we're switching to another task (skip restore)
        """

    @abc.abstractmethod
    def cleanup_current_sync(self, transaction: DataModelTransaction) -> None:
        """Cleanup current sync and restore original state for currently synced task. NOTE: there should only ever be one sync active at a time."""

    @abc.abstractmethod
    def is_task_synced(self, task_id: TaskID) -> bool:
        # TODO(mjr): unify with session_state once old service is deleted
        """Check if a task is currently synced."""
