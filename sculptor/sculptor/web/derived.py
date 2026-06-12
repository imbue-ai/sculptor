import datetime
import json
from abc import ABC
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from typing import Any
from typing import Generic
from typing import TypeVar
from typing import assert_never

from pydantic import PrivateAttr
from pydantic import Tag
from pydantic import ValidationError
from pydantic import computed_field

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.ids import AssistantMessageID
from imbue_core.itertools import only
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from imbue_core.sculptor.state.chat_state import AskUserQuestionData
from imbue_core.sculptor.state.chat_state import ChatMessage
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.chat_state import ToolUseBlock
from imbue_core.sculptor.state.chat_state import TurnMetrics
from imbue_core.sculptor.state.messages import AgentMessageSource
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.agents.harness_registry import get_harness_for_config
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import BaseTaskState
from sculptor.database.models import MustBeShutDownTaskInputsV1
from sculptor.database.models import NoOpTaskInputsV1
from sculptor.database.models import NoOpTaskStateV1
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import TaskInputs
from sculptor.database.models import UserSettings
from sculptor.database.models import Workspace
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingDoneAgentMessage
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.agent import RemoveQueuedMessageAgentMessage
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.artifacts import AgentTaskStatus
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.interfaces.agents.harness import Harness
from sculptor.interfaces.agents.harness import HarnessCapabilities
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import WorkspaceID
from sculptor.utils.functional import first
from sculptor.web.data_types import PrApproval  # noqa: F401 — re-exported for existing import sites
from sculptor.web.data_types import PrComment  # noqa: F401 — re-exported for existing import sites
from sculptor.web.data_types import PrStatusInfo  # noqa: F401 — re-exported for existing import sites
from sculptor.web.data_types import PrStatusInfoCleared  # noqa: F401 — re-exported for existing import sites
from sculptor.web.data_types import TaskInterface
from sculptor.web.data_types import WorkspaceBranchInfo  # noqa: F401 — re-exported for existing import sites
from sculptor.web.data_types import WorkspaceRemoteBranchesInfo  # noqa: F401 — re-exported for existing import sites


class TaskStatus(StrEnum):
    BUILDING = "BUILDING"  # Environment is being set up
    RUNNING = "RUNNING"  # Claude code process is actively running
    READY = "READY"  # Process completed successfully, idle
    WAITING = "WAITING"  # Agent asked a question or waiting for plan approval
    ERROR = "ERROR"  # Process encountered an error (stderr output)
    REQUEST_ERROR = "REQUEST_ERROR"  # Last request failed (e.g. API 429) but agent is still usable


