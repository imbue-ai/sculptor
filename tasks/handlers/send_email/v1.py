import datetime
from typing import Any
from typing import Callable

from loguru import logger

from sculptor.database.models import SendEmailTaskInputsV1
from sculptor.database.models import Task
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.task_service.data_types import ServiceCollectionForTask


def run_send_email_task_v1(
    task_data: SendEmailTaskInputsV1,
    task: Task,
    services: ServiceCollectionForTask,
    task_deadline: datetime.datetime | None,
) -> Callable[[DataModelTransaction], Any] | None:
    logger.info("Sending email with subject: {}", task_data.subject)
