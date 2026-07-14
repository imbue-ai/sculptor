from typing import Annotated
from typing import TypeGuard
from typing import get_args
from typing import get_origin

from loguru import logger

from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.agents.agent import WarningAgentMessage
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.interfaces.environments.errors import EnvironmentFailure
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.state.messages import Message


def get_warning_message(
    message: str,
    error: BaseException | None,
    task_id: TaskID,
) -> WarningAgentMessage:
    logger.bind(task_id=task_id).opt(exception=error).warning(message)
    warning_message = WarningAgentMessage(
        message_id=AgentMessageID(),
        message=message,
        error=SerializedException.build(error) if error is not None else None,
    )
    return warning_message


def get_state_file_contents(environment: AgentExecutionEnvironment, relative_path: str) -> str | None:
    try:
        contents = environment.read_file(str(environment.get_state_path() / relative_path))
    except FileNotFoundError:
        return None
    except EnvironmentFailure as e:
        logger.debug("Failed to read state file {}: {}", relative_path, e)
        return None
    else:
        if isinstance(contents, str):
            return contents.strip()
        else:
            assert isinstance(contents, bytes)
            return contents.decode("utf-8").strip()


def _get_user_message_union_types() -> tuple[type, ...]:
    """Extract all concrete types from UserMessageUnion for isinstance() checks."""

    union_args = get_args(UserMessageUnion)
    actual_types = []

    for arg in union_args:
        # Handle Annotated types (e.g., Annotated[ChatInputUserMessage, Tag("ChatInputUserMessage")])
        if get_origin(arg) is Annotated:
            actual_types.append(get_args(arg)[0])
        else:
            actual_types.append(arg)

    return tuple(actual_types)


def is_user_message(message: Message) -> TypeGuard[UserMessageUnion]:
    return isinstance(message, _get_user_message_union_types())


def get_turn_request_id(message: UserMessageUnion | ResumeAgentResponseRunnerMessage) -> AgentMessageID:
    """The id of the user turn that ``message`` drives.

    A ``ResumeAgentResponseRunnerMessage`` continues an earlier user turn after a
    restart, so its lifecycle messages (RequestStarted / RequestSuccess /
    RequestStopped / RequestFailure) must be keyed on that turn's id
    (``for_user_message_id``) -- NOT the resume message's own freshly generated
    ``message_id``. Otherwise the resumed turn's completion never matches the
    original chat message: the run-loop's ``is_agent_turn_finished`` never fires
    (queued follow-up stuck) and the frontend projection's ``current_request_id``
    never clears (stuck Streaming/Thinking pill). All other user messages key on
    their own ``message_id``.
    """
    if isinstance(message, ResumeAgentResponseRunnerMessage):
        return message.for_user_message_id
    return message.message_id


def serialize_agent_wrapper_error(
    e: Exception,
    message: UserMessageUnion | ResumeAgentResponseRunnerMessage,
    is_stopping: bool,
    stopped_by_user: bool = False,
) -> RequestStoppedAgentMessage | RequestFailureAgentMessage:
    serialized_exception = SerializedException.build(e)
    request_id = get_turn_request_id(message)
    if is_stopping:
        return RequestStoppedAgentMessage(
            message_id=AgentMessageID(),
            request_id=request_id,
            error=serialized_exception,
            stopped_by_user=stopped_by_user,
        )
    return RequestFailureAgentMessage(
        message_id=AgentMessageID(),
        request_id=request_id,
        error=serialized_exception,
    )
