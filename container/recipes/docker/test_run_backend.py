"""Tests for the docker recipe's `docker run` argument construction.

`run-backend.py` is a standalone script rather than an importable module (its
name is hyphenated and it ships as a copy-and-customize recipe), so it is loaded
through importlib here. Importing is side-effect free: the script guards its
entry point behind `if __name__ == "__main__"`.
"""

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).parent / "run-backend.py"

# Every host variable the recipe forwards, so a test asserting absence cannot be
# fooled by one of these leaking in from the ambient environment.
_FORWARDED_CREDENTIALS = ("SESSION_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


@pytest.fixture(scope="module")
def recipe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_backend_recipe", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def clean_credential_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start every test from a host with none of the forwarded variables set."""
    for name in _FORWARDED_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    yield


def _forwarded_env(recipe: ModuleType, **config_kwargs: object) -> dict[str, str]:
    """Return the `-e NAME=VALUE` pairs the recipe would pass to `docker run`."""
    config = recipe.ContainerConfig(dev_mode=False, **config_kwargs)
    args = recipe.build_docker_args(config)
    pairs = [args[index + 1] for index, arg in enumerate(args) if arg == "-e"]
    return dict(pair.split("=", 1) for pair in pairs)


def test_oauth_token_is_forwarded_when_set(recipe: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """The subscription credential must reach the container.

    Without it, a macOS host has no way to authenticate the in-container claude
    short of a separate sign-in, because the host's own credentials live in a
    keychain the container cannot read.
    """
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token-value")

    assert _forwarded_env(recipe)["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-token-value"


def test_api_key_is_forwarded_when_set(recipe: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "api-key-value")

    assert _forwarded_env(recipe)["ANTHROPIC_API_KEY"] == "api-key-value"


def test_session_token_is_forwarded_when_set(recipe: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_TOKEN", "session-token-value")

    assert _forwarded_env(recipe)["SESSION_TOKEN"] == "session-token-value"


def test_debug_env_keys_are_forwarded(recipe: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keys named by _DEBUGSCULPTOR_ENV_KEYS reach the container alongside the credentials."""
    monkeypatch.setenv("SOME_DEBUG_VAR", "debug-value")

    forwarded = _forwarded_env(recipe, extra_env_keys=["SOME_DEBUG_VAR"])

    assert forwarded["SOME_DEBUG_VAR"] == "debug-value"


def test_unset_credentials_are_not_forwarded(recipe: ModuleType) -> None:
    """An absent variable must be omitted, not passed through as an empty value.

    `docker run -e NAME=` sets NAME to the empty string inside the container,
    which reads as "configured, but blank" to anything checking for it.
    """
    forwarded = _forwarded_env(recipe)

    for name in _FORWARDED_CREDENTIALS:
        assert name not in forwarded


def test_empty_credential_is_treated_as_unset(recipe: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in _forwarded_env(recipe)


def test_debug_env_key_that_is_unset_is_not_forwarded(recipe: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ABSENT_DEBUG_VAR", raising=False)

    assert "ABSENT_DEBUG_VAR" not in _forwarded_env(recipe, extra_env_keys=["ABSENT_DEBUG_VAR"])
