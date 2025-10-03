from typing import Any
from typing import Callable

from imbue_core.errors import ExpectedError
from sculptor.services.data_model_service.data_types import DataModelTransaction


class TaskNotFound(ExpectedError):
    pass


class InvalidTaskOperation(ExpectedError):
    pass


class TaskError(ExpectedError):
    def __init__(self, transaction_callback: Callable[[DataModelTransaction], Any], is_user_notified: bool) -> None:
        super().__init__()
        self.transaction_callback = transaction_callback
        self.is_user_notified = is_user_notified


class UserStoppedTaskError(ExpectedError):
    def __init__(self) -> None:
        super().__init__(None, True)


class UserPausedTaskError(UserStoppedTaskError):
    """
    Raised when the user pauses the task.
    """
