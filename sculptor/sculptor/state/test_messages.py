from syrupy import SnapshotAssertion

from sculptor.primitives.ids import AssistantMessageID
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.state.messages import ResponseBlockAgentMessage


def test_create_messages(snapshot: SnapshotAssertion) -> None:
    _messages = [
        ResponseBlockAgentMessage(
            role="user",
            assistant_message_id=AssistantMessageID("some_id"),
            content=(TextBlock(text="some text"),),
        ),
        ChatInputUserMessage(
            text="some text",
            model_name=LLMModel.CLAUDE_4_OPUS,
        ),
    ]
