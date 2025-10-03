from imbue_core.errors import ExpectedError
from sculptor.interfaces.agents.v1.errors import AgentCrashed


class ClaudeClientError(AgentCrashed):
    """
    This error is raised when the Claude client encounters an error.
    """


class ClaudeTransientError(ClaudeClientError):
    """
    This error is raised when the Claude client encounters a transient error (ex. internal server error)
    """


class ClaudeAPIError(ClaudeClientError):
    """
    This error is raised when the Claude client encounters an API error.
    https://docs.anthropic.com/en/api/errors#http-errors
    """


class ClaudeOutputJsonDecodeError(ExpectedError):
    """
    This error is raised when the claude output JSON is not decodable.
    """


class InterruptFailure(ExpectedError):
    """
    This error is raised when the interrupt fails.
    """


class ClaudeCompactTimeoutError(TimeoutError):
    """
    This error is raised when the claude compact times out.
    """
