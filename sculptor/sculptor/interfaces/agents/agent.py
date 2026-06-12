"""
An Agent simply *is* a list of `Message`s.

The meaning of each of the message is defined below.
"""

from __future__ import annotations

import abc
import datetime
from enum import StrEnum
from typing import Annotated
from typing import Mapping

from pydantic import Field
from pydantic import Tag

from sculptor.foundation.pydantic_serialization import MutableModel
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import build_discriminator
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.serialization import SerializedException
from sculptor.foundation.time_utils import get_current_time
from sculptor.interfaces.agents.artifacts import FileAgentArtifact
from sculptor.interfaces.agents.messages import EphemeralAgentMessage
from sculptor.interfaces.agents.messages import EphemeralMessage
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import TaskID as TaskID
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import TurnMetrics
from sculptor.state.claude_state import ParsedAgentResponsePassthrough
from sculptor.state.claude_state import ParsedToolResultResponse
from sculptor.state.messages import AgentMessageSource
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import EffortLevel
from sculptor.state.messages import LLMModel
from sculptor.state.messages import Message
from sculptor.state.messages import PersistentAgentMessage
from sculptor.state.messages import PersistentMessage
from sculptor.state.messages import PersistentUserMessage
from sculptor.state.messages import ResponseBlockAgentMessage

ParsedAgentResponseType = ParsedAgentResponsePassthrough | ParsedToolResultResponse


class Agent(MutableModel, abc.ABC):
    @abc.abstractmethod
    def pop_messages(self) -> list[MessageTypes]: ...

    @abc.abstractmethod
    def push_message(self, message: Message) -> None: ...

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
    def start(
        self,
        secrets: Mapping[str, str | Secret],
    ) -> None: ...


EnvironmentTypes = LocalEnvironment


class EphemeralUserMessage(EphemeralMessage):
    """
    One of two base classes for messages sent from the user.
    Ephemeral user messages are not saved to the database.
    Ephemeral user messages are sent immediately to the agent and are not queued in the task runner.
    """

    # Override inherited fields
    object_type: str = Field(description="Type discriminator for user messages")
    message_id: AgentMessageID = Field(
        default_factory=AgentMessageID,
        description="Unique identifier for the user message",
    )
    source: AgentMessageSource = Field(default=AgentMessageSource.USER)
    approximate_creation_time: datetime.datetime = Field(
        default_factory=get_current_time,
        description="Approximate UTC timestamp when user message was created",
    )


class ClearContextUserMessage(PersistentUserMessage):
    object_type: str = Field(default="ClearContextUserMessage")


class UserQuestionAnswerMessage(PersistentUserMessage):
    object_type: str = Field(default="UserQuestionAnswerMessage")
    answers: dict[str, str] = Field(description="Map from question text to answer text")
    notes: dict[str, str] = Field(
        default_factory=dict,
        description="Map from question text to the freeform 'Other' text the user typed, when present. Mirrors the native AskUserQuestion tool's per-question `notes` annotation, which the result formatter renders as ` user notes: <text>` after the answer string.",
    )
    question_data: AskUserQuestionData = Field(description="The original questions for context")
    tool_use_id: str = Field(description="The original ToolUseBlock ID")


class StopAgentUserMessage(EphemeralUserMessage):
    object_type: str = Field(default="StopAgentUserMessage")


class InterruptProcessUserMessage(EphemeralUserMessage):
    object_type: str = Field(default="InterruptProcessUserMessage")


class RemoveQueuedMessageUserMessage(EphemeralUserMessage):
    object_type: str = Field(default="RemoveQueuedMessageUserMessage")
    target_message_id: AgentMessageID = Field(description="ID of the message to be removed from the queue")


PersistentUserMessageUnion = (
    Annotated[ChatInputUserMessage, Tag("ChatInputUserMessage")]
    | Annotated[ClearContextUserMessage, Tag("ClearContextUserMessage")]
    | Annotated[UserQuestionAnswerMessage, Tag("UserQuestionAnswerMessage")]
)
EphemeralUserMessageUnion = (
    Annotated[InterruptProcessUserMessage, Tag("InterruptProcessUserMessage")]
    | Annotated[RemoveQueuedMessageUserMessage, Tag("RemoveQueuedMessageUserMessage")]
    | Annotated[StopAgentUserMessage, Tag("StopAgentUserMessage")]
)
UserMessageUnion = PersistentUserMessageUnion | EphemeralUserMessageUnion


class PersistentRunnerMessage(PersistentMessage):
    """Base class for messages sent from the runner."""

    source: AgentMessageSource = AgentMessageSource.RUNNER


class EphemeralRunnerMessage(EphemeralMessage):
    """Base class for messages sent from the runner."""

    source: AgentMessageSource = AgentMessageSource.RUNNER


