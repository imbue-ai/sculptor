from pathlib import Path

import pytest

import sculptor.services.user_config.user_config as user_config_module
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import canonicalize_telemetry_flags
from sculptor.services.user_config.user_config import save_config


def _make_config(
    is_error_reporting_enabled: bool = True,
    is_product_analytics_enabled: bool = True,
) -> UserConfig:
    return UserConfig(
        user_email="alice@example.com",
        user_id="user_123",
        organization_id="org_123",
        instance_id="instance_123",
        is_error_reporting_enabled=is_error_reporting_enabled,
        is_product_analytics_enabled=is_product_analytics_enabled,
        is_session_recording_enabled=False,
    )


def test_canonicalize_passes_canonical_configs_through_unchanged() -> None:
    enabled = _make_config()
    assert canonicalize_telemetry_flags(enabled) is enabled

    disabled = _make_config(is_error_reporting_enabled=False, is_product_analytics_enabled=False)
    assert canonicalize_telemetry_flags(disabled) is disabled


@pytest.mark.parametrize(
    ("is_error_reporting_enabled", "is_product_analytics_enabled"),
    (
        (True, False),
        (False, True),
    ),
)
def test_canonicalize_normalizes_mixed_flags_to_disabled(
    is_error_reporting_enabled: bool, is_product_analytics_enabled: bool
) -> None:
    mixed = _make_config(
        is_error_reporting_enabled=is_error_reporting_enabled,
        is_product_analytics_enabled=is_product_analytics_enabled,
    )

    canonical = canonicalize_telemetry_flags(mixed)

    assert canonical is not mixed
    assert canonical.is_error_reporting_enabled is False
    assert canonical.is_product_analytics_enabled is False
    assert canonical.is_session_recording_enabled is False
    # Everything unrelated to telemetry consent is untouched.
    assert canonical.user_email == mixed.user_email


def test_initialize_from_file_normalizes_mixed_flags_and_persists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    mixed = _make_config(is_product_analytics_enabled=False)
    assert mixed.is_error_reporting_enabled is True
    save_config(mixed, user_config_module.get_config_path())

    try:
        assert user_config_module.initialize_from_file() is True

        loaded = user_config_module.get_user_config_instance()
        assert loaded.is_error_reporting_enabled is False
        assert loaded.is_product_analytics_enabled is False

        # The normalization is written back so the on-disk file is canonical too.
        reloaded = user_config_module.load_config(user_config_module.get_config_path())
        assert reloaded.is_error_reporting_enabled is False
        assert reloaded.is_product_analytics_enabled is False
    finally:
        user_config_module.set_user_config_instance(None)
