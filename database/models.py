import abc
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import AnyUrl
from pydantic import Tag

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ObjectID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID as AgentTaskID
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from imbue_core.sculptor.state.messages import AgentMessageSource
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import with_consent
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.serialization import SerializedException
from sculptor.database.automanaged import DatabaseModel
from sculptor.interfaces.agents.v1.agent import AgentConfigTypes
from sculptor.interfaces.agents.v1.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.v1.agent import PersistentMessageTypes
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.interfaces.environments.v1.base import EnvironmentConfigTypes
from sculptor.interfaces.environments.v1.base import ImageConfigTypes
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import UserSettingsID
from sculptor.utils.build import get_sculptor_folder

# FIXME: actually, move this down to the agent module
TaskID = AgentTaskID

# Basic tables


class ProductLoggingPermissionLevel(StrEnum):
    NONE = "NONE"
    OPEN_SOURCE = "OPEN_SOURCE"
    ALL = "ALL"


class UserSettings(DatabaseModel):
    """Settings for a locally stored user."""

    object_id: UserSettingsID
    user_reference: UserReference

    # whether the user has opted in to usage data collection.
    # could be prompted with something like "Contribute anonymous usage data so that we can improve the parts of the product that *you* use"
    is_usage_data_enabled: bool = False
    # set by the user. Controls what repos we are allowed to log for product improvement purposes.
    # could be prompted with something like "Link open source changes so that we can improve performance on your tasks"
    allowed_product_logging: ProductLoggingPermissionLevel = ProductLoggingPermissionLevel.NONE


class FixID(ObjectID):
    tag: str = "fix"


class Project(DatabaseModel):
    """
    A project is mostly a container for related tasks.  It has at most one git repository associated with it.

    Note that the git_repository_url's are optional because it should be possible to run simple agents that do not require an `Environment` at all.

    LOCAL_ONLY: For now, we should create a project with a file:/// URL whenever the server is started in some git repository.
    """

    object_id: ProjectID
    organization_reference: OrganizationReference
    # right now this is just the name of the folder that contains the project.
    name: str
    # the user's git repository URL, if any.  We don't necessarily always have access to this without user secrets.
    # note that this should be a file:/// URL right now
    user_git_repo_url: str | None = None
    # our own backup of that repository, if any.  Will be useful for ensuring that we can access particular hashes, and reducing load on the user's repository.
    # This URL should not contain a token.
    our_git_repo_url: str | None = None
    # whether the project can be logged in order to improve the product.
    is_loggable: bool = False
    # whether the project path exists and is accessible
    is_path_accessible: bool = True

    default_system_prompt: str | None = None

    def get_cached_repo_path(self) -> Path:
        return get_sculptor_folder() / "cached_repos" / str(self.object_id)


# Runtime tables


class TaskInputs(SerializableModel):
    """
    Base class for server task inputs. Is abstract.
    Note that implementations of this class should be versioned -- you run a version of a task, not just a type.
    """


class AgentTaskInputsV1(TaskInputs):
    """
    The primary task for running an agent.

    Contains the necessary information for the task runner, i.e., the function in sculptor/tasks/handlers/run_agent/v1.py,

    In particular, this defines the configuration for creating the `Environment` (e.g., the image_config, volume_config),
    as well as the relevant git information (git_hash, branch_name, new_branch) for ensuring the `Environment` is set up correctly.

    The `agent_config` is used to configure the `Agent` itself.  It contains the full (versioned) command to be run,
    and will be injected into the `Environment` as a file that the command can then read.
    """

    object_type: str = "AgentTaskInputsV1"

    # which agent to run
    agent_config: AgentConfigTypes

    # how to run that agent, i.e., the Environment in which it will run.
    image_config: ImageConfigTypes
    environment_config: EnvironmentConfigTypes | None = None
    available_secrets: tuple[str, ...] | None = None

    # git information. This is mostly advisory / for the UI --
    # the actual git state comes from copying the whole folder into the Environment.

    # this is the output of `git rev-parse HEAD` at the time the task was created.
    # note that we cannot be guaranteed to have started in a consistent git state --
    # there easily could be uncommitted changes, or even conflicts.
    git_hash: str
    # this is the branch name at the time the task was created.
    # there's no strict guarantee that you even *have* a branch at that time, eg, this could be empty
    initial_branch: str
    # if true, the above *completely* defines the git state of the Environment.
    # ie, git reset --hard will be called, and you can be sure that this is where the Environment started from.
    # otherwise you are starting from your current state, which will not be changed at all
    # in fact, we won't even make a sculptor/- prefixed branch -- the agent will have to do this later
    is_git_state_clean: bool