class WorkspacePeekAgentStatus(StrEnum):
    WORKING = "WORKING"
    WAITING = "WAITING"
    ERROR = "ERROR"
    COMPLETED = "COMPLETED"
    IDLE = "IDLE"


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
        # pyrefly: ignore [bad-return]
        return self.task.input_data

    @property
    def task_state(self) -> TaskStateType | None:
        # pyrefly: ignore [bad-return]
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
        I Extracted it when I thought we were caching task status on state.
        """
        if self.task.outcome == TaskState.FAILED:
            return TaskStatus.ERROR
        if self.task.outcome == TaskState.QUEUED:
            return TaskStatus.BUILDING

        if self.task.outcome in (TaskState.SUCCEEDED, TaskState.CANCELLED, TaskState.DELETED):
            return TaskStatus.READY

        # otherwise, the task is running.
        assert self.task.outcome == TaskState.RUNNING, f"Unexpected task outcome: {self.task.outcome}"
        # if there's no image, we're still building
        if self.task_state is None:
            return TaskStatus.BUILDING
        return None


def _is_content_message(msg: Message) -> bool:
    """Return True if the message represents user-visible content for read/unread tracking.

    Content messages are those that create new visual elements in the chat UI
    (agent responses, errors, warnings, etc.). Non-content messages include:
    - Ephemeral messages (not persisted, recreated on restart)
    - Request lifecycle bookkeeping (RequestStarted, RequestComplete, RemoveQueued)
    - User-initiated messages (the user already knows about their own actions)
    """
    if msg.is_ephemeral:
        return False
    if isinstance(
        msg, (RequestStartedAgentMessage, PersistentRequestCompleteAgentMessage, RemoveQueuedMessageAgentMessage)
    ):
        return False
    if msg.source == AgentMessageSource.USER:
        return False
    return True


# Maps raw exception class names to user-friendly error messages.
_FRIENDLY_ERROR_NAMES: dict[str, str] = {
    "KeyboardInterrupt": "Agent stopped unexpectedly",
    "SystemExit": "Agent stopped unexpectedly",
}

# (active, past, uses_file_path)
_TOOL_DESCRIPTIONS: dict[str, tuple[str, str, bool]] = {
    "Edit": ("Editing", "Edited", True),
    "Read": ("Reading", "Read", True),
    "Write": ("Creating", "Created", True),
    "Bash": ("Running command", "Ran command", False),
    "Grep": ("Searching codebase", "Searched codebase", False),
    "Glob": ("Finding files", "Found files", False),
    "Task": ("Running sub-agent", "Ran sub-agent", False),
}


def _describe_tool_use(block: ToolUseBlock, *, past_tense: bool = False) -> str:
    name = block.name
    entry = _TOOL_DESCRIPTIONS.get(name)
    if entry is None:
        return name

    active, past, uses_file_path = entry
    verb = past if past_tense else active

    if uses_file_path:
        file_path = block.input.get("file_path")
        short_path = file_path.rsplit("/", 1)[-1] if isinstance(file_path, str) and file_path else None
        return f"{verb} {short_path}" if short_path else f"{verb} file"

    return verb


def _get_last_task_list_artifact(messages: list[Message]) -> TaskListArtifact | None:
    """Return the most recent v2 TaskListArtifact referenced by a PLAN update.

    Walks the message stream backwards looking for an UpdatedArtifactAgentMessage
    whose artifact.name == ArtifactType.PLAN, then reads + parses the on-disk
    file. Skips legacy / unsupported-version files so older artifacts don't
    masquerade as fresh ones.
    """
    for msg in reversed(messages):
        if not isinstance(msg, UpdatedArtifactAgentMessage):
            continue
        if msg.artifact.name != ArtifactType.PLAN:
            continue
        url_str = str(msg.artifact.url)
        if not url_str.startswith("file://"):
            return None
        path = Path(url_str.removeprefix("file://"))
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("object_type") != "TaskListArtifact" or data.get("version") != 2:
            continue
        try:
            return TaskListArtifact.model_validate(data)
        except ValidationError:
            continue
    return None


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
    def is_auto_compacting(self) -> bool:
        """True when the agent is auto-compacting context (detected via plugin hook)."""
        for message in reversed(self._messages):
            if isinstance(message, AutoCompactingDoneAgentMessage):
                return False
            if isinstance(message, AutoCompactingAgentMessage):
                return True
        return False

    @computed_field
    @property
    def artifact_names(self) -> list[str]:
        artifact_messages = [x for x in self._messages if isinstance(x, UpdatedArtifactAgentMessage)]
        return list({x.artifact.name for x in artifact_messages})

    @computed_field
    @property
    def updated_at(self) -> datetime.datetime:
        if len(self._messages) == 0:
            return self.created_at
        # Only consider messages that represent user-visible content changes.
        # This excludes:
        # - Ephemeral messages (runner state transitions, environment lifecycle, artifact
        #   updates) which are not persisted and can be re-created on server restart.
        # - Request lifecycle messages (RequestStartedAgentMessage,
        #   PersistentRequestCompleteAgentMessage, RemoveQueuedMessageAgentMessage)
        #   which are bookkeeping and don't create visual content in the chat.
        # - User-initiated messages (source=USER) since the user already knows about
        #   their own actions.
        # Without this, updated_at can advance past last_read_at from bookkeeping
        # messages saved to the DB after the frontend's mark_read call, causing
        # previously-read tasks to appear unread after a server restart.
        for msg in reversed(self._messages):
            if _is_content_message(msg):
                return msg.approximate_creation_time
        # No content messages yet (e.g. freshly created task with only a user input)
        # — use the earliest message.
        return self._messages[0].approximate_creation_time

    def add_message(self, message: Message) -> None:
        """During each update, we add the new messages"""
        self._messages.append(message)


class CodingAgentTaskView(TaskView[AgentTaskInputsV2, AgentTaskStateV2]):
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

    _cache: dict[str, Any] = PrivateAttr(default_factory=dict)

    def add_message(self, message: Message) -> None:
        super().add_message(message)
        self._cache.clear()

    @property
    def _task_data(self) -> TaskListArtifact | None:
        if "task" not in self._cache:
            self._cache["task"] = _get_last_task_list_artifact(self._messages)
        return self._cache["task"]

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
        return TaskInterface.API

    @computed_field
    @property
    def model(self) -> LLMModel:
        # Use the most recent chat message that carried an explicit model selection.
        for message in reversed(self._messages):
            if isinstance(message, ChatInputUserMessage) and message.model_name is not None:
                return message.model_name
        # Fall back to the model selected at agent creation time, then to CLAUDE_FABLE_5.
        input_data = self.task.input_data
        if isinstance(input_data, AgentTaskInputsV2) and input_data.default_model is not None:
            return input_data.default_model
        return LLMModel.CLAUDE_FABLE_5

    @computed_field
    @property
    def harness_capabilities(self) -> HarnessCapabilities:
        return self._resolve_harness().capabilities()

    @computed_field
    @property
    def is_smooth_streaming_supported(self) -> bool:
        return self.model in (
            LLMModel.CLAUDE_4_SONNET,
            LLMModel.CLAUDE_4_SONNET_200K,
            LLMModel.CLAUDE_4_OPUS,
            LLMModel.CLAUDE_4_OPUS_200K,
            LLMModel.CLAUDE_4_7_OPUS,
            LLMModel.CLAUDE_4_7_OPUS_200K,
            LLMModel.CLAUDE_4_6_OPUS,
            LLMModel.CLAUDE_4_6_OPUS_200K,
            LLMModel.CLAUDE_4_HAIKU,
            LLMModel.CLAUDE_FABLE_5,
            LLMModel.FAKE_CLAUDE,
            LLMModel.FAKE_CLAUDE_2,
        )

    @computed_field
    @property
    def is_deleted(self) -> bool:
        return self.task.is_deleted or self.task.is_deleting

    @computed_field
    @property
    def last_read_at(self) -> datetime.datetime | None:
        return self.task.last_read_at

    @computed_field
    @property
    def title(self) -> str | None:
        task_state = self.task_state
        if task_state is None:
            return None
        assert isinstance(task_state, AgentTaskStateV2)
        return task_state.title

    @computed_field
    @property
    def status(self) -> TaskStatus:
        task_from_outcome = self._maybe_get_status_from_outcome()
        if task_from_outcome is not None:
            return task_from_outcome

        # Check if environment has been acquired via message
        has_environment = any(isinstance(m, EnvironmentAcquiredRunnerMessage) for m in self._messages)
        if not has_environment:
            # If no user message has been sent yet, the agent is waiting for input (prompt-less creation).
            # Show READY so the user can type the first message.
            has_user_message = any(isinstance(m, ChatInputUserMessage) for m in self._messages)
            if not has_user_message:
                return TaskStatus.READY
            return TaskStatus.BUILDING

        # if we're blocked on user input, return READY or WAITING.
        chat_input_messages = [
            x for x in self._messages if isinstance(x, (ChatInputUserMessage, UserQuestionAnswerMessage))
        ]
        request_finished_messages = set(
            [x.request_id for x in self._messages if isinstance(x, PersistentRequestCompleteAgentMessage)]
        )
        # NOTE: this used to exclude ``RequestStoppedAgentMessage`` as a workaround
        # for an older bug — interrupted/SIGTERM'd chats were re-delivered to
        # Claude on the next agent run, and the exclusion kept status pinned at
        # RUNNING during that re-processing window. With those bugs fixed at the
        # runner layer the
        # re-processing no longer happens, so a RequestStopped really does mean
        # "this chat is settled — agent is idle, user can send a new message."
        # If the agent has emitted an AskUserQuestion / ExitPlanMode whose
        # answer hasn't arrived yet, the task is WAITING regardless of
        # whether the in-flight request has formally completed. Under the
        # in-process MCP flow the held ``tools/call`` keeps the request
        # alive, so we'd otherwise fall through to ``RUNNING`` and never
        # surface the "needs your input" signal to the workspace peek.
        ready_or_waiting = self._ready_or_waiting()
        if ready_or_waiting == TaskStatus.WAITING:
            return TaskStatus.WAITING

        is_ready = all(input_message.message_id in request_finished_messages for input_message in chat_input_messages)
        if is_ready:
            if self._last_request_failed():
                return TaskStatus.REQUEST_ERROR
            return ready_or_waiting
        # otherwise we're running.
        return TaskStatus.RUNNING

    def _resolve_harness(self) -> Harness:
        """Return the `Harness` this task's config resolves to."""
        return get_harness_for_config(self.task_input.agent_config)

    def _ready_or_waiting(self) -> TaskStatus:
        """Return WAITING if the agent has an unanswered question or pending plan approval, else READY.

        Pending plan approval is signalled by an unanswered ``ExitPlanMode``
        tool block — NOT by ``is_in_plan_mode`` alone. ``EnterPlanMode`` flips
        ``is_in_plan_mode`` to True the moment the agent starts planning, but
        the agent is still working at that point and there is nothing for the
        user to act on.

        AskUserQuestion tool blocks whose input fails strict validation are
        skipped — those calls were rejected by the MCP server with a JSON-RPC
        error and the agent has already moved on, so they should not pin the
        workspace into a yellow ``Waiting for input`` state. ExitPlanMode
        accepts any input per its schema, so any tool_use of it surfaces.

        Likewise, an AUQ / ExitPlanMode tool block whose surrounding request
        has since completed (Success / Failure / Stopped) is no longer
        pending — the agent's process has moved on, so the question can no
        longer be answered against the same turn (SCU-530 follow-on).
        """
        harness = self._resolve_harness()
        # Check both the ephemeral AskUserQuestionAgentMessage (present during live
        # streaming) and the persistent ToolUseBlock evidence (survives page reloads).
        for msg in reversed(self._messages):
            if isinstance(msg, UserQuestionAnswerMessage):
                break
            if isinstance(msg, PersistentRequestCompleteAgentMessage):
                # Any AUQ older than the most recent completed request belongs
                # to a turn the agent has already settled — no pending question.
                break
            if isinstance(msg, AskUserQuestionAgentMessage):
                return TaskStatus.WAITING
            if isinstance(msg, ResponseBlockAgentMessage):
                for b in msg.content:
                    if not isinstance(b, ToolUseBlock):
                        continue
                    if harness.is_ask_user_question_tool(b.name) and harness.is_valid_ask_user_question_input(
                        b.name, b.input
                    ):
                        return TaskStatus.WAITING
                    if harness.is_exit_plan_mode_tool(b.name):
                        return TaskStatus.WAITING
        return TaskStatus.READY

    def _last_request_failed(self) -> bool:
        """Return True if the most recent completed request ended with a failure."""
        for msg in reversed(self._messages):
            if isinstance(msg, PersistentRequestCompleteAgentMessage):
                return isinstance(msg, RequestFailureAgentMessage)
        return False

    @computed_field
    @property
    def goal(self) -> str:
        # Get the first ChatInputUserMessage
        goal = first(x.text for x in self._messages if isinstance(x, ChatInputUserMessage))

        # NOTE: this is due to a quirk in the task subscription system.
        # goal should *rarely* be None, but it will be None for a single frame when the task is first created.
        if goal is None:
            return ""
        return goal

    @computed_field
    @property
    def workspace_id(self) -> WorkspaceID | None:
        """The workspace ID associated with this task.

        In Phase 1, workspaces are created implicitly 1:1 with tasks.
        """
        task_state = self.task_state
        if task_state is None:
            return None
        assert isinstance(task_state, AgentTaskStateV2)
        return task_state.workspace_id

    def _compute_workspace_peek_status(self) -> WorkspacePeekAgentStatus:
        if self.task.outcome == TaskState.SUCCEEDED:
            return WorkspacePeekAgentStatus.COMPLETED
        # For all other states, derive from TaskStatus which already handles WAITING.
        status_map: dict[TaskStatus, WorkspacePeekAgentStatus] = {
            TaskStatus.BUILDING: WorkspacePeekAgentStatus.WORKING,
            TaskStatus.RUNNING: WorkspacePeekAgentStatus.WORKING,
            TaskStatus.WAITING: WorkspacePeekAgentStatus.WAITING,
            TaskStatus.ERROR: WorkspacePeekAgentStatus.ERROR,
            TaskStatus.REQUEST_ERROR: WorkspacePeekAgentStatus.ERROR,
            TaskStatus.READY: WorkspacePeekAgentStatus.IDLE,
        }
        return status_map[self.status]

    @computed_field
    @property
    def workspace_peek_status(self) -> WorkspacePeekAgentStatus:
        if "wps" not in self._cache:
            self._cache["wps"] = self._compute_workspace_peek_status()
        return self._cache["wps"]

    @computed_field
    @property
    def current_activity(self) -> str | None:
        return self._find_latest_activity(past_tense=False)

    @computed_field
    @property
    def last_activity(self) -> str | None:
        return self._find_latest_activity(past_tense=True)

    def _find_latest_activity(self, *, past_tense: bool) -> str | None:
        for msg in reversed(self._messages):
            if not isinstance(msg, ResponseBlockAgentMessage):
                continue
            for block in reversed(msg.content):
                if isinstance(block, ToolUseBlock):
                    return _describe_tool_use(block, past_tense=past_tense)
                if isinstance(block, TextBlock) and block.text.strip():
                    return "Responded" if past_tense else "Responding"
        return None

    @computed_field
    @property
    def task_completed(self) -> int:
        artifact = self._task_data
        if artifact is None:
            return 0
        return sum(1 for t in artifact.tasks if t.status == AgentTaskStatus.COMPLETED)

    @computed_field
    @property
    def task_total(self) -> int:
        artifact = self._task_data
        if artifact is None:
            return 0
        return len(artifact.tasks)

    @computed_field
    @property
    def current_task_subject(self) -> str | None:
        artifact = self._task_data
        if artifact is None:
            return None
        for task in artifact.tasks:
            if task.status == AgentTaskStatus.IN_PROGRESS:
                return task.subject
        return None

    @computed_field
    @property
    def waiting_detail(self) -> str | None:
        if self.status != TaskStatus.WAITING:
            return None
        harness = self._resolve_harness()
        for msg in reversed(self._messages):
            if isinstance(msg, UserQuestionAnswerMessage):
                break
            if isinstance(msg, AskUserQuestionAgentMessage):
                # The plan-approval AUQ uses a known header — render the short
                # canonical text instead of the verbose internal question.
                questions = msg.question_data.questions
                if questions and questions[0].header == "Plan approval":
                    return "Waiting for plan approval"
                if questions:
                    return questions[0].question
                return None
            if isinstance(msg, ResponseBlockAgentMessage):
                if any(isinstance(b, ToolUseBlock) and harness.is_exit_plan_mode_tool(b.name) for b in msg.content):
                    return "Waiting for plan approval"
        return None

    @computed_field
    @property
    def error_detail(self) -> str | None:
        if self.status == TaskStatus.REQUEST_ERROR:
            for msg in reversed(self._messages):
                if isinstance(msg, RequestFailureAgentMessage):
                    if msg.error.args:
                        first_arg = msg.error.args[0]
                        if isinstance(first_arg, str):
                            return first_arg
                    return msg.error.exception
            return None
        if self.status != TaskStatus.ERROR:
            return None
        error = self.task.error
        if error is not None:
            if error.args:
                first_arg = error.args[0]
                if isinstance(first_arg, str):
                    return first_arg
            return _FRIENDLY_ERROR_NAMES.get(error.exception, error.exception)
        return None


