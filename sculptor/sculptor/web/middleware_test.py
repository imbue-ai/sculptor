from collections.abc import Iterator

import pytest

from sculptor.web.middleware import get_settings


@pytest.fixture
def fresh_settings_cache() -> Iterator[None]:
    """Isolate this module's tests from any get_settings() call elsewhere in the
    pytest process, and leave no snapshot behind for later tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_settings_returns_the_same_snapshot_every_call(fresh_settings_cache: None) -> None:
    assert get_settings() is get_settings()


def test_get_settings_snapshot_is_immune_to_runtime_env_changes(
    fresh_settings_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Settings are parsed from the environment once; a runtime env perturbation
    # must not flip settings-gated behavior mid-session (e.g. the FakeClaude
    # model gate).
    monkeypatch.setenv("TESTING__INTEGRATION_ENABLED", "true")
    first = get_settings()
    assert first.TESTING.INTEGRATION_ENABLED is True

    monkeypatch.setenv("TESTING__INTEGRATION_ENABLED", "false")
    assert get_settings() is first
    assert get_settings().TESTING.INTEGRATION_ENABLED is True
