from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.state.messages import Message


def get_user_input_message(task_id: TaskID, message: str) -> Message:
    return ChatInputUserMessage(
        message_id=AgentMessageID(),
        text=message,
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
