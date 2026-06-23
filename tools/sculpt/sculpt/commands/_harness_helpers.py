"""Shared harness (agent-type) resolution for the agent-creating commands.

``sculpt agent create`` and ``sculpt run`` both turn an optional ``--harness``
name into the agent type to send. The resolution — validating the built-in
harnesses and the server's registered terminal agents — lives here so the two
commands stay in lockstep.
"""

import httpx

from sculpt.client import Client
from sculpt.client.api.default import list_terminal_agent_registrations
from sculpt.client.models.terminal_agent_registration import TerminalAgentRegistration
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error
from sculpt.harness import HarnessSelection
from sculpt.harness import available_harness_names
from sculpt.harness import resolve_builtin_harness
from sculpt.harness import resolve_harness_name


def fetch_terminal_agent_registrations(client: Client, json_output: bool) -> list[TerminalAgentRegistration]:
    """Fetch the registered terminal agents the server currently offers."""
    try:
        result = list_terminal_agent_registrations.sync(client=client)
    except httpx.ConnectError:
        handle_connection_error(json_output)
    if result is None:
        cli_error("Failed to list harnesses", detail="No response from server", json_output=json_output)
    return result.registrations


def resolve_harness_selection(harness: str | None, client: Client, json_output: bool) -> HarnessSelection | None:
    """Resolve an explicitly requested harness, or None to let the server decide.

    An explicit choice is validated against the built-in harnesses (Claude,
    Pi, Terminal) and the server's registered terminal agents. With no
    choice, this returns None so the caller omits the agent type and the
    server applies the user's most-recently-used harness from the app.
    """
    if harness is None:
        return None

    builtin = resolve_builtin_harness(harness)
    if builtin is not None:
        return builtin

    registrations = fetch_terminal_agent_registrations(client, json_output)
    selection = resolve_harness_name(harness, registrations)
    if selection is None:
        valid = ", ".join(available_harness_names(registrations))
        cli_error(f"Invalid harness '{harness}'. Valid options: {valid}", json_output=json_output)
    return selection
