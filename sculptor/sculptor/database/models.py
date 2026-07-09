import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from typing import Any

from pydantic import Tag

from sculptor.database.automanaged import DatabaseModel
from sculptor.database.workspace_enums import DiffStatus
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import build_discriminator
from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import AgentConfigTypes
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PersistentMessageTypes
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import ObjectID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID as AgentTaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import UserSettingsID
from sculptor.primitives.ids import WorkspaceGroupID
from sculptor.primitives.ids import WorkspaceID
from sculptor.state.messages import AgentMessageSource
from sculptor.state.messages import LLMModel
from sculptor.state.messages import ModelCatalog
from sculptor.state.messages import ModelOption
from sculptor.state.messages import NOT_FETCHED_YET

TaskID = AgentTaskID


# Basic tables


class UserSettings(DatabaseModel):
    """Settings for a locally stored user."""

    object_id: UserSettingsID
    user_reference: UserReference


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
    # whether the project path exists and is accessible
    is_path_accessible: bool = True
    # whether the project has been deleted by the user
    is_deleted: bool = False

    default_system_prompt: str | None = None
    workspace_setup_command: str | None = None
    # Per-project override of UserConfig.default_workspace_branch_naming_pattern.
    naming_pattern: str | None = None

    def get_local_user_path(self) -> Path:
        """
        Get local path of the user's git repository.

        (In practice, we currently only support file:// URLs for user git repositories.
         This method should highlight that assumption in the code.)
        """
        assert self.user_git_repo_url is not None and self.user_git_repo_url.startswith("file://")
        return Path(self.user_git_repo_url.replace("file://", ""))


class Workspace(DatabaseModel):
    """
    A workspace represents an isolated working environment for one or more tasks.

    In Phase 1, workspaces are implicitly created 1:1 with tasks. Later phases will
    allow explicit workspace creation and multi-agent support.

    The workspace owns the environment and provides a consistent execution context
    that persists across task restarts.
    """

    object_id: WorkspaceID
    project_id: ProjectID
    organization_reference: OrganizationReference
    # User-provided or auto-generated description of the workspace
    description: str
    initialization_strategy: WorkspaceInitializationStrategy
    source_branch: str | None = None
    target_branch: str | None = None
    environment_id: str | None = None
    source_git_hash: str | None = None
    is_deleted: bool = False
    is_open: bool = True
    setup_command_triggered: bool = False
    setup_status: str = "pending"
    setup_run_id: str | None = None
    setup_command: str | None = None
    setup_exit_code: int | None = None
    setup_started_at: float | None = None
    setup_finished_at: float | None = None
    setup_log_path: str | None = None
    setup_log_truncated: bool = False
    diff_status: DiffStatus = DiffStatus.NONE
    diff_updated_at: datetime.datetime | None = None
    # User-supplied or auto-generated branch name. Required for WORKTREE workspaces (validated at the API layer); optional for CLONE; null for IN_PLACE.
    requested_branch_name: str | None = None
    # Per-workspace CI Babysitter pause flag. Set from the PR popover; persisted
    # here so it survives a backend restart (the coordinator's in-memory state is
    # rebuilt lazily and would otherwise revert to the default).
    ci_babysitter_paused: bool = False
    # The workspace group this workspace belongs to, if any. Membership lives
    # here (not on the group) so a workspace structurally belongs to at most
    # one group and membership changes stream with the workspace itself.
    group_id: WorkspaceGroupID | None = None


class WorkspaceGroup(DatabaseModel):
    """
    A named, colored collection of workspaces within a single project.

    Groups are purely an organizational container for the sidebar and the
    sculpt CLI: they never own their members' lifecycle. Membership lives on
    ``Workspace.group_id``; a group with no live members must not exist, so
    any operation that empties a group soft-deletes it in the same
    transaction.
    """

    object_id: WorkspaceGroupID
    organization_reference: OrganizationReference
    # Groups are repo-scoped: every member workspace must belong to this project.
    project_id: ProjectID
    name: str
    # A Radix accent color name. Any accent name is accepted (not just the
    # curated palette in sculptor.web.data_types) so rows written under a
    # future palette still load.
    color: str
    # Whether the group was created by the sculpt CLI; drives the CLI badge in the sidebar.
    created_via_cli: bool = False
    is_deleted: bool = False


