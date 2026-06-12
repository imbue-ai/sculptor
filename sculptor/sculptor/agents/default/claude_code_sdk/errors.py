from sculptor.interfaces.agents.errors import AgentClientError


class ClaudeAPIError(AgentClientError):
    """
    This error is raised when the Claude client encounters an API error.
    https://docs.anthropic.com/en/api/errors#http-errors
    """
