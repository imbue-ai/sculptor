"""
An Agent simply *is* a list of `Message`s.

The meaning of each of the message is defined below.
"""

from __future__ import annotations

import abc
import datetime
from contextlib import contextmanager
from enum import Enum
from enum import StrEnum
from queue import Queue
from subprocess import TimeoutExpired
from typing import Annotated
from typing import Any
from typing import Generator
from typing import Mapping

from loguru import logger
from pydantic import AnyUrl
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import Tag

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import RunningProcess
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from imbue_core.sculptor.state.chat_state import ImbueCLIToolContent
from imbue_core.sculptor.state.claude_state import ParsedAssistantMessage
from imbue_core.sculptor.state.claude_state import ParsedInitMessage
from imbue_core.sculptor.state.claude_state import ParsedStreamEndMessage
from imbue_core.sculptor.state.claude_state import ParsedToolResultMessage
from imbue_core.sculptor.state.messages import AgentMessageSource
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import PersistentAgentMessage
from imbue_core.sculptor.state.messages import PersistentMessage
from imbue_core.sculptor.state.messages import PersistentUserMessage
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from imbue_core.sculptor.state.messages import UpdateSystemPromptUserMessage
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import get_exception_payload
from imbue_core.sculptor.telemetry import never_log
from imbue_core.sculptor.telemetry import with_consent
from imbue_core.sculptor.telemetry import without_consent
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.serialization import SerializedException
from imbue_core.suggestions import Suggestion
from imbue_core.time_utils import get_current_time
from sculptor.agents.claude_code_sdk.errors import ClaudeClientError
from sculptor.agents.claude_code_sdk.errors import ClaudeTransientError
from sculptor.interfaces.agents.v1.errors import UncleanTerminationAgentError
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.primitives.ids import ObjectID
from sculptor.primitives.numeric import Probability
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials
from sculptor.services.environment_service.environments.docker_environment import DockerEnvironment
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.environment_service.environments.modal_environment import ModalEnvironment
from sculptor.utils.secret import Secret
from sculptor.utils.timeout import PosthogEventModel
from sculptor.utils.timeout import ProductComponent
from sculptor.utils.timeout import SculptorPosthogEvent
from sculptor.utils.timeout import emit_posthog_event

DEFAULT_CHECK_TIMEOUT_SECONDS = 10 * 60.0
AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT = 5
AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION = 6
AGENT_EXIT_CODE_FROM_SIGTERM = 143
AGENT_EXIT_CODE_FROM_SIGINT = 130


TMUX_OUTPUT_ARTIFACT_NAME = "tmux_output.txt"

# =========================
# Artifact Type Definitions
# =========================


# NOTE: TodoStatus and TodoPriority need to be lower case bc that is what we are given from the Claude Code tool call


class TodoStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TodoPriority(StrEnum):
    MEDIUM = "medium"
    HIGH = "high"
    LOW = "low"


class TodoItem(SerializableModel):
    id: str
    content: str
    status: TodoStatus
    priority: TodoPriority


class TodoListArtifact(SerializableModel):
    """Todo list artifact containing all todos."""

    object_type: str = "TodoListArtifact"
    todos: list[TodoItem]


class LogsArtifact(SerializableModel):
    """Logs artifact containing an array of log lines."""

    object_type: str = "LogsArtifact"
    logs: list[str]


class DiffArtifact(SerializableModel):
    """Unified diff artifact containing all diff types."""

    object_type: str = "DiffArtifact"
    committed_diff: str = ""  # Diff from base branch to HEAD
    uncommitted_diff: str = ""  # Uncommitted changes
    complete_diff: str = ""  # Combined view (base to current state)


class SuggestionsArtifact(SerializableModel):
    """Suggestions artifact containing Imbue CLI tool results."""

    object_type: str = "SuggestionsArtifact"
    content: ImbueCLIToolContent


class UsageArtifact(SerializableModel):
    """Usage artifact containing all tool results."""

    object_type: str = "UsageArtifact"
    cost_usd_info: float
    token_info: int


class AgentArtifact(SerializableModel):
    """
    An artifact produced by the agent during its work. Represents the "output" of the agent's work.

    The URL should point to a location where the artifact can be accessed.
    """

    # used to dispatch and discover the type of message
    object_type: str
    # the name of the artifact,
    # can be used to provide some structure to the outputs of an agent.
    # for a file, this is something like "output.txt" or "branch/main" or "whatever/thing.png"
    # for a branch, this is the branch name.
    name: str
    # where the artifact can be found
    url: AnyUrl
    # Probability that this output will be accepted by the user.
    # If this is set, the artifact is considered an "output"
    success: Probability | None = None


class FileAgentArtifact(AgentArtifact):
    object_type: str = "FileAgentArtifact"


ArtifactUnion = DiffArtifact | SuggestionsArtifact | TodoListArtifact | LogsArtifact | UsageArtifact


class ArtifactType(StrEnum):
    """Types of artifacts that agents can produce."""

    DIFF = "DIFF"  # Unified diff artifact with all three diff types
    SUGGESTIONS = "SUGGESTIONS"
    PLAN = "PLAN"
    LOGS = "LOGS"
    USAGE = "USAGE"
    NEW_SUGGESTIONS = "NEW_SUGGESTIONS"
    CHECKS = "CHECKS"