# Runtime tables


class TaskInputs(SerializableModel):
    """
    Base class for server task inputs. Is abstract.
    Note that implementations of this class should be versioned -- you run a version of a task, not just a type.
    """


class AgentTaskInputsV2(TaskInputs):
    """
    The primary task for running an agent.

    Contains the necessary information for the task runner.

    The `agent_config` is used to configure the `Agent` itself. It contains the full (versioned) command to be run.
    The `git_hash` records the starting commit for diff computation.
    """

    object_type: str = "AgentTaskInputsV2"

    # which agent to run
    agent_config: AgentConfigTypes

    # the output of `git rev-parse HEAD` at the time the task was created.
    # used for diff computation against the starting state.
    git_hash: str

    system_prompt: str | None = None

    # The model selected by the user when creating this agent.
    # Used as fallback when no messages have been sent yet.
    default_model: LLMModel | None = None


class NoOpTaskInputsV1(TaskInputs):
    """Test-only task input that runs a no-op handler and completes immediately.

    Used by the task-service tests to exercise the non-agent task path.
    """

    object_type: str = "NoOpTaskInputsV1"


class MustBeShutDownTaskInputsV1(TaskInputs):
    """Used in testing to make sure we can shut down tasks that do nothing but wait."""

    object_type: str = "MustBeShutDownTaskInputsV1"


TaskInputTypes = Annotated[
    Annotated[AgentTaskInputsV2, Tag("AgentTaskInputsV2")]
    | Annotated[NoOpTaskInputsV1, Tag("NoOpTaskInputsV1")]
    | Annotated[MustBeShutDownTaskInputsV1, Tag("MustBeShutDownTaskInputsV1")],
    build_discriminator(),
]


class BaseTaskState(SerializableModel):
    object_type: str


class AgentTaskStateV2(BaseTaskState):
    """
    The state of a run_agent server task.
    This is used to snapshot the state of the task at various points in time so that the agent can be resumed.
    """

    object_type: str = "AgentTaskStateV2"
    last_processed_message_id: AgentMessageID | None = None
    title: str | None = None
    workspace_id: WorkspaceID
    # Terminal agents only: the session id the registered program last
    # signalled (validated to [A-Za-z0-9._-]{1,128}), used to resume the
    # program after a backend restart.
    terminal_session_id: str | None = None
    # Terminal agents only: the shell pid of the handler's last PTY spawn,
    # used to reap a crash-surviving shell before relaunching.
    terminal_shell_pid: int | None = None
    # pi agents only: the curated model catalog the agent fetched from pi at
    # start (get_available_models), surfaced by the pi harness's
    # get_available_models so the chat switcher offers pi's real models. Defaults
    # to NOT_FETCHED_YET (the probe has not run) — distinct from a fetched-but-
    # empty [] (authenticated, no providers), so the switcher can tell a loading
    # catalog from a genuinely empty one instead of flashing the login CTA.
    available_models: ModelCatalog = NOT_FETCHED_YET
    # pi agents only: the model pi reported as current at start (get_state.model),
    # surfaced by the pi harness's get_selected_model_id as the switcher's value.
    current_model: ModelOption | None = None


class NoOpTaskStateV1(BaseTaskState):
    """Test-only task state paired with NoOpTaskInputsV1."""

    object_type: str = "NoOpTaskStateV1"


TaskStateTypes = Annotated[
    Annotated[AgentTaskStateV2, Tag("AgentTaskStateV2")] | Annotated[NoOpTaskStateV1, Tag("NoOpTaskStateV1")],
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
    is_deleted: bool = False
    is_deleting: bool = False
    last_read_at: datetime.datetime | None = None


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

    def model_post_init(self, context: Any) -> None:
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
    # When user_reference is None, it applies to all users.
    user_reference: UserReference | None
    # by convention, only the first line will be shown directly to the user, and of that, only the first X characters.
    # we assume that this is roughly markdown (eg, for formatting, links, etc).
    message: str
    importance: NotificationImportance = NotificationImportance.ACTIVE
    task_id: TaskID | None = None
    # Notifications can be related to a whole project, not necessarily a specific task.
    project_id: ProjectID | None = None
