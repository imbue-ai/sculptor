from sculptor.foundation.agents.data_types.ids import AgentMessageID
from sculptor.foundation.agents.data_types.ids import TaskID
from sculptor.foundation.state.messages import ChatInputUserMessage
from sculptor.foundation.state.messages import LLMModel
from sculptor.foundation.state.messages import Message


def get_user_input_message(task_id: TaskID, message: str) -> Message:
    return ChatInputUserMessage(
        message_id=AgentMessageID(),
        text=message,
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
