import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.time_utils import get_current_time
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.state.chat_state import ContentBlockTypes


class LLMModel(StrEnum):
    """Built-in (Claude-harness) model identities.

    Append-only: every value is persisted (chat messages carry ``model_name``,
    workspaces carry ``default_model``), so a value may be RETIRED but never renamed
    or deleted — old rows must always deserialize. ``MODEL_SHORTNAME_MAP``
    (agents/default/constants.py) maps each member to the exact ``--model`` id it runs.

    Every family (Fable, Opus, Sonnet, Haiku) has the same three kinds of member:
      - latest: a rolling member that runs the Claude CLI's own family alias, so it
        follows whatever the CLI treats as newest. ``sculpt``'s family shortcuts
        (``--model opus``) name it.
      - current: the newest pinned generation. The product default
        (``DEFAULT_LLM_MODEL``, ``sculpt``'s ``DEFAULT_CLAUDE_MODEL``) and ``BTW_MODEL``
        name current members.
      - previous: the pinned generation before it. Haiku has none for now: the Haiku
        before 5.5 is 4.5, which has a 200K window and no effort support, so Haiku 5.5
        becomes the first previous Haiku once a newer Haiku ships.
    The picker (frontend ``PRODUCTION_MODELS``) offers current and previous for each
    family; older pinned generations stay defined but leave the picker.

    One member per model: current models run a native 1M context window, so no model
    gets a 1M/200K pair. The ``_200K`` members stay defined for old rows, but new
    records never use one (``model_for_new_record``).

    Per-release runbook (a new generation in one family):
      1. Add a member named after the real model, and map it to its exact ``--model`` id.
      2. Label + capability-gate it (``modelConstants.ts``, ``modelCapabilities.ts``, and
         ``FAST_MODE_MODELS`` in constants.py) and add it to ``derived.py``'s streaming list.
      3. Put it first in its family's block in ``PRODUCTION_MODELS`` and drop that
         family's old previous generation — from the picker only; its enum value, label,
         capabilities and streaming all stay, so a stored selection still works.
      4. Repoint the pinned pointers the family holds: for Opus, ``DEFAULT_LLM_MODEL``
         (constants.py and ``modelConstants.ts``) and ``sculpt``'s ``DEFAULT_CLAUDE_MODEL``;
         for Haiku, ``BTW_MODEL``. Tests fail until each names its family's newest pinned
         member. The rolling members and ``sculpt``'s shortcuts need no change, and
         ``sculpt`` derives the new model id from the member's name.
      5. Bump the managed Claude CLI (``CLAUDE_VERSION_RANGE``) to a build that knows the
         id, and check what its family aliases now resolve to: the rolling members follow
         them, so their capabilities are a claim about whichever model each resolves to.
      6. Update what names models from outside this file. Integration and frontend
         tests select models by display name, and not only the ones about models —
         grep the tests for the retired entry's long name (``"Claude <gen> <family>"``)
         rather than working from a list. Then the model claims in ``docs/specs`` and
         ``docs/help``.
      7. Regenerate the API types + extension SDK + frozen schema last: this docstring
         is copied verbatim into both the SDK declarations and the frozen schema, so
         editing it after generating leaves them stale.
    """

    # Rolling "latest Opus" alias (shortnames `opus[1m]` / `opus`). Retired from the
    # GUI picker in favor of the explicit per-generation members below, but kept
    # defined: old persisted rows still deserialize, and `sculpt --model opus`
    # resolves through it to whatever the managed CLI treats as the newest Opus.
    # Bumping CLAUDE_VERSION_RANGE can therefore land these members on a new
    # generation with nothing in this repo changing.
    CLAUDE_4_OPUS = "CLAUDE-4-OPUS"
    CLAUDE_4_OPUS_200K = "CLAUDE-4-OPUS-200K"
    # Pinned Opus generations (explicit `--model` ids), newest first. Opus 4.7 and later
    # run a native 1M window that the `[1m]` suffix leaves unchanged, so each `_200K`
    # member from 4.7 on launches the same window as its sibling and stays defined only
    # so persisted rows still deserialize; the picker offers one entry per generation.
    CLAUDE_5_5_OPUS = "CLAUDE-5-5-OPUS"
    CLAUDE_5_5_OPUS_200K = "CLAUDE-5-5-OPUS-200K"
    CLAUDE_5_OPUS = "CLAUDE-5-OPUS"
    CLAUDE_5_OPUS_200K = "CLAUDE-5-OPUS-200K"
    CLAUDE_4_8_OPUS = "CLAUDE-4-8-OPUS"
    CLAUDE_4_8_OPUS_200K = "CLAUDE-4-8-OPUS-200K"
    CLAUDE_4_7_OPUS = "CLAUDE-4-7-OPUS"
    CLAUDE_4_7_OPUS_200K = "CLAUDE-4-7-OPUS-200K"
    CLAUDE_4_6_OPUS = "CLAUDE-4-6-OPUS"
    CLAUDE_4_6_OPUS_200K = "CLAUDE-4-6-OPUS-200K"
    # Rolling "latest Sonnet" / "latest Haiku" aliases (shortnames `sonnet[1m]` /
    # `sonnet` / `haiku`). Like the rolling Opus alias, they are retired from the GUI
    # picker but kept defined, and a managed CLI bump can move them to a new generation.
    CLAUDE_4_SONNET = "CLAUDE-4-SONNET"
    CLAUDE_4_SONNET_200K = "CLAUDE-4-SONNET-200K"
    CLAUDE_4_HAIKU = "CLAUDE-4-HAIKU"
    # Rolling "latest Fable" alias (`--model fable`), the Fable counterpart of the rolling
    # members above.
    CLAUDE_FABLE_LATEST = "CLAUDE-FABLE-LATEST"
    # Pinned Sonnet and Haiku generations, newest first, one member each.
    CLAUDE_5_5_SONNET = "CLAUDE-5-5-SONNET"
    CLAUDE_5_SONNET = "CLAUDE-5-SONNET"
    CLAUDE_5_5_HAIKU = "CLAUDE-5-5-HAIKU"
    # Fable (frontier line; single-context entries, no 1M/200K split).
    CLAUDE_FABLE_5 = "CLAUDE-FABLE-5"
    CLAUDE_FABLE_5_1 = "CLAUDE-FABLE-5-1"
    CLAUDE_FABLE_5_2 = "CLAUDE-FABLE-5-2"
    FAKE_CLAUDE = "FAKE_CLAUDE"
    FAKE_CLAUDE_2 = "FAKE_CLAUDE_2"


