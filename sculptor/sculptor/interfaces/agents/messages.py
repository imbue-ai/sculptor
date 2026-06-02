"""Agent messages that have no environment dependencies.

This module exists to break circular imports between agent.py and environment modules.
Messages defined here can be safely imported by environment implementations.
"""

from sculptor.foundation.state.messages import AgentMessageSource
from sculptor.foundation.state.messages import Message


class EphemeralMessage(Message):
    @property
    def is_ephemeral(self) -> bool:
        return True


class EphemeralAgentMessage(EphemeralMessage):
    """Base class for ephemeral messages sent from the agent."""

    source: AgentMessageSource = AgentMessageSource.AGENT
