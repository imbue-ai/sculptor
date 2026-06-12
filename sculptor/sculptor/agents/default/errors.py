from __future__ import annotations

from imbue_core.errors import ExpectedError


class InterruptFailure(ExpectedError):
    """
    This error is raised when the interrupt fails. It gets placed in the message queue on interrupt failures.
    """