def model_for_new_record(model: LLMModel) -> LLMModel:
    """The member a newly created record stores for `model`.

    The `_200K` members stay defined so persisted rows still deserialize, but nothing
    new is created with one: a 200K selection arriving from a stale client, a saved
    setting or an older agent is stored as its 1M sibling, the same value without the
    `-200K` suffix.
    """
    return LLMModel(model.value.removesuffix("-200K"))


class EffortLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTRA_HIGH = "xhigh"
    MAX = "max"


class ModelOption(SerializableModel):
    """One model a harness offers in its switcher.

    `provider` and `model_id` identify the model on the harness's own terms
    (pi sends them back as a `set_model` selection; for the Claude harness
    `model_id` is the `LLMModel` value). `display_name` is the selector label.
    """

    provider: str
    model_id: str
    display_name: str


class ModelCatalogState(StrEnum):
    """The catalog states a plain `list[ModelOption]` cannot express.

    `NOT_FETCHED_YET` is the birth state of a backend (pi) catalog on task state,
    before the start-time probe runs — distinct from a fetched-but-empty `[]`
    (authenticated, but no providers), which is what drives the empty state. Keeping
    the two apart is what stops the switcher flashing that empty state during startup. A
    StrEnum member is a value-less, interned singleton that survives serialization
    by identity, so read sites use `is` rather than overloading `None`.
    """

    NOT_FETCHED_YET = "not_fetched_yet"


# Canonical singleton, so call sites read `NOT_FETCHED_YET` not the dotted form.
NOT_FETCHED_YET = ModelCatalogState.NOT_FETCHED_YET

# A backend model catalog as stored on task state and surfaced to the switcher:
# the fetched list (possibly empty = no providers), or a lifecycle sentinel.
ModelCatalog = list[ModelOption] | ModelCatalogState


class AgentMessageSource(StrEnum):
    """
    Messages can come from the AGENT (in-container LLM), USER (chat messages & direct interactions), SCULPTOR_SYSTEM (multifaceted sculptor app and service code) and RUNNER (the process controlling a task on the server.)
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