class SendEmailTaskInputsV1(TaskInputs):
    """This is mostly here so that it is clear how to make additional server task inputs types in the future"""

    object_type: str = "SendEmailTaskInputsV1"
    subject: str
    message: str


class PeriodicTaskInputs(TaskInputs, abc.ABC):
    interval: timedelta


class CleanupImagesInputsV1(PeriodicTaskInputs):
    """This is for the task which cleans up excess Docker images created by deleted and archived Sculpltor tasks"""

    object_type: str = "CleanupImagesInputsV1"
    interval: timedelta = timedelta(minutes=10)


class CacheReposInputsV1(PeriodicTaskInputs):
    "This is for the task which copies the user repo once a day, so that it can be baked into docker images"

    object_type: str = "CacheReposInputsV1"
    interval: timedelta = timedelta(days=1)


class MustBeShutDownTaskInputsV1(TaskInputs):
    """Used in testing to make sure we can shut down tasks that do nothing but wait."""

    object_type: str = "MustBeShutDownTaskInputsV1"


TaskInputTypes = Annotated[
    Annotated[AgentTaskInputsV1, Tag("AgentTaskInputsV1")]
    | Annotated[SendEmailTaskInputsV1, Tag("SendEmailTaskInputsV1")]
    | Annotated[CleanupImagesInputsV1, Tag("CleanupImagesInputsV1")]
    | Annotated[CacheReposInputsV1, Tag("CacheReposInputsV1")]
    | Annotated[MustBeShutDownTaskInputsV1, Tag("MustBeShutDownTaskInputsV1")],
    build_discriminator(),
]


class BaseTaskState(SerializableModel):
    object_type: str


class AgentTaskStateV1(BaseTaskState):
    """
    The state of a run_agent server task.
    This is used to snapshot the state of the task at various points in time so that the agent can be resumed.
    """

    object_type: str = "AgentTaskStateV1"
    image: ImageTypes | None = None
    environment_id: str | None = None
    last_processed_message_id: AgentMessageID | None = None
    title: str | None = None
    branch_name: str | None = None
    task_repo_path: Path | None = None


class SendEmailTaskStateV1(BaseTaskState):
    """This is mostly here so that it is clear how to make additional server task state types in the future"""

    object_type: str = "SendEmailTaskStateV1"
    is_sent: bool


class CleanupImagesTaskStateV1(BaseTaskState):
    """This is mostly here so that it is clear how to make additional server task state types in the future"""

    object_type: str = "CleanupImagesTaskStateV1"


class CacheReposTaskStateV1(BaseTaskState):
    """This is mostly here so that it is clear how to make additional server task state types in the future"""

    object_type: str = "CacheReposTaskStateV1"


TaskStateTypes = Annotated[
    Annotated[AgentTaskStateV1, Tag("AgentTaskStateV1")]
    | Annotated[SendEmailTaskStateV1, Tag("SendEmailTaskStateV1")]
    | Annotated[CleanupImagesTaskStateV1, Tag("CleanupImagesTaskStateV1")]
    | Annotated[CacheReposTaskStateV1, Tag("CacheReposTaskStateV1")],
    build_discriminator(),
]


class Task(DatabaseModel):
    """
    A task that is run by the server on behalf of a user.
    These are often created directly by a user in order to actually accomplish some goal by running an agent.

    This notion is conceptually similar to a task in a library like Celery or RQ, though with:
    1. the additional restriction that tasks must be created (at least indirectly) by a single user, and
    2. a bit of additional metadata.

    Tasks must be idempotent.
    Tasks may save their current state to this model as they work.
    Tasks will be restarted until they are either completed or fail.

    You can think of the directly created (to-level) user-created tasks as similar to a "task" in a project management tool
    (like Linear) or an issue (e.g. at Github issue),
    but with a key difference that it is intended to be executed by an agent, rather than by a human.
    Top level tasks can be distinguished from subtasks by the fact that they have no parent task.
    """

    # ID fields
    # the ID fields may not be changed after creation, so we can use them to identify the task.

    # the ID of the task
    object_id: TaskID
    # the owning organization and user
    organization_reference: OrganizationReference
    user_reference: UserReference
    # the project -- required for understanding how the task should be executed
    project_id: ProjectID
    # the parent task, if any. This will enable us to make these recursive
    parent_task_id: TaskID | None

    # Inputs

    # the inputs to the task.  Tasks are executed by dispatching on this type.
    input_data: TaskInputTypes

    # Limits

    # may specify a timeout (so that we do not end up with unexpectedly long-running tasks)
    # note that, for agents, it doesn't make sense to specify a timeout since they are expected to run until completed.
    max_seconds: float | None = None

    # State

    # used to track the current state of the task while it is running.
    current_state: TaskStateTypes | None = None
    # whether the task is completed
    outcome: TaskState = TaskState.QUEUED
    # any error that was raised during the execution of the task. If this is set, outcome will be FAILED.
    error: SerializedException | None = None

    # User interaction
    is_archived: bool = False
    is_deleted: bool = False
    is_deleting: bool = False


