import json
import os
from pathlib import Path

from sculptor.agents.pi_agent.provider_catalog import ProviderGroup
from sculptor.agents.pi_agent.provider_catalog import get_provider_catalog
from sculptor.foundation.pydantic_serialization import FrozenModel


class ProviderAuthStatus(FrozenModel):
    """Per-provider authentication status, annotated against the two credential sources.

    ``in_auth_json`` reflects presence of the provider id as a top-level key in
    ``auth.json`` (presence, not validity, matching pi's gating). ``env_detected``
    reflects that at least one of the provider's env vars is present and non-empty.
    """

    provider_id: str
    display_name: str
    group: ProviderGroup
    is_subscription: bool
    in_auth_json: bool
    env_detected: bool
    env_var_names: tuple[str, ...]


def resolve_pi_auth_json_path() -> Path:
    """Return the path to pi's ``auth.json``, matching pi's ``getAgentDir()``.

    The agent dir is ``$PI_CODING_AGENT_DIR`` (expanded) when set and non-empty,
    else ``~/.pi/agent``; ``auth.json`` lives directly inside it.
    """
    agent_dir_override = os.environ.get("PI_CODING_AGENT_DIR")
    if agent_dir_override:
        agent_dir = Path(agent_dir_override).expanduser()
    else:
        agent_dir = Path.home() / ".pi" / "agent"
    return agent_dir / "auth.json"


def read_auth_json_provider_ids() -> set[str]:
    """Return the set of top-level provider ids in ``auth.json`` (best-effort).

    A missing, unreadable, non-JSON, or non-dict file yields an empty set; this
    reader never raises so a malformed file cannot break the picker or Settings.
    """
    auth_json_path = resolve_pi_auth_json_path()
    try:
        raw = auth_json_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(parsed, dict):
        return set()
    return set(parsed.keys())


def detect_env_authenticated_provider_ids() -> set[str]:
    """Return provider ids whose env vars are present and non-empty in ``os.environ``."""
    detected: set[str] = set()
    for entry in get_provider_catalog():
        for env_var_name in entry.env_var_names:
            if os.environ.get(env_var_name):
                detected.add(entry.provider_id)
                break
    return detected


def compute_authenticated_provider_ids() -> set[str]:
    """Return the authenticated set: ``keys(auth.json) ∪ env-detected providers``."""
    return read_auth_json_provider_ids() | detect_env_authenticated_provider_ids()


def get_provider_auth_statuses() -> tuple[ProviderAuthStatus, ...]:
    """Return the per-provider auth status for every catalog entry, annotated once."""
    auth_json_provider_ids = read_auth_json_provider_ids()
    env_detected_provider_ids = detect_env_authenticated_provider_ids()
    return tuple(
        ProviderAuthStatus(
            provider_id=entry.provider_id,
            display_name=entry.display_name,
            group=entry.group,
            is_subscription=entry.is_subscription,
            in_auth_json=entry.provider_id in auth_json_provider_ids,
            env_detected=entry.provider_id in env_detected_provider_ids,
            env_var_names=entry.env_var_names,
        )
        for entry in get_provider_catalog()
    )
