"""Tests for the CLI startup helpers (``sculptor.cli.app``)."""

import os
from collections.abc import Iterator

import pytest

from sculptor.cli.app import resolve_and_publish_backend_port
from sculptor.config.settings import DEFAULT_BACKEND_PORT
from sculptor.web.middleware import get_settings


@pytest.fixture
def fresh_settings_cache() -> Iterator[None]:
    """Isolate these tests from any get_settings() call elsewhere in the
    pytest process, and leave no snapshot behind for later tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_explicit_port_is_published_and_visible_in_the_settings_snapshot(
    fresh_settings_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The CLI primes the settings cache (for logging config) before the --port
    # option is applied. The helper must retake the snapshot afterwards, or
    # every consumer of settings.BACKEND_PORT (agent env setup, the service
    # collection) would see the pre-publish port instead of the one the server
    # actually listens on.
    monkeypatch.delenv("SCULPTOR_API_PORT", raising=False)
    assert get_settings().BACKEND_PORT == DEFAULT_BACKEND_PORT

    port = resolve_and_publish_backend_port(14242)

    assert port == 14242
    assert os.environ["SCULPTOR_API_PORT"] == "14242"
    assert get_settings().BACKEND_PORT == 14242


def test_default_port_comes_from_settings_and_is_republished(
    fresh_settings_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCULPTOR_API_PORT", "6060")

    port = resolve_and_publish_backend_port(None)

    assert port == 6060
    assert os.environ["SCULPTOR_API_PORT"] == "6060"
    assert get_settings().BACKEND_PORT == 6060
