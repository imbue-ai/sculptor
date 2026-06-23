"""Harness (agent-type) selection for ``sculpt agent create``.

Mirrors the harness chooser the UI shows: the built-in Claude, Pi, and
Terminal types plus any registered terminal agents (for example
"Claude CLI"). When no harness is requested the CLI sends nothing and lets
the server apply the user's most-recently-used choice from the Sculptor
app, so ``sculpt`` keeps no harness state of its own.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from sculpt.client.models.agent_type_name import AgentTypeName
from sculpt.client.models.terminal_agent_registration import TerminalAgentRegistration

# Display labels for the built-in harnesses, mirroring the frontend's
# AGENT_TYPE_LABELS so the CLI offers the same names the UI does.
BUILTIN_HARNESS_LABELS: dict[AgentTypeName, str] = {
    AgentTypeName.CLAUDE: "Claude",
    AgentTypeName.PI: "Pi",
    AgentTypeName.TERMINAL: "Terminal",
}


class HarnessSelection(BaseModel):
    """A resolved harness choice.

    ``registration_id`` is set only for registered terminal agents.
    """

    agent_type: AgentTypeName
    registration_id: str | None = None


def resolve_builtin_harness(name: str) -> HarnessSelection | None:
    """Resolve a built-in harness name (Claude, Pi, Terminal), or None.

    Matching is case-insensitive. Registered terminal agents are not
    resolved here because they require the server's registration list.
    """
    normalized = name.strip().casefold()
    for agent_type, label in BUILTIN_HARNESS_LABELS.items():
        if normalized == label.casefold():
            return HarnessSelection(agent_type=agent_type)
    return None


def resolve_harness_name(
    name: str,
    registrations: Sequence[TerminalAgentRegistration],
) -> HarnessSelection | None:
    """Resolve a harness name against the built-ins and registered agents.

    Registered terminal agents match on their display name (for example
    "Claude CLI"). Returns None when nothing matches.
    """
    builtin = resolve_builtin_harness(name)
    if builtin is not None:
        return builtin
    normalized = name.strip().casefold()
    for registration in registrations:
        if normalized == registration.display_name.casefold():
            return HarnessSelection(
                agent_type=AgentTypeName.REGISTERED,
                registration_id=registration.registration_id,
            )
    return None


def available_harness_names(
    registrations: Sequence[TerminalAgentRegistration],
) -> list[str]:
    """List the harness names a user may pass, in the order the UI shows them."""
    return [*BUILTIN_HARNESS_LABELS.values(), *(r.display_name for r in registrations)]