class FixRequest(PosthogEventPayload):
    """
    Represents a request from the user to fix an issue identified by imbue_verify.
    Used for PostHog analytics and dataset creation.
    """

    object_id: FixID = with_consent(ConsentLevel.PRODUCT_ANALYTICS, description="Fix request ID")
    description: str = with_consent(ConsentLevel.LLM_LOGS, description="Description of the issue to fix")
    project_id: ProjectID = with_consent(ConsentLevel.PRODUCT_ANALYTICS, description="Associated project ID")
    task_id: TaskID = with_consent(ConsentLevel.PRODUCT_ANALYTICS, description="Associated task ID")


class SavedAgentMessage(DatabaseModel):
    """
    Represents an event that occurs in the context of a user task.
    This is effectively a log of messages that are sent between the agent and the user.
    """

    # this is taken directly from the Message, so that we can query it more easily.
    object_id: AgentMessageID
    # the task that this message is associated with. This is the only data not contained in the message itself.
    task_id: TaskID
    # the message itself. The subclasses of Message are used to represent different types of messages.
    message: PersistentMessageTypes
    # this is taken directly from the Message, so that we can query it more easily.
    source: AgentMessageSource
    # this is basically just true if the message is a `StreamingChatResponseChunkAgentMessage`
    # it's here so that we can not bother to include partial messages in some queries.
    is_partial: bool

    def model_post_init(self, __context) -> None:
        if self.object_id != self.message.message_id:
            raise ValueError(
                f"SavedAgentMessage object_id {self.object_id} does not match message ID {self.message.message_id}."
            )
        if self.source != self.message.source:
            raise ValueError(
                f"SavedAgentMessage source {self.source} does not match message source {self.message.source}."
            )
        if self.is_partial != isinstance(self.message, PartialResponseBlockAgentMessage):
            raise ValueError(
                f"SavedAgentMessage is_partial {self.is_partial} does not match message type {type(self.message)}."
            )

    @classmethod
    def build(cls, message: PersistentMessageTypes, task_id: TaskID) -> "SavedAgentMessage":
        return cls(
            object_id=message.message_id,
            task_id=task_id,
            message=message,
            source=message.source,
            is_partial=isinstance(message, PartialResponseBlockAgentMessage),
        )


class NotificationID(ObjectID):
    tag: str = "ntf"


class NotificationImportance(StrEnum):
    """
    From the Apple Human Interface Guidelines: https://developer.apple.com/design/human-interface-guidelines/managing-notifications

    Passive. Information people can view at their leisure, like a restaurant recommendation.

    Active (the default). Information people might appreciate knowing about when it arrives, like a score update on their favorite sports team.

    Time Sensitive. Information that directly impacts the person and requires their immediate attention, like an account security issue or a package delivery.

    Critical. Urgent information about health and safety that directly impacts the person and demands their immediate attention. Critical notifications are extremely rare and typically come from governmental and public agencies or apps that help people manage their health or home.
    """

    PASSIVE = "PASSIVE"
    ACTIVE = "ACTIVE"
    TIME_SENSITIVE = "TIME_SENSITIVE"
    CRITICAL = "CRITICAL"


class Notification(DatabaseModel):
    object_id: NotificationID
    user_reference: UserReference
    # by convention, only the first line will be shown directly to the user, and of that, only the first X characters.
    # we assume that this is roughly markdown (eg, for formatting, links, etc).
    message: str
    importance: NotificationImportance = NotificationImportance.ACTIVE
    task_id: TaskID | None = None
    url: AnyUrl | None = None
