"""Harness (agent-type) selection for ``sculpt agent create``.

Mirrors the harness chooser the UI shows: the built-in Claude, Pi, and
Terminal types plus any registered terminal agents (for example
"Claude CLI"). The most-recently-used selection is persisted to a small
local state file so a bare ``sculpt agent create`` reuses it, matching the
UI's MRU default.
"""

import json
import os
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path

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

_STATE_DIR_ENV_VAR = "SCULPT_STATE_DIR"
_DEFAULT_STATE_DIR = "~/.sculpt"
_STATE_FILE_NAME = "cli_state.json"
_MRU_HARNESS_KEY = "mru_harness"
# Encoding for a registered terminal agent in the MRU file, matching the
# frontend's ``registered:<id>`` StoredAgentType form.
_REGISTERED_PREFIX = "registered:"


class HarnessSelection(BaseModel):
    """A resolved harness choice.

    ``registration_id`` is set only for registered terminal agents.
    """

    agent_type: AgentTypeName
    registration_id: str | None = None

    def encode(self) -> str:
        """Encode this selection for the MRU state file."""
        if self.agent_type == AgentTypeName.REGISTERED and self.registration_id is not None:
            return f"{_REGISTERED_PREFIX}{self.registration_id}"
        return self.agent_type.value


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


def read_most_recently_used_harness() -> HarnessSelection | None:
    """Read the most-recently-used harness, or None if unset or unreadable."""
    value = _read_state().get(_MRU_HARNESS_KEY)
    if not isinstance(value, str):
        return None
    return _decode_harness(value)


def write_most_recently_used_harness(selection: HarnessSelection) -> None:
    """Persist the most-recently-used harness selection (best-effort)."""
    state = dict(_read_state())
    state[_MRU_HARNESS_KEY] = selection.encode()
    _write_state(state)


def _decode_harness(value: str) -> HarnessSelection | None:
    if value.startswith(_REGISTERED_PREFIX):
        registration_id = value[len(_REGISTERED_PREFIX) :]
        if not registration_id:
            return None
        return HarnessSelection(agent_type=AgentTypeName.REGISTERED, registration_id=registration_id)
    try:
        agent_type = AgentTypeName(value)
    except ValueError:
        return None
    if agent_type == AgentTypeName.REGISTERED:
        # A registered agent without an id is not actionable.
        return None
    return HarnessSelection(agent_type=agent_type)


def _state_file_path() -> Path:
    state_dir = os.environ.get(_STATE_DIR_ENV_VAR, _DEFAULT_STATE_DIR)
    return Path(state_dir).expanduser() / _STATE_FILE_NAME


def _read_state() -> dict[str, object]:
    try:
        raw = _state_file_path().read_text()
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_state(state: Mapping[str, object]) -> None:
    path = _state_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(state), indent=2))
    except OSError:
        # MRU persistence is a convenience cache; never fail agent creation
        # because we could not write it (for example a read-only home).
        return
