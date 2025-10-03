import datetime
from typing import Any
from typing import Callable
from typing import assert_never

from imbue_core.common import is_running_within_a_pytest_tree
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import CacheReposInputsV1
from sculptor.database.models import CleanupImagesInputsV1
from sculptor.database.models import MustBeShutDownTaskInputsV1
from sculptor.database.models import SendEmailTaskInputsV1
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import StopAgentUserMessage
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.tasks.handlers.cache_repos.v1 import cache_repos_task_v1
from sculptor.tasks.handlers.cleanup_images.v1 import run_cleanup_images_task_v1
from sculptor.tasks.handlers.run_agent.v1 import run_agent_task_v1
from sculptor.tasks.handlers.send_email.v1 import run_send_email_task_v1


def run_task(
    task: Task,
    services: ServiceCollectionForTask,
    task_deadline: datetime.datetime | None,
    settings: SculptorSettings,
) -> Callable[[DataModelTransaction], Any] | None:
    """Simply calls the correct task function based on the type of the input_data."""
    data = task.input_data
    match data:
        case AgentTaskInputsV1():
            return run_agent_task_v1(data, task, services, task_deadline, settings)
        case SendEmailTaskInputsV1():
            return run_send_email_task_v1(data, task, services, task_deadline)
        case MustBeShutDownTaskInputsV1():
            assert is_running_within_a_pytest_tree(), "MustBeShutDownTaskInputsV1 should only be used in testing"
            with services.task_service.subscribe_to_user_and_sculptor_system_messages(
                task.object_id
            ) as input_message_queue:
                while True:
                    message = input_message_queue.get()
                    if isinstance(message, StopAgentUserMessage):
                        break
            return None
        case CleanupImagesInputsV1():
            return run_cleanup_images_task_v1(services)
        case CacheReposInputsV1():
            return cache_repos_task_v1(services)

        case _ as unreachable:
            assert_never(unreachable)
