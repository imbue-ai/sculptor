"""Converts agent messages to chat messages for the frontend."""

from loguru import logger

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.sculptor.state.chat_state import ChatMessage
from imbue_core.sculptor.state.chat_state import ChatMessageRole
from imbue_core.sculptor.state.chat_state import CommandBlock
from imbue_core.sculptor.state.chat_state import ContentBlockTypes
from imbue_core.sculptor.state.chat_state import ContextSummaryBlock
from imbue_core.sculptor.state.chat_state import ErrorBlock
from imbue_core.sculptor.state.chat_state import ForkedFromBlock
from imbue_core.sculptor.state.chat_state import ForkedToBlock
from imbue_core.sculptor.state.chat_state import ResumeResponseBlock
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.chat_state import ToolResultBlock
from imbue_core.sculptor.state.chat_state import ToolUseBlock
from imbue_core.sculptor.state.chat_state import WarningBlock
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from imbue_core.serialization import SerializedException
from sculptor.interfaces.agents.v1.agent import AgentCrashedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ArtifactType
from sculptor.interfaces.agents.v1.agent import CheckFinishedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckLaunchedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ChecksDefinedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CommandInputUserMessage
from sculptor.interfaces.agents.v1.agent import ContextSummaryMessage
from sculptor.interfaces.agents.v1.agent import EnvironmentCrashedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ForkAgentSystemMessage
from sculptor.interfaces.agents.v1.agent import NewSuggestionRunnerMessage
from sculptor.interfaces.agents.v1.agent import RemoveQueuedMessageAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.v1.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.v1.agent import UnexpectedErrorRunnerMessage
from sculptor.interfaces.agents.v1.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.v1.agent import UserCommandFailureAgentMessage
from sculptor.interfaces.agents.v1.agent import WarningAgentMessage
from sculptor.interfaces.agents.v1.agent import WarningRunnerMessage
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.web.derived import InsertedChatMessage
from sculptor.web.derived import TaskUpdate

# Message type groups
ERROR_MESSAGE_TYPES = (
    EnvironmentCrashedRunnerMessage,
    UnexpectedErrorRunnerMessage,
    AgentCrashedRunnerMessage,
    UserCommandFailureAgentMessage,
)

WARNING_MESSAGE_TYPES = (
    WarningAgentMessage,
    WarningRunnerMessage,
)


