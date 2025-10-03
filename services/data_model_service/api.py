from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from typing import Callable
from typing import Concatenate
from typing import Generator
from typing import Generic
from typing import ParamSpec
from typing import Protocol
from typing import TypeVar

from imbue_core.pydantic_serialization import FrozenModel
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import UserSettings
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction

P = ParamSpec("P")
T = TypeVar("T")


class CompletedTransaction(FrozenModel):
    # None for the initial queue filling and for requests that are not associated with a specific request ID
    request_id: RequestID | None
    updated_models: tuple[Notification | Project | UserSettings, ...] = ()


class CompletedTransactionQueue(Protocol):
    """
    This protocol only models the put method of Queue[CompletedTransaction],
    so that the Queue[T] where T is a supertype of CompletedTransaction also satisfies this protocol.
    """

    def put(self, item: CompletedTransaction) -> None: ...


TQ = TypeVar("TQ", bound=CompletedTransactionQueue)


class DataModelService(Service, ABC):
    """
    All transactional data is stored via the DataModelService.

    LOCAL_ONLY: tasks and messages are stored in a local database.
    """

    @abstractmethod
    @contextmanager
    def open_transaction(
        self, request_id: RequestID, is_user_request: bool = True
    ) -> Generator[DataModelTransaction, None, None]:
        """
        Open a transaction for changing the core application state.

        request_id only needs to be passed in when authenticating (and really just for logging purposes).
        """

    @abstractmethod
    @contextmanager
    def observe_user_changes(
        self, user_reference: UserReference, organization_reference: OrganizationReference, queue: TQ
    ) -> Generator[TQ, None, None]:
        """
        Subscribe to changes in the data model for a specific user in the scope of a specific organization.

        Only observes changes for Project, UserSettings, and Notification model types.

        """


class TaskDataModelService(DataModelService, ABC):
    """
    Avoid using this class directly *except* within:
    1. the TaskService implementation
    2. the runner for a given Task.

    All it does is communicate that this particular data model service implementation is able to read/write task-related data in the DB
    (by changing the type on the return value)
    """

    @abstractmethod
    @contextmanager
    def open_task_transaction(self) -> Generator[TaskAndDataModelTransaction, None, None]: ...


class StandaloneTopLevelTransactor(FrozenModel, Generic[P, T]):
    """
    For use ONLY outside of API routes where a transaction is ABSOLUTELY necessary
    """

    data_model_service: DataModelService
    target: Callable[Concatenate[DataModelTransaction, P], T]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            return self.target(transaction, *args, **kwargs)