ParsedAgentMessageType = ParsedInitMessage | ParsedAssistantMessage | ParsedToolResultMessage | ParsedStreamEndMessage


class RunID(ObjectID):
    tag: str = "run"


class CheckSource(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"


class CheckTrigger(StrEnum):
    MANUAL = "MANUAL"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    FILE_CHANGE = "FILE_CHANGE"
    # TODO: would be nice to implement this!  It would be useful to check that user messages are sufficiently clear before wasting a bunch of time
    #  realistically we'd want to at least suggest a better, clearer, longer message (in response to a bad user message)
    #  and we'd probably want to be fairly careful about how often this happened
    #  we could also give really small suggestions, which could actually be useful (ex: about things that are potentially unclear)
    #  when we're enabling this, we'll need to call _load_checks_from_environment twice -- once when we start, and once when the turn is complete
    #  otherwise, if we loaded only at the beginning, telling the agent to fix your config wouldn't work well
    # USER_MESSAGE = "USER_MESSAGE"


class Check(SerializableModel):
    # the shell (bash) command to run for this check.
    # may *not* end with "&" -- only blocking commands are allowed.
    # should not redirect stdout or stderr, as this will be done automatically.
    # this should only be None for the built-in check, which is just there to raise a fixed set of Suggestions
    command: str | None = Field(pattern=r"^.*[^&]$")
    # the name of the check, which is used to identify it in the system. Everything in the UI is keyed off of this.
    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")
    # a description of the check, which is used to provide context to the user / remember why you created this check.
    description: str = ""
    # default timeout of 10 minutes because you really don't want checks going for too long --
    # they will cause noticeable spending on containers
    timeout_seconds: float = Field(
        default=DEFAULT_CHECK_TIMEOUT_SECONDS, gt=0.0, description="Timeout for the check in seconds"
    )
    # severity for the Suggestion that results if this command returns a non-zero exit code.
    failure_severity: float = Field(ge=0.0, le=1.0, default=1.0)
    # if True, this check will be run in a separate container. If False, it will be within the agent's environment.
    # TODO: switch this to True as soon as we can
    is_forked: bool = False
    # if True, this check can be run concurrently with other checks in the same container, otherwise is killed when a new message is detected
    is_local_concurrency_allowed: bool = False
    # is set if and only if there is an error parsing this specific check
    config_error: str | None = None
    # set to AGENT_MESSAGE if you want to run it automatically when the agent message is complete (default)
    # set to MANUAL if you want to avoid running this check automatically,
    # set to USER_MESSAGE if you want to run it automatically after the user message is sent (useful for checking that the message makes sense)
    trigger: CheckTrigger = CheckTrigger.AGENT_MESSAGE
    # use this to specifically disable a check, for example, a built-in system check, or one that is enabled only by some users
    is_enabled: bool = True
    # whether this is shown in the row of checks after a conversation turn
    # this can be disabled in case users don't like seeing the system-level checks
    is_visible: bool = True
    # this is non-empty when a check fails to fully load because it is an outdated value from an earlier run
    outdated_reason: str = ""
    # where this check came from, either USER or SYSTEM.
    # it is an error for the user to set this to anything other than USER
    source: CheckSource = CheckSource.USER


# ==================================
# Backend Message Type Definitions
# ==================================

# The types of messages which are relevant to conversation history as well as the internal workings of sculptor
# are defined in imbue_core.sculptor.state.messages


class EphemeralMessage(Message):
    @property
    def is_ephemeral(self) -> bool:
        return True


class EphemeralUserMessage(EphemeralMessage, PosthogEventPayload):
    """
    One of two base classes for messages sent from the user.
    Ephemeral user messages are not saved to the database.
    Ephemeral user messages are sent immediately to the agent and are not queued in the task runner.
    """

    # Override inherited fields with consent annotations
    # TODO (moishe): if other classes that derive from Message also start getting logged,
    # change the base Message class to derive from PosthogEventPayload. For now, doing
    # that is overkill and requires lots of annotations of irrelevant classes.
    #
    # TODO (mjr): We should really have `PersistentHoggableMessage` and `EphemeralHoggableMessage` or something
    object_type: str = without_consent(description="Type discriminator for user messages")
    message_id: AgentMessageID = without_consent(
        default_factory=AgentMessageID,
        description="Unique identifier for the user message",
    )
    source: AgentMessageSource = without_consent(default=AgentMessageSource.USER)
    approximate_creation_time: datetime.datetime = without_consent(
        default_factory=get_current_time,
        description="Approximate UTC timestamp when user message was created",
    )


UserMessage = EphemeralUserMessage | PersistentUserMessage


class CompactTaskUserMessage(PersistentUserMessage):
    object_type: str = without_consent(default="CompactTaskUserMessage")


class CommandInputUserMessage(PersistentUserMessage):
    object_type: str = without_consent(default="CommandInputUserMessage")
    text: str = with_consent(ConsentLevel.LLM_LOGS, description="User input text content")
    is_included_in_context: bool = with_consent(
        ConsentLevel.PRODUCT_ANALYTICS, description="Whether this command should be included in conversation context"
    )
    is_checkpoint: bool = without_consent(default=False, description="Whether this command represents a checkpoint")
    run_with_sudo_privileges: bool = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    is_automated_command: bool = without_consent(
        default=False,
        description="Whether this command is an automated command executed by sculptor instead of the user",
    )


class SetUserConfigurationDataUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="SetUserConfigurationDataUserMessage")
    anthropic_credentials: AnthropicCredentials | None = never_log(default=None)


class SetProjectConfigurationDataUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="SetProjectConfigurationDataUserMessage")
    gitlab_token: str = never_log(default="")
    gitlab_url: str = never_log(default="")


class StopAgentUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="StopAgentUserMessage")


class InterruptProcessUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="InterruptProcessUserMessage")


class GitCommitAndPushUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="GitCommitAndPushUserMessage")
    commit_message: str = with_consent(ConsentLevel.LLM_LOGS, description="Commit message for the git commit")
    is_pushing: bool = without_consent(default=False)


class GitPullUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="GitPullUserMessage")


class RemoveQueuedMessageUserMessage(EphemeralUserMessage):
    object_type: str = without_consent(default="RemoveQueuedMessageUserMessage")
    target_message_id: AgentMessageID = without_consent(description="ID of the message to be removed from the queue")


class CheckControlUserMessage(EphemeralUserMessage, abc.ABC):
    check_name: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS, description="Which check is being affected")
    user_message_id: AgentMessageID = with_consent(
        ConsentLevel.PRODUCT_ANALYTICS, description="Which user message this is for"
    )


class StopCheckUserMessage(CheckControlUserMessage):
    object_type: str = without_consent(default="StopCheckUserMessage")
    run_id: RunID = with_consent(ConsentLevel.PRODUCT_ANALYTICS, description="Which run is being affected")


class RestartCheckUserMessage(CheckControlUserMessage):
    object_type: str = without_consent(default="RestartCheckUserMessage")


PersistentUserMessageUnion = (
    Annotated[ChatInputUserMessage, Tag("ChatInputUserMessage")]
    | Annotated[CommandInputUserMessage, Tag("CommandInputUserMessage")]
    | Annotated[UpdateSystemPromptUserMessage, Tag("UpdateSystemPromptUserMessage")]
    | Annotated[StopAgentUserMessage, Tag("StopAgentUserMessage")]
    | Annotated[CompactTaskUserMessage, Tag("CompactTaskUserMessage")]
)

EphemeralUserMessageUnion = (
    Annotated[InterruptProcessUserMessage, Tag("InterruptProcessUserMessage")]
    | Annotated[RemoveQueuedMessageUserMessage, Tag("RemoveQueuedMessageUserMessage")]
    | Annotated[GitCommitAndPushUserMessage, Tag("GitCommitAndPushUserMessage")]
    | Annotated[GitPullUserMessage, Tag("GitPullUserMessage")]
    | Annotated[StopCheckUserMessage, Tag("StopCheckUserMessage")]
    | Annotated[RestartCheckUserMessage, Tag("RestartCheckUserMessage")]
    | Annotated[StopAgentUserMessage, Tag("StopAgentUserMessage")]
    | Annotated[SetUserConfigurationDataUserMessage, Tag("SetUserConfigurationDataUserMessage")]
    | Annotated[SetProjectConfigurationDataUserMessage, Tag("SetProjectConfigurationDataUserMessage")]
)

UserMessageUnion = PersistentUserMessageUnion | EphemeralUserMessageUnion


class PersistentRunnerMessage(PersistentMessage):
    """Base class for messages sent from the runner."""

    source: AgentMessageSource = AgentMessageSource.RUNNER


class EphemeralRunnerMessage(EphemeralMessage):
    """Base class for messages sent from the runner."""

    source: AgentMessageSource = AgentMessageSource.RUNNER


RunnerMessage = PersistentRunnerMessage | EphemeralRunnerMessage

EnvironmentTypes = Annotated[
    Annotated[DockerEnvironment, Tag("DockerEnvironment")]
    | Annotated[LocalEnvironment, Tag("LocalEnvironment")]
    | Annotated[ModalEnvironment, Tag("ModalEnvironment")],
    build_discriminator(),
]


class EnvironmentCreatedRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "EnvironmentCreatedRunnerMessage"
    environment: EnvironmentTypes


class EnvironmentStoppedRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "EnvironmentStoppedRunnerMessage"


class KilledAgentRunnerMessage(PersistentRunnerMessage):
    object_type: str = "KilledAgentRunnerMessage"
    full_output_url: AnyUrl | None


class AgentCrashedRunnerMessage(PersistentRunnerMessage):
    """
    Note that (like EnvironmentCrashedRunnerMessage and UnexpectedErrorRunnerMessage),
    this can happen before *or after* the agent has finished processing a given message.
    """

    object_type: str = "AgentCrashedRunnerMessage"
    exit_code: int | None
    full_output_url: AnyUrl | None
    error: SerializedException


class ErrorType(StrEnum):
    PROCESS_CRASHED = "PROCESS_CRASHED"
    TMUX_SESSION_DIED = "TMUX_SESSION_DIED"
    NONZERO_EXIT_CODE = "NONZERO_EXIT_CODE"
    RESPONSE_INCOMPLETE = "RESPONSE_INCOMPLETE"


class EnvironmentCrashedRunnerMessage(PersistentRunnerMessage):
    object_type: str = "EnvironmentCrashedRunnerMessage"
    error: SerializedException
    full_output_url: AnyUrl | None


