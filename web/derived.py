import datetime
from abc import ABC
from enum import StrEnum
from typing import Annotated
from typing import Generic
from typing import TypeVar

from pydantic import AnyUrl
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import Tag
from pydantic import computed_field

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.itertools import only
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from imbue_core.sculptor.state.chat_state import ChatMessage
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import UpdateSystemPromptUserMessage
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import BaseTaskState
from sculptor.database.models import CacheReposInputsV1
from sculptor.database.models import CacheReposTaskStateV1
from sculptor.database.models import CleanupImagesInputsV1
from sculptor.database.models import CleanupImagesTaskStateV1
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import SendEmailTaskInputsV1
from sculptor.database.models import SendEmailTaskStateV1
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import TaskInputs
from sculptor.database.models import UserSettings
from sculptor.interfaces.agents.v1.agent import AgentSnapshotRunnerMessage
from sculptor.interfaces.agents.v1.agent import ArtifactType
from sculptor.interfaces.agents.v1.agent import CheckFinishedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckLaunchedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ChecksDefinedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ClaudeCodeTextAgentConfig
from sculptor.interfaces.agents.v1.agent import CommandInputUserMessage
from sculptor.interfaces.agents.v1.agent import CompactTaskUserMessage
from sculptor.interfaces.agents.v1.agent import EnvironmentCreatedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ForkAgentSystemMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncDisabledMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupAndEnabledMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdateCompletedMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdatePausedMessage
from sculptor.interfaces.agents.v1.agent import MCPServerInfo
from sculptor.interfaces.agents.v1.agent import MCPStateUpdateAgentMessage
from sculptor.interfaces.agents.v1.agent import NewSuggestionRunnerMessage
from sculptor.interfaces.agents.v1.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.v1.agent import ServerReadyAgentMessage
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.interfaces.agents.v1.agent import TaskStatusRunnerMessage
from sculptor.interfaces.agents.v1.agent import UpdatedArtifactAgentMessage
from sculptor.primitives.ids import RequestID
from sculptor.services.git_repo_service.api import GitRepoStatus
from sculptor.utils.functional import first


class TaskInterface(StrEnum):
    TERMINAL = "TERMINAL"
    API = "API"


class TaskStatus(StrEnum):
    BUILDING = "BUILDING"  # Docker container is being built
    RUNNING = "RUNNING"  # Claude code process is actively running
    READY = "READY"  # Process completed successfully, waiting for input
    ERROR = "ERROR"  # Process encountered an error (stderr output)


