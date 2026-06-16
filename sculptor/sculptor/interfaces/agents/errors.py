from __future__ import annotations

from enum import StrEnum
from typing import Any

from sculptor.foundation.errors import ExpectedError


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


class AgentClientError(AgentCrashed):
    """
    This error is raised when the agent's client encounters an error.
    """


class AgentTransientError(AgentClientError):
    """
    This error is raised when the Claude client encounters a transient error (ex. internal server error)
    """


class ClaudeBinaryNotFoundError(AgentClientError):
    """
    This error is raised when the Claude binary cannot be found at the configured path.
    """

    def __init__(self) -> None:
        super().__init__("Claude binary not found or is invalid.", exit_code=None)


class PiBinaryNotFoundError(AgentClientError):
    """
    This error is raised when the pi binary cannot be found at the configured path.
    """

    def __init__(self) -> None:
        super().__init__("Pi binary not found or is invalid.", exit_code=None)


class PiVersionMismatchError(AgentClientError):
    """
    This error is raised when the detected pi version is outside the pinned range.
    """

    def __init__(self, detected_version: str, pinned_version: str) -> None:
        message = (
            f"Pi version {detected_version} is outside the pinned range (expected {pinned_version}). "
            + "Set the pi Binary Source to Managed in Settings to install the pinned version "
            + f"automatically, or point pi at a {pinned_version} build."
        )
        super().__init__(message, exit_code=None)
        self.detected_version = detected_version
        self.pinned_version = pinned_version


class PiContextResetError(AgentClientError):
    """Raised when pi's ``new_session`` (the ``/clear`` context-reset path) fails.

    An ``AgentClientError`` rather than a crash: a failed reset (``success:false``,
    a ``data.cancelled:true`` veto, or no response within the budget) is reported
    as a failed request while the agent keeps running.
    """


class PiCrashError(AgentCrashed):
    """
    This error is raised when pi reports a structured error mid-turn or its subprocess exits unexpectedly.
    """


class ErrorType(StrEnum):
    NONZERO_EXIT_CODE = "NONZERO_EXIT_CODE"
    RESPONSE_INCOMPLETE = "RESPONSE_INCOMPLETE"