class EnvironmentAcquiredRunnerMessage(EphemeralRunnerMessage):
    """Emitted when the task acquires an environment from its workspace."""

    object_type: str = "EnvironmentAcquiredRunnerMessage"
    # TODO(SCU-135): Remove this field when git/diff operations move to workspace level.
    # The environment will be accessed via WorkspaceService instead of this message.
    environment: EnvironmentTypes


class EnvironmentReleasedRunnerMessage(EphemeralRunnerMessage):
    """Emitted when the task handler releases the environment to the workspace."""

    object_type: str = "EnvironmentReleasedRunnerMessage"


class KilledAgentRunnerMessage(PersistentRunnerMessage):
    object_type: str = "KilledAgentRunnerMessage"


class ErrorMessage(SerializableModel):
    pass
    # TODO: remove the `error` field from the subclasses and enable it here.
    # this will require a schema migration
    # error: SerializedException


class AgentCrashedRunnerMessage(PersistentRunnerMessage, ErrorMessage):
    """
    Note that (like EnvironmentCrashedRunnerMessage and UnexpectedErrorRunnerMessage),
    this can happen before *or after* the agent has finished processing a given message.
    """

    object_type: str = "AgentCrashedRunnerMessage"
    exit_code: int | None
    error: SerializedException


class EnvironmentCrashedRunnerMessage(PersistentRunnerMessage, ErrorMessage):
    object_type: str = "EnvironmentCrashedRunnerMessage"
    error: SerializedException


class UnexpectedErrorRunnerMessage(PersistentRunnerMessage, ErrorMessage):
    object_type: str = "UnexpectedErrorRunnerMessage"
    error: SerializedException


class TaskStatusRunnerMessage(EphemeralRunnerMessage):
    object_type: str = "TaskStatusRunnerMessage"
    outcome: TaskState


class ResumeAgentResponseRunnerMessage(PersistentRunnerMessage):
    object_type: str = "ResumeAgentResponseRunnerMessage"
    for_user_message_id: AgentMessageID
    error: SerializedException | None = None
    model_name: LLMModel | None = Field(default=None, description="Selected LLM model for the chat request")
    fast_mode: bool = Field(default=False, description="Whether to enable fast output mode")
    effort: EffortLevel = Field(default=EffortLevel.EXTRA_HIGH, description="Thinking effort level")


class WarningMessage(Message):
    error: SerializedException | None
    message: str


PersistentRunnerMessageUnion = (
    Annotated[KilledAgentRunnerMessage, Tag("KilledAgentRunnerMessage")]
    | Annotated[AgentCrashedRunnerMessage, Tag("AgentCrashedRunnerMessage")]
    | Annotated[EnvironmentCrashedRunnerMessage, Tag("EnvironmentCrashedRunnerMessage")]
    | Annotated[UnexpectedErrorRunnerMessage, Tag("UnexpectedErrorRunnerMessage")]
    | Annotated[ResumeAgentResponseRunnerMessage, Tag("ResumeAgentResponseRunnerMessage")]
)
EphemeralRunnerMessageUnion = (
    Annotated[TaskStatusRunnerMessage, Tag("TaskStatusRunnerMessage")]
    | Annotated[EnvironmentAcquiredRunnerMessage, Tag("EnvironmentAcquiredRunnerMessage")]
    | Annotated[EnvironmentReleasedRunnerMessage, Tag("EnvironmentReleasedRunnerMessage")]
)
RunnerMessageUnion = PersistentRunnerMessageUnion | EphemeralRunnerMessageUnion


class ContextSummaryMessage(PersistentAgentMessage):
    object_type: str = "ContextSummaryMessage"
    content: str


class ContextClearedMessage(PersistentAgentMessage):
    object_type: str = "ContextClearedMessage"


class PartialResponseBlockAgentMessage(EphemeralAgentMessage):
    """Ephemeral message with accumulated streaming content.

    Contains complete accumulated content so far (not just delta).
    Used for real-time UI updates during streaming.
    """

    object_type: str = "PartialResponseBlockAgentMessage"
    content: tuple[ContentBlockTypes, ...] = ()
    assistant_message_id: AssistantMessageID
    # The message_id that will be used for the first ResponseBlockAgentMessage of this turn.
    # Used to ensure ChatMessage.id is stable from the first partial and matches a persisted message.
    first_response_message_id: AgentMessageID
    parent_tool_use_id: str | None = None


class StreamingMessageCompleteAgentMessage(EphemeralAgentMessage):
    """Ephemeral marker indicating streaming for one response block is complete.

    Emitted on message_stop from Claude Code. Not persisted to DB - only used
    for live message_conversion to reset its streaming state.
    """

    object_type: str = "StreamingMessageCompleteAgentMessage"