class UnexpectedErrorRunnerMessage(PersistentRunnerMessage):
    object_type: str = "UnexpectedErrorRunnerMessage"
    error: SerializedException
    full_output_url: AnyUrl | None


class TaskState(StrEnum):
    """The possible states of a server task."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"
    SUCCEEDED = "SUCCEEDED"


class TaskStatusRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "TaskStatusRunnerMessage"
    outcome: TaskState


class AgentSnapshotRunnerMessage(PersistentRunnerMessage):
    object_type: str = "AgentSnapshotRunnerMessage"
    image: ImageTypes
    for_user_message_id: AgentMessageID | None
    is_settled: bool = True


class ResumeAgentResponseRunnerMessage(PersistentRunnerMessage):
    object_type: str = "ResumeAgentResponseRunnerMessage"
    for_user_message_id: AgentMessageID
    model_name: LLMModel = with_consent(
        ConsentLevel.PRODUCT_ANALYTICS, default=None, description="Selected LLM model for the chat request"
    )


# TODO: Consider making Runner messages inhereit from this as well
class SculptorSystemEphemeralMessage(EphemeralMessage, PosthogEventPayload, abc.ABC):
    # TODO (mjr): We should really have `PersistentHoggableMessage` and `EphemeralHoggableMessage` or something
    object_type: str = without_consent(description="Type discriminator for sculptor system messages")
    message_id: AgentMessageID = without_consent(
        default_factory=AgentMessageID,
        description="Unique identifier for the sculptor system message",
    )
    source: AgentMessageSource = without_consent(default=AgentMessageSource.SCULPTOR_SYSTEM)
    approximate_creation_time: datetime.datetime = without_consent(
        default_factory=get_current_time,
        description="Approximate UTC timestamp when sculptor system message was created",
    )


class SculptorSystemPersistentMessage(PersistentMessage, PosthogEventPayload, abc.ABC):
    object_type: str = without_consent(description="Type discriminator for sculptor system messages")
    message_id: AgentMessageID = without_consent(
        default_factory=AgentMessageID,
        description="Unique identifier for the sculptor system persistent message",
    )
    source: AgentMessageSource = without_consent(default=AgentMessageSource.SCULPTOR_SYSTEM)
    approximate_creation_time: datetime.datetime = without_consent(
        default_factory=get_current_time,
        description="Approximate UTC timestamp when sculptor system message was created",
    )


class ForkAgentSystemMessage(SculptorSystemPersistentMessage):
    object_type: str = without_consent(default="ForkAgentSystemMessage")
    parent_task_id: TaskID = without_consent(description="The task ID of the parent task")
    child_task_id: TaskID = without_consent(description="The task ID of the child task")
    fork_point_chat_message_id: AgentMessageID = without_consent(description="The fork point chat message ID")


class LocalSyncNotice(SerializableModel, abc.ABC):
    source_tag: str
    reason: str

    def describe(self) -> str:
        subtype = self.__class__.__name__
        return f"{subtype} from {self.source_tag}: {self.reason}"

    @property
    def priority_for_ordering(self) -> int:
        raise NotImplementedError


# TODO: unused so far.
# Will reconsider this taxonomy based on if we end up implementing any actual non-pause notices
class LocalSyncNoticeOfWarning(LocalSyncNotice):
    object_type: str = without_consent(default="LocalSyncNoticeOfWarning")

    @property
    def priority_for_ordering(self) -> int:
        return 1


class LocalSyncNoticeOfPause(LocalSyncNotice):
    object_type: str = without_consent(default="LocalSyncNoticeOfPause")

    @property
    def priority_for_ordering(self) -> int:
        return 0


LocalSyncNonPausingNoticeUnion = Annotated[LocalSyncNoticeOfWarning, Tag("LocalSyncNoticeOfWarning")]
LocalSyncNoticeUnion = LocalSyncNonPausingNoticeUnion | LocalSyncNoticeOfPause


class LocalSyncMessage(SculptorSystemEphemeralMessage, abc.ABC):
    pass


class LocalSyncSetupStartedMessage(LocalSyncMessage):
    object_type: str = without_consent(default="LocalSyncSetupStartedMessage")


class LocalSyncSetupStep(Enum):
    # DISABLING_PRIOR_SYNC = "DISABLING_PRIOR_SYNC"
    VALIDATE_GIT_STATE_SAFETY = "VALIDATE_GIT_STATE_SAFETY"
    MIRROR_AGENT_INTO_LOCAL_REPO = "MIRROR_AGENT_INTO_LOCAL_REPO"
    BEGIN_TWO_WAY_CONTROLLED_SYNC = "BEGIN_TWO_WAY_CONTROLLED_SYNC"


class LocalSyncSetupProgressMessage(LocalSyncMessage):
    next_step: LocalSyncSetupStep = without_consent(description="next step in setup process")
    object_type: str = without_consent(default="LocalSyncSetupProgressMessage")


class LocalSyncSetupAndEnabledMessage(LocalSyncMessage):
    object_type: str = without_consent(default="LocalSyncSetupAndEnabledMessage")


class LocalSyncUpdateMessage(LocalSyncMessage, abc.ABC):
    event_description: str = with_consent(
        level=ConsentLevel.PRODUCT_ANALYTICS,
        description="description of the event (ie summary of files that triggered sync)",
    )
    nonpause_notices: tuple[LocalSyncNonPausingNoticeUnion, ...] = with_consent(
        default=tuple(),
        level=ConsentLevel.PRODUCT_ANALYTICS,
        description="non-pausing notices, ie large file ignored warnings (currently unimplemented)",
    )

    @property
    def all_notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        return self.nonpause_notices


class LocalSyncUpdatePendingMessage(LocalSyncUpdateMessage):
    object_type: str = without_consent(default="LocalSyncUpdatePendingMessage")


class LocalSyncUpdateCompletedMessage(LocalSyncUpdateMessage):
    object_type: str = without_consent(default="LocalSyncUpdateCompletedMessage")

    # whether this is the first batch completion after a pause
    is_resumption: bool = without_consent(default=False)


class LocalSyncUpdatePausedMessage(LocalSyncUpdateMessage):
    """Local Sync update failed and is paused instead of completed"""

    pause_notices: tuple[LocalSyncNoticeOfPause, ...] = with_consent(
        default=tuple(),
        level=ConsentLevel.PRODUCT_ANALYTICS,
        description="notices that caused a pause state",
    )

    object_type: str = without_consent(default="LocalSyncUpdatePausedMessage")

    @property
    def all_notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        return tuple((*self.pause_notices, *self.nonpause_notices))

    def model_post_init(self, __context: Any) -> None:
        assert len(self.pause_notices) > 0, "should not construct pause without pause issue"
        return super().model_post_init(__context)


class LocalSyncDisabledMessage(LocalSyncMessage):
    object_type: str = without_consent(default="LocalSyncDisabledMessage")


LocalSyncUpdateMessageUnion = (
    Annotated[LocalSyncUpdatePendingMessage, Tag("LocalSyncUpdatePendingMessage")]
    | Annotated[LocalSyncUpdateCompletedMessage, Tag("LocalSyncUpdateCompletedMessage")]
    | Annotated[LocalSyncUpdatePausedMessage, Tag("LocalSyncUpdatePausedMessage")]
)


LocalSyncMessageUnion = (
    Annotated[LocalSyncSetupStartedMessage, Tag("LocalSyncSetupStartedMessage")]
    | Annotated[LocalSyncSetupProgressMessage, Tag("LocalSyncSetupProgressMessage")]
    | Annotated[LocalSyncSetupAndEnabledMessage, Tag("LocalSyncSetupAndEnabledMessage")]
    | LocalSyncUpdateMessageUnion
    | Annotated[LocalSyncDisabledMessage, Tag("LocalSyncDisabledMessage")]
)


class ManualSyncMessage(SculptorSystemEphemeralMessage, abc.ABC):
    pass


# NOTE: This is just for posthog atm
class ManualSyncMergeIntoUserAttemptedMessage(ManualSyncMessage):
    object_type: str = without_consent(default="ManualSyncMergeIntoUserAttemptedMessage")
    reached_operation_label: str | None = without_consent()
    reached_operation_failure_label: str | None = without_consent()
    reached_decision_label: str | None = without_consent()
    selection_by_decision_label: dict[str, str] | None = without_consent()


class ManualSyncMergeIntoAgentNoticeLabel(StrEnum):
    AGENT_UNCOMMITTED_CHANGES = "AGENT_UNCOMMITTED_CHANGES"
    LOCAL_UNCOMMITTED_CHANGES = "LOCAL_UNCOMMITTED_CHANGES"
    LOCAL_BRANCH_NOT_FOUND = "LOCAL_BRANCH_NOT_FOUND"
    PUSH_TO_AGENT_SUCCEEDED = "PUSH_TO_AGENT_SUCCEEDED"
    PUSH_TO_AGENT_ERROR = "PUSH_TO_AGENT_ERROR"
    MERGED_INTO_AGENT_IN_CONFLICT = "MERGED_INTO_AGENT_IN_CONFLICT"
    MERGE_INTO_AGENT_ERROR = "MERGE_INTO_AGENT_ERROR"
    # This is a point in the state graph we aren't sure can be reached: no error, no merge result, but no conflict either
    MERGE_INTO_AGENT_INCOMPLETE_ODD_EDGECASE = "MERGE_INTO_AGENT_INCOMPLETE_ODD_EDGECASE"
    NO_MERGE_NEEDED = "NO_MERGE_NEEDED"
    MERGE_COMPLETED_CLEANLY = "MERGE_COMPLETED_CLEANLY"


class ManualSyncMergeIntoAgentAttemptedMessage(ManualSyncMessage):
    object_type: str = without_consent(default="ManualSyncMergeIntoAgentAttemptedMessage")

    is_attempt_unambiguously_successful: bool = without_consent()
    is_merge_in_progress: bool = without_consent()
    labels: list[ManualSyncMergeIntoAgentNoticeLabel] = without_consent()


# note: we expect to add more ManualSync message types
ManualSyncMessageUnion = (
    Annotated[ManualSyncMergeIntoUserAttemptedMessage, Tag("ManualSyncMergeIntoUserAttemptedMessage")]
    | Annotated[ManualSyncMergeIntoAgentAttemptedMessage, Tag("ManualSyncMergeIntoAgentAttemptedMessage")]
)

PersistentSystemMessageUnion = Annotated[ForkAgentSystemMessage, Tag("ForkAgentSystemMessage")]

SystemMessageUnion = LocalSyncMessageUnion | ManualSyncMessageUnion | PersistentSystemMessageUnion


class TaskLifecycleAction(StrEnum):
    DELETED = "DELETED"
    ARCHIVED = "ARCHIVED"
    UNARCHIVED = "UNARCHIVED"


class TaskLifecycleRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "TaskLifecycleRunnerMessage"
    action: TaskLifecycleAction


class WarningRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "WarningRunnerMessage"
    error: SerializedException | None
    message: str


class CheckLaunchedRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "CheckLaunchedRunnerMessage"
    user_message_id: AgentMessageID
    check: Check
    run_id: RunID
    # this can be None for local checks when no snapshot is taken
    snapshot: ImageTypes | None


class CheckFinishedReason(StrEnum):
    # the command actually exited and we observed an exit code
    # there is no guarantee that the exit code is 0 though!
    FINISHED = "FINISHED"
    # took too long to run, was stopped by us
    TIMEOUT = "TIMEOUT"
    # manually stopped by the user
    STOPPED = "STOPPED"
    # stopped when the agent started the next message. This only matters for non-forked tasks
    INTERRUPTED = "INTERRUPTED"
    # effectively stopped because it was running in our parent, but we are a forked task
    FORKED = "FORKED"
    # the case where sculptor was shut down while the check was running
    SHUTDOWN = "SHUTDOWN"
    # the case where the task exited while the check was running
    TASK_EXIT = "TASK_EXIT"
    # if sculptor itself crashed while the check was running
    SCULPTOR_CRASHED = "SCULPTOR_CRASHED"
    # if the environment crashed while the check was running
    ENVIRONMENT_CRASHED = "ENVIRONMENT_CRASHED"


class CheckFinishedRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "CheckFinishedRunnerMessage"
    user_message_id: AgentMessageID
    check: Check
    run_id: RunID
    exit_code: int | None
    finished_reason: CheckFinishedReason
    # if non-empty, this check wasn't even able to be properly loaded, and this is the reason why
    archival_reason: str


class NewSuggestionRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "NewSuggestionRunnerMessage"
    user_message_id: AgentMessageID
    check_name: str
    run_id: RunID
    suggestions: tuple[Suggestion, ...]


class ChecksDefinedRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "ChecksDefinedRunnerMessage"
    user_message_id: AgentMessageID
    check_by_name: dict[str, Check]


PersistentRunnerMessageUnion = (
    Annotated[KilledAgentRunnerMessage, Tag("KilledAgentRunnerMessage")]
    | Annotated[AgentCrashedRunnerMessage, Tag("AgentCrashedRunnerMessage")]
    | Annotated[EnvironmentCrashedRunnerMessage, Tag("EnvironmentCrashedRunnerMessage")]
    | Annotated[UnexpectedErrorRunnerMessage, Tag("UnexpectedErrorRunnerMessage")]
    | Annotated[AgentSnapshotRunnerMessage, Tag("AgentSnapshotRunnerMessage")]
    | Annotated[ResumeAgentResponseRunnerMessage, Tag("ResumeAgentResponseRunnerMessage")]
)


EphemeralRunnerMessageUnion = (
    Annotated[WarningRunnerMessage, Tag("WarningRunnerMessage")]
    | Annotated[TaskLifecycleRunnerMessage, Tag("TaskLifecycleRunnerMessage")]
    | Annotated[TaskStatusRunnerMessage, Tag("TaskStatusRunnerMessage")]
    | Annotated[CheckLaunchedRunnerMessage, Tag("CheckLaunchedRunnerMessage")]
    | Annotated[CheckFinishedRunnerMessage, Tag("CheckFinishedRunnerMessage")]
    | Annotated[NewSuggestionRunnerMessage, Tag("NewSuggestionRunnerMessage")]
    | Annotated[ChecksDefinedRunnerMessage, Tag("ChecksDefinedRunnerMessage")]
    | Annotated[EnvironmentStoppedRunnerMessage, Tag("EnvironmentStoppedRunnerMessage")]
    | Annotated[EnvironmentCreatedRunnerMessage, Tag("EnvironmentCreatedRunnerMessage")]
)


RunnerMessageUnion = PersistentRunnerMessageUnion | EphemeralRunnerMessageUnion


class EphemeralAgentMessage(EphemeralMessage):
    """Base class for messages sent from the agent."""

    source: AgentMessageSource = AgentMessageSource.AGENT


AgentMessage = PersistentAgentMessage | EphemeralAgentMessage


class ContextSummaryMessage(PersistentAgentMessage):
    object_type: str = "ContextSummaryMessage"
    content: str


class PartialResponseBlockAgentMessage(EphemeralAgentMessage):
    object_type: str = "PartialResponseBlockAgentMessage"
    chunk: str


class UpdatedArtifactAgentMessage(EphemeralAgentMessage):
    object_type: str = "UpdatedArtifactAgentMessage"
    artifact: FileAgentArtifact


class RequestStartedAgentMessage(PersistentAgentMessage):
    object_type: str = "RequestStartedAgentMessage"
    request_id: AgentMessageID


class RemoveQueuedMessageAgentMessage(PersistentAgentMessage):
    object_type: str = "RemoveQueuedMessageAgentMessage"
    removed_message_id: AgentMessageID


class PersistentRequestCompleteAgentMessage(PersistentAgentMessage, abc.ABC):
    request_id: AgentMessageID
    error: SerializedException | None


class EphemeralRequestCompleteAgentMessage(EphemeralAgentMessage):
    object_type: str = "EphemeralRequestCompleteAgentMessage"
    request_id: AgentMessageID
    error: SerializedException | None


class RequestSkippedAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestSkippedAgentMessage"
    error: None = None


class RequestSuccessAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestSuccessAgentMessage"
    error: None = None


class RequestFailureAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestFailureAgentMessage"
    error: SerializedException


class RequestStoppedAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestStoppedAgentMessage"
    error: SerializedException


class UserCommandFailureAgentMessage(PersistentAgentMessage):
    object_type: str = "UserCommandFailureAgentMessage"
    error: SerializedException


class ServerReadyAgentMessage(EphemeralAgentMessage):
    object_type: str = "ServerReadyAgentMessage"
    url: AnyUrl
    name: str


class MCPServerType(StrEnum):
    """Type of MCP server"""

    IMBUE_CLI = "imbue_cli"  # Servers provided by imbue-cli
    EXTERNAL = "external"  # External/third-party MCP servers


class MCPServerInfo(SerializableModel):
    """Information about an MCP server including its status and available tools"""

    status: str = Field(..., description="Connection status of the MCP server")
    server_type: MCPServerType = Field(..., description="Type of MCP server")
    tools: list[str] = Field(default_factory=list, description="List of tool names available from this server")


class MCPStateUpdateAgentMessage(EphemeralAgentMessage):
    object_type: str = "MCPStateUpdateAgentMessage"
    mcp_servers: dict[str, MCPServerInfo]


class StreamingStderrAgentMessage(EphemeralAgentMessage):
    object_type: str = "StreamingStderrAgentMessage"
    stderr_line: str
    metadata: dict[str, Any] | None = None


class WarningAgentMessage(PersistentAgentMessage):
    object_type: str = "WarningAgentMessage"
    error: SerializedException | None
    message: str


PersistentAgentMessageUnion = (
    Annotated[EphemeralRequestCompleteAgentMessage, Tag("EphemeralRequestCompleteAgentMessage")]
    | Annotated[RequestSuccessAgentMessage, Tag("RequestSuccessAgentMessage")]
    | Annotated[RequestFailureAgentMessage, Tag("RequestFailureAgentMessage")]
    | Annotated[UserCommandFailureAgentMessage, Tag("UserCommandFailureAgentMessage")]
    | Annotated[ResponseBlockAgentMessage, Tag("ResponseBlockAgentMessage")]
    | Annotated[WarningAgentMessage, Tag("WarningAgentMessage")]
    | Annotated[RequestStartedAgentMessage, Tag("RequestStartedAgentMessage")]
    | Annotated[RequestSkippedAgentMessage, Tag("RequestSkippedAgentMessage")]
    | Annotated[RequestStoppedAgentMessage, Tag("RequestStoppedAgentMessage")]
    | Annotated[ContextSummaryMessage, Tag("ContextSummaryMessage")]
    | Annotated[RemoveQueuedMessageAgentMessage, Tag("RemoveQueuedMessageAgentMessage")]
)


EphemeralAgentMessageUnion = (
    Annotated[PartialResponseBlockAgentMessage, Tag("PartialResponseBlockAgentMessage")]
    | Annotated[ServerReadyAgentMessage, Tag("ServerReadyAgentMessage")]
    | Annotated[StreamingStderrAgentMessage, Tag("StreamingStderrAgentMessage")]
    | Annotated[MCPStateUpdateAgentMessage, Tag("MCPStateUpdateAgentMessage")]
    | Annotated[UpdatedArtifactAgentMessage, Tag("UpdatedArtifactAgentMessage")]
)

AgentMessageUnion = PersistentAgentMessageUnion | EphemeralAgentMessageUnion

PersistentMessageTypes = Annotated[
    PersistentAgentMessageUnion
    | PersistentRunnerMessageUnion
    | PersistentUserMessageUnion
    | PersistentSystemMessageUnion,
    build_discriminator(),
]

MessageTypes = Annotated[
    PersistentAgentMessageUnion
    | PersistentRunnerMessageUnion
    | PersistentUserMessageUnion
    | EphemeralAgentMessageUnion
    | EphemeralRunnerMessageUnion
    | EphemeralUserMessageUnion
    | LocalSyncMessageUnion,
    build_discriminator(),
]


class AgentConfig(SerializableModel):
    object_type: str


class StandardAgentConfig(AgentConfig):
    """
    By convention, we suggest that all agents create tmux panes and a ttyd server to allow easy inspection of the agent.
    """

    tmux_session_name: str | None = None
    tmux_scrollback_path: str | None = None
    ttyd_port: int | None = None


class Agent(MutableModel, abc.ABC):
    @abc.abstractmethod
    def pop_messages(self) -> list[Message]: ...

    @abc.abstractmethod
    def push_message(self, message: UserMessageUnion | SystemMessageUnion) -> None: ...

    @abc.abstractmethod
    def terminate(self, force_kill_seconds: float = 5.0) -> None: ...

    @abc.abstractmethod
    def poll(self) -> int | None: ...

    @abc.abstractmethod
    def wait(self, timeout: float) -> int:
        """
        Wait for the agent to finish running and return the exit code.

        Raises:
            AgentCrashed: If some part of the agent code failed with an unexpected exception.
            WaitTimeoutAgentError: If the agent did not finish within the specified timeout.
        """

    @abc.abstractmethod
    def start(self, secrets: Mapping[str, str | Secret], anthropic_credentials: AnthropicCredentials) -> None: ...


class ProcessWrapperAgent(Agent):
    environment: Environment
    _output_messages: Queue[Message] = PrivateAttr(default_factory=Queue)
    _exception: BaseException | None = PrivateAttr(default=None)
    _process: RunningProcess | None = PrivateAttr(default=None)
    _exit_code: int | None = PrivateAttr(default=None)
    _is_stopping: bool = PrivateAttr(default=False)

    def pop_messages(self) -> list[Message]:
        new_logs = []
        while self._output_messages.qsize() > 0:
            message = self._output_messages.get_nowait()
            new_logs.append(message)
        return new_logs

    @contextmanager
    def _handle_user_message(self, message: UserMessageUnion) -> Generator[None, None, None]:
        self._output_messages.put(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=message.message_id,
            )
        )
        try:
            yield
        except Exception as e:
            # log_exception defaults log level to "ERROR" when priority is None
            # https://gitlab.com/generally-intelligent/generally_intelligent/-/blob/main/imbue_core/imbue_core/async_monkey_patches.py#L386
            # We can't directly set it as "ERROR" isn't mapped to an ExceptionPriority
            exception_priority_level = None
            if isinstance(e, ClaudeClientError):
                # Lower priority of transient LLM API errors
                exception_priority_level = ExceptionPriority.LOW_PRIORITY
            # if we got a sigterm, it's likely because we are shutting down in tests, so, probably worth bailing
            is_stopping = False
            if isinstance(e, ClaudeClientError) and e.exit_code == AGENT_EXIT_CODE_FROM_SIGTERM:
                is_stopping = True
                self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
                logger.info("Received SIGTERM, likely due to shutdown, no need to log further")
            elif isinstance(e, ClaudeClientError) and e.exit_code == AGENT_EXIT_CODE_FROM_SIGINT:
                is_stopping = True
                self._exit_code = AGENT_EXIT_CODE_FROM_SIGINT
                logger.info("Received SIGINT, likely due to controlled shutdown, no need to log further")
            elif isinstance(e, ClaudeTransientError):
                maybe_task_id = getattr(self, "task_id", None)
                emit_posthog_event(
                    PosthogEventModel(
                        name=SculptorPosthogEvent.CLAUDE_TRANSIENT_ERROR,
                        component=ProductComponent.CLAUDE_CODE,
                        payload=get_exception_payload(e),
                        task_id=str(maybe_task_id) if maybe_task_id else None,
                    )
                )
            else:
                log_exception(e, f"Error handling user message: {message}", priority=exception_priority_level)
            serialized_exception = SerializedException.build(e)
            # message_type = RequestStoppedAgentMessage if is_stopping else RequestFailureAgentMessage
            message_type = RequestFailureAgentMessage
            self._output_messages.put(
                message_type(
                    message_id=AgentMessageID(),
                    request_id=message.message_id,
                    error=serialized_exception,
                )
            )
            if not isinstance(e, ClaudeClientError):
                # if it is a claude client error, let's report it and allow the user to retry or continue
                # otherwise, let's raise it out of the agent wrapper
                raise e
        else:
            if not self._is_stopping:
                self._output_messages.put(
                    RequestSuccessAgentMessage(
                        message_id=AgentMessageID(),
                        request_id=message.message_id,
                        error=None,
                    )
                )

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        if self._process is not None:
            try:
                self._process.terminate(force_kill_seconds)
            except TimeoutExpired as e:
                raise UncleanTerminationAgentError(
                    f"Failed to terminate agent process within {force_kill_seconds} seconds"
                ) from e
            else:
                self._process = None

    def poll(self) -> int | None:
        return self._exit_code

    def start(self, secrets: Mapping[str, str | Secret], anthropic_credentials: AnthropicCredentials) -> None:
        logger.debug("running agent wrapper: {}", self.__class__.__name__)
        self._on_start(secrets, anthropic_credentials)

    def _on_start(self, secrets: Mapping[str, str | Secret], anthropic_credentials: AnthropicCredentials) -> None:
        raise NotImplementedError("Subclasses must implement this method")


class HelloAgentConfig(StandardAgentConfig):
    object_type: str = "HelloAgentConfig"
    command: str = "echo"  # Default command to run


class ClaudeCodeSDKAgentConfig(StandardAgentConfig):
    object_type: str = "ClaudeCodeSDKAgentConfig"


class ClaudeCodeTextAgentConfig(StandardAgentConfig):
    object_type: str = "ClaudeCodeTextAgentConfig"
    initial_prompt: str | None = None


AgentConfigTypes = Annotated[
    Annotated[HelloAgentConfig, Tag("HelloAgentConfig")]
    | Annotated[ClaudeCodeSDKAgentConfig, Tag("ClaudeCodeSDKAgentConfig")]
    | Annotated[ClaudeCodeTextAgentConfig, Tag("ClaudeCodeTextAgentConfig")],
    build_discriminator(),
]
