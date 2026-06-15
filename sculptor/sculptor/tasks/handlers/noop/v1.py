import datetime
from typing import Any
from typing import Callable

from loguru import logger

from sculptor.database.models import NoOpTaskInputsV1
from sculptor.database.models import Task
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.task_service.data_types import ServiceCollectionForTask


def run_noop_task_v1(
    task_data: NoOpTaskInputsV1,
    task: Task,
    services: ServiceCollectionForTask,
    task_deadline: datetime.datetime | None,
) -> Callable[[DataModelTransaction], Any] | None:
    """Test-only task handler that does no work and completes immediately."""
    logger.debug("Running no-op task {}", task.object_id)
    return None