class UpdatedArtifactAgentMessage(EphemeralAgentMessage):
    object_type: str = "UpdatedArtifactAgentMessage"
    artifact: FileAgentArtifact


class RequestStartedAgentMessage(PersistentAgentMessage):
    object_type: str = "RequestStartedAgentMessage"
    request_id: AgentMessageID


class RemoveQueuedMessageAgentMessage(PersistentAgentMessage):
    object_type: str = "RemoveQueuedMessageAgentMessage"
    removed_message_id: AgentMessageID


class RequestCompleteAgentMessage(abc.ABC):
    request_id: AgentMessageID
    error: SerializedException | None


class PersistentRequestCompleteAgentMessage(PersistentAgentMessage, RequestCompleteAgentMessage, abc.ABC): ...


class RequestSkippedAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestSkippedAgentMessage"
    request_id: AgentMessageID
    error: None = None


class RequestSuccessAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestSuccessAgentMessage"
    request_id: AgentMessageID
    error: None = None
    interrupted: bool = False


class RequestFailureAgentMessage(PersistentRequestCompleteAgentMessage, ErrorMessage):
    object_type: str = "RequestFailureAgentMessage"
    request_id: AgentMessageID
    error: SerializedException


class RequestStoppedAgentMessage(PersistentRequestCompleteAgentMessage):
    object_type: str = "RequestStoppedAgentMessage"
    request_id: AgentMessageID
    error: SerializedException


ErrorMessageUnion = Annotated[
    Annotated[RequestFailureAgentMessage, Tag("RequestFailureAgentMessage")]
    | Annotated[EnvironmentCrashedRunnerMessage, Tag("EnvironmentCrashedRunnerMessage")]
    | Annotated[UnexpectedErrorRunnerMessage, Tag("UnexpectedErrorRunnerMessage")]
    | Annotated[AgentCrashedRunnerMessage, Tag("AgentCrashedRunnerMessage")],
    build_discriminator(),
]


class TurnMetricsAgentMessage(PersistentAgentMessage):
    """Emitted by the output processor at the end of a turn with per-turn metrics.

    Always arrives on the queue before the corresponding RequestSuccessAgentMessage
    or RequestStoppedAgentMessage, so message_conversion can attach it to the
    in-progress chat message before finalizing the request.

    Persistent so that metrics survive server restarts and are available during
    historical message replay.
    """

    object_type: str = "TurnMetricsAgentMessage"
    turn_metrics: TurnMetrics


class BackgroundTaskStartedAgentMessage(EphemeralAgentMessage):
    """Emitted when Claude Code launches a background task (run_in_background)."""

    object_type: str = "BackgroundTaskStartedAgentMessage"
    background_task_id: str
    tool_use_id: str
    description: str = ""
    task_type: str = ""


class BackgroundTaskNotificationAgentMessage(PersistentAgentMessage):
    """Emitted when a background task completes.

    The assistant turn that follows this message is a response to the background task
    completion, not a continuation of the previous conversation. message_conversion uses
    this to separate the background response into its own chat message.

    This is persistent (not ephemeral) because the separation must survive page reloads.
    The entire background notification cycle (system/task_notification → system/init →
    assistant streaming → result/success) happens within a single RequestStarted/
    RequestSuccess pair, so without this persisted marker the background response would
    be concatenated with the preceding assistant message on replay.
    """

    object_type: str = "BackgroundTaskNotificationAgentMessage"
    background_task_id: str
    tool_use_id: str
    status: str
    summary: str = ""
    # Wallclock run time of the background task, in seconds. Parsed from the
    # CLI's task_notification `usage.duration_ms` field. Used by message
    # conversion to compute an accurate subagent-pill duration even when the
    # subagent's own messages never reach the parent's stream (which is the
    # common case for Agent-tool background tasks — see SCU-1151).
    duration_seconds: float | None = None


class AutoCompactingAgentMessage(EphemeralAgentMessage):
    """Ephemeral message indicating the agent has started auto-compacting context.

    Emitted when the PreCompact hook signals that auto-compaction has begun.
    A corresponding AutoCompactingDoneAgentMessage is emitted when it completes.
    """

    object_type: str = "AutoCompactingAgentMessage"


class AutoCompactingDoneAgentMessage(EphemeralAgentMessage):
    """Ephemeral message indicating the agent has finished auto-compacting context."""

    object_type: str = "AutoCompactingDoneAgentMessage"


class AskUserQuestionAgentMessage(EphemeralAgentMessage):
    object_type: str = "AskUserQuestionAgentMessage"
    question_data: AskUserQuestionData


class PlanModeAgentMessage(EphemeralAgentMessage):
    object_type: str = "PlanModeAgentMessage"
    is_in_plan_mode: bool


class WarningAgentMessage(PersistentAgentMessage, WarningMessage):
    object_type: str = "WarningAgentMessage"


