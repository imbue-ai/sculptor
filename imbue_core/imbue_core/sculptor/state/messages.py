import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.ids import AssistantMessageID
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.sculptor.state.chat_state import ContentBlockTypes
from imbue_core.time_utils import get_current_time


class LLMModel(StrEnum):
    CLAUDE_4_OPUS = "CLAUDE-4-OPUS"
    CLAUDE_4_OPUS_200K = "CLAUDE-4-OPUS-200K"
    CLAUDE_4_7_OPUS = "CLAUDE-4-7-OPUS"
    CLAUDE_4_7_OPUS_200K = "CLAUDE-4-7-OPUS-200K"
    CLAUDE_4_6_OPUS = "CLAUDE-4-6-OPUS"
    CLAUDE_4_6_OPUS_200K = "CLAUDE-4-6-OPUS-200K"
    CLAUDE_4_SONNET = "CLAUDE-4-SONNET"
    CLAUDE_4_SONNET_200K = "CLAUDE-4-SONNET-200K"
    CLAUDE_4_HAIKU = "CLAUDE-4-HAIKU"
    CLAUDE_FABLE_5 = "CLAUDE-FABLE-5"
    FAKE_CLAUDE = "FAKE_CLAUDE"
    FAKE_CLAUDE_2 = "FAKE_CLAUDE_2"


class EffortLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTRA_HIGH = "xhigh"
    MAX = "max"


# ==================================
# Backend Message Type Definitions
# ==================================


class AgentMessageSource(StrEnum):
    """
    Messages can come the AGENT (in-container LLM), USER (chat messages & direct interactions), SCULPTOR_SYSTEM (multifaceted sculptor app and service code) and RUNNER (the process controlling a task on the server.)
    """

    # Messages coming directly from the agent from inside the environment.
    AGENT = "AGENT"

    # Messages coming directly from a user interacting with the interface, ie chat
    USER = "USER"

    # Messages coming from sculptor-mediated actions and automations, like local sync updates or manual sync operations.
    # If there is ambiguity, (ie, "the user _did_ click a button but we did a lot of magic in the resolution") prefer SCULPTOR_SYSTEM.
    SCULPTOR_SYSTEM = "SCULPTOR_SYSTEM"

    # Messages coming from the task runner wrapper, such as environment shutdown.
    # conceptually a subset of SCULPTOR_SYSTEM
    RUNNER = "RUNNER"


class Message(SerializableModel):
    """Base class for all messages sent to or from the agent and user."""

    # used to dispatch and discover the type of message
    object_type: str
    # the unique ID of the message, used to track it across the system and prevent duplicates.
    message_id: AgentMessageID = Field(default_factory=AgentMessageID)
    # the source of the message, which can be either the agent, user, or runner.
    source: AgentMessageSource
    # roughly when the message was created, in UTC.
    # note that this is approximate due to clock skew -- these messages are created on different machines.
    # you should *not* sort by this field -- instead, rely on the order in which the messages are received.
    approximate_creation_time: datetime.datetime = Field(default_factory=get_current_time)

    # if the message is ephemeral, it will be logged but not saved to the database
    # if it is persistent, it will be logged AND saved to the database
    @property
    def is_ephemeral(self) -> bool:
        raise NotImplementedError("All messages must be subclassed off of PersistentMessage or EphemeralMessage")


class PersistentMessage(Message):
    @property
    def is_ephemeral(self) -> bool:
        return False


class PersistentUserMessage(PersistentMessage):
    """
    One of two base classes for messages sent from the user.
    Persistent user messages are saved to the database.
    Persistent user messages are queued in the task runner before they are sent to the agent.
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


class ChatInputUserMessage(PersistentUserMessage):
    object_type: str = Field(default="ChatInputUserMessage")
    text: str = Field(description="User input text content")
    model_name: LLMModel | None = Field(default=None, description="Selected LLM model for the chat request")
    files: list[str] = Field(
        default_factory=list,
        description="List of file paths (images, PDFs, etc., stored in Electron app folder) attached to this message",
    )
    enter_plan_mode: bool = Field(default=False, description="Whether the user requested to enter plan mode")
    exit_plan_mode: bool = Field(default=False, description="Whether the user requested to exit plan mode")
    fast_mode: bool = Field(default=False, description="Whether to enable fast output mode")
    effort: EffortLevel = Field(default=EffortLevel.EXTRA_HIGH, description="Thinking effort level")
    sent_via: str | None = Field(default=None, description="Interface that sent this message, e.g. 'sculpt'")


class PersistentAgentMessage(PersistentMessage):
    """Base class for messages sent from the agent."""

    source: AgentMessageSource = AgentMessageSource.AGENT


class ResponseBlockAgentMessage(PersistentAgentMessage):
    object_type: str = "ResponseBlockAgentMessage"
    role: Literal["user", "assistant", "system"]
    assistant_message_id: AssistantMessageID
    content: tuple[ContentBlockTypes, ...]
    parent_tool_use_id: str | None = None
