from queue import Queue

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import Message
from sculptor.interfaces.agents.v1.agent import CommandInputUserMessage
from sculptor.tasks.handlers.run_agent.setup import _drop_already_processed_messages


def test_drop_already_processed_messages_with_processed_id() -> None:
    """Test dropping messages up to last_processed_input_message_id."""
    user_queue: Queue[Message] = Queue()

    # Create test messages
    msg1 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    msg2 = CommandInputUserMessage(
        message_id=AgentMessageID(),
        text="ls -la",
        is_included_in_context=True,
    )
    target_msg = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Target message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    msg3 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Should remain",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    # Add messages to queue
    user_queue.put(msg1)
    user_queue.put(msg2)
    user_queue.put(target_msg)
    user_queue.put(msg3)

    # Drop messages up to target
    dropped = _drop_already_processed_messages(
        last_processed_input_message_id=target_msg.message_id,
        user_message_queue=user_queue,
    )

    # Verify results
    assert len(dropped) == 3
    assert dropped == [msg1, msg2, target_msg]
    assert user_queue.qsize() == 1
    assert user_queue.get() == msg3


def test_drop_already_processed_messages_none_values() -> None:
    """Test edge case with None value for last_processed_input_message_id."""
    user_queue: Queue[Message] = Queue()

    # Create test messages
    msg1 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    msg2 = CommandInputUserMessage(
        message_id=AgentMessageID(),
        text="pwd",
        is_included_in_context=True,
    )

    user_queue.put(msg1)
    user_queue.put(msg2)

    # Test with None - should not drop anything
    dropped = _drop_already_processed_messages(
        last_processed_input_message_id=None,
        user_message_queue=user_queue,
    )

    assert len(dropped) == 0
    assert user_queue.qsize() == 2


def test_drop_already_processed_messages_empty_queue() -> None:
    """Test with empty queue."""
    user_queue: Queue[Message] = Queue()

    dropped = _drop_already_processed_messages(
        last_processed_input_message_id=AgentMessageID(),
        user_message_queue=user_queue,
    )

    assert len(dropped) == 0
    assert user_queue.empty()
