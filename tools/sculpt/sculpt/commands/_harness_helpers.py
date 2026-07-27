"""Shared harness and model resolution for the agent-creating commands.

``sculpt agent create`` and ``sculpt run`` both turn an optional ``--harness``
name and an optional ``--model`` name into the agent type and model to send.
The resolution — validating the built-in harnesses, the server's registered
terminal agents, and each harness's model catalog — lives here so the two
commands stay in lockstep.
"""

from collections.abc import Sequence

import httpx

from sculpt.auth import MODEL_MAPPING
from sculpt.client import Client
from sculpt.client.api.default import get_pi_models
from sculpt.client.api.default import list_terminal_agent_registrations
from sculpt.client.models.agent_type_name import AgentTypeName
from sculpt.client.models.llm_model import LLMModel
from sculpt.client.models.model_option import ModelOption
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


# Shared --model help so `agent create` and `run` describe the same contract.
MODEL_HELP = (
    "The model to use (haiku, sonnet, sonnet[1m], opus, opus[1m], fable;"
    + " default opus). With --harness pi, a model from pi's own catalog:"
    + " model_id, display name, or provider/model_id (default: pi's own"
    + " default model)."
)


def _pi_model_names(option: ModelOption) -> tuple[str, str, str]:
    """The accepted spellings of a pi catalog model, lowercased for matching."""
    return (
        option.model_id.lower(),
        option.display_name.lower(),
        f"{option.provider}/{option.model_id}".lower(),
    )


def _format_pi_model_list(options: Sequence[ModelOption]) -> str:
    return ", ".join(f"{o.display_name} ({o.provider}/{o.model_id})" for o in options)


def _resolve_pi_backend_model(client: Client, json_output: bool, requested_model: str | None = None) -> ModelOption:
    """Pick the backend model a pi prompt runs under, from pi's own catalog.

    A pi prompt must name a model from pi's curated, authenticated-only catalog
    (GET /api/v1/pi/models) — the Claude ``--model`` names do not apply to pi.
    A requested model matches exactly (case-insensitive) on model_id, display
    name, or provider/model_id; with no request, uses pi's own default when
    usable, else the newest available model. Errors when the catalog is empty
    (no authenticated provider / unusable pi).
    """
    try:
        catalog = get_pi_models.sync(client=client)
    except httpx.ConnectError:
        handle_connection_error(json_output)
    if catalog is None:
        cli_error("Failed to fetch pi models", detail="No response from server", json_output=json_output)
    if requested_model is None:
        if catalog.default_model is not None:
            return catalog.default_model
        if catalog.available_models:
            return catalog.available_models[0]
    else:
        requested_lower = requested_model.lower()
        matches = [o for o in catalog.available_models if requested_lower in _pi_model_names(o)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            cli_error(
                f"'{requested_model}' matches multiple pi models: {_format_pi_model_list(matches)}."
                + " Use provider/model_id to pick one",
                json_output=json_output,
            )
        if catalog.available_models:
            cli_error(
                f"Unknown pi model '{requested_model}'. Available pi models: {_format_pi_model_list(catalog.available_models)}",
                json_output=json_output,
            )
    cli_error(
        "pi has no usable model — authenticate a provider (Sculptor Settings → Pi → Providers), then retry",
        json_output=json_output,
    )


def resolve_prompt_models(
    selection: HarnessSelection | None,
    model: str | None,
    client: Client,
    json_output: bool,
) -> tuple[LLMModel | None, ModelOption | None]:
    """Resolve --model for a prompted agent against the resolved harness's catalog.

    Returns ``(claude_model, pi_backend_model)`` — exactly one is set: a pi
    harness takes a backend model from pi's own catalog, anything else a
    Claude model from MODEL_MAPPING.
    """
    if selection is not None and selection.agent_type == AgentTypeName.PI:
        return None, _resolve_pi_backend_model(client, json_output, model)
    model_lower = "opus" if model is None else model.lower()
    if model_lower not in MODEL_MAPPING:
        valid = ", ".join(MODEL_MAPPING.keys())
        cli_error(f"Invalid model '{model}'. Valid options: {valid}", json_output=json_output)
    return MODEL_MAPPING[model_lower], None