class LocalSyncStatus(StrEnum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class LocalSyncState(SerializableModel):
    status: LocalSyncStatus
    last_updated: datetime.datetime | None
    notices: tuple[LocalSyncNoticeUnion, ...] = Field(default_factory=tuple)
    is_resumption: bool = False


TaskInputType = TypeVar("TaskInputType", bound=TaskInputs)
TaskStateType = TypeVar("TaskStateType", bound=BaseTaskState)


class LimitedBaseTaskView(SerializableModel, Generic[TaskInputType, TaskStateType], ABC):
    """
    This class represents a view of the state of any task that is being executed.

    It is limited in that an implementor shouldn't necessarily _need_ messages

    Note that this class is mutable!  The messages are continually updated over time.
    """

    # the actual task object, wrapped in a list which we effectively use as a mutable reference
    _task_container: list[Task] = PrivateAttr(default_factory=list)

    @property
    def task(self) -> Task:
        return only(self._task_container)

    def update_task(self, task: Task) -> None:
        """Update the underlying task object with fresh data"""
        self._task_container[0] = task

    @property
    def task_input(self) -> TaskInputType:
        # pyre-fixme[7]: self.task.input_data is a union type, but the return value is a type variable, which could be a fixed variant. Maybe make the Task type generic in its input_data type.
        return self.task.input_data

    @property
    def task_state(self) -> TaskStateType | None:
        # pyre-fixme[7]: self.task.current_state is a union type, but the return value is a type variable, which could be a fixed variant. Maybe make the Task type generic in its current_state type.
        return self.task.current_state

    @computed_field
    @property
    def id(self) -> TaskID:
        return self.task.object_id

    @computed_field
    @property
    def project_id(self) -> ProjectID:
        return self.task.project_id

    @computed_field
    @property
    def created_at(self) -> datetime.datetime:
        return self.task.created_at

    @computed_field
    @property
    def task_status(self) -> TaskState:
        return self.task.outcome

    def _maybe_get_status_from_outcome(self) -> TaskStatus | None:
        """
        NOTE: This is almost always None because outcome is never set while task is running.
        I Extracted it when I thought we were caching task status on state somehow.
        """
        if self.task.outcome == TaskState.FAILED:
            return TaskStatus.ERROR
        if self.task.outcome == TaskState.QUEUED:
            return TaskStatus.BUILDING

        # FIXME: fix this status
        # this is a little weird, but sure, I guess that's the right state...
        if self.task.outcome in (TaskState.SUCCEEDED, TaskState.CANCELLED):
            return TaskStatus.READY

        # otherwise, the task is running.
        assert self.task.outcome == TaskState.RUNNING, f"Unexpected task outcome: {self.task.outcome}"
        # if there's no image, we're still building
        if self.task_state is None:
            return TaskStatus.BUILDING


class TaskView(LimitedBaseTaskView[TaskInputType, TaskStateType], Generic[TaskInputType, TaskStateType], ABC):
    """
    This class represents a view of the state of any task that is being executed.

    The messages serialized and sent separately, but are logically part of the task's state.

    Note that this class is mutable!  The messages are continually updated over time.
    """

    object_type: str

    # our reference to settings (controls some serialized fields)
    _settings_container: list[SculptorSettings] = PrivateAttr(default_factory=list)

    # messages that were sent to or from the task.
    # this attribute is private because it enables easy serialization to the front end.
    _messages: list[Message] = PrivateAttr(default_factory=list)

    @property
    def settings(self) -> SculptorSettings:
        return only(self._settings_container)

    @computed_field
    @property
    def is_compacting(self) -> bool:
        compact_message = None
        for message in reversed(self._messages):
            if isinstance(message, CompactTaskUserMessage):
                compact_message = message.message_id
                break
        if compact_message is None:
            return False
        for message in reversed(self._messages):
            if isinstance(message, RequestSuccessAgentMessage):
                if message.request_id == compact_message:
                    return False
            if isinstance(message, RequestStartedAgentMessage):
                if message.request_id == compact_message:
                    return True
        return False

    @computed_field
    @property
    def artifact_names(self) -> list[str]:
        return list(set(x.artifact.name for x in self._messages if isinstance(x, UpdatedArtifactAgentMessage)))

    @computed_field
    @property
    def updated_at(self) -> datetime.datetime:
        if len(self._messages) == 0:
            return self.created_at
        return self._messages[-1].approximate_creation_time

    def add_message(self, message: Message) -> None:
        """During each update, we add the new messages"""
        self._messages.append(message)

    @computed_field
    @property
    def sync(self) -> LocalSyncState:
        for message in reversed(self._messages):
            if isinstance(message, LocalSyncSetupAndEnabledMessage):
                return LocalSyncState(status=LocalSyncStatus.ACTIVE, last_updated=message.approximate_creation_time)
            elif isinstance(message, LocalSyncUpdatePausedMessage):
                return LocalSyncState(
                    status=LocalSyncStatus.PAUSED,
                    notices=message.all_notices,
                    last_updated=message.approximate_creation_time,
                )
            elif isinstance(message, LocalSyncUpdateCompletedMessage):
                # updates should always imply active, and active can have non-blocking issues.
                return LocalSyncState(
                    status=LocalSyncStatus.ACTIVE,
                    notices=message.all_notices,
                    last_updated=message.approximate_creation_time,
                    is_resumption=message.is_resumption,
                )
            elif isinstance(message, LocalSyncDisabledMessage):
                return LocalSyncState(status=LocalSyncStatus.INACTIVE, last_updated=message.approximate_creation_time)

        return LocalSyncState(status=LocalSyncStatus.INACTIVE, last_updated=None)

    @computed_field
    @property
    def sync_started_at(self) -> datetime.datetime | None:
        for message in reversed(self._messages):
            if isinstance(message, LocalSyncSetupAndEnabledMessage):
                return message.approximate_creation_time
            elif isinstance(message, LocalSyncDisabledMessage):
                return None
        return None


class CodingAgentTaskView(TaskView[AgentTaskInputsV1, AgentTaskStateV1]):
    """
    messages are the primary way of interacting with an agent.

    this class is simply a way of deriving the current state of the agent based on the message log.

    because agents are run as idempotent tasks, consumers MUST be able to handle duplicate messages.
    this is particularly tricky because you cannot deduplicate on message_id here --
    the ids may be different between two different runs
    (and that cannot be fixed because different things may have happened)
    consumers *may* process messages in a "task aware" manner, eg,
    by paying attention to the task start and stop messages in order to properly discard outdated messages.
    """

    object_type: str = "CodingAgentTaskView"

    # TODO(post swap): replace with goal or updated_goal
    @computed_field
    @property
    def initial_prompt(self) -> str:
        return self.goal

    @computed_field
    @property
    def title_or_something_like_it(self) -> str:
        return self.title or self.initial_prompt

    @computed_field
    @property
    def interface(self) -> TaskInterface:
        if isinstance(self.task_input.agent_config, ClaudeCodeTextAgentConfig):
            return TaskInterface.TERMINAL
        else:
            return TaskInterface.API

    @computed_field
    @property
    def system_prompt(self) -> str | None:
        return first(x.text for x in reversed(self._messages) if isinstance(x, UpdateSystemPromptUserMessage))

    @computed_field
    @property
    def parent_id(self) -> TaskID | None:
        return self.task.parent_task_id

    @computed_field
    @property
    def model(self) -> LLMModel:
        last_input_message = first(
            x for x in reversed(self._messages) if isinstance(x, ChatInputUserMessage) and x.model_name is not None
        )
        # NOTE: this is hacky, but it is due to a quirk in the task subscription system. Talk to Guinness for more details.
        # goal should *rarely* be None, but it will be None for a single frame when the task is first created.
        if last_input_message is None:
            return LLMModel.CLAUDE_4_SONNET
        return last_input_message.model_name

    @computed_field
    @property
    def is_archived(self) -> bool:
        return self.task.is_archived

    @computed_field
    @property
    def is_deleted(self) -> bool:
        return self.task.is_deleted or self.task.is_deleting

    @computed_field
    @property
    def source_branch(self) -> str:
        return self.task_input.initial_branch

    @computed_field
    @property
    def branch_name(self) -> str | None:
        if self.task_state is None:
            return None
        return self.task_state.branch_name

    @computed_field
    @property
    def title(self) -> str | None:
        if self.task_state is None:
            return None
        return self.task_state.title

    # TODO(post swap): split into task_status and agent_status, separate the BUILDING state out of TaskStatus
    @computed_field
    @property
    def status(self) -> TaskStatus:
        task_from_outcome = self._maybe_get_status_from_outcome()
        if task_from_outcome is not None:
            return task_from_outcome

        # if we have started running but don't have an environment created message, we're still building.
        environment_created_message = None
        for message in self._messages:
            if isinstance(message, EnvironmentCreatedRunnerMessage):
                environment_created_message = message
            elif isinstance(message, TaskStatusRunnerMessage) and message.outcome == TaskState.RUNNING:
                environment_created_message = None
        if environment_created_message is None:
            return TaskStatus.BUILDING

        # if we're blocked on user input, return READY.
        chat_input_messages = [
            x
            for x in self._messages
            if isinstance(x, ChatInputUserMessage)
            or isinstance(x, CommandInputUserMessage)
            or isinstance(x, CompactTaskUserMessage)
        ]
        request_finished_messages = set(
            [x.request_id for x in self._messages if isinstance(x, PersistentRequestCompleteAgentMessage)]
        )
        is_ready = all(input_message.message_id in request_finished_messages for input_message in chat_input_messages)
        if is_ready:
            return TaskStatus.READY
        # otherwise I guess we're running.
        return TaskStatus.RUNNING

    @computed_field
    @property
    def number_of_snapshots(self) -> int:
        return len([x for x in self._messages if isinstance(x, AgentSnapshotRunnerMessage)])

    @computed_field
    @property
    def server_url_by_name(self) -> dict[str, AnyUrl]:
        server_url_by_name = {}
        for message in self._messages:
            if isinstance(message, ServerReadyAgentMessage):
                server_url_by_name[message.name] = message.url
        return server_url_by_name

    # TODO: it's not clear that we want to bother doing much of this logic at all on the server.
    #  (mostly because it's really inefficient, and it also can't be as easily altered by plugins.)
    @computed_field
    @property
    def goal(self) -> str:
        # Find the last fork message (if any) by searching in reverse
        last_fork_index = None
        for i in range(len(self._messages) - 1, -1, -1):
            if isinstance(self._messages[i], ForkAgentSystemMessage):
                last_fork_index = i
                break

        # If there's a fork message, get the first ChatInputUserMessage after it
        if last_fork_index is not None:
            goal = first(
                x.text
                for i, x in enumerate(self._messages)
                if i > last_fork_index and isinstance(x, ChatInputUserMessage)
            )
        else:
            # Otherwise, just get the first ChatInputUserMessage
            goal = first(x.text for x in self._messages if isinstance(x, ChatInputUserMessage))

        # NOTE: this is hacky, but it is due to a quirk in the task subscription system. Talk to Guinness for more details.
        # goal should *rarely* be None, but it will be None for a single frame when the task is first created.
        if goal is None:
            return ""
        return goal

    @computed_field
    @property
    def is_dev(self) -> bool:
        return self.settings.DEV_MODE

    @computed_field
    @property
    def mcp_servers(self) -> dict[str, MCPServerInfo]:
        last_message = first(x for x in reversed(self._messages) if isinstance(x, MCPStateUpdateAgentMessage))
        if last_message is None:
            return {}
        return last_message.mcp_servers


class SyncedTaskView(LimitedBaseTaskView[AgentTaskInputsV1, AgentTaskStateV1]):
    """Limited interface necessary for sync components in the frontend"""

    _sync: LocalSyncState = PrivateAttr()
    _sync_started_at: datetime.datetime = PrivateAttr()

    @computed_field
    @property
    def sync(self) -> LocalSyncState:
        return self._sync

    @computed_field
    @property
    def sync_started_at(self) -> datetime.datetime | None:
        return self._sync_started_at

    # Ultimately had to copy a bunch anyways because of type genericism
    @computed_field
    @property
    def is_archived(self) -> bool:
        return self.task.is_archived

    @computed_field
    @property
    def is_deleted(self) -> bool:
        return self.task.is_deleted or self.task.is_deleting

    @computed_field
    @property
    def source_branch(self) -> str:
        return self.task_input.initial_branch

    @computed_field
    @property
    def branch_name(self) -> str | None:
        if self.task_state is None:
            return None
        return self.task_state.branch_name

    @computed_field
    @property
    def title(self) -> str | None:
        if self.task_state is None:
            return None
        return self.task_state.title

    @computed_field
    @property
    def title_or_something_like_it(self) -> str:
        return self.title or str(self.task.object_id)

    @computed_field
    @property
    def status(self) -> TaskStatus | None:
        return self._maybe_get_status_from_outcome()

    @classmethod
    def build(cls, task: Task, sync: LocalSyncState, sync_started_at: datetime.datetime) -> "SyncedTaskView":
        view = cls()
        view._sync = sync
        view._sync_started_at = sync_started_at
        view._task_container = [task]
        return view


class GlobalLocalSyncInfo(SerializableModel):
    """Container for global sync state information across projects."""

    synced_task: SyncedTaskView
    project_path: str


class SendEmailTaskView(TaskView[SendEmailTaskInputsV1, SendEmailTaskStateV1]):
    object_type: str = "SendEmailTaskView"


class CleanupImagesTaskView(TaskView[CleanupImagesInputsV1, CleanupImagesTaskStateV1]):
    object_type: str = "CleanupImagesTaskView"


class CacheReposTaskView(TaskView[CacheReposInputsV1, CacheReposTaskStateV1]):
    object_type: str = "CacheReposTaskView"


TaskViewTypes = Annotated[
    Annotated[CodingAgentTaskView, Tag("CodingAgentTaskView")]
    | Annotated[SendEmailTaskView, Tag("SendEmailTaskView")]
    | Annotated[CleanupImagesTaskView, Tag("CleanupImagesTaskView")]
    | Annotated[CacheReposTaskView, Tag("CacheReposTaskView")],
    build_discriminator(),
]


class InsertedChatMessage(SerializableModel):
    message: ChatMessage
    after_message_id: AgentMessageID


class TaskUpdate(SerializableModel):
    """Represents an incremental update to task state sent to the frontend via SSE/WebSocket.

    Initial Connection:
    - Sends complete current state (all completed messages, current in-progress message, etc.)
    - Provides frontend with full context to render the UI

    Subsequent Updates:
    - Only sends deltas (new messages, changed state, etc.)
    - Frontend merges updates with existing state

    Field Update Patterns:
    - chat_messages: Only new completed messages are sent; frontend appends to existing list
    - in_progress_chat_message: Sent in full each time it changes; frontend replaces previous value
    - queued_chat_messages: Full list sent each time; frontend replaces entire queue
    - updated_artifacts: Lists artifacts that changed; frontend fetches updated content
    - finished_request_ids: IDs of completed requests for frontend to acknowledge
    - logs: New log lines only; frontend appends to existing logs
    - inserted_chat_messages: For when we want to insert the message after a specific message, not just append

    The frontend is responsible for:
    - Maintaining cumulative state by merging updates
    - Replacing vs appending based on field semantics
    - Fetching artifact data when notified of updates
    """

    task_id: TaskID
    chat_messages: tuple[ChatMessage, ...]
    updated_artifacts: tuple[ArtifactType, ...]
    in_progress_chat_message: ChatMessage | None
    queued_chat_messages: tuple[ChatMessage, ...]
    finished_request_ids: tuple[RequestID, ...]
    logs: tuple[str, ...]
    in_progress_user_message_id: AgentMessageID | None
    check_update_messages: tuple[
        ChecksDefinedRunnerMessage | CheckLaunchedRunnerMessage | CheckFinishedRunnerMessage, ...
    ]
    new_suggestion_messages: tuple[NewSuggestionRunnerMessage, ...]
    inserted_messages: tuple[InsertedChatMessage, ...] = ()


TaskIDStr = str


class TaskListUpdate(SerializableModel):
    task_by_task_id: dict[TaskIDStr, CodingAgentTaskView] = Field(default_factory=dict)
    finished_request_ids: tuple[RequestID, ...] = ()


# NOTE: not currently related to sculptor/sculptor/web/data_types.py RepoInfo,
# which contains more concrete data like Path as well as "recent branches."
# May want to consolidate in the future.
class LocalRepoInfo(SerializableModel):
    status: GitRepoStatus
    current_branch: str
    project_id: ProjectID


class UserUpdate(SerializableModel):
    user_settings: UserSettings | None = None
    projects: tuple[Project, ...] = ()
    settings: SculptorSettings | None = None
    notifications: tuple[Notification, ...] = ()
    finished_request_ids: tuple[RequestID, ...] = ()
    local_repo_info: LocalRepoInfo | None = None
