from abc import ABC

from imbue_core.agents.data_types.ids import AgentMessageID
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.interfaces.agents.v1.agent import TaskStatusRunnerMessage
from sculptor.services.task_service.base_implementation import BaseTaskService


class ImmediateTaskService(BaseTaskService, ABC):
    """
    This is mostly useful for testing -- immediately executes each task that is created.

    Is handy because then you don't need to muck around with separate threads -- everything crashes immediately.
    """

    def on_new_task(self, task: Task) -> None:
        # mark the task as RUNNING
        with self.data_model_service.open_task_transaction() as transaction:
            updated_task = task.evolve(task.ref().outcome, TaskState.RUNNING)
            transaction.upsert_task(updated_task)
            message = TaskStatusRunnerMessage(outcome=TaskState.RUNNING, message_id=AgentMessageID())
            self.create_message(message=message, task_id=updated_task.object_id, transaction=transaction)

        # and just immediately execute it
        services = self._get_services_for_task()
        self._run_task(updated_task, services, self.settings)
