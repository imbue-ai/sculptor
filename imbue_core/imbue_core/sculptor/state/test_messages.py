from syrupy import SnapshotAssertion

from imbue_core.ids import AssistantMessageID
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage


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
