"""Authentication and shared configuration for the sculpt CLI."""

import os
import re

import httpx

from sculpt.client import Client
from sculpt.client.models import LLMModel
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error
from sculpt.session import SessionTokenError
from sculpt.session import get_session_token

DEFAULT_PORT = 5050

# httpx silently defaults to a 5s request timeout, which a momentarily slow local
# backend can exceed, dropping the request. Pin a longer, explicit ceiling so
# transient slowness isn't mistaken for failure.
_HTTP_TIMEOUT_SECONDS = 30.0


def get_default_base_url() -> str:
    """Get the default base URL, respecting SCULPT_API_PORT if set."""
    port = os.environ.get("SCULPT_API_PORT", str(DEFAULT_PORT))
    return f"http://localhost:{port}"


def build_client(base_url: str) -> Client:
    """Build a sculpt API client with an explicit, generous request timeout."""
    return Client(base_url=base_url, timeout=httpx.Timeout(_HTTP_TIMEOUT_SECONDS))


# Family shortcuts name each family's rolling "latest" member, which the Claude CLI
# resolves to whatever it treats as the newest model of that family. The `[1m]`
# spellings are accepted synonyms: these models already run a 1M context window.
MODEL_MAPPING: dict[str, LLMModel] = {
    "haiku": LLMModel.CLAUDE_4_HAIKU,
    "sonnet": LLMModel.CLAUDE_4_SONNET,
    "sonnet[1m]": LLMModel.CLAUDE_4_SONNET,
    "opus": LLMModel.CLAUDE_4_OPUS,
    "opus[1m]": LLMModel.CLAUDE_4_OPUS,
    "fable": LLMModel.CLAUDE_FABLE_LATEST,
}

# A pinned member's name spells its Claude CLI `--model` id: CLAUDE_5_5_OPUS is
# claude-opus-5-5 and CLAUDE_FABLE_5_2 is claude-fable-5-2. The fullmatch leaves out
# the `_200K` members, which new records never use.
_PINNED_NAME = re.compile(
    r"CLAUDE_(?:(?P<version>\d+(?:_\d+)*)_(?P<family>OPUS|SONNET|HAIKU)|FABLE_(?P<fable>\d+(?:_\d+)*))"
)


def _pinned_model_id(model: LLMModel) -> str | None:
    match = _PINNED_NAME.fullmatch(model.name)
    if match is None or model in MODEL_MAPPING.values():
        return None
    if match["fable"] is not None:
        return "claude-fable-" + match["fable"].replace("_", "-")
    return f"claude-{match['family'].lower()}-{match['version'].replace('_', '-')}"


def _pinned_model_ids() -> dict[str, LLMModel]:
    model_ids: dict[str, LLMModel] = {}
    for model in LLMModel:
        model_id = _pinned_model_id(model)
        if model_id is not None:
            model_ids[model_id] = model
    return model_ids


# Every pinned model, by the `--model` id the Claude CLI knows it as.
PINNED_MODEL_IDS: dict[str, LLMModel] = _pinned_model_ids()


def resolve_claude_model(name: str) -> LLMModel | None:
    """The member a `--model` value names: a family shortcut, or a pinned model id (`[1m]` optional)."""
    lowered = name.lower()
    return MODEL_MAPPING.get(lowered) or PINNED_MODEL_IDS.get(lowered.removesuffix("[1m]"))


def invalid_model_message(name: str) -> str:
    shortcuts = ", ".join(MODEL_MAPPING)
    return f"Invalid model '{name}'. Use a family shortcut ({shortcuts}) or a model id such as claude-opus-5-5."


# What an unspecified --model resolves to, kept out of MODEL_MAPPING on purpose. The
# `opus` entry above is the Claude CLI's rolling alias, which lands on a different
# generation as the managed CLI is bumped; a default that follows it would move new
# agents onto a new model with no change here. Track the GUI's default
# (`defaultModelAtom`, `web/derived.py`) when this moves.
DEFAULT_CLAUDE_MODEL: LLMModel = LLMModel.CLAUDE_5_5_OPUS


def get_authenticated_client(base_url: str, json_output: bool = False) -> Client:
    """Create an authenticated client for the Sculptor API."""
    client = build_client(base_url)
    try:
        session_token = get_session_token(client)
    except SessionTokenError as e:
        cli_error(str(e), json_output=json_output)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output, base_url=base_url)
    return client.with_headers({"x-session-token": session_token})