PersistentAgentMessageUnion = (
    Annotated[RequestSuccessAgentMessage, Tag("RequestSuccessAgentMessage")]
    | Annotated[RequestFailureAgentMessage, Tag("RequestFailureAgentMessage")]
    | Annotated[ResponseBlockAgentMessage, Tag("ResponseBlockAgentMessage")]
    | Annotated[WarningAgentMessage, Tag("WarningAgentMessage")]
    | Annotated[RequestStartedAgentMessage, Tag("RequestStartedAgentMessage")]
    | Annotated[RequestSkippedAgentMessage, Tag("RequestSkippedAgentMessage")]
    | Annotated[RequestStoppedAgentMessage, Tag("RequestStoppedAgentMessage")]
    | Annotated[ContextSummaryMessage, Tag("ContextSummaryMessage")]
    | Annotated[ContextClearedMessage, Tag("ContextClearedMessage")]
    | Annotated[RemoveQueuedMessageAgentMessage, Tag("RemoveQueuedMessageAgentMessage")]
    | Annotated[BackgroundTaskNotificationAgentMessage, Tag("BackgroundTaskNotificationAgentMessage")]
    | Annotated[TurnMetricsAgentMessage, Tag("TurnMetricsAgentMessage")]
)
EphemeralAgentMessageUnion = (
    Annotated[PartialResponseBlockAgentMessage, Tag("PartialResponseBlockAgentMessage")]
    | Annotated[UpdatedArtifactAgentMessage, Tag("UpdatedArtifactAgentMessage")]
    | Annotated[AskUserQuestionAgentMessage, Tag("AskUserQuestionAgentMessage")]
    | Annotated[PlanModeAgentMessage, Tag("PlanModeAgentMessage")]
    | Annotated[AutoCompactingAgentMessage, Tag("AutoCompactingAgentMessage")]
    | Annotated[AutoCompactingDoneAgentMessage, Tag("AutoCompactingDoneAgentMessage")]
)
AgentMessageUnion = PersistentAgentMessageUnion | EphemeralAgentMessageUnion
# this is necessary because pydantic won't let us use PersistentMessageTypes, which already has a discriminator, to make MessageTypes
PersistentMessageTypesUnannotated = (
    PersistentAgentMessageUnion | PersistentRunnerMessageUnion | PersistentUserMessageUnion
)
PersistentMessageTypes = Annotated[PersistentMessageTypesUnannotated, build_discriminator()]

EphemeralMessageTypes = EphemeralAgentMessageUnion | EphemeralRunnerMessageUnion | EphemeralUserMessageUnion

MessageTypes = Annotated[
    PersistentMessageTypesUnannotated | EphemeralMessageTypes,
    build_discriminator(),
]


class AgentConfig(SerializableModel):
    object_type: str


class HelloAgentConfig(AgentConfig):
    object_type: str = "HelloAgentConfig"
    command: str = "echo"  # Default command to run


class ClaudeCodeSDKAgentConfig(AgentConfig):
    object_type: str = "ClaudeCodeSDKAgentConfig"


class PiAgentConfig(AgentConfig):
    object_type: str = "PiAgentConfig"


class TerminalAgentConfig(AgentConfig):
    object_type: str = "TerminalAgentConfig"


class RegisteredTerminalAgentConfig(AgentConfig):
    """A terminal agent that launches a registered program in its shell.

    Launch parameters are stamped at creation from the registration so the
    task stays self-describing even if the registration file later changes.
    """

    object_type: str = "RegisteredTerminalAgentConfig"
    registration_id: str
    display_name: str
    launch_command: str
    # May contain the literal placeholder `{session_id}`.
    resume_command_template: str | None = None
    accepts_automated_prompts: bool = False


AgentConfigTypes = Annotated[
    Annotated[HelloAgentConfig, Tag("HelloAgentConfig")]
    | Annotated[ClaudeCodeSDKAgentConfig, Tag("ClaudeCodeSDKAgentConfig")]
    | Annotated[PiAgentConfig, Tag("PiAgentConfig")]
    | Annotated[TerminalAgentConfig, Tag("TerminalAgentConfig")]
    | Annotated[RegisteredTerminalAgentConfig, Tag("RegisteredTerminalAgentConfig")],
    build_discriminator(),
]

TERMINAL_AGENT_CONFIG_TYPES = (TerminalAgentConfig, RegisteredTerminalAgentConfig)


def is_terminal_agent_config(config: AgentConfigTypes) -> bool:
    return isinstance(config, TERMINAL_AGENT_CONFIG_TYPES)


# DELIBERATE-TEMPORARY: workspace-bound harness selection.
class HarnessName(StrEnum):
    CLAUDE = "claude"
    PI = "pi"
