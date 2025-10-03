from typing import Any

from imbue_core.errors import ExpectedError


class AgentCrashed(ExpectedError):
    def __init__(self, message: str, exit_code: int | None, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message, exit_code, metadata)
        self.exit_code = exit_code
        self.metadata = metadata


class UncleanTerminationAgentError(ExpectedError):
    pass


class IllegalOperationError(ExpectedError):
    pass


class WaitTimeoutAgentError(ExpectedError):
    pass
