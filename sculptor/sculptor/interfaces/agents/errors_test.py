from imbue_core.serialization import SerializedException
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGINT
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.interfaces.agents.errors import ErrorType


def test_serialization():
    try:
        raise AgentClientError(
            "Agent exited with exit code 0, but it did not have the final message -- it was probably terminated.",
            exit_code=AGENT_EXIT_CODE_FROM_SIGINT,
            metadata={
                "source_command": " ".join(["claude", "-p", "whatever"]),
                "error": ErrorType.RESPONSE_INCOMPLETE,
                "stderr": "some data",
                "stdout": "some more data",
            },
        )
    except AgentClientError as e:
        serialized_exception = SerializedException.build(e)
        assert serialized_exception.construct_instance().exit_code == AGENT_EXIT_CODE_FROM_SIGINT