class NoOpTaskView(TaskView[NoOpTaskInputsV1, NoOpTaskStateV1]):
    object_type: str = "NoOpTaskView"


TaskViewTypes = Annotated[
    Annotated[CodingAgentTaskView, Tag("CodingAgentTaskView")] | Annotated[NoOpTaskView, Tag("NoOpTaskView")],
    build_discriminator(),
]


class SubmittedQuestionAnswers(SerializableModel):
    question_data: AskUserQuestionData
    answers: dict[str, str]
    tool_use_id: str


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
    in_progress_user_message_id: AgentMessageID | None
    # Track streaming state across updates - index where streaming content starts in in_progress_chat_message
    streaming_start_index: int
    is_streaming_active: bool = False
    # True when in_progress_chat_message content was built via streaming partials.
    # Used to skip the duplicate full ResponseBlockAgentMessage that the SDK emits
    # after streaming ends (for DB persistence) — its text/tool_use content is already present.
    in_progress_message_was_streamed: bool = False
    # SDK assistant_message_ids delivered via streaming partials this request.
    # Carried across batches so a late persistence ResponseBlockAgentMessage
    # still dedupes text/tool_use blocks after UserQuestionAnswerMessage
    # reset in_progress_message_was_streamed.
    streamed_assistant_message_ids: frozenset[AssistantMessageID] = frozenset()
    # first_response_message_id of the partial that built the in-progress
    # message's current streaming segment. Carried across SSE batches so a new
    # streamed turn is detected by an id CHANGE between partials, not by comparing
    # against the in-progress message id (which stays pinned to the first turn's
    # id). Without this, a turn whose id was re-minted after a subagent context
    # switch re-ran complete_segment on every growing partial and stacked them —
    # the chat "double printing" / staircase bug.
    streamed_segment_first_response_id: AgentMessageID | None = None
    pending_user_question: AskUserQuestionData | None = None
    submitted_question_answers: dict[str, SubmittedQuestionAnswers] = {}
    is_in_plan_mode: bool = False
    # Buffered TurnMetrics waiting to be stamped onto the message at RequestSuccess/RequestStopped.
    # Must survive across SSE batches because TurnMetricsAgentMessage and the terminating
    # RequestSuccess/RequestStopped may arrive in separate calls to convert_agent_messages_to_task_update.
    pending_turn_metrics: TurnMetrics | None = None
    # Background tasks (run_in_background Bash, Agent/Task, etc.) whose
    # ``task_started`` event has arrived but whose ``task_notification`` has
    # not. When non-empty the harness's output processor is keeping the
    # parent request alive — even after the agent's own result/success — so
    # the eventual ``task_notification`` can be delivered to the same turn.
    # The frontend reads this to distinguish "agent is thinking" from
    # "harness is idle, waiting for a background task notification"
    # (SCU-387).
    pending_background_task_ids: frozenset[str] = frozenset()


class UserUpdate(SerializableModel):
    user_settings: UserSettings | None = None
    projects: tuple[Project, ...] = ()
    workspaces: tuple[Workspace, ...] = ()
    settings: SculptorSettings | None = None
    notifications: tuple[Notification, ...] = ()


def create_initial_task_view(
    task: Task,
    settings: SculptorSettings,
) -> TaskViewTypes:
    task_view_class: type[TaskViewTypes]
    match task.input_data:
        case AgentTaskInputsV2():
            task_view_class = CodingAgentTaskView
        case NoOpTaskInputsV1():
            task_view_class = NoOpTaskView
        case MustBeShutDownTaskInputsV1():
            assert False, "MustBeShutDownTaskInputsV1 should only occur in testing"
        case _ as unreachable:
            assert_never(unreachable)
    instance = task_view_class()
    instance._task_container.append(task)
    instance._settings_container.append(settings)
    return instance