def convert_agent_messages_to_task_update(
    new_messages: list[Message | CompletedTransaction | dict],
    task_id: TaskID,
    current_state: TaskUpdate | None = None,
) -> TaskUpdate:
    """Convert a batch of agent messages to a TaskUpdate.

    Takes a stream of agent messages and converts them into a TaskUpdate
    with pure UI state that can be displayed in the frontend. Manages the state
    transitions of messages from queued -> completed and builds up assistant messages
    incrementally.
    """

    completed_chat_messages = []
    queued_chat_messages = list(current_state.queued_chat_messages) if current_state else []
    in_progress_chat_message = current_state.in_progress_chat_message if current_state else None
    current_request_id = current_state.in_progress_user_message_id if current_state else None
    update_artifacts = set()
    finished_request_ids = []
    logs = []
    check_update_messages = []
    new_suggestion_messages = []
    inserted_messages = []

    for msg in new_messages:
        if isinstance(msg, ChatInputUserMessage):
            # Queue user message until confirmed
            queued_chat_messages.append(
                ChatMessage(
                    id=msg.message_id,
                    role=ChatMessageRole.USER,
                    content=(TextBlock(text=msg.text),),
                )
            )

        elif isinstance(msg, CommandInputUserMessage):
            queued_chat_messages.append(
                ChatMessage(
                    id=msg.message_id,
                    role=ChatMessageRole.USER,
                    content=(CommandBlock(command=msg.text, is_automated=msg.is_automated_command),),
                )
            )

        elif isinstance(msg, RequestStartedAgentMessage):
            # Promote queued message to completed
            for i, message in enumerate(queued_chat_messages):
                assert isinstance(msg.request_id, AgentMessageID)
                if message.id == msg.request_id:
                    completed_chat_messages.append(queued_chat_messages.pop(i))
                    current_request_id = msg.request_id
                    break

        elif isinstance(msg, RemoveQueuedMessageAgentMessage):
            # Remove queued message without completing it
            queued_chat_messages = [m for m in queued_chat_messages if m.id != msg.removed_message_id]

        elif isinstance(msg, ResponseBlockAgentMessage):
            # Add content to the in progress assistant message or create a new one
            in_progress_chat_message = _handle_response_blocks(in_progress_chat_message, msg.content, msg.message_id)

        elif isinstance(msg, ResumeAgentResponseRunnerMessage):
            # add a block to indicate that we are resuming
            in_progress_chat_message = _handle_response_blocks(
                in_progress_chat_message, (ResumeResponseBlock(),), msg.message_id
            )

        elif isinstance(msg, ContextSummaryMessage):
            in_progress_chat_message = _add_context_summary_to_message(in_progress_chat_message, msg)
            completed_chat_messages.append(in_progress_chat_message)
            in_progress_chat_message = None

        elif isinstance(msg, RequestSuccessAgentMessage):
            # Finalize assistant message when ready
            if current_request_id and msg.request_id == current_request_id and in_progress_chat_message:
                completed_chat_messages.append(in_progress_chat_message)
                in_progress_chat_message = None
                current_request_id = None

        elif isinstance(msg, RequestFailureAgentMessage):
            # Add error block to assistant message
            in_progress_chat_message = _add_error_to_message(in_progress_chat_message, msg)
            # Finalize assistant message when ready
            if current_request_id and msg.request_id == current_request_id and in_progress_chat_message:
                completed_chat_messages.append(in_progress_chat_message)
                in_progress_chat_message = None
                current_request_id = None

        elif isinstance(msg, ForkAgentSystemMessage):
            if msg.parent_task_id == task_id:
                _insert_forked_to_block(inserted_messages, msg)
            # This could be a fork from another task, or a nested fork. Either way, show the "forked from" block.
            else:
                _insert_forked_from_block(inserted_messages, msg)

        elif isinstance(msg, ERROR_MESSAGE_TYPES):
            # Add error block to assistant message
            if in_progress_chat_message is not None:
                in_progress_chat_message = _add_error_to_message(in_progress_chat_message, msg)
            else:
                new_message = _add_error_to_message(in_progress_chat_message, msg)
                completed_chat_messages.append(new_message)

        elif isinstance(msg, WARNING_MESSAGE_TYPES):
            # Add warning block to assistant message
            if in_progress_chat_message is not None:
                in_progress_chat_message = _add_warning_to_message(in_progress_chat_message, msg)
            else:
                new_message = _add_warning_to_message(in_progress_chat_message, msg)
                completed_chat_messages.append(new_message)

        elif isinstance(msg, UpdatedArtifactAgentMessage):
            artifact_type = ArtifactType(msg.artifact.name)
            if artifact_type:
                update_artifacts.add(artifact_type)

        # Handle build log messages
        elif isinstance(msg, dict):
            logs.append(_reformat_log(msg["text"]))

        # Track completed requests
        elif isinstance(msg, CompletedTransaction):
            if msg.request_id:
                finished_request_ids.append(msg.request_id)

        # handle messages for when the check was started, stopped, or defined
        # (and include container status messages, which affect local checks)
        elif isinstance(
            msg,
            (
                CheckLaunchedRunnerMessage,
                CheckFinishedRunnerMessage,
                ChecksDefinedRunnerMessage,
            ),
        ):
            check_update_messages.append(msg)

        elif isinstance(msg, NewSuggestionRunnerMessage):
            new_suggestion_messages.append(msg)

    # Build final update
    return TaskUpdate(
        task_id=task_id,
        chat_messages=tuple(completed_chat_messages),
        in_progress_chat_message=in_progress_chat_message,
        queued_chat_messages=tuple(queued_chat_messages),
        updated_artifacts=tuple(update_artifacts),
        finished_request_ids=tuple(finished_request_ids),
        logs=tuple(logs),
        in_progress_user_message_id=current_request_id,
        check_update_messages=tuple(check_update_messages),
        new_suggestion_messages=tuple(new_suggestion_messages),
        inserted_messages=tuple(inserted_messages),
    )


def _create_empty_assistant_message(chat_message_id: AgentMessageID) -> ChatMessage:
    """Create a new empty assistant message."""
    return ChatMessage(
        id=chat_message_id,
        role=ChatMessageRole.ASSISTANT,
        content=(),
    )


