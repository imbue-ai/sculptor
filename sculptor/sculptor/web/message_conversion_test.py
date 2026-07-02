from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.pi_agent.backchannel import build_ask_user_question_data
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.foundation.itertools import only
from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskNotificationAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskStartedAgentMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import RemoveQueuedMessageAgentMessage
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import StreamingMessageCompleteAgentMessage
from sculptor.interfaces.agents.agent import TurnMetricsAgentMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import ToolUseID
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import ChatMessage
from sculptor.state.chat_state import ChatMessageRole
from sculptor.state.chat_state import ErrorBlock
from sculptor.state.chat_state import FileBlock
from sculptor.state.chat_state import GenericToolContent
from sculptor.state.chat_state import QuestionOption
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.chat_state import TurnMetrics
from sculptor.state.chat_state import UserQuestion
from sculptor.state.chat_state import make_plan_approval_question
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.web.derived import TaskUpdate
from sculptor.web.message_conversion import convert_agent_messages_to_task_update


def _make_request_success(request_id: AgentMessageID) -> RequestSuccessAgentMessage:
    return RequestSuccessAgentMessage(request_id=request_id)


def _make_serialized_exception(message: str = "boom") -> SerializedException:
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return SerializedException.build(exc, exc.__traceback__)


def test_convert_agent_messages_to_task_update_promotes_user_and_assistant_messages() -> None:
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    user_follow_up_message = ChatInputUserMessage(
        text="Goodbye!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_message, user_follow_up_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.chat_messages == ()
    assert len(state.queued_chat_messages) == 2
    queued_user, queued_user_2 = state.queued_chat_messages
    assert queued_user.role == ChatMessageRole.USER
    assert queued_user_2.role == ChatMessageRole.USER

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-1")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely right!"),),
    )

    state = convert_agent_messages_to_task_update(
        [request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.chat_messages) == 1
    promoted_user = state.chat_messages[0]
    assert promoted_user.id == user_message.message_id
    assert state.in_progress_user_message_id == user_message.message_id
    assert state.in_progress_chat_message is not None
    assert [block.text for block in state.in_progress_chat_message.content if isinstance(block, TextBlock)] == [
        "You're absolutely right!"
    ]
    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_follow_up_message.message_id

    follow_up_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Let me explain..."),),
    )

    state = convert_agent_messages_to_task_update(
        [follow_up_response],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is not None
    assert [block.text for block in state.in_progress_chat_message.content if isinstance(block, TextBlock)] == [
        "You're absolutely right!",
        "Let me explain...",
    ]

    request_success = _make_request_success(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.chat_messages) == 1
    assistant_reply = state.chat_messages[0]
    assert assistant_reply.role == ChatMessageRole.ASSISTANT
    assert [block.text for block in assistant_reply.content if isinstance(block, TextBlock)] == [
        "You're absolutely right!",
        "Let me explain...",
    ]
    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_follow_up_message.message_id
    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None
    assert completed_by_id[user_message.message_id].role == ChatMessageRole.USER
    assert completed_by_id[assistant_reply.id].role == ChatMessageRole.ASSISTANT


def test_convert_agent_messages_to_task_update_replaces_tool_use_with_result() -> None:
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id = ToolUseID("tool-use-1")
    assistant_message_id = AssistantMessageID("assistant-tool-message")
    assistant_chat_message_id = AgentMessageID()

    tool_use = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(ToolUseBlock(id=tool_use_id, name="tool", input={"command": "ls"}),),
    )

    state = convert_agent_messages_to_task_update(
        [tool_use],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.chat_messages == ()
    assert state.in_progress_chat_message is not None
    content_blocks = state.in_progress_chat_message.content
    assert len(content_blocks) == 1
    assert isinstance(content_blocks[0], ToolUseBlock)

    tool_result = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="tool",
                invocation_string="tool('ls')",
                content=GenericToolContent(text="done"),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [tool_result],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.chat_messages == ()
    assert state.in_progress_chat_message is not None
    content_blocks = state.in_progress_chat_message.content
    assert len(content_blocks) == 1
    tool_result_block = content_blocks[0]
    assert isinstance(tool_result_block, ToolResultBlock)
    tool_content = tool_result_block.content
    assert isinstance(tool_content, GenericToolContent)
    assert tool_content.text == "done"


def test_convert_agent_messages_to_task_update_handles_partial_response_blocks() -> None:
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.chat_messages == ()
    assert len(state.queued_chat_messages) == 1

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-1")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    partial_response_block_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're"),),
    )
    partial_response_block_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely"),),
    )
    partial_response_block_3 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely right!"),),
    )
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely right!"),),
    )

    state = convert_agent_messages_to_task_update(
        [
            request_started,
            partial_response_block_1,
            partial_response_block_2,
            partial_response_block_3,
            response_block,
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.chat_messages) == 1
    promoted_user = state.chat_messages[0]
    assert promoted_user.id == user_message.message_id
    assert state.in_progress_user_message_id == user_message.message_id
    assert state.in_progress_chat_message is not None
    assert (
        only([block.text for block in state.in_progress_chat_message.content if isinstance(block, TextBlock)])
        == "You're absolutely right!"
    )

    request_success = _make_request_success(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.chat_messages) == 1
    assistant_reply = state.chat_messages[0]
    assert assistant_reply.role == ChatMessageRole.ASSISTANT
    assert (
        only([block.text for block in assistant_reply.content if isinstance(block, TextBlock)])
        == "You're absolutely right!"
    )


def test_convert_agent_messages_to_task_update_provides_stable_chat_message_id() -> None:
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.chat_messages == ()
    assert len(state.queued_chat_messages) == 1

    # This is the persistent ID that will be used for the ChatMessage and the first ResponseBlockAgentMessage
    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-1")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    partial_response_block_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),  # Ephemeral, unique per partial
        first_response_message_id=assistant_chat_message_id,  # Persistent, same for all partials
        content=(TextBlock(text="You're"),),
    )

    state = convert_agent_messages_to_task_update(
        [request_started, partial_response_block_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert in_progress_msg.content == (TextBlock(text="You're"),)
    initial_id = in_progress_msg.id
    # The initial ID should be the persistent first_response_message_id
    assert initial_id == assistant_chat_message_id

    partial_response_block_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely"),),
    )
    state = convert_agent_messages_to_task_update(
        [partial_response_block_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert in_progress_msg.content == (TextBlock(text="You're absolutely"),)
    assert in_progress_msg.id == initial_id

    partial_response_block_3 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely right!"),),
    )

    state = convert_agent_messages_to_task_update(
        [partial_response_block_3],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert in_progress_msg.content == (TextBlock(text="You're absolutely right!"),)
    assert in_progress_msg.id == initial_id

    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="You're absolutely right!"),),
    )
    state = convert_agent_messages_to_task_update(
        [response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert in_progress_msg.content == (TextBlock(text="You're absolutely right!"),)
    assert in_progress_msg.id == initial_id

    request_success = _make_request_success(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.chat_messages) == 1
    assistant_reply = state.chat_messages[0]
    assert assistant_reply.role == ChatMessageRole.ASSISTANT
    assert (
        only([block.text for block in assistant_reply.content if isinstance(block, TextBlock)])
        == "You're absolutely right!"
    )
    assert assistant_reply.id == initial_id


def test_convert_agent_messages_to_task_update_processes_tool_results_during_streaming() -> None:
    """Test that tool results are processed even when streaming is active.

    This regression test covers the bug where ToolResultBlock messages were skipped
    because they arrive as ResponseBlockAgentMessage while is_streaming_active is True.
    The StreamingMessageCompleteAgentMessage that turns off streaming arrives AFTER
    the tool result, so we must not skip tool results during streaming.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id = ToolUseID("tool-use-streaming-1")
    assistant_message_id = AssistantMessageID("assistant-streaming-tool")
    assistant_chat_message_id = AgentMessageID()

    # First, a partial response with text and tool use (streaming starts)
    partial_with_tool_use = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Let me check that for you."),
            ToolUseBlock(id=tool_use_id, name="Read", input={"file_path": "/test.txt"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial_with_tool_use],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Streaming is now active
    assert state.is_streaming_active is True
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert len(in_progress_msg.content) == 2
    assert isinstance(in_progress_msg.content[1], ToolUseBlock)

    # Tool result arrives as ResponseBlockAgentMessage while streaming is still active
    tool_result = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="Read",
                invocation_string="/test.txt",
                content=GenericToolContent(text="file contents here"),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [tool_result],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The tool result should be processed even though streaming is active
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    content_blocks = in_progress_msg.content
    # Should have: TextBlock, ToolResultBlock (replaced ToolUseBlock)
    assert len(content_blocks) == 2
    assert isinstance(content_blocks[0], TextBlock)
    # The ToolUseBlock should have been replaced by ToolResultBlock
    tool_result_block = content_blocks[1]
    assert isinstance(tool_result_block, ToolResultBlock)
    tool_content = tool_result_block.content
    assert isinstance(tool_content, GenericToolContent)
    assert tool_content.text == "file contents here"

    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    state = convert_agent_messages_to_task_update(
        [streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is False
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert isinstance(in_progress_msg.content[1], ToolResultBlock)


def test_convert_agent_messages_to_task_update_tool_result_survives_subsequent_partial() -> None:
    """Regression test: a tool result must not be reverted to a ToolUseBlock by a later partial.

    Sequence:
    1. Partial with [Text, ToolUse(id=abc)]
    2. Response with [ToolResult(tool_use_id=abc)]  -> replaces ToolUse
    3. Another Partial with [Text, ToolUse(id=abc), Text("more")]  -> must NOT revert the result
    4. StreamingComplete -> finalize
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id = ToolUseID("tool-use-survive-1")
    assistant_message_id = AssistantMessageID("assistant-survive")
    assistant_chat_message_id = AgentMessageID()

    # Step 1: partial with text + tool use
    partial_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Let me check."),
            ToolUseBlock(id=tool_use_id, name="Read", input={"file_path": "/test.txt"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.is_streaming_active is True
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 2
    assert isinstance(in_progress.content[0], TextBlock)
    assert isinstance(in_progress.content[1], ToolUseBlock)

    # Step 2: tool result arrives, replaces the ToolUseBlock
    tool_result_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="Read",
                invocation_string="/test.txt",
                content=GenericToolContent(text="file contents here"),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [tool_result_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 2
    assert isinstance(in_progress.content[0], TextBlock)
    assert isinstance(in_progress.content[1], ToolResultBlock)

    # Step 3: another partial arrives (still contains the original ToolUseBlock + new text)
    # This would previously revert the ToolResultBlock back to ToolUseBlock.
    partial_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Let me check."),
            ToolUseBlock(id=tool_use_id, name="Read", input={"file_path": "/test.txt"}),
            TextBlock(text="Now continuing..."),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 3
    assert isinstance(in_progress.content[0], TextBlock)
    # The ToolResultBlock must survive the partial overwrite
    survived_result = in_progress.content[1]
    assert isinstance(survived_result, ToolResultBlock)
    tool_content = survived_result.content
    assert isinstance(tool_content, GenericToolContent)
    assert tool_content.text == "file contents here"
    trailing_text = in_progress.content[2]
    assert isinstance(trailing_text, TextBlock)
    assert trailing_text.text == "Now continuing..."

    # Step 4: streaming completes
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    state = convert_agent_messages_to_task_update(
        [streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is False
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 3
    assert isinstance(in_progress.content[1], ToolResultBlock)


def _make_ask_user_question_messages(
    tool_use_id: ToolUseID,
    assistant_message_id: AssistantMessageID,
    assistant_chat_message_id: AgentMessageID,
) -> tuple[
    AskUserQuestionData,
    PartialResponseBlockAgentMessage,
    AskUserQuestionAgentMessage,
    StreamingMessageCompleteAgentMessage,
    ResponseBlockAgentMessage,
]:
    """Build the standard set of messages for an AskUserQuestion flow."""
    question_data = AskUserQuestionData(
        questions=[
            UserQuestion(
                question="What language?",
                header="Lang",
                options=[
                    QuestionOption(label="Python", description="Great language"),
                    QuestionOption(label="Rust", description="Systems language"),
                ],
                multi_select=False,
            )
        ],
        tool_use_id=str(tool_use_id),
    )

    tool_block = ToolUseBlock(
        id=tool_use_id,
        name="AskUserQuestion",
        input={"questions": [q.model_dump() for q in question_data.questions]},
    )

    partial = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(tool_block,),
    )

    ask_msg = AskUserQuestionAgentMessage(
        message_id=AgentMessageID(),
        question_data=question_data,
    )

    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(tool_block,),
    )

    return question_data, partial, ask_msg, streaming_complete, persistence_msg


def test_ask_user_question_persistence_after_streaming_does_not_duplicate() -> None:
    """Regression test: when the persistence ResponseBlockAgentMessage arrives AFTER
    StreamingMessageCompleteAgentMessage (the correct order after buffering), the
    AskUserQuestion tool block must NOT be duplicated.

    Message order (after output_processor buffers correctly):
    1. PartialResponseBlockAgentMessage (streaming)
    2. AskUserQuestionAgentMessage (ephemeral)
    3. StreamingMessageCompleteAgentMessage
    4. ResponseBlockAgentMessage (persistence, buffered until after streaming)
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Ask me a question",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    tool_use_id = ToolUseID("toolu_ask_q_1")
    assistant_message_id = AssistantMessageID("assistant-ask-q-1")
    assistant_chat_message_id = AgentMessageID()

    _, partial, ask_msg, streaming_complete, persistence_msg = _make_ask_user_question_messages(
        tool_use_id, assistant_message_id, assistant_chat_message_id
    )

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [user_message, request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Streaming partial → AskUserQuestion → StreamingComplete → Persistence
    state = convert_agent_messages_to_task_update(
        [partial, ask_msg, streaming_complete, persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    tool_use_blocks = [b for b in in_progress.content if isinstance(b, ToolUseBlock)]
    assert len(tool_use_blocks) == 1, (
        f"Expected 1 AskUserQuestion ToolUseBlock, got {len(tool_use_blocks)}. Persistence after streaming duplicated the block."
    )
    assert state.pending_user_question is not None


def test_ask_user_question_persistence_before_partial_does_not_duplicate() -> None:
    """Regression test: if the persistence ResponseBlockAgentMessage arrives BEFORE the
    streaming partial (possible if buffering fails or in a different message delivery
    order), the AskUserQuestion tool block must still NOT be duplicated.

    This was the original bug: Claude Code emits ParsedAssistantResponse before
    content_block_stop, so the persistence message can arrive before the partial.

    Message order (the broken order without buffering):
    1. ResponseBlockAgentMessage (persistence, arrived too early)
    2. PartialResponseBlockAgentMessage (streaming)
    3. AskUserQuestionAgentMessage (ephemeral)
    4. StreamingMessageCompleteAgentMessage
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Ask me a question",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    tool_use_id = ToolUseID("toolu_ask_q_2")
    assistant_message_id = AssistantMessageID("assistant-ask-q-2")
    assistant_chat_message_id = AgentMessageID()

    _, partial, ask_msg, streaming_complete, persistence_msg = _make_ask_user_question_messages(
        tool_use_id, assistant_message_id, assistant_chat_message_id
    )

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [user_message, request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Persistence arrives BEFORE streaming partial (the broken order)
    state = convert_agent_messages_to_task_update(
        [persistence_msg, partial, ask_msg, streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    tool_use_blocks = [b for b in in_progress.content if isinstance(b, ToolUseBlock)]
    assert len(tool_use_blocks) == 1, (
        f"Expected 1 AskUserQuestion ToolUseBlock, got {len(tool_use_blocks)}. Persistence before partial duplicated the block."
    )
    assert state.pending_user_question is not None


def test_user_question_answer_does_not_create_queued_message() -> None:
    """UserQuestionAnswerMessage should update submitted_question_answers state
    but not create any queued chat messages in the UI."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    question_data = AskUserQuestionData(
        questions=[
            UserQuestion(
                question="What language do you prefer?",
                header="Language",
                options=[
                    QuestionOption(label="Python", description="A versatile language"),
                    QuestionOption(label="Rust", description="A systems language"),
                ],
                multi_select=False,
            )
        ],
        tool_use_id="tool-use-ask-1",
    )

    answer_message = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"What language do you prefer?": "Python"},
        question_data=question_data,
        tool_use_id="tool-use-ask-1",
    )

    state = convert_agent_messages_to_task_update(
        [answer_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # No queued chat messages — the answer is rendered via submittedQuestionAnswers
    assert len(state.queued_chat_messages) == 0
    assert state.pending_user_question is None
    assert "tool-use-ask-1" in state.submitted_question_answers
    assert state.submitted_question_answers["tool-use-ask-1"].answers == {"What language do you prefer?": "Python"}


def test_malformed_ask_user_question_tool_block_does_not_set_pending_user_question() -> None:
    """Regression for the stuck-yellow-state bug: when the agent emits a
    ``mcp__sculptor__ask_user_question`` tool_use whose input fails the MCP
    server's strict validation (e.g. ``multiSelect: 'false'`` as a string),
    the MCP server replies with a JSON-RPC error so the agent can retry.

    The persisted ``ToolUseBlock`` must NOT also get re-coerced into a
    pending question by ``convert_agent_messages_to_task_update`` — that
    would leave the workspace in a yellow ``Waiting for input`` state with
    no panel for the user to answer, since the agent already received the
    error and moved on.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Ask me a question",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    tool_use_id = ToolUseID("toolu_malformed_auq")
    assistant_message_id = AssistantMessageID("assistant-malformed-auq")

    # ``multiSelect: 'false'`` (string) is the canonical agent typo: lenient
    # pydantic coerces it to ``False`` and the call would silently re-pend.
    # Strict validation rejects it, matching what the MCP server does.
    malformed_tool_block = ToolUseBlock(
        id=tool_use_id,
        name="mcp__sculptor__ask_user_question",
        input={
            "questions": [
                {
                    "question": "Pick one",
                    "header": "Header",
                    "options": [{"label": "A", "description": "a"}],
                    "multiSelect": "false",
                }
            ]
        },
    )

    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(malformed_tool_block,),
    )

    state = convert_agent_messages_to_task_update(
        [user_message, persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.pending_user_question is None, (
        "pending_user_question must stay None for a tool_use the MCP server rejected — otherwise the workspace gets stuck in 'Waiting for input'."
    )


def test_user_question_answer_sets_in_progress_user_message_id() -> None:
    """UserQuestionAnswerMessage should immediately set in_progress_user_message_id.

    Regression: in_progress_user_message_id was only set by RequestStartedAgentMessage,
    creating a gap after answering a question where workingUserMessageId was null.
    This caused the ThinkingIndicator to not render even though task.status was RUNNING.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    question_data = AskUserQuestionData(
        questions=[
            UserQuestion(
                question="What language do you prefer?",
                header="Language",
                options=[
                    QuestionOption(label="Python", description="A versatile language"),
                    QuestionOption(label="Rust", description="A systems language"),
                ],
                multi_select=False,
            )
        ],
        tool_use_id="tool-use-ask-1",
    )

    answer_message = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"What language do you prefer?": "Python"},
        question_data=question_data,
        tool_use_id="tool-use-ask-1",
    )

    state = convert_agent_messages_to_task_update(
        [answer_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # in_progress_user_message_id should be set immediately, not wait for RequestStartedAgentMessage
    assert state.in_progress_user_message_id == answer_message.message_id


def _make_simple_question_data(question_text: str, tool_use_id: str) -> AskUserQuestionData:
    return AskUserQuestionData(
        questions=[
            UserQuestion(
                question=question_text,
                header="Header",
                options=[
                    QuestionOption(label="A", description="first"),
                    QuestionOption(label="B", description="second"),
                ],
                multi_select=False,
            )
        ],
        tool_use_id=tool_use_id,
    )


def test_answering_one_of_two_pending_questions_surfaces_the_other() -> None:
    """Two questions can pend concurrently (e.g. two subagents each asking
    mid-turn). Answering the visible one must surface the other instead of
    forgetting it — the frozen-question half of the subagent AUQ bug.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    question_a = _make_simple_question_data("Question A?", "tool-use-ask-a")
    question_b = _make_simple_question_data("Question B?", "tool-use-ask-b")

    state = convert_agent_messages_to_task_update(
        [
            AskUserQuestionAgentMessage(message_id=AgentMessageID(), question_data=question_a),
            AskUserQuestionAgentMessage(message_id=AgentMessageID(), question_data=question_b),
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    # The most recent question is the visible one; both are tracked.
    assert state.pending_user_question is not None
    assert state.pending_user_question.tool_use_id == "tool-use-ask-b"
    assert [q.tool_use_id for q in state.pending_user_questions] == ["tool-use-ask-a", "tool-use-ask-b"]

    answer_b = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"Question B?": "A"},
        question_data=question_b,
        tool_use_id="tool-use-ask-b",
    )
    state = convert_agent_messages_to_task_update(
        [answer_b],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.pending_user_question is not None
    assert state.pending_user_question.tool_use_id == "tool-use-ask-a"

    answer_a = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"Question A?": "B"},
        question_data=question_a,
        tool_use_id="tool-use-ask-a",
    )
    state = convert_agent_messages_to_task_update(
        [answer_a],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.pending_user_question is None
    assert state.pending_user_questions == ()


def test_request_started_sets_current_request_id_without_queued_message() -> None:
    """RequestStartedAgentMessage should set current_request_id even when there is
    no matching queued message (e.g. for UserQuestionAnswerMessage which doesn't
    produce a queued chat message). This ensures RequestSuccessAgentMessage can
    finalize the assistant response."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    answer_message_id = AgentMessageID()
    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-answer-reply")

    # RequestStarted for a message that has no queued chat representation
    request_started = RequestStartedAgentMessage(request_id=answer_message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Great choice! Python it is."),),
    )

    state = convert_agent_messages_to_task_update(
        [request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # The assistant message should be in progress
    assert state.in_progress_chat_message is not None
    assert state.in_progress_user_message_id == answer_message_id

    # Now finalize with RequestSuccess — this should work because current_request_id was set
    request_success = _make_request_success(request_id=answer_message_id)

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The assistant message should be finalized (completed)
    assert len(state.chat_messages) == 1
    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None


def test_convert_agent_messages_to_task_update_clears_state_on_request_stopped() -> None:
    """Regression test: RequestStoppedAgentMessage must finalize the in-progress message.

    When the agent is stopped (e.g., user clicks Stop), a RequestStoppedAgentMessage is
    emitted. This must clear in_progress_chat_message and in_progress_user_message_id,
    otherwise the frontend will keep showing the "Thinking..." indicator and Stop button
    even though the agent has finished.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-stopped")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Let me help you with"),),
    )

    state = convert_agent_messages_to_task_update(
        [request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Agent is mid-response
    assert state.in_progress_chat_message is not None
    assert state.in_progress_user_message_id == user_message.message_id

    # Agent is stopped
    serialized_error = _make_serialized_exception("Agent was stopped by user")
    request_stopped = RequestStoppedAgentMessage(
        request_id=user_message.message_id,
        error=serialized_error,
    )

    state = convert_agent_messages_to_task_update(
        [request_stopped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # in_progress state must be cleared so the frontend stops showing "Thinking..."
    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None


def test_full_response_block_after_streaming_does_not_duplicate_content() -> None:
    """The full ResponseBlockAgentMessage after streaming must not duplicate content.

    After streaming completes, the Claude Code SDK emits the full assistant message
    as a non-streaming ResponseBlockAgentMessage. Since these blocks were already
    placed by partials, the non-streaming handler must not append them again.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id = ToolUseID("tool-use-dup-1")
    assistant_message_id = AssistantMessageID("assistant-dup")
    assistant_chat_message_id = AgentMessageID()

    # Step 1: Partial with text + tool use (streaming starts)
    partial = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Let me check."),
            ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "git log --oneline -3"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.is_streaming_active is True
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 2

    # Step 2: Streaming completes
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    state = convert_agent_messages_to_task_update(
        [streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is False
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # Content should still be [Text, ToolUse] — unchanged
    assert len(in_progress.content) == 2

    # Step 3: Full assistant ResponseBlockAgentMessage (non-streaming path)
    # This is the complete assistant message that the SDK emits after streaming ends.
    # It contains the same text + tool_use blocks that were already placed by partials.
    full_assistant_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Let me check."),
            ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "git log --oneline -3"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [full_assistant_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # BUG: Without the fix, this will be 4 (duplicated text + duplicated tool_use).
    # With the fix, it should remain 2 (the partials already placed these blocks).
    assert len(in_progress.content) == 2, (
        f"Expected 2 content blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}. The full ResponseBlockAgentMessage after streaming duplicated content."
    )

    # Step 4: Tool result arrives (non-streaming path)
    tool_result_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="Bash",
                invocation_string="git log --oneline -3",
                content=GenericToolContent(text="abc123 Initial commit"),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [tool_result_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # Should be [TextBlock, ToolResultBlock] — tool use replaced by result
    assert len(in_progress.content) == 2, (
        f"Expected 2 content blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}"
    )
    first_block = in_progress.content[0]
    assert isinstance(first_block, TextBlock)
    assert first_block.text == "Let me check."
    second_block = in_progress.content[1]
    assert isinstance(second_block, ToolResultBlock)
    tool_content = second_block.content
    assert isinstance(tool_content, GenericToolContent)
    assert tool_content.text == "abc123 Initial commit"

    # Verify there are no stale ToolUseBlocks remaining
    tool_use_blocks = [b for b in in_progress.content if isinstance(b, ToolUseBlock)]
    assert len(tool_use_blocks) == 0, (
        f"Found {len(tool_use_blocks)} stale ToolUseBlock(s) — these would show as 'Running command...' in the UI"
    )


def test_full_response_block_after_streaming_with_multiple_tools_does_not_duplicate() -> None:
    """Same bug with multiple tool calls in a single assistant message.

    This exercises the grouped tool section path in the UI where N completed
    tools would each show a stale 'Running command...' counterpart.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id_1 = ToolUseID("tool-multi-1")
    tool_use_id_2 = ToolUseID("tool-multi-2")
    tool_use_id_3 = ToolUseID("tool-multi-3")
    assistant_message_id = AssistantMessageID("assistant-multi")
    assistant_chat_message_id = AgentMessageID()

    # Step 1: Partial with text + 3 parallel tool uses
    partial = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Running three commands in parallel."),
            ToolUseBlock(id=tool_use_id_1, name="Bash", input={"command": "echo 1"}),
            ToolUseBlock(id=tool_use_id_2, name="Bash", input={"command": "echo 2"}),
            ToolUseBlock(id=tool_use_id_3, name="Bash", input={"command": "echo 3"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.is_streaming_active is True
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 4

    # Step 2: Streaming completes
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    state = convert_agent_messages_to_task_update(
        [streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is False

    # Step 3: Full assistant message (non-streaming, same content as partial)
    full_assistant_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Running three commands in parallel."),
            ToolUseBlock(id=tool_use_id_1, name="Bash", input={"command": "echo 1"}),
            ToolUseBlock(id=tool_use_id_2, name="Bash", input={"command": "echo 2"}),
            ToolUseBlock(id=tool_use_id_3, name="Bash", input={"command": "echo 3"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [full_assistant_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # Should still be 4 blocks, not 8
    assert len(in_progress.content) == 4, (
        f"Expected 4 content blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}. The full ResponseBlockAgentMessage after streaming duplicated content."
    )

    # Step 4: Tool results for all three
    tool_results_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id_1,
                tool_name="Bash",
                invocation_string="echo 1",
                content=GenericToolContent(text="1"),
            ),
            ToolResultBlock(
                tool_use_id=tool_use_id_2,
                tool_name="Bash",
                invocation_string="echo 2",
                content=GenericToolContent(text="2"),
            ),
            ToolResultBlock(
                tool_use_id=tool_use_id_3,
                tool_name="Bash",
                invocation_string="echo 3",
                content=GenericToolContent(text="3"),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [tool_results_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None

    # Should be [TextBlock, ToolResultBlock, ToolResultBlock, ToolResultBlock]
    assert len(in_progress.content) == 4, (
        f"Expected 4 content blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}"
    )

    # Verify no stale ToolUseBlocks remain
    tool_use_blocks = [b for b in in_progress.content if isinstance(b, ToolUseBlock)]
    assert len(tool_use_blocks) == 0, (
        f"Found {len(tool_use_blocks)} stale ToolUseBlock(s) — these would show as 'Running command...' in the UI"
    )

    # Verify all three tool results are present
    tool_result_blocks = [b for b in in_progress.content if isinstance(b, ToolResultBlock)]
    assert len(tool_result_blocks) == 3


def test_streaming_state_reset_after_stop_prevents_staircase() -> None:
    """After stopping an agent mid-stream, the next response's partials must replace each other.

    Without the fix, the stale streaming_start_index causes each partial to be appended
    to the message content rather than replacing the previous partial, creating the
    staircase rendering effect.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    request_id_1 = AgentMessageID()
    assistant_msg_id_1 = AssistantMessageID("assistant-turn-1")
    chat_msg_id_1 = AgentMessageID()
    tool_use_id = ToolUseID("tool-1")

    # === Turn 1: Agent streams text + tool, completes normally ===

    # RequestStarted for turn 1
    state = convert_agent_messages_to_task_update(
        [RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id_1)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Partial with text + tool use
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_1,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_1,
                content=(
                    TextBlock(text="Checking..."),
                    ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "ls"}),
                ),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    assert state.streaming_start_index == 0

    # Streaming segment completes normally
    state = convert_agent_messages_to_task_update(
        [StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is False
    # streaming_start_index advanced past the committed content
    assert state.streaming_start_index == 2

    # Tool result arrives
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_msg_id_1,
                message_id=AgentMessageID(),
                content=(
                    ToolResultBlock(
                        tool_use_id=tool_use_id,
                        tool_name="Bash",
                        invocation_string="ls",
                        content=GenericToolContent(text="file1.py file2.py"),
                    ),
                ),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # === Turn 1 continued: Agent streams more text, then user clicks Stop ===
    assistant_msg_id_2 = AssistantMessageID("assistant-turn-1-continued")

    # New streaming segment starts (after tool result)
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_2,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_1,
                content=(TextBlock(text="Now I'll look at"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    # streaming_start_index should be past the committed content (text + tool_result = 2 blocks)
    assert state.streaming_start_index == 2

    # User clicks Stop! No StreamingMessageCompleteAgentMessage arrives.
    stopped_error = _make_serialized_exception("Agent stopped by user")
    state = convert_agent_messages_to_task_update(
        [
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=request_id_1,
                error=stopped_error,
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The key assertions: streaming state must be fully reset after stop
    assert state.is_streaming_active is False, "is_streaming_active must be False after RequestStoppedAgentMessage"
    assert state.streaming_start_index == 0, (
        f"streaming_start_index must be 0 after stop (was {state.streaming_start_index})"
    )
    assert state.in_progress_chat_message is None, "in_progress message should be finalized"

    # === Turn 2: New user message, agent streams new response ===
    request_id_2 = AgentMessageID()
    assistant_msg_id_3 = AssistantMessageID("assistant-turn-2")
    chat_msg_id_2 = AgentMessageID()

    state = convert_agent_messages_to_task_update(
        [RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id_2)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # First partial of new response
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_3,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_2,
                content=(TextBlock(text="Let"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 1, (
        f"First partial should produce 1 content block, got {len(in_progress.content)}: {[type(b).__name__ for b in in_progress.content]}"
    )
    first_block = in_progress.content[0]
    assert isinstance(first_block, TextBlock)
    assert first_block.text == "Let"

    # Second partial — should REPLACE, not append
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_3,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_2,
                content=(TextBlock(text="Let me re-read"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # BUG: Without the fix, this would be 2 (staircase: ["Let", "Let me re-read"])
    assert len(in_progress.content) == 1, (
        f"Second partial should replace the first, producing 1 content block. Got {len(in_progress.content)} blocks (staircase bug): {[b.text if isinstance(b, TextBlock) else type(b).__name__ for b in in_progress.content]}"
    )
    second_block = in_progress.content[0]
    assert isinstance(second_block, TextBlock)
    assert second_block.text == "Let me re-read"

    # Third partial — should still be a single block
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_3,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_2,
                content=(TextBlock(text="Let me re-read the current state"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 1, (
        f"Third partial should still be 1 block. Got {len(in_progress.content)} blocks: {[b.text if isinstance(b, TextBlock) else type(b).__name__ for b in in_progress.content]}"
    )
    third_block = in_progress.content[0]
    assert isinstance(third_block, TextBlock)
    assert third_block.text == "Let me re-read the current state"


def test_streaming_state_reset_after_stop_on_first_streaming_segment() -> None:
    """Even when stop occurs during the first streaming segment, state should be clean.

    This is a simpler case where streaming_start_index is 0, so the staircase
    doesn't manifest. But we verify the state is still properly reset.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    request_id = AgentMessageID()
    assistant_msg_id = AssistantMessageID("assistant-simple")
    chat_msg_id = AgentMessageID()

    state = convert_agent_messages_to_task_update(
        [RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Start streaming
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id,
                content=(TextBlock(text="Hello"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True

    # Stop
    stopped_error = _make_serialized_exception("Agent stopped by user")
    state = convert_agent_messages_to_task_update(
        [
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=request_id,
                error=stopped_error,
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is False
    assert state.streaming_start_index == 0
    assert state.in_progress_chat_message is None


def test_convert_agent_messages_to_task_update_clears_state_on_request_skipped() -> None:
    """Regression test: RequestSkippedAgentMessage must clear in_progress_user_message_id.

    When a queued message is removed before processing, a RequestSkippedAgentMessage is
    emitted. This must properly clear the request tracking state.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_user_message_id == user_message.message_id

    # Request is skipped (message was removed from queue)
    request_skipped = RequestSkippedAgentMessage(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [request_skipped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_user_message_id is None


def test_answered_plan_approval_not_re_shown_after_ephemeral_replay() -> None:
    """Regression test: an already-answered plan approval must not reappear.

    After a restart, the agent runner resumes the Claude CLI session. If the
    CLI re-emits a historical assistant response containing an ExitPlanMode
    ToolUseBlock, the output processor emits a NEW ephemeral
    AskUserQuestionAgentMessage for the same tool_use_id. When this ephemeral
    message is processed by convert_agent_messages_to_task_update, it must NOT
    override the fact that the user already answered (via a persisted
    UserQuestionAnswerMessage).

    Scenario:
    1. Persistent ResponseBlockAgentMessage with ExitPlanMode ToolUseBlock
    2. Persistent UserQuestionAnswerMessage (user approved the plan)
    3. Ephemeral AskUserQuestionAgentMessage re-emitted after restart
    Expected: pending_user_question is None (already answered)
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id = ToolUseID("toolu_exit_plan_1")
    assistant_message_id = AssistantMessageID("assistant-plan-1")
    assistant_chat_message_id = AgentMessageID()

    # Step 1: Persistent ResponseBlockAgentMessage with ExitPlanMode ToolUseBlock
    exit_plan_tool_block = ToolUseBlock(
        id=tool_use_id,
        name="ExitPlanMode",
        input={},
    )
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is my plan."), exit_plan_tool_block),
    )

    # Step 2: Persistent UserQuestionAnswerMessage (user approved the plan)
    plan_question_data = make_plan_approval_question(str(tool_use_id))
    answer_msg = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"Planning complete. How would you like to proceed?": "Approve plan"},
        question_data=plan_question_data,
        tool_use_id=str(tool_use_id),
    )

    # Step 3: Ephemeral AskUserQuestionAgentMessage re-emitted after restart
    # (output processor calls _maybe_handle_exit_plan_mode on the replayed response)
    ephemeral_ask_msg = AskUserQuestionAgentMessage(
        message_id=AgentMessageID(),
        question_data=make_plan_approval_question(str(tool_use_id)),
    )

    # Process all messages in order (simulating what happens on frontend connect
    # after restart: persistent messages from DB + ephemeral messages from
    # _messages_by_task_id)
    state = convert_agent_messages_to_task_update(
        [persistence_msg, answer_msg, ephemeral_ask_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # The answer was already submitted, so pending_user_question must be None
    assert state.pending_user_question is None, (
        "pending_user_question should be None because the user already answered."
        + " The ephemeral AskUserQuestionAgentMessage must not override the answer."
    )
    assert str(tool_use_id) in state.submitted_question_answers


def test_user_question_answer_before_request_success_produces_separate_messages() -> None:
    """Regression test: UserQuestionAnswerMessage arriving before RequestSuccessAgentMessage
    must not merge the follow-up assistant response into the first assistant message.

    Race condition: The UserQuestionAnswerMessage (from the HTTP answer endpoint) can
    arrive via the streaming queue before the first invocation's RequestSuccessAgentMessage
    (from the agent output queue). Without the fix, UserQuestionAnswerMessage overwrites
    current_request_id, causing the subsequent RequestSuccessAgentMessage to be silently
    ignored (request_id mismatch). The in-progress message stays open, and the second
    invocation's response blocks are appended to the first message.

    Expected: 2 completed assistant messages (one with AskUserQuestion tool, one with follow-up text).
    Bug: 1 combined assistant message containing both.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="fake_claude:ask_user_question ...",
        model_name=LLMModel.FAKE_CLAUDE,
    )
    tool_use_id = ToolUseID("toolu_ask_race")
    assistant_message_id_1 = AssistantMessageID("assistant-ask-race-1")
    assistant_chat_message_id_1 = AgentMessageID()

    question_data, partial, ask_msg, streaming_complete, persistence_msg = _make_ask_user_question_messages(
        tool_use_id, assistant_message_id_1, assistant_chat_message_id_1
    )

    # === First invocation: AskUserQuestion ===
    request_started_1 = RequestStartedAgentMessage(request_id=user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [user_message, request_started_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Streaming + persistence for first invocation
    state = convert_agent_messages_to_task_update(
        [partial, ask_msg, streaming_complete, persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.in_progress_chat_message is not None, "First assistant message should be in progress"

    # === RACE: UserQuestionAnswerMessage arrives BEFORE RequestSuccess from first invocation ===
    answer_message = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"What language?": "Python"},
        question_data=question_data,
        tool_use_id=str(tool_use_id),
    )
    state = convert_agent_messages_to_task_update(
        [answer_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The fix: in_progress should be flushed by UserQuestionAnswerMessage
    assert state.in_progress_chat_message is None, (
        "in_progress_chat_message should be flushed when UserQuestionAnswerMessage arrives"
    )
    # First assistant message should now be completed
    first_assistant_messages = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(first_assistant_messages) == 1, "First assistant message should be completed"

    # === RequestSuccess from first invocation arrives (late) ===
    request_success_1 = _make_request_success(request_id=user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [request_success_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # === Second invocation: follow-up response ===
    assistant_message_id_2 = AssistantMessageID("assistant-follow-up")
    assistant_chat_message_id_2 = AgentMessageID()
    request_started_2 = RequestStartedAgentMessage(request_id=answer_message.message_id)
    follow_up_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id_2,
        message_id=assistant_chat_message_id_2,
        content=(TextBlock(text="[FakeClaude] Task completed."),),
    )
    request_success_2 = _make_request_success(request_id=answer_message.message_id)

    state = convert_agent_messages_to_task_update(
        [request_started_2, follow_up_response, request_success_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # === Verify: Two separate assistant messages across all batches ===
    # completed_by_id accumulates messages across all batches, so use it to verify
    # that we have two distinct assistant messages
    all_assistant_messages = [m for m in completed_by_id.values() if m.role == ChatMessageRole.ASSISTANT]
    assert len(all_assistant_messages) == 2, (
        f"Expected 2 separate assistant messages, got {len(all_assistant_messages)}. "
        + "UserQuestionAnswerMessage arriving before RequestSuccess merged the messages."
    )

    # One message should have the AskUserQuestion tool block
    ask_messages = [m for m in all_assistant_messages if any(isinstance(b, ToolUseBlock) for b in m.content)]
    assert len(ask_messages) == 1, "Exactly one message should have the AskUserQuestion tool block"
    tool_blocks = [b for b in ask_messages[0].content if isinstance(b, ToolUseBlock)]
    assert tool_blocks[0].name == "AskUserQuestion"

    # The other message should have the follow-up text
    follow_up_messages = [
        m
        for m in all_assistant_messages
        if any(isinstance(b, TextBlock) and "[FakeClaude] Task completed." in b.text for b in m.content)
    ]
    assert len(follow_up_messages) == 1, "Exactly one message should have the follow-up text"


def test_ask_user_question_msg_2_partial_with_reused_first_response_message_id_does_not_overwrite() -> None:
    """Regression for SCU-1151 follow-up: when MCP-based AUQ keeps a single CLI
    process alive across the user wait, ``_first_response_message_id`` never
    resets between msg_1 (the AUQ turn) and msg_2 (the follow-up text turn).

    After RequestSuccess flushes the AUQ in_progress(id=A) to completed[A] and
    the synthetic tool_result ResponseBlock creates a fresh in_progress(id=X),
    msg_2's partial arrives carrying ``first_response_message_id=A`` (the same
    ID msg_1 used).  The PartialResponseBlockAgentMessage flush condition must
    NOT fire in this case — flushing would create a new in_progress(id=A)
    whose later flush would overwrite the completed msg_1 in
    ``completed_message_by_id``, silently dropping the AUQ tool block.

    Expected: 3 distinct ChatMessages (user, msg_1 with tool_use, msg_2 with text).
    Bug: 2 messages (user + msg_2 with text — msg_1 overwritten).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="fake_claude:ask_user_question ...",
        model_name=LLMModel.FAKE_CLAUDE,
    )
    tool_use_id = ToolUseID("toolu_auq_reused_id")
    msg_1_assistant_message_id = AssistantMessageID("assistant-msg-1")
    msg_1_chat_message_id = AgentMessageID()  # this is "A" — _first_response_message_id

    # === Request 1: msg_1 (AUQ tool_use) ===
    request_started_1 = RequestStartedAgentMessage(request_id=user_message.message_id)
    _, partial_msg_1, ask_msg, streaming_complete_1, persistence_msg_1 = _make_ask_user_question_messages(
        tool_use_id, msg_1_assistant_message_id, msg_1_chat_message_id
    )
    request_success_1 = _make_request_success(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [
            user_message,
            request_started_1,
            partial_msg_1,
            ask_msg,
            streaming_complete_1,
            persistence_msg_1,
            request_success_1,
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    # msg_1 should be flushed into completed under its assistant_chat_message_id (A).
    assert msg_1_chat_message_id in completed_by_id
    msg_1_completed = completed_by_id[msg_1_chat_message_id]
    assert any(isinstance(b, ToolUseBlock) and b.id == tool_use_id for b in msg_1_completed.content), (
        "msg_1 must contain the AUQ ToolUseBlock"
    )

    # === User answers ===
    answer_message = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"What language?": "Python"},
        question_data=ask_msg.question_data,
        tool_use_id=str(tool_use_id),
    )

    # === Synthetic tool_result ResponseBlock — emitted by _parse_tool_result_response.
    # It uses a fresh message_id (X), assistant_message_id reuses msg_1's current_turn_id
    # (so dedup against streamed_assistant_message_ids does NOT match — RequestSuccess
    # already cleared it via streaming.reset()).
    tool_result_message_id = AgentMessageID()  # this is "X"
    tool_result_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=msg_1_assistant_message_id,
        message_id=tool_result_message_id,
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="AskUserQuestion",
                invocation_string="ask_user_question",
                content=GenericToolContent(text="Python"),
            ),
        ),
    )

    # === Request 2: msg_2 (follow-up text). Its partial carries the SAME
    # first_response_message_id as msg_1 because _first_response_message_id
    # never resets across the MCP wait in the single-CLI-process AUQ flow.
    request_started_2 = RequestStartedAgentMessage(request_id=answer_message.message_id)
    msg_2_assistant_message_id = AssistantMessageID("assistant-msg-2")
    msg_2_text = "[FakeClaude] Task completed."
    partial_msg_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=msg_2_assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=msg_1_chat_message_id,  # reuses A
        content=(TextBlock(text=msg_2_text),),
    )
    streaming_complete_2 = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())
    persistence_msg_2 = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=msg_2_assistant_message_id,
        message_id=AgentMessageID(),  # fresh ID — _used_first_response_id was True
        content=(TextBlock(text=msg_2_text),),
    )
    request_success_2 = _make_request_success(request_id=answer_message.message_id)

    state = convert_agent_messages_to_task_update(
        [
            answer_message,
            tool_result_response,
            request_started_2,
            partial_msg_2,
            streaming_complete_2,
            persistence_msg_2,
            request_success_2,
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # msg_1 (with the AUQ tool_use) must still be intact in completed_message_by_id —
    # it must NOT have been overwritten by msg_2's partial reusing its ID.
    assert msg_1_chat_message_id in completed_by_id, "msg_1 must remain in completed_message_by_id"
    msg_1_after = completed_by_id[msg_1_chat_message_id]
    msg_1_tool_uses = [b for b in msg_1_after.content if isinstance(b, ToolUseBlock)]
    assert len(msg_1_tool_uses) == 1, (
        "msg_1 must still contain its AUQ ToolUseBlock — msg_2's partial reusing first_response_message_id=A must not overwrite it"
    )
    assert msg_1_tool_uses[0].id == tool_use_id

    # We should have exactly 2 assistant messages total (msg_1 + msg_2), distinct IDs.
    all_assistant_messages = [m for m in completed_by_id.values() if m.role == ChatMessageRole.ASSISTANT]
    text_only_messages = [
        m for m in all_assistant_messages if any(isinstance(b, TextBlock) and msg_2_text in b.text for b in m.content)
    ]
    assert len(text_only_messages) >= 1, "msg_2's text must appear somewhere in completed assistant messages"


def test_write_tool_result_replaces_tool_use_when_exit_plan_mode_in_same_message() -> None:
    """Regression test: Write tool_use must be replaced by its tool_result even when
    ExitPlanMode is in the same assistant message.

    This exercises the exact scenario where the agent writes a plan file and calls
    ExitPlanMode in the same turn. The output_processor intercepts ExitPlanMode at
    content_block_stop and emits PlanModeAgentMessage + AskUserQuestionAgentMessage
    before the final partial. The Write tool_result arrives later and must replace
    the Write ToolUseBlock so the UI shows "Created file" instead of "Creating file...".
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    write_tool_use_id = ToolUseID("write-plan-1")
    exit_plan_tool_use_id = ToolUseID("exit-plan-1")
    assistant_message_id = AssistantMessageID("assistant-plan")
    assistant_chat_message_id = AgentMessageID()

    request_id = AgentMessageID()

    write_tool_block = ToolUseBlock(
        id=write_tool_use_id,
        name="Write",
        input={"file_path": "plan.md", "content": "# Plan\nStep 1: Do X\nStep 2: Do Y"},
    )
    exit_plan_tool_block = ToolUseBlock(
        id=exit_plan_tool_use_id,
        name="ExitPlanMode",
        input={},
    )

    # --- Step 0: Request starts ---
    request_started = RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id)

    state = convert_agent_messages_to_task_update(
        [request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # --- Step 1: Streaming partials (text only, then text + Write, then ExitPlanMode interception) ---

    # Partial 1: text only
    partial_text = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is my plan."),),
    )

    state = convert_agent_messages_to_task_update(
        [partial_text],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 1

    # Partial 2: text + Write tool_use
    partial_write = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is my plan."), write_tool_block),
    )

    state = convert_agent_messages_to_task_update(
        [partial_write],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 2

    # --- Step 2: ExitPlanMode interception (PlanMode + AskUserQuestion emitted BEFORE final partial) ---
    plan_mode_msg = PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=False)
    ask_question_msg = AskUserQuestionAgentMessage(
        message_id=AgentMessageID(),
        question_data=make_plan_approval_question(str(exit_plan_tool_use_id)),
    )

    # Partial 3: text + Write + ExitPlanMode (emitted AFTER interception messages)
    partial_exit = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is my plan."), write_tool_block, exit_plan_tool_block),
    )

    state = convert_agent_messages_to_task_update(
        [plan_mode_msg, ask_question_msg, partial_exit],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_in_plan_mode is False
    assert state.pending_user_question is not None
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 3  # [TextBlock, ToolUseBlock(Write), ToolUseBlock(ExitPlanMode)]

    # --- Step 3: Streaming completes ---
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    state = convert_agent_messages_to_task_update(
        [streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is False
    assert state.in_progress_message_was_streamed is True

    # --- Step 4: Persistence copy (full assistant message, same content as streaming) ---
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is my plan."), write_tool_block, exit_plan_tool_block),
    )

    state = convert_agent_messages_to_task_update(
        [persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # Content should still be 3 blocks (persistence copy doesn't duplicate)
    assert len(in_progress.content) == 3, (
        f"Expected 3 blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}"
    )

    # --- Step 5: Write tool result arrives ---
    write_tool_result = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=write_tool_use_id,
                tool_name="Write",
                invocation_string="plan.md",
                content=GenericToolContent(text="File written successfully."),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [write_tool_result],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 3, (
        f"Expected 3 blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}"
    )

    # The Write ToolUseBlock at index 1 MUST be replaced by ToolResultBlock
    assert isinstance(in_progress.content[0], TextBlock)
    write_block = in_progress.content[1]
    assert isinstance(write_block, ToolResultBlock), (
        f"Expected ToolResultBlock at index 1 but got {type(write_block).__name__}. The Write tool_use was not replaced by its tool_result."
    )
    assert write_block.tool_use_id == str(write_tool_use_id)

    # ExitPlanMode ToolUseBlock at index 2 must remain as ToolUseBlock (not replaced)
    exit_block = in_progress.content[2]
    assert isinstance(exit_block, ToolUseBlock), (
        f"Expected ToolUseBlock at index 2 but got {type(exit_block).__name__}. ExitPlanMode ToolUseBlock should not be replaced."
    )
    assert exit_block.name == "ExitPlanMode"

    # --- Step 6: ExitPlanMode tool result arrives (should be skipped) ---
    exit_plan_tool_result = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=exit_plan_tool_use_id,
                tool_name="ExitPlanMode",
                invocation_string="",
                content=GenericToolContent(text="Tool ExitPlanMode executed."),
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [exit_plan_tool_result],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # Still 3 blocks — ExitPlanMode result was skipped
    assert len(in_progress.content) == 3
    # Write is still ToolResultBlock
    assert isinstance(in_progress.content[1], ToolResultBlock)
    # ExitPlanMode is still ToolUseBlock (not replaced)
    assert isinstance(in_progress.content[2], ToolUseBlock)

    # --- Step 7: RequestSuccess finalizes the message ---
    request_success = RequestSuccessAgentMessage.model_construct(request_id=request_id)

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # After finalization, the message should be completed
    assert state.in_progress_chat_message is None
    assert len(state.chat_messages) == 1
    completed = state.chat_messages[0]
    assert isinstance(completed.content[1], ToolResultBlock), (
        f"Expected ToolResultBlock at index 1 in completed message but got {type(completed.content[1]).__name__}. The Write tool result was lost during finalization."
    )


def test_write_tool_result_replaces_tool_use_with_enter_plan_mode_preceding() -> None:
    """Regression test: Write tool_use must be replaced even when an EnterPlanMode streaming
    cycle preceded the Write+ExitPlanMode streaming cycle.

    Models the exact multi_step(enter_plan_mode, parallel_tools(Write, ExitPlanMode)) scenario.
    Step 1 (EnterPlanMode) creates a streaming cycle that adds blocks to in_progress_chat_message.
    Step 2 (Write+ExitPlanMode) creates a second streaming cycle at a higher streaming_start_index.
    The Write tool_result must still replace the Write ToolUseBlock at its correct index.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # IDs for the two streaming cycles
    first_response_id = AgentMessageID()  # shared across both cycles (_first_response_message_id)
    enter_plan_tool_use_id = ToolUseID("enter-plan-1")
    write_tool_use_id = ToolUseID("write-plan-1")
    exit_plan_tool_use_id = ToolUseID("exit-plan-1")
    assistant_msg_id_step1 = AssistantMessageID("assistant-step1")
    assistant_msg_id_step2 = AssistantMessageID("assistant-step2")
    request_id = AgentMessageID()

    enter_plan_tool_block = ToolUseBlock(
        id=enter_plan_tool_use_id,
        name="EnterPlanMode",
        input={},
    )
    write_tool_block = ToolUseBlock(
        id=write_tool_use_id,
        name="Write",
        input={"file_path": "plan.md", "content": "# Plan\nStep 1: Do X"},
    )
    exit_plan_tool_block = ToolUseBlock(
        id=exit_plan_tool_use_id,
        name="ExitPlanMode",
        input={},
    )

    # --- Request starts ---
    state = convert_agent_messages_to_task_update(
        [RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # === STEP 1: EnterPlanMode streaming cycle ===

    # M1: Partial with text
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_step1,
                message_id=AgentMessageID(),
                first_response_message_id=first_response_id,
                content=(TextBlock(text="Let me explore the codebase."),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    assert state.streaming_start_index == 0

    # M2: PlanModeAgentMessage (interception at EnterPlanMode content_block_stop)
    # M3: Partial with text + EnterPlanMode
    state = convert_agent_messages_to_task_update(
        [
            PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=True),
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_step1,
                message_id=AgentMessageID(),
                first_response_message_id=first_response_id,
                content=(TextBlock(text="Let me explore the codebase."), enter_plan_tool_block),
            ),
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_in_plan_mode is True
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 2

    # M4: StreamingMessageComplete (Step 1 ends)
    state = convert_agent_messages_to_task_update(
        [StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is False
    assert state.streaming_start_index == 2  # 2 blocks from Step 1

    # M5: Persistence message for Step 1 (uses first_response_id as message_id)
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_msg_id_step1,
                message_id=first_response_id,
                content=(TextBlock(text="Let me explore the codebase."), enter_plan_tool_block),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    # Content unchanged (persistence is deduplicated)
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 2

    # === STEP 2: Write + ExitPlanMode streaming cycle ===

    # M6: Partial with text (new streaming cycle, same first_response_id)
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_step2,
                message_id=AgentMessageID(),
                first_response_message_id=first_response_id,
                content=(TextBlock(text="Here is my plan."),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    assert state.streaming_start_index == 2
    # Step 1 blocks preserved, Step 2 text appended
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 3

    # M7: Partial with text + Write (Write content_block_stop)
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_step2,
                message_id=AgentMessageID(),
                first_response_message_id=first_response_id,
                content=(TextBlock(text="Here is my plan."), write_tool_block),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 4

    # M8, M9, M10: ExitPlanMode interception + final partial
    state = convert_agent_messages_to_task_update(
        [
            PlanModeAgentMessage(message_id=AgentMessageID(), is_in_plan_mode=False),
            AskUserQuestionAgentMessage(
                message_id=AgentMessageID(),
                question_data=make_plan_approval_question(str(exit_plan_tool_use_id)),
            ),
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_step2,
                message_id=AgentMessageID(),
                first_response_message_id=first_response_id,
                content=(TextBlock(text="Here is my plan."), write_tool_block, exit_plan_tool_block),
            ),
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_in_plan_mode is False
    assert state.pending_user_question is not None
    # 5 blocks: [TextBlock(Step1), ToolUseBlock(EnterPlanMode), TextBlock(Step2), ToolUseBlock(Write), ToolUseBlock(ExitPlanMode)]
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 5

    # M11: StreamingMessageComplete (Step 2 ends)
    state = convert_agent_messages_to_task_update(
        [StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is False
    assert state.streaming_start_index == 5

    # M12: Persistence message for Step 2 (new message_id, different from first_response_id)
    step2_persistence_id = AgentMessageID()
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_msg_id_step2,
                message_id=step2_persistence_id,
                content=(TextBlock(text="Here is my plan."), write_tool_block, exit_plan_tool_block),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    # Content unchanged (persistence is deduplicated via in_progress_message_was_streamed)
    assert state.in_progress_chat_message is not None
    assert len(state.in_progress_chat_message.content) == 5

    # M13: Write tool result
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_msg_id_step2,
                message_id=AgentMessageID(),
                content=(
                    ToolResultBlock(
                        tool_use_id=write_tool_use_id,
                        tool_name="Write",
                        invocation_string="plan.md",
                        content=GenericToolContent(text="File written successfully."),
                    ),
                ),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 5, (
        f"Expected 5 blocks but got {len(in_progress.content)}. Block types: {[type(b).__name__ for b in in_progress.content]}"
    )
    # Index 0: TextBlock (Step 1)
    assert isinstance(in_progress.content[0], TextBlock)
    # Index 1: ToolUseBlock(EnterPlanMode)
    enter_block = in_progress.content[1]
    assert isinstance(enter_block, ToolUseBlock)
    assert enter_block.name == "EnterPlanMode"
    # Index 2: TextBlock (Step 2)
    assert isinstance(in_progress.content[2], TextBlock)
    # Index 3: ToolResultBlock(Write) — MUST be replaced
    write_block = in_progress.content[3]
    assert isinstance(write_block, ToolResultBlock), (
        f"Expected ToolResultBlock at index 3 but got {type(write_block).__name__}. The Write tool_use was not replaced by its tool_result."
    )
    assert write_block.tool_use_id == str(write_tool_use_id)
    # Index 4: ToolUseBlock(ExitPlanMode) — must remain
    exit_block = in_progress.content[4]
    assert isinstance(exit_block, ToolUseBlock)
    assert exit_block.name == "ExitPlanMode"

    # M14: ExitPlanMode tool result (should be skipped)
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_msg_id_step2,
                message_id=AgentMessageID(),
                content=(
                    ToolResultBlock(
                        tool_use_id=exit_plan_tool_use_id,
                        tool_name="ExitPlanMode",
                        invocation_string="",
                        content=GenericToolContent(text="Tool ExitPlanMode executed."),
                    ),
                ),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    # Still 5 blocks, Write is ToolResultBlock, ExitPlanMode is ToolUseBlock
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 5
    assert isinstance(in_progress.content[3], ToolResultBlock)
    assert isinstance(in_progress.content[4], ToolUseBlock)


def test_remove_queued_message_removes_from_queue() -> None:
    """RemoveQueuedMessageAgentMessage removes the target message from queued_chat_messages.

    The message should be removed without affecting any in-progress request state.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_msg1 = ChatInputUserMessage(
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    user_msg2 = ChatInputUserMessage(
        text="Second message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    # Queue both messages, then start processing msg1
    request_started = RequestStartedAgentMessage(request_id=user_msg1.message_id)

    state = convert_agent_messages_to_task_update(
        [user_msg1, user_msg2, request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # msg1 was promoted; msg2 is still queued
    assert len(state.chat_messages) == 1
    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_msg2.message_id
    assert state.in_progress_user_message_id == user_msg1.message_id

    # Remove msg2 from the queue
    remove_msg = RemoveQueuedMessageAgentMessage(
        message_id=AgentMessageID(),
        removed_message_id=user_msg2.message_id,
    )

    state = convert_agent_messages_to_task_update(
        [remove_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Queue should be empty; in-progress state for msg1 is unaffected
    assert len(state.queued_chat_messages) == 0
    assert state.in_progress_user_message_id == user_msg1.message_id


def test_remove_queued_message_does_not_affect_in_progress() -> None:
    """RemoveQueuedMessage lifecycle must NOT clobber the current_request_id.

    The RequestStarted/RequestSuccess pair emitted for a RemoveQueuedMessage
    must be ignored for request tracking purposes because they belong to
    an ephemeral lifecycle, not the real in-progress agent turn.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_msg1 = ChatInputUserMessage(
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    # Queue and promote msg1 — agent starts processing it
    request_started_1 = RequestStartedAgentMessage(request_id=user_msg1.message_id)

    state = convert_agent_messages_to_task_update(
        [user_msg1, request_started_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.in_progress_user_message_id == user_msg1.message_id

    # User queues a second message
    user_msg2 = ChatInputUserMessage(
        text="Second message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_msg2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.queued_chat_messages) == 1

    # RemoveQueuedMessage lifecycle: RequestStarted → RemoveQueuedMessage → RequestSuccess
    remove_request_id = AgentMessageID()
    remove_request_started = RequestStartedAgentMessage(request_id=remove_request_id)
    remove_msg = RemoveQueuedMessageAgentMessage(
        message_id=AgentMessageID(),
        removed_message_id=user_msg2.message_id,
    )
    remove_request_success = _make_request_success(request_id=remove_request_id)

    state = convert_agent_messages_to_task_update(
        [remove_request_started, remove_msg, remove_request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Critical: current_request_id must still track msg1, not the remove lifecycle
    assert state.in_progress_user_message_id == user_msg1.message_id
    assert len(state.queued_chat_messages) == 0

    # Queue a third message — it must appear as queued, not promoted
    user_msg3 = ChatInputUserMessage(
        text="Third message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_msg3],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_msg3.message_id


def test_promotion_after_request_success() -> None:
    """Queued message is promoted when the agent finishes with RequestSuccess.

    After RequestSuccess, the queued message remains in queued_chat_messages
    awaiting the next RequestStarted to promote it.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_msg1 = ChatInputUserMessage(
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    user_msg2 = ChatInputUserMessage(
        text="Second message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    # Queue both, start processing msg1
    request_started_1 = RequestStartedAgentMessage(request_id=user_msg1.message_id)
    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-promo-1")

    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Response to first"),),
    )

    state = convert_agent_messages_to_task_update(
        [user_msg1, user_msg2, request_started_1, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_msg2.message_id

    # Agent finishes msg1
    request_success_1 = _make_request_success(request_id=user_msg1.message_id)

    state = convert_agent_messages_to_task_update(
        [request_success_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # After success: msg2 is still queued, awaiting next RequestStarted
    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_msg2.message_id
    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None

    # Agent picks up msg2
    request_started_2 = RequestStartedAgentMessage(request_id=user_msg2.message_id)

    state = convert_agent_messages_to_task_update(
        [request_started_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # msg2 should be promoted to chat_messages, queue should be empty
    assert len(state.queued_chat_messages) == 0
    assert state.in_progress_user_message_id == user_msg2.message_id
    promoted_ids = [m.id for m in state.chat_messages]
    assert user_msg2.message_id in promoted_ids


def test_promotion_after_request_failure() -> None:
    """Queued message survives agent failure and is promotable on next RequestStarted.

    After a failure the error is finalized and the queued message remains available.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_msg1 = ChatInputUserMessage(
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    user_msg2 = ChatInputUserMessage(
        text="Second message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    request_started_1 = RequestStartedAgentMessage(request_id=user_msg1.message_id)
    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-fail-1")

    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Partial response before failure"),),
    )

    state = convert_agent_messages_to_task_update(
        [user_msg1, user_msg2, request_started_1, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert len(state.queued_chat_messages) == 1

    # Agent fails
    serialized_error = _make_serialized_exception("Agent crashed")
    request_failure = RequestFailureAgentMessage(
        request_id=user_msg1.message_id,
        error=serialized_error,
    )

    state = convert_agent_messages_to_task_update(
        [request_failure],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # In-progress cleared, queued message still available
    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None
    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].id == user_msg2.message_id


def test_request_skipped_for_removed_message() -> None:
    """RequestSkipped handles the case where a removed message reaches the agent.

    When a message is removed and the agent skips it, the state machine
    handles it cleanly.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_msg1 = ChatInputUserMessage(
        text="Message to remove",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_msg1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert len(state.queued_chat_messages) == 1

    # Message is removed from queue
    remove_msg = RemoveQueuedMessageAgentMessage(
        message_id=AgentMessageID(),
        removed_message_id=user_msg1.message_id,
    )

    state = convert_agent_messages_to_task_update(
        [remove_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert len(state.queued_chat_messages) == 0

    # Agent attempts to process the removed message: RequestStarted then RequestSkipped
    request_started = RequestStartedAgentMessage(request_id=user_msg1.message_id)
    request_skipped = RequestSkippedAgentMessage(request_id=user_msg1.message_id)

    state = convert_agent_messages_to_task_update(
        [request_started, request_skipped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # State should be clean: no queued messages, no in-progress, no crash
    assert len(state.queued_chat_messages) == 0
    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None


def test_at_most_one_queued_message_constraint() -> None:
    """State machine handles multiple queued messages gracefully.

    The "at most one" constraint is enforced by the UI, not the backend.
    The state machine should accept multiple queued messages without errors.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_msg1 = ChatInputUserMessage(
        text="First",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    user_msg2 = ChatInputUserMessage(
        text="Second",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    user_msg3 = ChatInputUserMessage(
        text="Third",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_msg1, user_msg2, user_msg3],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # All three should be queued — the state machine doesn't enforce the constraint
    assert len(state.queued_chat_messages) == 3
    assert state.queued_chat_messages[0].id == user_msg1.message_id
    assert state.queued_chat_messages[1].id == user_msg2.message_id
    assert state.queued_chat_messages[2].id == user_msg3.message_id


def test_streaming_state_reset_after_interrupt_success_prevents_staircase() -> None:
    """After interrupting an agent mid-stream, the next response's partials must replace each other.

    When the user clicks "Stop", an InterruptProcessUserMessage kills the agent process.
    Because the _is_interrupted flag is set, the process exit is treated as clean and
    RequestSuccessAgentMessage (not RequestStoppedAgentMessage) is emitted. Without
    resetting streaming state in the RequestSuccessAgentMessage handler, the stale
    is_streaming_active / streaming_start_index cause the next response's partial
    updates to accumulate instead of replacing each other (the "staircase" bug).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    request_id_1 = AgentMessageID()
    assistant_msg_id_1 = AssistantMessageID("assistant-turn-1")
    chat_msg_id_1 = AgentMessageID()
    tool_use_id = ToolUseID("tool-1")

    # === Turn 1: Agent streams text + tool, completes first streaming segment normally ===
    state = convert_agent_messages_to_task_update(
        [RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id_1)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Partial with text + tool use
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_1,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_1,
                content=(
                    TextBlock(text="Checking..."),
                    ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "ls"}),
                ),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    assert state.streaming_start_index == 0

    # First streaming segment completes
    state = convert_agent_messages_to_task_update(
        [StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is False
    assert state.streaming_start_index == 2

    # Tool result arrives
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_msg_id_1,
                message_id=AgentMessageID(),
                content=(
                    ToolResultBlock(
                        tool_use_id=tool_use_id,
                        tool_name="Bash",
                        invocation_string="ls",
                        content=GenericToolContent(text="file1.py"),
                    ),
                ),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # === Turn 1 continued: Agent starts second streaming segment, then user interrupts ===
    assistant_msg_id_2 = AssistantMessageID("assistant-turn-1-continued")

    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_2,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_1,
                content=(TextBlock(text="Now I'll look at"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_streaming_active is True
    assert state.streaming_start_index == 2

    # User clicks Stop! The interrupt kills the process. No StreamingMessageCompleteAgentMessage
    # arrives. Because _is_interrupted is set, the exit is treated as clean: the message
    # processing thread emits RequestSuccessAgentMessage (NOT RequestStoppedAgentMessage).
    state = convert_agent_messages_to_task_update(
        [RequestSuccessAgentMessage(request_id=request_id_1)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The key assertions: streaming state must be fully reset after success
    assert state.is_streaming_active is False, "is_streaming_active must be False after RequestSuccessAgentMessage"
    assert state.streaming_start_index == 0, (
        f"streaming_start_index must be 0 after success (was {state.streaming_start_index})"
    )
    assert state.in_progress_chat_message is None, "in_progress message should be finalized"

    # === Turn 2: New user message, agent streams new response ===
    request_id_2 = AgentMessageID()
    assistant_msg_id_3 = AssistantMessageID("assistant-turn-2")
    chat_msg_id_2 = AgentMessageID()

    state = convert_agent_messages_to_task_update(
        [RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=request_id_2)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # First partial of new response
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_3,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_2,
                content=(TextBlock(text="Good"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 1
    first_block = in_progress.content[0]
    assert isinstance(first_block, TextBlock)
    assert first_block.text == "Good"

    # Second partial — should REPLACE, not append
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_3,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_2,
                content=(TextBlock(text="Good question."),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    # BUG: Without the fix, this would be 2 (staircase: ["Good", "Good question."])
    assert len(in_progress.content) == 1, (
        "Second partial should replace the first, producing 1 content block. "
        + f"Got {len(in_progress.content)} blocks (staircase bug): "
        + f"{[b.text if isinstance(b, TextBlock) else type(b).__name__ for b in in_progress.content]}"
    )
    second_block = in_progress.content[0]
    assert isinstance(second_block, TextBlock)
    assert second_block.text == "Good question."

    # Third partial — should still be a single block
    state = convert_agent_messages_to_task_update(
        [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_msg_id_3,
                message_id=AgentMessageID(),
                first_response_message_id=chat_msg_id_2,
                content=(TextBlock(text="Good question. Let me trace the callback"),),
            )
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 1, (
        f"Third partial should still be 1 block. Got {len(in_progress.content)} blocks: "
        + f"{[b.text if isinstance(b, TextBlock) else type(b).__name__ for b in in_progress.content]}"
    )
    third_block = in_progress.content[0]
    assert isinstance(third_block, TextBlock)
    assert third_block.text == "Good question. Let me trace the callback"


def test_enter_plan_mode_on_user_message_sets_is_in_plan_mode() -> None:
    """When a ChatInputUserMessage has enter_plan_mode=True, is_in_plan_mode should be True immediately."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    state = convert_agent_messages_to_task_update(
        [ChatInputUserMessage(text="Implement feature", enter_plan_mode=True)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.is_in_plan_mode is True


def test_exit_plan_mode_on_user_message_clears_is_in_plan_mode() -> None:
    """When a ChatInputUserMessage has exit_plan_mode=True, is_in_plan_mode should be False."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # First, set is_in_plan_mode via enter_plan_mode
    state = convert_agent_messages_to_task_update(
        [ChatInputUserMessage(text="Plan this", enter_plan_mode=True)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.is_in_plan_mode is True

    # Now send a message with exit_plan_mode
    state = convert_agent_messages_to_task_update(
        [ChatInputUserMessage(text="Just do it", exit_plan_mode=True)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_in_plan_mode is False


def test_default_user_message_does_not_change_plan_mode() -> None:
    """A default ChatInputUserMessage (no plan mode flags) should not change is_in_plan_mode."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # Set plan mode on
    state = convert_agent_messages_to_task_update(
        [ChatInputUserMessage(text="Plan this", enter_plan_mode=True)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.is_in_plan_mode is True

    # Default message should not change it
    state = convert_agent_messages_to_task_update(
        [ChatInputUserMessage(text="Hello")],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.is_in_plan_mode is True


def _make_turn_metrics() -> TurnMetrics:
    return TurnMetrics(
        duration_seconds=9.3,
        input_tokens=500,
        output_tokens=200,
        reasoning_tokens=100,
    )


def _setup_assistant_mid_response() -> tuple[
    TaskID, dict[AgentMessageID, ChatMessage], ChatInputUserMessage, TaskUpdate
]:
    """Set up a common scenario: user message sent, agent mid-response with one text block."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-metrics")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is some output"),),
    )

    state = convert_agent_messages_to_task_update(
        [request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is not None
    return task_id, completed_by_id, user_message, state


def test_request_success_with_interrupted_sets_stopped_on_chat_message() -> None:
    """When RequestSuccessAgentMessage has interrupted=True, the completed ChatMessage gets stopped=True."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    request_success = RequestSuccessAgentMessage(
        request_id=user_message.message_id,
        interrupted=True,
    )

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None
    # The completed assistant message should have stopped=True
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].stopped is True
    assert completed_assistant[0].turn_metrics is None


def test_request_success_with_turn_metrics_attaches_metrics_to_chat_message() -> None:
    """When TurnMetricsAgentMessage precedes RequestSuccessAgentMessage, the completed ChatMessage gets those metrics."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    metrics = _make_turn_metrics()
    turn_metrics_msg = TurnMetricsAgentMessage(turn_metrics=metrics)
    request_success = RequestSuccessAgentMessage(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [turn_metrics_msg, request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].turn_metrics == metrics
    assert completed_assistant[0].stopped is False


def test_request_success_with_interrupted_and_turn_metrics() -> None:
    """When TurnMetricsAgentMessage precedes an interrupted RequestSuccessAgentMessage, the ChatMessage gets both stopped=True and metrics."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    metrics = _make_turn_metrics()
    turn_metrics_msg = TurnMetricsAgentMessage(turn_metrics=metrics)
    request_success = RequestSuccessAgentMessage(
        request_id=user_message.message_id,
        interrupted=True,
    )

    state = convert_agent_messages_to_task_update(
        [turn_metrics_msg, request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].stopped is True
    assert completed_assistant[0].turn_metrics == metrics


def test_request_success_without_interrupt_does_not_set_stopped() -> None:
    """A normal RequestSuccessAgentMessage (no interrupt, no metrics) leaves stopped=False and turn_metrics=None."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    request_success = RequestSuccessAgentMessage(
        request_id=user_message.message_id,
    )

    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].stopped is False
    assert completed_assistant[0].turn_metrics is None


def test_request_stopped_with_turn_metrics_attaches_metrics_and_sets_stopped() -> None:
    """TurnMetricsAgentMessage before RequestStoppedAgentMessage sets both stopped=True and metrics."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    metrics = _make_turn_metrics()
    turn_metrics_msg = TurnMetricsAgentMessage(turn_metrics=metrics)
    serialized_error = _make_serialized_exception("Agent was stopped by SIGTERM")
    request_stopped = RequestStoppedAgentMessage(
        request_id=user_message.message_id,
        error=serialized_error,
    )

    state = convert_agent_messages_to_task_update(
        [turn_metrics_msg, request_stopped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None
    assert state.in_progress_user_message_id is None
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].stopped is True
    assert completed_assistant[0].turn_metrics == metrics


def test_request_stopped_without_turn_metrics_sets_stopped_only() -> None:
    """RequestStoppedAgentMessage without turn_metrics still sets stopped=True."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    serialized_error = _make_serialized_exception("Agent was stopped")
    request_stopped = RequestStoppedAgentMessage(
        request_id=user_message.message_id,
        error=serialized_error,
    )

    state = convert_agent_messages_to_task_update(
        [request_stopped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].stopped is True
    assert completed_assistant[0].turn_metrics is None


def test_request_stopped_does_not_attach_error_block() -> None:
    """SCU-925: RequestStoppedAgentMessage must NOT append an ErrorBlock.

    A RequestStoppedAgentMessage is the wrapper's SIGTERM/SIGINT branch — it
    means the turn was stopped (typically by a Sculptor restart), not that
    the agent crashed. The `stopped=True` marker on the chat message already
    communicates that the turn was interrupted; rendering the wrapped
    "Agent died with exit code 143" as a red ErrorBlock surfaces a misleading
    crash to the user. The handler must therefore avoid appending an
    ErrorBlock to the message content.
    """
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    serialized_error = _make_serialized_exception("Agent died with exit code 143")
    request_stopped = RequestStoppedAgentMessage(
        request_id=user_message.message_id,
        error=serialized_error,
    )

    state = convert_agent_messages_to_task_update(
        [request_stopped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].stopped is True
    # The pre-existing TextBlock content must remain — only the ErrorBlock
    # should be suppressed.
    assert any(isinstance(b, TextBlock) for b in completed_assistant[0].content)
    error_blocks = [b for b in completed_assistant[0].content if isinstance(b, ErrorBlock)]
    assert error_blocks == [], (
        f"RequestStoppedAgentMessage should not produce an ErrorBlock, but {len(error_blocks)} were appended: {error_blocks}"  # noqa: E501
    )


def test_turn_metrics_survive_full_replay_from_scratch() -> None:
    """Simulates a server restart: all persistent messages are replayed from scratch.

    TurnMetricsAgentMessage is persistent, so it should be included in the replay
    and metrics should appear on the completed ChatMessage.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello!",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-replay")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is some output"),),
    )

    metrics = _make_turn_metrics()
    turn_metrics_msg = TurnMetricsAgentMessage(turn_metrics=metrics)
    request_success = RequestSuccessAgentMessage(request_id=user_message.message_id)

    # Process all messages in one batch from scratch (no current_state), simulating replay on restart.
    state = convert_agent_messages_to_task_update(
        [user_message, request_started, response_block, turn_metrics_msg, request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].turn_metrics == metrics


def test_turn_metrics_attached_during_incremental_streaming() -> None:
    """Metrics arrive while streaming, then RequestSuccess completes the turn.

    This is the live (non-replay) path: messages arrive incrementally
    with current_state carrying forward between calls.
    """
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    # Metrics arrive before request success
    metrics = _make_turn_metrics()
    turn_metrics_msg = TurnMetricsAgentMessage(turn_metrics=metrics)

    state = convert_agent_messages_to_task_update(
        [turn_metrics_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Message should still be in-progress at this point
    assert state.in_progress_chat_message is not None

    # Now complete the request
    request_success = _make_request_success(user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Metrics should be on the completed message
    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].turn_metrics == metrics


def test_turn_metrics_attached_when_stopped() -> None:
    """Metrics should also be attached when the turn is stopped (interrupted)."""
    task_id, completed_by_id, user_message, state = _setup_assistant_mid_response()

    metrics = _make_turn_metrics()
    turn_metrics_msg = TurnMetricsAgentMessage(turn_metrics=metrics)
    serialized_error = _make_serialized_exception("Agent was stopped by user")
    request_stopped = RequestStoppedAgentMessage(
        request_id=user_message.message_id,
        error=serialized_error,
    )

    state = convert_agent_messages_to_task_update(
        [turn_metrics_msg, request_stopped],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    completed_assistant = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistant) == 1
    assert completed_assistant[0].turn_metrics == metrics
    assert completed_assistant[0].stopped is True


# ========== Background Task Notification Tests ==========


def test_background_task_notification_does_not_flush_in_progress_message() -> None:
    """BackgroundTaskNotificationAgentMessage must NOT flush the in-progress message.

    The notification is an out-of-band signal and can arrive mid-turn while the
    agent is still emitting content. Flushing would split the turn into separate
    ChatMessages sharing the same first_response_message_id, which the frontend
    then dedupes — silently losing pre-notification content. Message boundaries
    are established naturally by RequestSuccess or by a parent_tool_use_id
    change.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Run tests in the background",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-before-bg")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="I'll run the tests in the background."),),
    )

    state = convert_agent_messages_to_task_update(
        [user_message, request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Verify we have an in-progress assistant message
    assert state.in_progress_chat_message is not None
    assert [b.text for b in state.in_progress_chat_message.content if isinstance(b, TextBlock)] == [
        "I'll run the tests in the background."
    ]

    # Background task notification arrives — must not disturb the in-progress message.
    notification = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-123",
        tool_use_id="toolu-456",
        status="completed",
        summary="Tests passed",
    )

    state = convert_agent_messages_to_task_update(
        [notification],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The in-progress message should be unchanged.
    assert state.in_progress_chat_message is not None
    assert [b.text for b in state.in_progress_chat_message.content if isinstance(b, TextBlock)] == [
        "I'll run the tests in the background."
    ]
    # The notification synthesizes a child ASSISTANT ChatMessage attached to the
    # subagent's tool_use (see SCU-1151), so the subagent pill's metadata
    # builder gets a completion signal even when the subagent's content never
    # reaches the parent's stream. That synthetic message is NOT the
    # in-progress message — the in-progress flush invariant is the point of
    # this test, and the synthetic counts as a separate completed message.
    completed_assistants = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistants) == 1
    assert completed_assistants[0].parent_tool_use_id == "toolu-456"
    assert [b.text for b in completed_assistants[0].content if isinstance(b, TextBlock)] == ["Tests passed"]


def test_background_task_notification_when_no_in_progress_message() -> None:
    """BackgroundTaskNotificationAgentMessage with no in-progress still synthesizes a completion child.

    SCU-1151: a stand-alone notification arrives when the prior turn is fully
    flushed (no in-progress) — common when a background task completes after
    the launching turn already ended. We still synthesize a child ChatMessage
    so the subagent pill can mark itself complete; the in_progress
    invariant (must not be touched) is unaffected.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    notification = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-123",
        tool_use_id="toolu-456",
        status="completed",
        summary="Done",
    )

    state = convert_agent_messages_to_task_update(
        [notification],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.in_progress_chat_message is None
    assert len(state.chat_messages) == 1
    synthetic = state.chat_messages[0]
    assert synthetic.role == ChatMessageRole.ASSISTANT
    assert synthetic.parent_tool_use_id == "toolu-456"
    assert [b.text for b in synthetic.content if isinstance(b, TextBlock)] == ["Done"]


def test_background_task_notification_for_bash_does_not_synthesize_child() -> None:
    """SCU-1151 regression: auto-promoted foreground Bash must not gain a child ChatMessage.

    The real Claude CLI emits the same ``system/task_notification`` subtype for
    two distinct cases:

      - Genuine Agent-tool background subagents — child synthesis is required
        so the subagent pill flips out of its "running" state.
      - Foreground Bash calls auto-promoted to ``local_bash`` background
        tasks (``task_started`` + ``task_notification`` arrive alongside the
        normal ``tool_use`` / ``tool_result`` pair, all sharing one
        ``tool_use_id``) — child synthesis is WRONG here.  AlphaToolGroup
        classifies a tool_use as a subagent when its tool_use_id has any
        child messages in the tree (``children.length > 0``), so a synthetic
        child attached to the Bash tool_use_id would force the Bash to
        render as a subagent pill and hide the bash block entirely
        (``test_alpha_chat_auto_bg_bash.py``).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Sleep 3 seconds",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-bash-tool")
    bash_tool_use_id = "toolu-bash-1"

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(
            ToolUseBlock(
                id=ToolUseID(bash_tool_use_id),
                name="Bash",
                input={"command": "sleep 3 && echo done", "description": "Sleep 3 seconds"},
            ),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [user_message, request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.in_progress_chat_message is not None

    notification = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-bash",
        tool_use_id=bash_tool_use_id,
        status="completed",
        summary="Sleep 3 seconds",
    )

    state = convert_agent_messages_to_task_update(
        [notification],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # No synthetic child should have been created — the parent is a Bash tool,
    # not Agent/Task, so attaching a child would make the frontend misclassify
    # it as a subagent.
    assert [m for m in state.chat_messages if m.parent_tool_use_id == bash_tool_use_id] == []


def test_background_bash_notification_in_later_batch_does_not_synthesize_child() -> None:
    """A background Bash whose completion arrives in a LATER batch (after the
    launching turn was finalized) must still be recognised as a Bash and skip
    child synthesis — otherwise the bash block silently turns into a subagent
    pill and vanishes once the turn is done.

    Real Claude keeps its process alive while a ``run_in_background`` Bash is
    pending, so the completion normally arrives in the same request. But if the
    user STOPS the turn while the command runs, ``RequestStopped`` finalizes the
    turn (flushing the Bash ToolUseBlock to history) and the detached command's
    completion is delivered on a later invocation — a SEPARATE conversion batch
    in which the parent Bash is no longer in ``in_progress`` nor in the
    per-batch completed list, only in the cross-batch history. The notification
    handler must find it there and NOT synthesize a child (which AlphaToolGroup
    would treat as ``children.length > 0`` and render as a subagent pill).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Profile the backend",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    bash_tool_use_id = "toolu-bg-bash-pyspy"

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-bg-bash"),
        message_id=AgentMessageID(),
        content=(
            ToolUseBlock(
                id=ToolUseID(bash_tool_use_id),
                name="Bash",
                input={"command": "sudo py-spy record --pid 123", "description": "Profile", "run_in_background": True},
            ),
        ),
    )
    task_started = BackgroundTaskStartedAgentMessage(
        background_task_id="bg-task-pyspy",
        tool_use_id=bash_tool_use_id,
        description="Profile",
    )

    # Batch 1: the turn launches the background Bash and the user Stops it. The
    # RequestStopped finalizes the turn, flushing the Bash to history.
    state = convert_agent_messages_to_task_update(
        [
            user_message,
            request_started,
            response_block,
            task_started,
            RequestStoppedAgentMessage(
                request_id=user_message.message_id, error=_make_serialized_exception("stopped")
            ),
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.in_progress_chat_message is None

    # Batch 2 (later invocation): the detached command finished and its
    # notification is delivered. The parent Bash is only in cross-batch history.
    notification = BackgroundTaskNotificationAgentMessage(
        background_task_id="bg-task-pyspy",
        tool_use_id=bash_tool_use_id,
        status="completed",
        summary="Profile",
    )
    state = convert_agent_messages_to_task_update(
        [notification],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Assert against the cross-batch history (``completed_by_id``), which is what
    # the frontend merges — the batch-2 ``state.chat_messages`` is only the
    # incremental update and would not carry batch-1's Bash either way.
    #
    # No synthetic child attached to the Bash tool_use_id: the parent was found
    # in history and recognised as a Bash, so synthesis was skipped. Without the
    # cross-batch lookup, a child would be appended here and the frontend would
    # render the Bash as a subagent pill instead of a bash block.
    assert [m for m in completed_by_id.values() if m.parent_tool_use_id == bash_tool_use_id] == []
    # The Bash ToolUseBlock itself is still present in history (still rendered).
    all_tool_use_ids = {
        block.id
        for message in completed_by_id.values()
        for block in message.content
        if isinstance(block, ToolUseBlock)
    }
    assert bash_tool_use_id in all_tool_use_ids


def test_background_task_started_is_noop() -> None:
    """BackgroundTaskStartedAgentMessage should not affect message state."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-bg-started")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(TextBlock(text="Working on it."),),
    )

    state = convert_agent_messages_to_task_update(
        [user_message, request_started, response_block],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # task_started should not change state
    task_started_msg = BackgroundTaskStartedAgentMessage(
        background_task_id="task-123",
        tool_use_id="toolu-456",
        description="Running tests",
    )

    state_after = convert_agent_messages_to_task_update(
        [task_started_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Everything should be unchanged
    assert state_after.in_progress_chat_message is not None
    assert [b.text for b in state_after.in_progress_chat_message.content if isinstance(b, TextBlock)] == [
        "Working on it."
    ]


def test_background_notification_then_new_response_produces_separate_messages() -> None:
    """Full lifecycle: main turn ends, then notification, then post-notification response.

    In real Claude Code, when a background task notification arrives after the
    main turn has ended, RequestSuccess has already flushed the in-progress
    message. The notification itself is a no-op, and the post-notification
    response (which arrives after a new system/init) creates a separate
    ChatMessage naturally.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Run tests in background",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    first_assistant_msg_id = AgentMessageID()
    first_assistant_message_id = AssistantMessageID("assistant-1")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    first_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=first_assistant_message_id,
        message_id=first_assistant_msg_id,
        content=(TextBlock(text="I'll run tests in the background."),),
    )
    # Main turn ends — this is what flushes the in-progress message, not the notification.
    request_success = RequestSuccessAgentMessage(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [user_message, request_started, first_response, request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # After RequestSuccess, in-progress is flushed to completed.
    assert state.in_progress_chat_message is None

    # Background task notification arrives (after turn end) — no-op for message conversion.
    notification = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-123",
        tool_use_id="toolu-456",
        status="completed",
        summary="Tests passed",
    )

    state = convert_agent_messages_to_task_update(
        [notification],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.in_progress_chat_message is None

    # Now a new response arrives for the background task result
    second_assistant_msg_id = AgentMessageID()
    second_assistant_message_id = AssistantMessageID("assistant-2")

    second_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=second_assistant_message_id,
        message_id=second_assistant_msg_id,
        content=(TextBlock(text="All 42 tests passed."),),
    )

    state = convert_agent_messages_to_task_update(
        [second_response],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The second response should be a new in-progress message, not appended to the first
    assert state.in_progress_chat_message is not None
    assert [b.text for b in state.in_progress_chat_message.content if isinstance(b, TextBlock)] == [
        "All 42 tests passed."
    ]

    # The first message should be tracked in completed_by_id (persisted across calls)
    first_completed = completed_by_id[first_assistant_msg_id]
    assert first_completed.role == ChatMessageRole.ASSISTANT
    assert [b.text for b in first_completed.content if isinstance(b, TextBlock)] == [
        "I'll run tests in the background."
    ]


def test_multiple_background_tasks_produce_separate_messages() -> None:
    """Multiple background tasks completing after the main thread each produce separate messages.

    Scenario matches real Claude Code: each background response arrives in its
    own request cycle, separated by RequestSuccess + RequestStarted. The
    notifications themselves are no-ops for message conversion; the natural
    request-cycle boundaries are what split the messages.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Run tests and lint in background",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    # --- Main thread response (ends its own turn) ---
    main_msg_id = AgentMessageID()
    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    main_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-main"),
        message_id=main_msg_id,
        content=(TextBlock(text="I'll run tests and lint in the background."),),
    )
    main_success = RequestSuccessAgentMessage(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [user_message, request_started, main_response, main_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.in_progress_chat_message is None

    # --- First background task notification (no-op) + its response (in a new request cycle) ---
    notification_1 = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-tests",
        tool_use_id="toolu-tests",
        status="completed",
        summary="Tests passed",
    )
    bg1_request_id = AgentMessageID()
    bg1_request_started = RequestStartedAgentMessage(request_id=bg1_request_id)
    bg1_msg_id = AgentMessageID()
    bg1_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-bg1"),
        message_id=bg1_msg_id,
        content=(TextBlock(text="All 42 tests passed."),),
    )
    bg1_success = RequestSuccessAgentMessage(request_id=bg1_request_id)
    state = convert_agent_messages_to_task_update(
        [notification_1, bg1_request_started, bg1_response, bg1_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    assert state.in_progress_chat_message is None

    # --- Second background task notification (no-op) + its response (in its own request cycle) ---
    notification_2 = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-lint",
        tool_use_id="toolu-lint",
        status="completed",
        summary="Lint passed",
    )
    bg2_request_id = AgentMessageID()
    bg2_request_started = RequestStartedAgentMessage(request_id=bg2_request_id)
    bg2_msg_id = AgentMessageID()
    bg2_response = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-bg2"),
        message_id=bg2_msg_id,
        content=(TextBlock(text="No lint errors found."),),
    )
    state = convert_agent_messages_to_task_update(
        [notification_2, bg2_request_started, bg2_response],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # --- Verify: 3 separate assistant messages ---
    # 2 completed (tracked in completed_by_id) + 1 in-progress
    assert main_msg_id in completed_by_id
    assert bg1_msg_id in completed_by_id

    main_completed = completed_by_id[main_msg_id]
    assert [b.text for b in main_completed.content if isinstance(b, TextBlock)] == [
        "I'll run tests and lint in the background."
    ]

    bg1_completed = completed_by_id[bg1_msg_id]
    assert [b.text for b in bg1_completed.content if isinstance(b, TextBlock)] == ["All 42 tests passed."]

    assert state.in_progress_chat_message is not None
    assert [b.text for b in state.in_progress_chat_message.content if isinstance(b, TextBlock)] == [
        "No lint errors found."
    ]

    # All three messages should have distinct IDs
    all_ids = {main_msg_id, bg1_msg_id, bg2_msg_id}
    assert len(all_ids) == 3


def test_concurrent_subagent_interleave_keeps_main_agent_tools_in_one_message() -> None:
    """Concurrent subagent output interleaved with the main agent's tool calls
    must not fragment the main agent's tools into one ChatMessage per call.

    Repro of the broken-apart "staircase": when many background subagents stream
    their output into the parent stream as non-streamed ``assistant`` lines
    carrying a ``parent_tool_use_id``, the parent toggles between None (main) and
    the subagent id around each main-agent tool call, and output_processor mints a
    fresh ``first_response_message_id`` for each post-interleave main turn. Before
    the fix, message_conversion flushed the main in-progress message on every
    interleaved subagent message (after StreamingMessageComplete deactivates
    streaming) and on every fresh-id partial, so each main-agent tool call landed
    in its own ChatMessage — rendered one-per-row.

    The main agent's tool calls must stay grouped in a single ChatMessage, while
    each subagent message stays a separate child ChatMessage (so nothing drops).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    agent_tool_id = ToolUseID("toolu_agent")

    user_message = ChatInputUserMessage(text="audit the codebase", model_name=LLMModel.CLAUDE_4_SONNET)
    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    stream: list = [user_message, request_started]

    def _main_turn(blocks: tuple) -> list:
        """A streamed main-agent turn: partial (fresh id) → StreamingComplete → persistence."""
        first_response_id = AgentMessageID()
        assistant_id = AssistantMessageID(str(AgentMessageID()))
        return [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant_id,
                message_id=AgentMessageID(),
                first_response_message_id=first_response_id,
                content=blocks,
                parent_tool_use_id=None,
            ),
            StreamingMessageCompleteAgentMessage(message_id=AgentMessageID()),
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=assistant_id,
                message_id=first_response_id,
                content=blocks,
                parent_tool_use_id=None,
            ),
        ]

    def _subagent_message(index: int) -> ResponseBlockAgentMessage:
        """Non-streamed subagent output reaching the parent stream (parent set)."""
        return ResponseBlockAgentMessage(
            role="assistant",
            assistant_message_id=AssistantMessageID(f"subagent-{index}"),
            message_id=AgentMessageID(),
            content=(
                TextBlock(text=f"subagent step {index}"),
                ToolUseBlock(id=ToolUseID(f"sub-tool-{index}"), name="Grep", input={"pattern": "x"}),
            ),
            parent_tool_use_id=agent_tool_id,
        )

    # Main agent launches a background subagent...
    stream += _main_turn(
        (
            TextBlock(text="Launching the audit subagent."),
            ToolUseBlock(id=agent_tool_id, name="Agent", input={"run_in_background": True, "prompt": "audit"}),
        )
    )
    # ...then makes five Bash tool calls, each its own streamed turn, with the
    # subagent's output interleaved between them.
    bash_tool_count = 5
    for i in range(bash_tool_count):
        stream.append(_subagent_message(i))
        stream += _main_turn(
            (ToolUseBlock(id=ToolUseID(f"main-bash-{i}"), name="Bash", input={"command": f"echo {i}"}),)
        )
    stream.append(RequestSuccessAgentMessage(request_id=user_message.message_id))

    state = convert_agent_messages_to_task_update(
        stream,
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
    )

    def _bash_count(message: ChatMessage) -> int:
        return sum(1 for block in message.content if isinstance(block, ToolUseBlock) and block.name == "Bash")

    main_nodes = [
        m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT and m.parent_tool_use_id is None
    ]
    nodes_with_bash = [m for m in main_nodes if _bash_count(m) > 0]
    # All five main-agent Bash calls must land in ONE ChatMessage, not five.
    assert len(nodes_with_bash) == 1, (
        f"main-agent Bash calls fragmented into {len(nodes_with_bash)} ChatMessages (staircase); expected 1"
    )
    assert _bash_count(nodes_with_bash[0]) == bash_tool_count

    # Every interleaved subagent message survives as its own child ChatMessage.
    subagent_children = [m for m in state.chat_messages if m.parent_tool_use_id == agent_tool_id]
    assert len(subagent_children) == bash_tool_count
    # No two ChatMessages share an id (a collision would silently drop one).
    all_ids = [m.id for m in state.chat_messages]
    assert len(all_ids) == len(set(all_ids))


def test_streamed_text_turn_after_subagent_does_not_stack_growing_partials() -> None:
    """A re-minted main-agent text turn must not stack its growing partials.

    Live repro of the reported chat "double printing": after a subagent runs
    inside a still-open request cycle, output_processor mints a fresh
    ``first_response_message_id`` for the next main-agent turn (SCU-1421). The
    in-progress ChatMessage keeps the PRIOR turn's id, so
    ``starts_new_streamed_turn`` — which compares the partial's id against
    ``in_progress.id`` — stays True for EVERY one of the new turn's growing text
    partials, re-running ``complete_segment`` per partial and APPENDING each
    snapshot instead of replacing it. The result is the same message rendered at
    progressively-longer lengths, stacked.

    Real streaming emits many growing partials per turn (one per text delta); the
    other staircase tests model each turn as a single full-content partial, so
    they never exercise this. Here the second turn streams three growing
    snapshots that all share one re-minted id; the final message must contain
    that text exactly once.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    agent_tool_id = ToolUseID("toolu_agent")

    user_message = ChatInputUserMessage(text="/verify-conversation", model_name=LLMModel.CLAUDE_4_SONNET)
    stream: list = [user_message, RequestStartedAgentMessage(request_id=user_message.message_id)]

    # Main turn A launches a subagent. Establishes an in-progress ChatMessage
    # whose id is turn A's first_response_message_id and leaves it open.
    turn_a_id = AgentMessageID()
    turn_a_assistant = AssistantMessageID(str(AgentMessageID()))
    turn_a_blocks = (
        TextBlock(text="Launching review subagent."),
        ToolUseBlock(id=agent_tool_id, name="Agent", input={"run_in_background": True, "prompt": "review"}),
    )
    stream += [
        PartialResponseBlockAgentMessage(
            assistant_message_id=turn_a_assistant,
            message_id=AgentMessageID(),
            first_response_message_id=turn_a_id,
            content=turn_a_blocks,
            parent_tool_use_id=None,
        ),
        StreamingMessageCompleteAgentMessage(message_id=AgentMessageID()),
        ResponseBlockAgentMessage(
            role="assistant",
            assistant_message_id=turn_a_assistant,
            message_id=turn_a_id,
            content=turn_a_blocks,
            parent_tool_use_id=None,
        ),
    ]

    # Subagent output reaches the parent as a non-streamed assistant line (parent
    # set). Handled as a separate child; it must NOT flush the main in-progress
    # message — which is what leaves turn A's id stale for turn B.
    stream.append(
        ResponseBlockAgentMessage(
            role="assistant",
            assistant_message_id=AssistantMessageID("subagent"),
            message_id=AgentMessageID(),
            content=(
                TextBlock(text="subagent working"),
                ToolUseBlock(id=ToolUseID("sub-tool"), name="Bash", input={"cmd": "ls"}),
            ),
            parent_tool_use_id=agent_tool_id,
        )
    )

    # Main turn B: the re-minted streamed text turn. output_processor mints a
    # fresh id (!= turn A's) because the last seen parent was the subagent. Real
    # streaming delivers it as growing partials that all carry this one id.
    turn_b_id = AgentMessageID()
    turn_b_assistant = AssistantMessageID(str(AgentMessageID()))
    growing_snapshots = [
        "REVIEW_MARKER alpha",
        "REVIEW_MARKER alpha beta",
        "REVIEW_MARKER alpha beta gamma",
    ]
    for snapshot in growing_snapshots:
        stream.append(
            PartialResponseBlockAgentMessage(
                assistant_message_id=turn_b_assistant,
                message_id=AgentMessageID(),
                first_response_message_id=turn_b_id,
                content=(TextBlock(text=snapshot),),
                parent_tool_use_id=None,
            )
        )
    stream.append(StreamingMessageCompleteAgentMessage(message_id=AgentMessageID()))
    stream.append(RequestSuccessAgentMessage(request_id=user_message.message_id))

    state = convert_agent_messages_to_task_update(
        stream,
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
    )

    all_messages = list(state.chat_messages)
    if state.in_progress_chat_message is not None:
        all_messages.append(state.in_progress_chat_message)
    main_messages = [m for m in all_messages if m.role == ChatMessageRole.ASSISTANT and m.parent_tool_use_id is None]
    main_text = "".join(block.text for m in main_messages for block in m.content if isinstance(block, TextBlock))

    # The streamed turn's text must appear exactly once — not once per growing
    # partial. Before the fix, all three snapshots are stacked (count == 3).
    marker_count = main_text.count("REVIEW_MARKER")
    assert marker_count == 1, (
        "streamed text turn after a subagent stacked its growing partials "
        + f"({marker_count} copies; expected 1): {main_text!r}"
    )
    # The latest (longest) snapshot must be the one that survives.
    assert "REVIEW_MARKER alpha beta gamma" in main_text


def test_streamed_turns_split_across_batches_preserve_segment_id() -> None:
    """The current segment's first_response_message_id must survive across convert
    calls (SSE batches) so a distinct later turn appends instead of overwriting.

    Reproduces the SCU-1421 concurrent-subagent shape (distinct main turns with NO
    StreamingMessageComplete between them) but SPLIT across two
    convert_agent_messages_to_task_update calls. Batch one ends mid-stream with the
    segment id set to turn A's id; without persisting it via
    TaskUpdate.streamed_segment_first_response_id, batch two would not recognize
    turn B as a new turn and would overwrite turn A's content under the same
    streaming window.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    request_id = AgentMessageID()
    assistant = AssistantMessageID("assistant-1")
    main_a, main_b = AgentMessageID(), AgentMessageID()

    # Batch one: user + start + turn A + an interleaved subagent line, with NO
    # StreamingMessageComplete, so the batch ends mid-stream (is_active True).
    batch_one: list = [
        ChatInputUserMessage(message_id=request_id, text="/go", model_name=LLMModel.CLAUDE_4_SONNET),
        RequestStartedAgentMessage(request_id=request_id),
        PartialResponseBlockAgentMessage(
            assistant_message_id=assistant,
            message_id=AgentMessageID(),
            first_response_message_id=main_a,
            content=(TextBlock(text="MARKER_A"), ToolUseBlock(id=ToolUseID("toolu_agent"), name="Task", input={})),
            parent_tool_use_id=None,
        ),
        ResponseBlockAgentMessage(
            role="assistant",
            assistant_message_id=AssistantMessageID("subagent-1"),
            message_id=AgentMessageID(),
            content=(TextBlock(text="MARKER_SUB"), ToolUseBlock(id=ToolUseID("toolu_sub"), name="Bash", input={})),
            parent_tool_use_id="toolu_agent",
        ),
    ]
    state = convert_agent_messages_to_task_update(
        batch_one, task_id=task_id, harness=CLAUDE_CODE_HARNESS, completed_message_by_id=completed_by_id
    )
    # The segment id from turn A must be emitted so the next batch can use it.
    assert state.streamed_segment_first_response_id == main_a

    # Batch two: a new distinct turn (different id, parent None) with no preceding
    # StreamingMessageComplete. It must append after turn A, not overwrite it.
    batch_two: list = [
        PartialResponseBlockAgentMessage(
            assistant_message_id=assistant,
            message_id=AgentMessageID(),
            first_response_message_id=main_b,
            content=(TextBlock(text="MARKER_B"),),
            parent_tool_use_id=None,
        ),
        RequestSuccessAgentMessage(request_id=request_id),
    ]
    state = convert_agent_messages_to_task_update(
        batch_two,
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    all_messages = list(state.chat_messages)
    if state.in_progress_chat_message is not None:
        all_messages.append(state.in_progress_chat_message)
    main_text = "".join(
        block.text
        for m in all_messages
        if m.parent_tool_use_id is None
        for block in m.content
        if isinstance(block, TextBlock)
    )
    assert "MARKER_A" in main_text and "MARKER_B" in main_text, (
        f"a distinct turn delivered in a later batch overwrote the earlier turn: {main_text!r}"
    )


def test_background_notification_mid_stream_does_not_flush() -> None:
    """SCU-267: notification arriving mid-stream must NOT flush the in-progress message.

    When streaming is active (partials are being delivered), a background task
    notification is out-of-band and should be ignored by the flush logic.  The
    current turn will be completed naturally via StreamingMessageComplete.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Do something",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    assistant_chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("assistant-streaming")

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)

    # Start streaming with partials
    partial_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="Working on it"),),
    )
    partial_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="Working on it..."),),
    )

    state = convert_agent_messages_to_task_update(
        [user_message, request_started, partial_1, partial_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Streaming is active — in-progress message exists
    assert state.in_progress_chat_message is not None
    assert [b.text for b in state.in_progress_chat_message.content if isinstance(b, TextBlock)] == ["Working on it..."]

    # Background notification arrives MID-STREAM
    notification = BackgroundTaskNotificationAgentMessage(
        background_task_id="task-bg",
        tool_use_id="toolu-bg",
        status="completed",
        summary="Background done",
    )

    state = convert_agent_messages_to_task_update(
        [notification],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The in-progress message must NOT be flushed — streaming is still active
    assert state.in_progress_chat_message is not None, (
        "notification mid-stream should not flush the in-progress message"
    )
    assert [b.text for b in state.in_progress_chat_message.content if isinstance(b, TextBlock)] == ["Working on it..."]
    # The mid-stream assistant message is still in-progress; the notification
    # synthesizes its own ASSISTANT child message (see SCU-1151) attached to
    # the subagent's tool_use, but that's separate from the mid-stream
    # message and doesn't share its id.
    completed_assistants = [m for m in completed_by_id.values() if m.role == ChatMessageRole.ASSISTANT]
    assert len(completed_assistants) == 1
    assert completed_assistants[0].parent_tool_use_id == "toolu-bg"
    in_progress_msg = state.in_progress_chat_message
    assert in_progress_msg is not None
    assert completed_assistants[0].id != in_progress_msg.id


def test_file_block_survives_subsequent_streaming_partial() -> None:
    """Regression test: a FileBlock must not be lost when a later streaming partial arrives.

    The output_processor includes FileBlocks in every streaming partial (via
    _build_current_content inserting them from _extracted_file_blocks).
    Verify that message_conversion preserves FileBlocks across partial updates.

    Sequence:
    1. Partial with [TextBlock("Here is a screenshot")]
    2. Partial with [TextBlock("Here is a screenshot"), FileBlock] (after text finalization)
    3. Partial with [TextBlock("..."), FileBlock, ToolUseBlock] (tool added, FileBlock preserved)
    4. StreamingComplete
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id = ToolUseID("tool-use-fileblock-1")
    assistant_message_id = AssistantMessageID("assistant-fileblock")
    assistant_chat_message_id = AgentMessageID()

    # Step 1: partial with text only (text block streaming)
    partial_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="Here is a screenshot"),),
    )

    state = convert_agent_messages_to_task_update(
        [partial_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.is_streaming_active is True
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 1

    # Step 2: partial with text + FileBlock (after text finalization extracts <img>)
    partial_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Here is a screenshot"),
            FileBlock(source="/tmp/test_image.png"),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    assert len(in_progress.content) == 2
    assert isinstance(in_progress.content[0], TextBlock)
    file_block = in_progress.content[1]
    assert isinstance(file_block, FileBlock)
    assert file_block.source == "/tmp/test_image.png"

    # Step 3: partial with text + FileBlock + ToolUseBlock (tool finalized, FileBlock still present)
    partial_3 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="Here is a screenshot"),
            FileBlock(source="/tmp/test_image.png"),
            ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "echo hello"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [partial_3],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None

    # The FileBlock must still be present alongside the text and tool use
    file_blocks = [b for b in in_progress.content if isinstance(b, FileBlock)]
    assert len(file_blocks) == 1, (
        f"FileBlock was lost after streaming partial! Content types: {[type(b).__name__ for b in in_progress.content]}"
    )
    assert file_blocks[0].source == "/tmp/test_image.png"

    # Text and tool use should also be present
    text_blocks = [b for b in in_progress.content if isinstance(b, TextBlock)]
    tool_blocks = [b for b in in_progress.content if isinstance(b, ToolUseBlock)]
    assert len(text_blocks) == 1
    assert len(tool_blocks) == 1

    # FileBlock must appear BEFORE the ToolUseBlock (image was output before the tool call)
    content_types = [type(b).__name__ for b in in_progress.content]
    file_idx = next(i for i, b in enumerate(in_progress.content) if isinstance(b, FileBlock))
    tool_idx = next(i for i, b in enumerate(in_progress.content) if isinstance(b, ToolUseBlock))
    assert file_idx < tool_idx, f"FileBlock should appear before ToolUseBlock but ordering was: {content_types}"

    # Step 4: Streaming completes
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    state = convert_agent_messages_to_task_update(
        [streaming_complete],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is False
    in_progress = state.in_progress_chat_message
    assert in_progress is not None

    # FileBlock should still be there after streaming ends
    file_blocks = [b for b in in_progress.content if isinstance(b, FileBlock)]
    assert len(file_blocks) == 1
    assert file_blocks[0].source == "/tmp/test_image.png"


def test_file_block_ordering_preserved_with_multiple_tool_calls() -> None:
    """FileBlocks in streaming partials must appear at their correct position.

    The output_processor includes FileBlocks in streaming partials (via
    _build_current_content inserting them before the first ToolUseBlock).
    When there are multiple tool calls, the FileBlock should appear between
    the text it was extracted from and the following tool call.

    Sequence:
    1. Partial with [TextBlock1]
    2. Partial with [TextBlock1, ToolUseBlock1]
    3. Partial with [TextBlock1, ToolUseBlock1, TextBlock2, FileBlock]
    4. Partial with [TextBlock1, ToolUseBlock1, TextBlock2, FileBlock, ToolUseBlock2]
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    tool_use_id_1 = ToolUseID("tool-use-ordering-1")
    tool_use_id_2 = ToolUseID("tool-use-ordering-2")
    assistant_message_id = AssistantMessageID("assistant-ordering")
    assistant_chat_message_id = AgentMessageID()

    # Step 1: partial with first text block
    partial_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(TextBlock(text="First text"),),
    )
    state = convert_agent_messages_to_task_update(
        [partial_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Step 2: partial with first text + first tool call
    partial_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="First text"),
            ToolUseBlock(id=tool_use_id_1, name="Bash", input={"command": "echo 1"}),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [partial_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Step 3: partial with second text + FileBlock (output_processor inserts before ToolUseBlock)
    partial_3 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="First text"),
            ToolUseBlock(id=tool_use_id_1, name="Bash", input={"command": "echo 1"}),
            TextBlock(text="Second text with image"),
            FileBlock(source="/tmp/ordering_test.png"),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [partial_3],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Step 4: partial with all blocks including second tool call
    partial_4 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(
            TextBlock(text="First text"),
            ToolUseBlock(id=tool_use_id_1, name="Bash", input={"command": "echo 1"}),
            TextBlock(text="Second text with image"),
            FileBlock(source="/tmp/ordering_test.png"),
            ToolUseBlock(id=tool_use_id_2, name="Bash", input={"command": "echo 2"}),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [partial_4],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None

    # Verify the ordering: TextBlock1, ToolUseBlock1, TextBlock2, FileBlock, ToolUseBlock2
    content_types = [type(b).__name__ for b in in_progress.content]
    assert content_types == ["TextBlock", "ToolUseBlock", "TextBlock", "FileBlock", "ToolUseBlock"], (
        f"Expected [TextBlock, ToolUseBlock, TextBlock, FileBlock, ToolUseBlock] but got {content_types}"
    )

    # Verify the FileBlock is at the correct position
    file_block = in_progress.content[3]
    assert isinstance(file_block, FileBlock)
    assert file_block.source == "/tmp/ordering_test.png"


def test_img_tags_extracted_as_file_blocks_during_replay() -> None:
    """FileBlocks must be created from <img> tags in persisted TextBlocks during replay.

    When a streamed message is persisted to the database, the ResponseBlockAgentMessage
    contains the original TextBlocks with raw <img> tags (the Claude API response).
    During streaming, FileBlocks are extracted and sent separately, but these are
    transient.  On restart/replay, the persisted message goes through the non-streaming
    path which must also extract <img> tags into FileBlocks so that images are visible.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # Simulate a persisted message being replayed (non-streaming).
    # The text contains an <img> tag that was NOT extracted during persistence.
    img_tag = '<img src="/tmp/replay_test.png" alt="screenshot">'
    text_with_img = f"Here is a screenshot:\n\n{img_tag}\n\nDone."
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-replay"),
        message_id=AgentMessageID(),
        content=(
            TextBlock(text=text_with_img),
            ToolUseBlock(id=ToolUseID("tool-replay-1"), name="Bash", input={"command": "echo hello"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None

    # The <img> tag should have been extracted into a FileBlock
    file_blocks = [b for b in in_progress.content if isinstance(b, FileBlock)]
    content_type_names = [type(b).__name__ for b in in_progress.content]
    assert len(file_blocks) == 1, (
        f"Expected 1 FileBlock from <img> extraction but got {len(file_blocks)}. Content types: {content_type_names}"
    )
    assert file_blocks[0].source == "/tmp/replay_test.png"

    # The text should have the <img> tag removed and be split around the image
    text_blocks = [b for b in in_progress.content if isinstance(b, TextBlock)]
    assert len(text_blocks) == 2
    assert all("<img" not in tb.text for tb in text_blocks)
    assert "Here is a screenshot" in text_blocks[0].text
    assert "Done." in text_blocks[1].text

    # The ToolUseBlock should still be present
    tool_blocks = [b for b in in_progress.content if isinstance(b, ToolUseBlock)]
    assert len(tool_blocks) == 1


def test_file_blocks_survive_replay_with_pre_extracted_content() -> None:
    """FileBlocks in persisted messages must survive replay on restart.

    In practice, _handle_assistant_message already extracts <img> tags into
    FileBlocks before persistence. This test verifies that when a persisted
    ResponseBlockAgentMessage with FileBlocks is replayed (non-streaming),
    the FileBlocks appear in the final ChatMessage content.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # This is what the persistence message actually looks like after
    # _handle_assistant_message extracts <img> tags:
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-replay-2"),
        message_id=AgentMessageID(),
        content=(
            TextBlock(text="Here is a screenshot:\n\nDone."),
            FileBlock(source="/tmp/replay_test_2.png"),
            ToolUseBlock(id=ToolUseID("tool-replay-2"), name="Bash", input={"command": "echo hello"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    in_progress = state.in_progress_chat_message
    assert in_progress is not None

    # FileBlock must be present in the replayed message
    file_blocks = [b for b in in_progress.content if isinstance(b, FileBlock)]
    assert len(file_blocks) == 1
    assert file_blocks[0].source == "/tmp/replay_test_2.png"

    # All content types should be present
    content_types = [type(b).__name__ for b in in_progress.content]
    assert content_types == ["TextBlock", "FileBlock", "ToolUseBlock"]

    # Order should be: TextBlock, FileBlock, ToolUseBlock
    content_types = [type(b).__name__ for b in in_progress.content]
    assert content_types == ["TextBlock", "FileBlock", "ToolUseBlock"], (
        f"Expected [TextBlock, FileBlock, ToolUseBlock] but got {content_types}"
    )


def test_file_blocks_survive_full_streaming_then_replay() -> None:
    """End-to-end test: simulate live streaming of text+img+tool, then replay persistent messages.

    This simulates the EXACT message sequence from the output_processor for a single
    assistant message with [TextBlock("text with <img>"), ToolUseBlock], including:
    - Streaming partials (ephemeral)
    - FileBlock arriving via partial (after text finalization, before tool overwrite)
    - StreamingMessageComplete (ephemeral)
    - Persistence ResponseBlockAgentMessage (persistent, from _handle_assistant_message)
    - Tool result ResponseBlockAgentMessage (persistent)
    - RequestSuccess (persistent)

    Then replays ONLY the persistent messages to verify FileBlocks survive restart.
    """
    task_id = TaskID()
    user_msg = ChatInputUserMessage(text="Show me a screenshot", model_name=LLMModel.CLAUDE_4_SONNET)
    chat_message_id = AgentMessageID()  # _first_response_message_id
    assistant_message_id = AssistantMessageID("assistant-e2e")
    tool_use_id = ToolUseID("tool-e2e-1")

    # === PHASE 1: Live streaming ===
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # User message + request started
    state = convert_agent_messages_to_task_update(
        [
            user_msg,
            RequestStartedAgentMessage(request_id=user_msg.message_id),
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Partial 1: text accumulating (still has raw <img> but cleaned for display)
    partial_1 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=chat_message_id,
        content=(TextBlock(text="Here is a screenshot:"),),
    )
    state = convert_agent_messages_to_task_update(
        [partial_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Partial 2: after text block finalized with <img> extraction.
    # The output_processor creates FileBlock in _completed_streaming_blocks and emits partial.
    partial_2 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=chat_message_id,
        content=(
            TextBlock(text="Here is a screenshot:\n\n\n\nDone."),
            FileBlock(source="/tmp/e2e_test.png"),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [partial_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Verify FileBlock is visible during streaming
    assert state.in_progress_chat_message is not None
    live_file_blocks = [b for b in state.in_progress_chat_message.content if isinstance(b, FileBlock)]
    assert len(live_file_blocks) == 1, "FileBlock should be visible after text finalization partial"

    # Partial 3: after tool block finalized. The output_processor splices the
    # FileBlock extracted from the screenshot text right after that text (which
    # precedes the tool here), so this partial DOES contain the FileBlock in the
    # correct position.
    partial_3 = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=chat_message_id,
        content=(
            TextBlock(text="Here is a screenshot:\n\n\n\nDone."),
            FileBlock(source="/tmp/e2e_test.png"),
            ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "echo hello"}),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [partial_3],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # FileBlock should still be present — it's included in every streaming partial.
    in_progress = state.in_progress_chat_message
    assert in_progress is not None
    live_file_blocks_after_tool = [b for b in in_progress.content if isinstance(b, FileBlock)]
    # This assertion checks our streaming fix: FileBlocks must survive partial overwrites
    assert len(live_file_blocks_after_tool) == 1, (
        f"FileBlock lost after tool partial! Content: {[type(b).__name__ for b in in_progress.content]}"
    )

    # StreamingMessageComplete
    state = convert_agent_messages_to_task_update(
        [StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Persistence message from _handle_assistant_message (has cleaned text + FileBlock + ToolUseBlock)
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=chat_message_id,
        content=(
            TextBlock(text="Here is a screenshot:\n\n\n\nDone."),
            FileBlock(source="/tmp/e2e_test.png"),
            ToolUseBlock(id=tool_use_id, name="Bash", input={"command": "echo hello"}),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Tool result
    tool_result_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="Bash",
                invocation_string="Bash('echo hello')",
                content=GenericToolContent(text="hello\n"),
            ),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [tool_result_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # RequestSuccess
    state = convert_agent_messages_to_task_update(
        [_make_request_success(user_msg.message_id)],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Capture the live final content
    assert state.in_progress_chat_message is None, "Message should be finalized after RequestSuccess"
    live_assistant_messages = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(live_assistant_messages) == 1
    live_content = live_assistant_messages[0].content
    live_content_types = [type(b).__name__ for b in live_content]
    live_file_blocks_final = [b for b in live_content if isinstance(b, FileBlock)]
    assert len(live_file_blocks_final) >= 1, f"FileBlock missing from live final content: {live_content_types}"

    # === PHASE 2: Replay (only persistent messages, simulating restart) ===
    replay_completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    replay_messages = [
        user_msg,
        RequestStartedAgentMessage(request_id=user_msg.message_id),
        persistence_msg,
        tool_result_msg,
        _make_request_success(user_msg.message_id),
    ]

    replay_state = convert_agent_messages_to_task_update(
        replay_messages,
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=replay_completed_by_id,
        current_state=None,
    )

    # Verify replay produces the same content
    assert replay_state.in_progress_chat_message is None, "Replayed message should be finalized"
    replay_assistant_messages = [m for m in replay_state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(replay_assistant_messages) == 1
    replay_content = replay_assistant_messages[0].content
    replay_content_types = [type(b).__name__ for b in replay_content]

    # FileBlocks must be present after replay
    replay_file_blocks = [b for b in replay_content if isinstance(b, FileBlock)]
    assert len(replay_file_blocks) >= 1, f"FileBlock missing after replay! Content types: {replay_content_types}"
    assert replay_file_blocks[0].source == "/tmp/e2e_test.png"

    # Text should be present
    replay_text_blocks = [b for b in replay_content if isinstance(b, TextBlock)]
    assert len(replay_text_blocks) >= 1, f"TextBlock missing after replay! Content types: {replay_content_types}"
    assert "Here is a screenshot" in replay_text_blocks[0].text

    # ToolResult should be present (replacing ToolUse)
    replay_tool_results = [b for b in replay_content if isinstance(b, ToolResultBlock)]
    assert len(replay_tool_results) >= 1, (
        f"ToolResultBlock missing after replay! Content types: {replay_content_types}"
    )


def test_text_and_file_blocks_survive_restart_when_persistence_message_missing_text() -> None:
    """Regression test: Claude Code SDK may emit an 'assistant' message that only contains
    tool_use blocks, omitting text blocks that were delivered via streaming. This causes
    the persistence ResponseBlockAgentMessage to be missing TextBlocks and FileBlocks,
    so after restart (replay), the text and images disappear.

    Scenario:
    - Streaming delivers: TextBlock(''), TextBlock('text...<img>...'), then ToolUseBlock
    - _finalize_block_from_accumulator extracts img into FileBlock, but ToolUseBlock overwrites it
    - The raw 'assistant' message only contains [ToolUseBlock] (no text)
    - Persistence message is created with only [ToolUseBlock]
    - After restart, replay only sees [ToolUseBlock] + [ToolResultBlock] — text and image are gone
    """
    task_id = TaskID()
    user_msg = ChatInputUserMessage(text="Output text, image, tool call")
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    chat_message_id = AgentMessageID()
    assistant_message_id = AssistantMessageID("msg_test_123")
    tool_use_id = ToolUseID("toolu_test_456")

    # The persistence message from the output_processor only has ToolUseBlock
    # because the raw Claude Code "assistant" message omitted the text block.
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        message_id=chat_message_id,
        assistant_message_id=assistant_message_id,
        content=(ToolUseBlock(id=tool_use_id, name="Read", input={"file_path": "/tmp/image.png"}),),
    )

    tool_result_msg = ResponseBlockAgentMessage(
        role="assistant",
        message_id=AgentMessageID(),
        assistant_message_id=assistant_message_id,
        content=(
            ToolResultBlock(
                tool_use_id=tool_use_id,
                tool_name="Read",
                invocation_string="Read('/tmp/image.png')",
                content=GenericToolContent(text="<image data>"),
            ),
        ),
    )

    # Second turn: text describing the image
    second_turn_msg = ResponseBlockAgentMessage(
        role="assistant",
        message_id=AgentMessageID(),
        assistant_message_id=AssistantMessageID("msg_test_789"),
        content=(TextBlock(text="The image shows a red square."),),
    )

    replay_messages = [
        user_msg,
        RequestStartedAgentMessage(request_id=user_msg.message_id),
        persistence_msg,
        tool_result_msg,
        second_turn_msg,
        _make_request_success(user_msg.message_id),
    ]

    state = convert_agent_messages_to_task_update(
        replay_messages,
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert state.in_progress_chat_message is None
    assistant_messages = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(assistant_messages) == 1

    content = assistant_messages[0].content
    content_types = [type(b).__name__ for b in content]

    # The ToolResultBlock and second-turn TextBlock should be present
    tool_results = [b for b in content if isinstance(b, ToolResultBlock)]
    assert len(tool_results) >= 1, f"ToolResultBlock missing: {content_types}"

    text_blocks = [b for b in content if isinstance(b, TextBlock)]
    assert any("red square" in b.text for b in text_blocks), f"Second-turn text missing: {content_types}"

    # NOTE: This test exercises the message_conversion layer in isolation. The actual fix
    # is in output_processor._enrich_persistence_content, which ensures the persistence
    # message includes TextBlocks and FileBlocks from streaming before it reaches
    # message_conversion. This test verifies that message_conversion handles the case
    # where the persistence message only has ToolUseBlock (i.e. the pre-fix scenario).


def test_subagent_tool_results_not_added_to_parent_during_streaming() -> None:
    """Subagent ResponseBlockAgentMessages must not leak into the parent message during streaming.

    When the parent message is being streamed (PartialResponseBlockAgentMessage) and subagent
    ResponseBlockAgentMessages arrive (with a different parent_tool_use_id), the streaming
    branch used to process ALL ResponseBlocks regardless of parent. This caused subagent
    ToolResultBlocks to be appended to the parent's in-progress message, producing duplicate
    tool entries in the UI — once as a CompletedToolLine in the parent and again as a ToolLine
    in the subagent child view.

    Reproduces the exact interleaving from the bug report: the parent streams two Agent
    tool_uses, then 2 subagent tool_uses and 2 subagent tool_results arrive while the
    parent is still streaming — all 4 leaked into the parent message.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    # IDs for the parent assistant message
    parent_assistant_msg_id = AssistantMessageID("parent-assistant")
    parent_chat_msg_id = AgentMessageID()

    # IDs for subagent tools
    agent_tool_use_id = ToolUseID("agent-tool-use-1")
    subagent_bash_id = ToolUseID("subagent-bash-1")
    subagent_read_id = ToolUseID("subagent-read-1")

    # Step 1: First subagent ResponseBlock with tool_use arrives BEFORE parent streaming.
    # It is emitted as its own completed child ChatMessage immediately — a subagent
    # message must never become the main agent's in-progress message (that is what
    # let interleaved subagent output flush and fragment the main agent's turn).
    subagent_tool_use_1 = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("subagent-assistant"),
        message_id=AgentMessageID(),
        content=(ToolUseBlock(id=subagent_bash_id, name="Bash", input={"command": "ls"}),),
        parent_tool_use_id=agent_tool_use_id,
    )

    state = convert_agent_messages_to_task_update(
        [subagent_tool_use_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Subagent message went straight to a completed child; nothing is in-progress.
    assert state.in_progress_chat_message is None
    assert len(state.chat_messages) == 1
    assert state.chat_messages[0].parent_tool_use_id == agent_tool_use_id

    # Step 2: Parent starts streaming. The subagent was already completed above,
    # so this call only opens the parent's in-progress message.
    parent_partial = PartialResponseBlockAgentMessage(
        assistant_message_id=parent_assistant_msg_id,
        message_id=AgentMessageID(),
        first_response_message_id=parent_chat_msg_id,
        content=(
            TextBlock(text="I'll use a subagent."),
            ToolUseBlock(id=agent_tool_use_id, name="Agent", input={"prompt": "explore"}),
        ),
    )

    state = convert_agent_messages_to_task_update(
        [parent_partial],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    assert state.is_streaming_active is True
    # Parent is now in-progress (the main agent context).
    assert state.in_progress_chat_message is not None
    assert state.in_progress_chat_message.parent_tool_use_id is None

    # Step 3: Second subagent tool_use arrives while parent is streaming.
    subagent_tool_use_2 = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("subagent-assistant"),
        message_id=AgentMessageID(),
        content=(ToolUseBlock(id=subagent_read_id, name="Read", input={"file_path": "/tmp/x"}),),
        parent_tool_use_id=agent_tool_use_id,
    )

    state = convert_agent_messages_to_task_update(
        [subagent_tool_use_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Step 4: First subagent tool_result arrives while parent is streaming.
    subagent_tool_result_1 = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("subagent-assistant"),
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=subagent_bash_id,
                tool_name="Bash",
                invocation_string="ls",
                content=GenericToolContent(text="file1.txt file2.txt"),
            ),
        ),
        parent_tool_use_id=agent_tool_use_id,
    )

    state = convert_agent_messages_to_task_update(
        [subagent_tool_result_1],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Step 5: Second subagent tool_result arrives while parent is streaming.
    subagent_tool_result_2 = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("subagent-assistant"),
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=subagent_read_id,
                tool_name="Read",
                invocation_string="/tmp/x",
                content=GenericToolContent(text="contents of file"),
            ),
        ),
        parent_tool_use_id=agent_tool_use_id,
    )

    state = convert_agent_messages_to_task_update(
        [subagent_tool_result_2],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The parent's in-progress message must NOT contain any subagent blocks.
    parent_msg = state.in_progress_chat_message
    assert parent_msg is not None
    parent_tool_uses = [b for b in parent_msg.content if isinstance(b, ToolUseBlock) and b.name != "Agent"]
    parent_tool_results = [b for b in parent_msg.content if isinstance(b, ToolResultBlock)]
    leaked_blocks = parent_tool_uses + parent_tool_results
    leaked_tool_use_names = [b.name for b in parent_tool_uses]
    leaked_tool_result_ids = [b.tool_use_id for b in parent_tool_results]
    assert len(leaked_blocks) == 0, (
        f"Subagent blocks leaked into parent message. Leaked tool_uses: {leaked_tool_use_names}, Leaked tool_results: {leaked_tool_result_ids}"
    )

    # All 4 subagent blocks (2 tool_uses + 2 tool_results) should be in completed subagent messages.
    subagent_messages = [m for m in list(completed_by_id.values()) if m.parent_tool_use_id == agent_tool_use_id]
    assert len(subagent_messages) >= 1, "Subagent message(s) should exist in completed messages"

    all_completed_content = [b for m in subagent_messages for b in m.content]
    subagent_tool_uses = [b for b in all_completed_content if isinstance(b, ToolUseBlock)]
    subagent_results = [b for b in all_completed_content if isinstance(b, ToolResultBlock)]
    assert len(subagent_tool_uses) == 2, (
        f"Expected 2 subagent ToolUseBlocks in completed messages, got {len(subagent_tool_uses)}"
    )
    assert len(subagent_results) == 2, (
        f"Expected 2 subagent ToolResultBlocks in completed messages, got {len(subagent_results)}"
    )


# ---------------------------------------------------------------------------
# sent_via propagation
# ---------------------------------------------------------------------------


def test_sent_via_propagates_from_chat_input_to_chat_message() -> None:
    """sent_via on ChatInputUserMessage is preserved on the resulting queued ChatMessage."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello from sculpt",
        model_name=LLMModel.CLAUDE_4_SONNET,
        sent_via="sculpt",
    )

    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].sent_via == "sculpt"


def test_sent_via_none_when_not_set() -> None:
    """sent_via defaults to None for messages that do not specify it (backward compat)."""
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Hello from UI",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    state = convert_agent_messages_to_task_update(
        [user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assert len(state.queued_chat_messages) == 1
    assert state.queued_chat_messages[0].sent_via is None


# ---------------------------------------------------------------------------
# Regression: duplicate ChatMessage when persistence ResponseBlock arrives
# AFTER UserQuestionAnswerMessage (alpha-view duplicate EXIT_PLAN_MODE_TOOL_BLOCK)
# ---------------------------------------------------------------------------


def test_response_block_after_user_question_answer_does_not_duplicate_completed_message() -> None:
    """Regression: the persistence ResponseBlockAgentMessage that mirrors a
    streamed assistant message must not produce a duplicate ChatMessage when
    it arrives AFTER the UserQuestionAnswerMessage that flushed the
    in-progress message.

    Surfaced as the alpha-view "two EXIT_PLAN_MODE_TOOL_BLOCK nodes for the
    same tool_use" symptom: each TaskUpdate's chat_messages field is
    *appended* on the frontend (see TaskUpdate docstring in derived.py), so
    if convert_agent_messages_to_task_update emits the same logical message
    in two separate updates, the frontend ends up rendering it twice.

    Sequence:
    1. Streaming partial builds msg = [Text, ExitPlanMode tool_use]
    2. AskUserQuestionAgentMessage (plan-approval question)
    3. StreamingMessageCompleteAgentMessage
    4. Persistence ResponseBlockAgentMessage(msg, [Text, tool_use]) — handled
       on the streamed path (text/tool_use deduped against partials)
    5. UserQuestionAnswerMessage (approve) — flushes in-progress to
       completed_chat_messages and resets message_was_streamed=False
    6. A late persistence ResponseBlockAgentMessage with the same message_id
       and content arrives. Without the fix, the non-streamed branch creates
       a fresh in-progress carrying the duplicate tool_use; the next request
       finalization flushes it as a SECOND completed ChatMessage with the
       same id.
    7. The frontend accumulator now holds two ChatMessages with the same id
       and content — two EXIT_PLAN_MODE_TOOL_BLOCK nodes in DOM.

    Fix: in the non-streamed ResponseBlockAgentMessage branch, treat the
    message as if message_was_streamed=True when its message_id has already
    been completed, so only ToolResultBlocks/new FileBlocks are processed.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="fake_claude:multi_step ...",
        model_name=LLMModel.FAKE_CLAUDE,
    )
    tool_use_id = ToolUseID("toolu_exit_plan_dup")
    assistant_message_id = AssistantMessageID("assistant-exit-plan-dup")
    assistant_chat_message_id = AgentMessageID()

    exit_plan_tool_block = ToolUseBlock(
        id=tool_use_id,
        name="mcp__sculptor__exit_plan_mode",
        input={},
    )
    msg_content = (TextBlock(text="I'll do that."), exit_plan_tool_block)

    # 1. Streaming partial
    partial = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=msg_content,
    )

    # 2. AskUserQuestionAgentMessage (plan-approval question)
    question_data = make_plan_approval_question(str(tool_use_id))
    ask_msg = AskUserQuestionAgentMessage(
        message_id=AgentMessageID(),
        question_data=question_data,
    )

    # 3. StreamingMessageCompleteAgentMessage
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    # 4. Persistence ResponseBlockAgentMessage (same content as the partial)
    persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=msg_content,
    )

    # Initial request
    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [user_message, request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Stream + ask + complete + persistence
    state = convert_agent_messages_to_task_update(
        [partial, ask_msg, streaming_complete, persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # 5. UserQuestionAnswerMessage — user approves; flushes in_progress and
    # sets streaming.message_was_streamed = False
    answer_message = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={list(question_data.questions[0].question for _ in [0])[0]: "Approve plan"},
        question_data=question_data,
        tool_use_id=str(tool_use_id),
    )
    state = convert_agent_messages_to_task_update(
        [answer_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # The state.chat_messages above contained the flushed in_progress.
    # Simulate the frontend's accumulator: it appends each TaskUpdate's
    # chat_messages to a running list. (See TaskUpdate docstring in derived.py:
    # "chat_messages: Only new completed messages are sent; frontend appends
    # to existing list".)
    accumulator: list[ChatMessage] = list(state.chat_messages)

    # 6. Hypothesised late-arriving persistence ResponseBlockAgentMessage —
    # same content arrives again on the non-streamed path because
    # message_was_streamed was just reset to False.
    late_persistence_msg = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=msg_content,
    )
    state = convert_agent_messages_to_task_update(
        [late_persistence_msg],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    accumulator.extend(state.chat_messages)

    # 7. Eventually the request that contained the answer completes; the
    # newly-rebuilt in_progress gets flushed into completed_chat_messages and
    # appended on the frontend a SECOND time.
    request_success = _make_request_success(request_id=answer_message.message_id)
    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    accumulator.extend(state.chat_messages)

    # Count ExitPlanMode tool_use occurrences across the frontend accumulator.
    # The duplicate-block bug would render one EXIT_PLAN_MODE_TOOL_BLOCK per
    # occurrence, so >1 here matches the symptom seen in the alpha view.
    matching_tool_uses = [
        block
        for msg in accumulator
        for block in msg.content
        if isinstance(block, ToolUseBlock) and block.id == tool_use_id
    ]
    accumulator_ids = [str(m.id) for m in accumulator]
    assert len(matching_tool_uses) == 1, (
        "Expected exactly 1 ExitPlanMode ToolUseBlock across the accumulated chat_messages"
        + f" list, found {len(matching_tool_uses)}. Accumulator message ids: {accumulator_ids}."
        + f" This would render as {len(matching_tool_uses)} EXIT_PLAN_MODE_TOOL_BLOCKs in DOM."
    )


def test_multi_step_persistence_after_user_question_answer_does_not_duplicate() -> None:
    """Regression for SCU-740: in a multi-step streaming session, the
    persistence ResponseBlockAgentMessage for a non-first assistant turn has
    its OWN fresh ``message_id`` (not equal to ``first_response_message_id``).
    If that persistence arrives AFTER the UserQuestionAnswerMessage flushes
    the in-progress, the prior fix's ``msg.message_id in completed_message_by_id``
    check misses it (because the ChatMessage was completed under
    ``first_response_message_id``, not the persistence's fresh id) and the
    non-streamed branch builds a duplicate ChatMessage carrying the same
    ExitPlanMode tool_use.

    Concretely, ``fake_claude:multi_step`` with ``[enter_plan_mode, text,
    exit_plan_mode]`` generates three SDK assistant messages within one
    streaming session. The output_processor mints a fresh AgentMessageID
    for the persistence of each turn after the first (see
    ``_parse_assistant_response``'s ``_used_first_response_id`` branch),
    so this scenario is reproducible whenever any non-first turn's
    persistence is delayed past the user's approval.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="fake_claude:multi_step ...",
        model_name=LLMModel.FAKE_CLAUDE,
    )
    first_assistant_message_id = AssistantMessageID("assistant-step-1")
    third_assistant_message_id = AssistantMessageID("assistant-step-3")
    chat_message_id = AgentMessageID()  # = first_response_message_id (used for the ChatMessage)

    enter_plan_tool_id = ToolUseID("toolu_enter_plan")
    exit_plan_tool_id = ToolUseID("toolu_exit_plan")
    enter_plan_block = ToolUseBlock(id=enter_plan_tool_id, name="EnterPlanMode", input={})
    exit_plan_block = ToolUseBlock(
        id=exit_plan_tool_id,
        name="mcp__sculptor__exit_plan_mode",
        input={},
    )

    # Step 1 streamed partial: text + EnterPlanMode tool_use.
    step1_partial = PartialResponseBlockAgentMessage(
        assistant_message_id=first_assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=chat_message_id,
        content=(TextBlock(text="I'll do that."), enter_plan_block),
    )
    # Step 1's persistence reuses the first_response_message_id (this is the
    # branch in output_processor where _used_first_response_id was False).
    step1_persistence = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=first_assistant_message_id,
        message_id=chat_message_id,
        content=(TextBlock(text="I'll do that."), enter_plan_block),
    )

    # Step 3 (skipping step 2 for brevity): text + ExitPlanMode tool_use.
    step3_partial = PartialResponseBlockAgentMessage(
        assistant_message_id=third_assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=chat_message_id,
        content=(TextBlock(text="I'll do that."), exit_plan_block),
    )
    # Step 3's persistence has a FRESH AgentMessageID — this is the path in
    # output_processor where _used_first_response_id is True.
    step3_persistence_fresh_id = AgentMessageID()
    step3_persistence = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=third_assistant_message_id,
        message_id=step3_persistence_fresh_id,
        content=(TextBlock(text="I'll do that."), exit_plan_block),
    )

    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    state = convert_agent_messages_to_task_update(
        [user_message, request_started],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    # Stream step 1 + flush, stream step 3 + flush, then UserQuestionAnswer
    # arrives BEFORE step 3's persistence.
    question_data = make_plan_approval_question(str(exit_plan_tool_id))
    ask_msg = AskUserQuestionAgentMessage(
        message_id=AgentMessageID(),
        question_data=question_data,
    )
    answer_message = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={question_data.questions[0].question: "Approve plan"},
        question_data=question_data,
        tool_use_id=str(exit_plan_tool_id),
    )
    state = convert_agent_messages_to_task_update(
        [
            step1_partial,
            streaming_complete,
            step1_persistence,
            step3_partial,
            streaming_complete,
            ask_msg,
            answer_message,
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )

    # Frontend accumulator mirrors derived.py's append-per-update merge.
    accumulator: list[ChatMessage] = list(state.chat_messages)

    # Step 3's persistence arrives late, after the answer flushed in_progress
    # and reset streaming.message_was_streamed to False.
    state = convert_agent_messages_to_task_update(
        [step3_persistence],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    accumulator.extend(state.chat_messages)

    # Eventually the request completes; flush any remaining in_progress.
    request_success = _make_request_success(request_id=answer_message.message_id)
    state = convert_agent_messages_to_task_update(
        [request_success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    accumulator.extend(state.chat_messages)

    # Bug surfaces as TWO EXIT_PLAN_MODE_TOOL_BLOCKs in the alpha view: the
    # original flushed ChatMessage carries the ExitPlanMode tool_use, AND a
    # second ChatMessage built from the late persistence carries another copy.
    matching_tool_uses = [
        block
        for msg in accumulator
        for block in msg.content
        if isinstance(block, ToolUseBlock) and block.id == exit_plan_tool_id
    ]
    accumulator_ids = [str(m.id) for m in accumulator]
    assert len(matching_tool_uses) == 1, (
        "Expected exactly 1 ExitPlanMode ToolUseBlock across the accumulated chat_messages"
        + f" list, found {len(matching_tool_uses)}. Accumulator message ids: {accumulator_ids}."
        + f" This would render as {len(matching_tool_uses)} EXIT_PLAN_MODE_TOOL_BLOCKs in DOM."
    )


# ----------------------------------------------------------------------------------------------
# Chat-message id-collision contract (SCU-1422)
# ----------------------------------------------------------------------------------------------
#
# The chat list renders one element per ChatMessage keyed by its id
# (AlphaChatInterface.tsx: ``key={node.message.id}``).  React therefore keeps only the LAST
# message when two share an id, silently dropping a whole agent turn -- the SCU-1421 failure
# mode, and a class that has recurred (SCU-267, SCU-1151, the "staircase" bug).
#
# SCU-1421 fixed the specific id-assignment bug in the output_processor and guards it there.
# The tests below guard the WEB-LAYER CONTRACT directly and independently of the
# output_processor: given a correctly-distinguished message stream, the converter must never
# collapse two distinct turns onto one id (nor merge one turn's content away under a reused id).
#
# They are deliberately DETECTION-only.  We intentionally do NOT add a runtime "reassign a
# duplicate id" guard: silently de-colliding ids in the product would mask the very
# id-assignment regressions these tests exist to surface, trading a loud test failure for a
# quiet, invisible data-loss bug in production.


def _rendered_chat_messages(update: TaskUpdate) -> list[ChatMessage]:
    """The messages the frontend renders and keys by id: completed turns plus the in-progress one."""
    rendered = list(update.chat_messages)
    if update.in_progress_chat_message is not None:
        rendered.append(update.in_progress_chat_message)
    return rendered


def _assert_no_chat_message_id_collision(rendered: list[ChatMessage]) -> None:
    """No two rendered ChatMessages may share an id.

    The chat list keys by ``message.id``; a collision makes React drop all but the last, so a
    whole turn silently vanishes (SCU-1421 class).
    """
    ids = [message.id for message in rendered]
    duplicate_ids = sorted({str(message_id) for message_id in ids if ids.count(message_id) > 1})
    assert not duplicate_ids, (
        f"convert_agent_messages_to_task_update emitted colliding ChatMessage id(s) {duplicate_ids}. "
        + "The chat list keys by message.id (AlphaChatInterface key={node.message.id}), so colliding "
        + "ids collapse to one and a whole turn silently vanishes (SCU-1421 class)."
    )


def _assert_turns_survive(
    update: TaskUpdate,
    *,
    expected_text_markers: tuple[str, ...],
    expected_tool_ids: tuple[str, ...] = (),
) -> None:
    """Assert every distinct turn's marker text/tool survives into the rendered chat.

    Catches both collapse mechanisms at once: two completed messages sharing an id (the frontend
    drops one) AND a later turn's partial overwriting an earlier turn's in-progress content under
    a reused id.  Models the frontend reducer's dedupe-by-id (last write wins) before reading
    content, so a same-id collision can never hide a dropped turn from the assertion.
    """
    rendered = _rendered_chat_messages(update)
    _assert_no_chat_message_id_collision(rendered)
    deduped_by_id = {message.id: message for message in rendered}
    visible_messages = list(deduped_by_id.values())
    visible_text = " || ".join(
        block.text for message in visible_messages for block in message.content if isinstance(block, TextBlock)
    )
    visible_tool_ids = {
        block.id for message in visible_messages for block in message.content if isinstance(block, ToolUseBlock)
    }
    missing_text = [marker for marker in expected_text_markers if marker not in visible_text]
    assert not missing_text, (
        "turn(s) silently dropped from the chat (id collision or destructive in-progress merge): "
        + f"{missing_text}. Visible text was: {visible_text!r}"
    )
    missing_tools = [tool_id for tool_id in expected_tool_ids if tool_id not in visible_tool_ids]
    assert not missing_tools, f"tool call(s) silently dropped from the chat: {missing_tools}"


class TestChatMessageIdCollisionContract:
    """SCU-1422: the converter must never emit two distinct turns under one ChatMessage id.

    Web-layer counterpart to output_processor's ``TestSubagentInterleavedTurnIds`` (SCU-1421):
    these drive ``convert_agent_messages_to_task_update`` directly with hand-built messages, so a
    converter-side regression in the id/flush bookkeeping is caught even if the output_processor
    is correct.  Each test feeds a *correctly* distinguished stream and asserts no turn is lost.
    """

    @staticmethod
    def _user_and_start(request_id: AgentMessageID) -> list:
        return [
            ChatInputUserMessage(message_id=request_id, text="/go", model_name=LLMModel.CLAUDE_4_SONNET),
            RequestStartedAgentMessage(request_id=request_id),
        ]

    def test_interleaved_subagent_and_main_turns_keep_distinct_ids(self) -> None:
        """SCU-1421 shape: streamed main turns (parent None) interleaved with a non-streamed
        subagent ResponseBlock (parent set).  Each main turn carries its own
        first_response_message_id, so all four turns must render as four distinct messages."""
        request_id = AgentMessageID()
        assistant = AssistantMessageID("assistant-1")
        main_a, main_b, main_c = AgentMessageID(), AgentMessageID(), AgentMessageID()
        subagent = AgentMessageID()

        stream = self._user_and_start(request_id) + [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=main_a,
                content=(TextBlock(text="MARKER_A"), ToolUseBlock(id=ToolUseID("toolu_agent"), name="Task", input={})),
            ),
            # Subagent output (parent set) interleaves before the main agent's next turn.
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=AssistantMessageID("subagent-1"),
                message_id=subagent,
                content=(TextBlock(text="MARKER_SUB"), ToolUseBlock(id=ToolUseID("toolu_sub"), name="Bash", input={})),
                parent_tool_use_id="toolu_agent",
            ),
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=main_b,
                content=(TextBlock(text="MARKER_B"), ToolUseBlock(id=ToolUseID("toolu_b"), name="Bash", input={})),
            ),
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=main_c,
                content=(TextBlock(text="MARKER_C"),),
            ),
            RequestSuccessAgentMessage(request_id=request_id),
        ]

        update = convert_agent_messages_to_task_update(
            stream, task_id=TaskID(), harness=CLAUDE_CODE_HARNESS, completed_message_by_id={}
        )
        _assert_turns_survive(
            update,
            expected_text_markers=("MARKER_A", "MARKER_SUB", "MARKER_B", "MARKER_C"),
            expected_tool_ids=("toolu_agent", "toolu_sub", "toolu_b"),
        )

    def test_two_level_nested_subagent_turns_keep_parent_attribution(self) -> None:
        """Two-level nesting (a subagent that spawns its own subagent) must preserve each
        level's parent_tool_use_id so the frontend can rebuild the depth-2 tree.

        Claude 2.1.172 lets a sub-agent spawn its own sub-agents.  A foreground grandchild's
        messages carry their *immediate* parent's tool_use id (the level-1 Agent tool_use),
        which itself lives in a message whose parent is the top-level Agent tool_use.  The
        converter must keep all three parent contexts distinct as control descends
        None -> toolu_l1 -> toolu_l2 and returns back to None: collapsing any adjacent pair
        merges turns and loses an Agent tool_use or a subagent reply (the SCU-1421/1422
        collapse class, one level deeper than
        ``test_interleaved_subagent_and_main_turns_keep_distinct_ids``).  buildSubagentTree
        reconstructs the nesting purely from these ids, so a flattened/dropped parent here
        silently breaks the rendered tree.
        """
        request_id = AgentMessageID()
        assistant = AssistantMessageID("assistant-1")
        main_a, main_b = AgentMessageID(), AgentMessageID()
        child, grandchild = AgentMessageID(), AgentMessageID()

        stream = self._user_and_start(request_id) + [
            # Main agent spawns the level-1 subagent (parent None).
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=main_a,
                content=(TextBlock(text="MAIN_BEFORE"), ToolUseBlock(id=ToolUseID("toolu_l1"), name="Task", input={})),
            ),
            # Level-1 subagent runs and itself spawns the level-2 subagent
            # (parent = the main agent's Agent tool_use).
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=AssistantMessageID("subagent-l1"),
                message_id=child,
                content=(TextBlock(text="L1_TEXT"), ToolUseBlock(id=ToolUseID("toolu_l2"), name="Task", input={})),
                parent_tool_use_id="toolu_l1",
            ),
            # Level-2 grandchild runs a leaf tool (parent = the level-1 Agent tool_use).
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=AssistantMessageID("subagent-l2"),
                message_id=grandchild,
                content=(
                    TextBlock(text="L2_TEXT"),
                    ToolUseBlock(id=ToolUseID("toolu_l2_bash"), name="Bash", input={}),
                ),
                parent_tool_use_id="toolu_l2",
            ),
            # Control returns to the main agent (parent None again).
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=main_b,
                content=(TextBlock(text="MAIN_AFTER"),),
            ),
            RequestSuccessAgentMessage(request_id=request_id),
        ]

        update = convert_agent_messages_to_task_update(
            stream, task_id=TaskID(), harness=CLAUDE_CODE_HARNESS, completed_message_by_id={}
        )
        _assert_turns_survive(
            update,
            expected_text_markers=("MAIN_BEFORE", "L1_TEXT", "L2_TEXT", "MAIN_AFTER"),
            expected_tool_ids=("toolu_l1", "toolu_l2", "toolu_l2_bash"),
        )

        # Every turn keeps its own nesting context: the grandchild points at the level-1
        # Agent tool_use, the child at the top-level Agent tool_use, and the main turns at
        # nothing.  A regression that flattened deep nesting would surface here as a wrong
        # (or None) parent on L2_TEXT even while the survival assertion above still passes.
        parent_by_marker = {
            block.text: message.parent_tool_use_id
            for message in _rendered_chat_messages(update)
            for block in message.content
            if isinstance(block, TextBlock)
        }
        assert parent_by_marker.get("MAIN_BEFORE") is None
        assert parent_by_marker.get("L1_TEXT") == "toolu_l1"
        assert parent_by_marker.get("L2_TEXT") == "toolu_l2"
        assert parent_by_marker.get("MAIN_AFTER") is None

    def test_multi_step_turn_reusing_id_preserves_every_step(self) -> None:
        """A multi-step turn legitimately reuses one first_response_message_id across segments
        (text -> tool -> more text), separated by StreamingMessageComplete.  Reusing the id must
        ACCUMULATE content, never drop the earlier segment; a following distinct turn keeps its
        own id."""
        request_id = AgentMessageID()
        assistant = AssistantMessageID("assistant-1")
        first_turn, second_turn = AgentMessageID(), AgentMessageID()

        stream = self._user_and_start(request_id) + [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=first_turn,
                content=(TextBlock(text="STEP_ONE"), ToolUseBlock(id=ToolUseID("toolu_x"), name="Bash", input={})),
            ),
            StreamingMessageCompleteAgentMessage(message_id=AgentMessageID()),
            # Same id, continuation after the tool -- must append, not overwrite STEP_ONE.
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=first_turn,
                content=(TextBlock(text="STEP_TWO"),),
            ),
            StreamingMessageCompleteAgentMessage(message_id=AgentMessageID()),
            # A brand-new turn with its own id.
            PartialResponseBlockAgentMessage(
                assistant_message_id=AssistantMessageID("assistant-2"),
                message_id=AgentMessageID(),
                first_response_message_id=second_turn,
                content=(TextBlock(text="SECOND_TURN"),),
            ),
            RequestSuccessAgentMessage(request_id=request_id),
        ]

        update = convert_agent_messages_to_task_update(
            stream, task_id=TaskID(), harness=CLAUDE_CODE_HARNESS, completed_message_by_id={}
        )
        _assert_turns_survive(
            update,
            expected_text_markers=("STEP_ONE", "STEP_TWO", "SECOND_TURN"),
            expected_tool_ids=("toolu_x",),
        )

    def test_mid_turn_background_notification_does_not_drop_surrounding_content(self) -> None:
        """A background-task notification arriving MID-turn must not split or collapse the turn:
        content before and after the notification share the turn's id and both must survive.

        Flushing the in-progress message on the notification would create two same-id messages
        and the frontend would drop the pre-notification half -- the case message_conversion
        explicitly guards against (see the BackgroundTaskNotification handler)."""
        request_id = AgentMessageID()
        assistant = AssistantMessageID("assistant-1")
        turn = AgentMessageID()
        before = (TextBlock(text="BEFORE_NOTIFICATION"), ToolUseBlock(id=ToolUseID("toolu_bg"), name="Bash", input={}))

        stream = self._user_and_start(request_id) + [
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=turn,
                content=before,
            ),
            BackgroundTaskStartedAgentMessage(background_task_id="bg-1", tool_use_id="toolu_bg", description="bg"),
            BackgroundTaskNotificationAgentMessage(
                background_task_id="bg-1", tool_use_id="toolu_bg", status="completed", summary="done"
            ),
            # Same turn continues (cumulative snapshot) after the notification.
            PartialResponseBlockAgentMessage(
                assistant_message_id=assistant,
                message_id=AgentMessageID(),
                first_response_message_id=turn,
                content=before + (TextBlock(text="AFTER_NOTIFICATION"),),
            ),
            RequestSuccessAgentMessage(request_id=request_id),
        ]

        update = convert_agent_messages_to_task_update(
            stream, task_id=TaskID(), harness=CLAUDE_CODE_HARNESS, completed_message_by_id={}
        )
        _assert_turns_survive(
            update,
            expected_text_markers=("BEFORE_NOTIFICATION", "AFTER_NOTIFICATION"),
            expected_tool_ids=("toolu_bg",),
        )

    def test_parent_tool_use_id_switch_keeps_turns_separate(self) -> None:
        """When the active parent_tool_use_id switches (main -> subagent context -> main), each
        context must land in its own ChatMessage.  A regression letting them share an id would
        drop a turn."""
        request_id = AgentMessageID()
        main_one, child, main_two = AgentMessageID(), AgentMessageID(), AgentMessageID()

        stream = self._user_and_start(request_id) + [
            PartialResponseBlockAgentMessage(
                assistant_message_id=AssistantMessageID("a1"),
                message_id=AgentMessageID(),
                first_response_message_id=main_one,
                content=(TextBlock(text="PARENT_MAIN_ONE"),),
                parent_tool_use_id=None,
            ),
            PartialResponseBlockAgentMessage(
                assistant_message_id=AssistantMessageID("a2"),
                message_id=AgentMessageID(),
                first_response_message_id=child,
                content=(TextBlock(text="CHILD_SUBAGENT"),),
                parent_tool_use_id="toolu_agent",
            ),
            PartialResponseBlockAgentMessage(
                assistant_message_id=AssistantMessageID("a3"),
                message_id=AgentMessageID(),
                first_response_message_id=main_two,
                content=(TextBlock(text="PARENT_MAIN_TWO"),),
                parent_tool_use_id=None,
            ),
            RequestSuccessAgentMessage(request_id=request_id),
        ]

        update = convert_agent_messages_to_task_update(
            stream, task_id=TaskID(), harness=CLAUDE_CODE_HARNESS, completed_message_by_id={}
        )
        _assert_turns_survive(
            update,
            expected_text_markers=("PARENT_MAIN_ONE", "CHILD_SUBAGENT", "PARENT_MAIN_TWO"),
        )


def test_reinjected_message_after_hard_kill_is_not_requeued_while_already_completed() -> None:
    """A message re-injected on restart must not appear in BOTH completed and queued.

    Repro for the "queued message renders as a sent message and never
    un-renders" bug. When Sculptor is hard-killed (SIGKILL / crash) while an
    agent is mid-turn, no terminal completion (RequestStopped / RequestSuccess)
    is persisted for the in-flight user message. On restart the dedup cursor
    therefore never advanced, so the message is re-queued and re-saved with the
    SAME object_id. But its original copy was already promoted to ``completed``
    via the pre-shutdown RequestStarted. Replaying the persisted log must not
    place the same id in ``queued_chat_messages`` as well -- otherwise the
    frontend renders it twice (once sent, once stuck-queued) and the duplicate
    React key corrupts the virtualized message list.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="look through the logs and attempt to fix this issue",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)
    response_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-1"),
        message_id=AgentMessageID(),
        content=(TextBlock(text="On it..."),),
    )

    # A full replay on restart: the original turn (queued -> promoted -> partial
    # response, then hard-killed with no completion) followed by the re-injected
    # copy of the same user message (same object_id).
    state = convert_agent_messages_to_task_update(
        [user_message, request_started, response_block, user_message],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    completed_ids = [message.id for message in state.chat_messages]
    queued_ids = [message.id for message in state.queued_chat_messages]

    # The original promotion put it in completed exactly once...
    assert completed_ids.count(user_message.message_id) == 1
    # ...and the re-injected copy must NOT also be queued.
    assert user_message.message_id not in queued_ids, "re-injected already-completed message must not be re-queued"
    assert state.queued_chat_messages == ()


def test_resumed_turn_log_shape_replays_to_a_finalized_state() -> None:
    """Replaying the log shape the FIXED resume path persists must finalize cleanly.

    A hard kill + restart + resumed turn leaves a log shape that did not exist
    before the resume request-id fix: a SECOND RequestStarted with the SAME
    request_id (the resumed turn re-reports the original turn's id), followed by
    a RequestSuccess keyed on that id. Replaying it (page load / backend
    restart) must produce exactly one completed copy of the user message,
    nothing queued, and -- because the completion now matches
    ``current_request_id`` -- no stuck in-progress request (the
    Streaming/Thinking pill clears).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="look through the logs and attempt to fix this issue",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    started_original = RequestStartedAgentMessage(request_id=user_message.message_id)
    partial_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-1"),
        message_id=AgentMessageID(),
        content=(TextBlock(text="On it..."),),
    )
    # -- hard kill + restart: the resumed turn re-emits RequestStarted with the
    # SAME request_id, continues, and completes keyed on the original turn id.
    started_resume = RequestStartedAgentMessage(request_id=user_message.message_id)
    resume_block = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-2"),
        message_id=AgentMessageID(),
        content=(TextBlock(text="...continuing where I left off."),),
    )
    success = RequestSuccessAgentMessage(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [user_message, started_original, partial_block, started_resume, resume_block, success],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    completed_ids = [message.id for message in state.chat_messages]
    assert completed_ids.count(user_message.message_id) == 1, f"user message duplicated: {completed_ids}"
    assert state.queued_chat_messages == (), f"nothing should stay queued: {state.queued_chat_messages}"
    assert state.in_progress_user_message_id is None, (
        f"the turn must finalize (no stuck Thinking pill); got {state.in_progress_user_message_id}"
    )
    assert state.in_progress_chat_message is None


def test_pi_ask_user_question_stamps_role_and_correlates_with_answer() -> None:
    """Real-pi AUQ rendering parity with Claude — the gap FakePi can't catch.

    Pi emits the ask_user_question call as a tool block with the extension's flat
    ``{question, options}`` input. Conversion must (1) stamp ``interactive_role``
    from the pi harness so the frontend renders the question panel by role rather
    than by tool name, and (2) key ``submitted_question_answers`` by the same
    tool-call id the rendered ToolUseBlock carries, so the answered panel
    correlates (the dispatcher unifies the question's tool_use_id onto the
    tool-call id; FakePi never emits this tool block, so this is unit-level).
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    tool_call_id = ToolUseID("toolu_pi_auq")

    tool_use = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=AssistantMessageID("assistant-pi-auq"),
        message_id=AgentMessageID(),
        content=(
            ToolUseBlock(
                id=tool_call_id,
                name="ask_user_question",
                input={"question": "Tabs or spaces?", "options": ["Tabs", "Spaces"]},
            ),
        ),
    )
    state = convert_agent_messages_to_task_update(
        [tool_use],
        task_id=task_id,
        harness=PI_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.in_progress_chat_message is not None
    use_block = state.in_progress_chat_message.content[0]
    assert isinstance(use_block, ToolUseBlock)
    assert use_block.interactive_role == "ask_user_question"

    answer = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"Tabs or spaces?": "Spaces"},
        question_data=build_ask_user_question_data("Tabs or spaces?", ["Tabs", "Spaces"], str(tool_call_id)),
        tool_use_id=str(tool_call_id),
    )
    state = convert_agent_messages_to_task_update(
        [answer],
        task_id=task_id,
        harness=PI_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=state,
    )
    # The answer is keyed by the same id the rendered tool block carries, so the
    # answered question panel finds it (this is the correlation that was broken).
    assert str(use_block.id) in state.submitted_question_answers
    assert state.submitted_question_answers[str(use_block.id)].answers == {"Tabs or spaces?": "Spaces"}


def test_pi_ask_user_question_result_block_is_stamped_for_suppression() -> None:
    """A pi AUQ tool_result that reaches the frontend (its tool use lived in an
    earlier, already-finalized message) must carry ``interactive_role`` so the
    frontend suppresses it — otherwise it renders as a stray second tool card."""
    state = convert_agent_messages_to_task_update(
        [
            ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=AssistantMessageID("assistant-pi-auq-result"),
                message_id=AgentMessageID(),
                content=(
                    ToolResultBlock(
                        tool_use_id=ToolUseID("toolu_pi_auq_orphan"),
                        tool_name="ask_user_question",
                        invocation_string="",
                        content=GenericToolContent(text="The user answered: Spaces"),
                    ),
                ),
            )
        ],
        task_id=TaskID(),
        harness=PI_HARNESS,
        completed_message_by_id={},
        current_state=None,
    )
    assert state.in_progress_chat_message is not None
    result_block = state.in_progress_chat_message.content[0]
    assert isinstance(result_block, ToolResultBlock)
    assert result_block.interactive_role == "ask_user_question"


def test_pi_ask_user_question_role_stamped_when_delivered_via_partial_first() -> None:
    """The live-streaming escape: the AUQ tool block arrives first in a
    PartialResponseBlockAgentMessage (the agent re-advertises its interleaved
    content as a partial), and the later ResponseBlockAgentMessage is skipped as
    a duplicate. The partial path must stamp interactive_role too, or the live
    turn renders as a generic tool card instead of the question panel.
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}
    assistant_message_id = AssistantMessageID("assistant-pi-partial")
    chat_message_id = AgentMessageID()
    tool_call_id = ToolUseID("toolu_pi_partial")
    auq_block = ToolUseBlock(id=tool_call_id, name="ask_user_question", input={"question": "Tabs or spaces?"})

    partial = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=chat_message_id,
        content=(auq_block,),
    )
    final = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=chat_message_id,
        content=(auq_block,),
    )
    state = convert_agent_messages_to_task_update(
        [partial, final],
        task_id=task_id,
        harness=PI_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )
    assert state.in_progress_chat_message is not None
    blocks = [b for b in state.in_progress_chat_message.content if isinstance(b, ToolUseBlock)]
    assert len(blocks) == 1, "the duplicate final block must not double-render"
    assert blocks[0].interactive_role == "ask_user_question"


def test_streamed_edit_tool_use_input_survives_mid_stream_tool_result() -> None:
    """Regression test for SCU-512: a streamed Edit's ToolUseBlock input must not be
    lost when its tool_result arrives mid-stream.

    While ``is_streaming_active`` is True the tool_result ``ResponseBlockAgentMessage``
    runs through the streaming branch, which replaces the Edit ``ToolUseBlock`` in
    place with its ``ToolResultBlock`` — dropping the rich input (``old_string`` /
    ``new_string`` / ``file_path``). The buffered final ``ResponseBlockAgentMessage``
    re-asserts the Edit ``ToolUseBlock`` for persistence, but the
    ``message_was_streamed`` branch used to filter every ``ToolUseBlock`` out as
    "already streamed", so the input was never restored. The resulting ``ChatMessage``
    held only a bare ``ToolResultBlock`` (no diff / no input args), which renders as
    an empty/minimal pill — easily mistaken for "the Edit didn't show up at all".

    Message order mirrors the real output_processor stream for an Edit:
      1. PartialResponseBlockAgentMessage [Edit ToolUseBlock(input)]  (streaming starts)
      2. ResponseBlockAgentMessage [Edit ToolResultBlock]  (mid-stream; overwrites tool_use)
      3. StreamingMessageCompleteAgentMessage
      4. ResponseBlockAgentMessage [Edit ToolUseBlock(input)]  (buffered persistence copy)
      5. RequestSuccessAgentMessage
    """
    task_id = TaskID()
    completed_by_id: dict[AgentMessageID, ChatMessage] = {}

    user_message = ChatInputUserMessage(
        text="Remove the comment.",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    edit_tool_use_id = ToolUseID("toolu_edit_scu512")
    assistant_message_id = AssistantMessageID("assistant-edit-scu512")
    assistant_chat_message_id = AgentMessageID()  # "ID1" — first_response_message_id

    edit_input = {"file_path": "/x.py", "old_string": "a", "new_string": "b"}
    edit_tool_block = ToolUseBlock(id=edit_tool_use_id, name="Edit", input=edit_input)

    request_started = RequestStartedAgentMessage(request_id=user_message.message_id)

    # 1. Streaming partial carrying the Edit tool_use with full input.
    partial = PartialResponseBlockAgentMessage(
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        first_response_message_id=assistant_chat_message_id,
        content=(edit_tool_block,),
    )

    # 2. Tool result arrives mid-stream (is_streaming_active=True). GenericToolContent
    #    matches the real session where the diff was not embedded in the result, so the
    #    diff can only be reconstructed from the surviving ToolUseBlock input.
    mid_stream_result = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=AgentMessageID(),
        content=(
            ToolResultBlock(
                tool_use_id=edit_tool_use_id,
                tool_name="Edit",
                invocation_string="/x.py",
                content=GenericToolContent(text="The file /x.py has been updated successfully."),
            ),
        ),
    )

    # 3. Streaming completes.
    streaming_complete = StreamingMessageCompleteAgentMessage(message_id=AgentMessageID())

    # 4. Buffered persistence copy re-asserts the Edit tool_use under the same
    #    first_response_message_id (this is the copy that must restore the input).
    buffered_persistence = ResponseBlockAgentMessage(
        role="assistant",
        assistant_message_id=assistant_message_id,
        message_id=assistant_chat_message_id,
        content=(edit_tool_block,),
    )

    request_success = _make_request_success(request_id=user_message.message_id)

    state = convert_agent_messages_to_task_update(
        [
            user_message,
            request_started,
            partial,
            mid_stream_result,
            streaming_complete,
            buffered_persistence,
            request_success,
        ],
        task_id=task_id,
        harness=CLAUDE_CODE_HARNESS,
        completed_message_by_id=completed_by_id,
        current_state=None,
    )

    assistant_messages = [m for m in state.chat_messages if m.role == ChatMessageRole.ASSISTANT]
    assert len(assistant_messages) == 1, (
        f"Expected exactly one finalized assistant ChatMessage, got {len(assistant_messages)}."
    )
    completed = assistant_messages[0]

    # The Edit ToolUseBlock with its original input must survive so the frontend can
    # render the diff (old_string -> new_string). On main the content is a bare
    # ToolResultBlock and this assertion fails.
    tool_use_blocks = [b for b in completed.content if isinstance(b, ToolUseBlock)]
    block_types = [type(b).__name__ for b in completed.content]
    assert len(tool_use_blocks) == 1, (
        f"Expected the Edit ToolUseBlock to survive, but content was {block_types}. The streamed Edit input was dropped."
    )
    surviving = tool_use_blocks[0]
    assert surviving.id == edit_tool_use_id
    assert surviving.input.get("old_string") == "a"
    assert surviving.input.get("new_string") == "b"
    assert surviving.input.get("file_path") == "/x.py"

    # The tool_result must still be present (paired with the tool_use by tool_use_id).
    tool_result_blocks = [b for b in completed.content if isinstance(b, ToolResultBlock)]
    assert len(tool_result_blocks) == 1
    assert tool_result_blocks[0].tool_use_id == str(edit_tool_use_id)