def _handle_response_blocks(
    in_progress: ChatMessage | None, blocks: tuple[ContentBlockTypes, ...], agent_message_id: AgentMessageID
) -> ChatMessage:
    """Process response blocks, returns the updated in-progress chat message.

    Handles both text/tool use blocks (append) and tool result blocks
    (replace matching tool use or append if no match).
    """
    if not in_progress:
        in_progress = _create_empty_assistant_message(chat_message_id=agent_message_id)

    content = list(in_progress.content)

    for block in blocks:
        if isinstance(block, (TextBlock, ToolUseBlock)):
            content.append(block)
        elif isinstance(block, ToolResultBlock):
            # Try to replace matching tool use with result
            content, replaced = _replace_tool_use_with_result(content, block)
            assert replaced, "No tool use found for result"

    return in_progress.model_copy(update={"content": tuple(content)})


def _replace_tool_use_with_result(content: list, result: ToolResultBlock) -> tuple[list, bool]:
    """Try to replace a tool use block with its result.

    Returns (updated_content, was_replaced).
    """
    for i, block in enumerate(content):
        if isinstance(block, ToolUseBlock) and block.id == result.tool_use_id:
            content[i] = result
            return content, True
    return content, False


def _add_context_summary_to_message(
    in_progress: ChatMessage | None,
    message: ContextSummaryMessage,
) -> ChatMessage:
    """Add error block to message."""

    context_summary_block = ContextSummaryBlock(
        text=message.content,
    )

    return _add_system_block_to_message(in_progress, context_summary_block, chat_message_id=message.message_id)


def _insert_forked_to_block(
    inserted_messages: list[InsertedChatMessage],
    message: ForkAgentSystemMessage,
) -> None:
    """Add forked to block to message."""
    forked_to_block = ForkedToBlock(forked_to_task_id=message.child_task_id)
    new_message = _create_empty_assistant_message(chat_message_id=message.message_id)
    new_message = new_message.model_copy(update={"content": (forked_to_block,)})
    inserted_messages.append(
        InsertedChatMessage(message=new_message, after_message_id=message.fork_point_chat_message_id)
    )


def _insert_forked_from_block(
    inserted_messages: list[InsertedChatMessage],
    message: ForkAgentSystemMessage,
) -> None:
    """Add forked from block to message."""
    forked_from_block = ForkedFromBlock(forked_from_task_id=message.parent_task_id)
    new_message = _create_empty_assistant_message(chat_message_id=message.message_id)
    new_message = new_message.model_copy(update={"content": (forked_from_block,)})
    inserted_messages.append(
        InsertedChatMessage(message=new_message, after_message_id=message.fork_point_chat_message_id)
    )


def _add_error_to_message(
    in_progress: ChatMessage | None,
    message: RequestFailureAgentMessage
    | EnvironmentCrashedRunnerMessage
    | UnexpectedErrorRunnerMessage
    | AgentCrashedRunnerMessage
    | UserCommandFailureAgentMessage,
) -> ChatMessage:
    """Add error block to message."""
    error = message.error
    chat_message_id = message.message_id
    if not isinstance(error, SerializedException):
        logger.error("Expected SerializedException, got {}", type(message.error))
        return in_progress or _create_empty_assistant_message(chat_message_id=chat_message_id)

    args = message.error.args
    message_text = args[0] if args and isinstance(args[0], str) else f"{message.error}"
    error_block = ErrorBlock(
        message=message_text,
        traceback=message.error.as_formatted_traceback(),
        error_type=message.error.exception,
    )

    return _add_system_block_to_message(in_progress=in_progress, block=error_block, chat_message_id=chat_message_id)


def _add_warning_to_message(
    in_progress: ChatMessage | None, message: WarningAgentMessage | WarningRunnerMessage
) -> ChatMessage:
    """Add warning block to message."""
    traceback = None
    warning_type = None

    error = message.error

    if isinstance(error, SerializedException):
        traceback = error.as_formatted_traceback()
        warning_type = error.exception

    warning_block = WarningBlock(
        message=message.message,
        traceback=traceback,
        warning_type=warning_type,
    )

    return _add_system_block_to_message(
        in_progress=in_progress, block=warning_block, chat_message_id=message.message_id
    )


def _add_system_block_to_message(
    in_progress: ChatMessage | None, block: ContentBlockTypes, chat_message_id: AgentMessageID
) -> ChatMessage:
    """Add any system block (error/warning) to message."""
    if not in_progress:
        in_progress = _create_empty_assistant_message(chat_message_id=chat_message_id)

    return in_progress.model_copy(update={"content": in_progress.content + (block,)})


def _reformat_log(log: str) -> str:
    """Reformat log line for display."""
    try:
        timestamp, level, rest = log.split("|", 2)
        _, useful = rest.split("- ", 1)
        return f"{timestamp}|{level}| {useful.strip()}"
    except ValueError:
        # If log format is unexpected, return as-is
        return log
