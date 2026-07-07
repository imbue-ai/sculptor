import concurrent.futures
import threading
from pathlib import Path

import pytest

import sculptor.services.user_config.user_config as user_config_module
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import canonicalize_telemetry_flags
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import make_onboarded_user_config
from sculptor.services.user_config.user_config import merge_config
from sculptor.services.user_config.user_config import save_config
from sculptor.services.user_config.user_config import seed_onboarded_config_if_needed


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


def test_make_onboarded_user_config_sets_consent_and_enables_telemetry() -> None:
    base = _make_config(is_error_reporting_enabled=False, is_product_analytics_enabled=False)
    assert base.is_privacy_policy_consented is False
    assert base.is_telemetry_level_set is False

    onboarded = make_onboarded_user_config(base, is_telemetry_enabled=True)

    assert onboarded.is_privacy_policy_consented is True
    assert onboarded.is_telemetry_level_set is True
    assert onboarded.is_error_reporting_enabled is True
    assert onboarded.is_product_analytics_enabled is True
    # Session recording has no consent toggle and stays off even when telemetry is on.
    assert onboarded.is_session_recording_enabled is False
    # Identity fields are carried through untouched.
    assert onboarded.user_email == base.user_email


def test_make_onboarded_user_config_can_disable_telemetry() -> None:
    onboarded = make_onboarded_user_config(_make_config(), is_telemetry_enabled=False)

    assert onboarded.is_privacy_policy_consented is True
    assert onboarded.is_telemetry_level_set is True
    assert onboarded.is_error_reporting_enabled is False
    assert onboarded.is_product_analytics_enabled is False
    assert onboarded.is_session_recording_enabled is False


def test_seed_onboarded_config_writes_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    wrote = seed_onboarded_config_if_needed(config_path, is_telemetry_enabled=False)

    assert wrote is True
    seeded = load_config(config_path)
    assert seeded.is_privacy_policy_consented is True
    assert seeded.is_telemetry_level_set is True
    assert seeded.is_error_reporting_enabled is False
    assert seeded.is_product_analytics_enabled is False


def test_seed_onboarded_config_is_idempotent_for_onboarded_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    assert seed_onboarded_config_if_needed(config_path, is_telemetry_enabled=False) is True
    original_bytes = config_path.read_bytes()

    # A second call must leave an already-onboarded config exactly as-is.
    assert seed_onboarded_config_if_needed(config_path, is_telemetry_enabled=True) is False
    assert config_path.read_bytes() == original_bytes


def test_seed_onboarded_config_completes_partially_onboarded_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    not_onboarded = _make_config()
    assert not_onboarded.is_privacy_policy_consented is False
    save_config(not_onboarded, config_path)

    wrote = seed_onboarded_config_if_needed(config_path, is_telemetry_enabled=False)

    assert wrote is True
    completed = load_config(config_path)
    assert completed.is_privacy_policy_consented is True
    assert completed.is_telemetry_level_set is True
    # The developer's existing identity is preserved rather than reset to the default.
    assert completed.user_email == not_onboarded.user_email


def test_seed_onboarded_config_overwrites_corrupt_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is not valid toml = = =")

    wrote = seed_onboarded_config_if_needed(config_path, is_telemetry_enabled=False)

    assert wrote is True
    recovered = load_config(config_path)
    assert recovered.is_privacy_policy_consented is True
    assert recovered.is_telemetry_level_set is True


# Concurrency regression test: concurrent partial updates to different fields
# must both be preserved on the singleton and on disk (SCU-710). The test
# calls ``merge_config`` directly — the same function the PUT handler calls —
# so it exercises the real locked write path, not a replica.


@pytest.mark.parametrize("iteration", range(30))
def test_concurrent_partial_updates_preserve_both_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, iteration: int
) -> None:
    """Two concurrent ``merge_config`` calls each contribute their field.

    Without the internal lock this test loses one of the two writes on
    disk. ``iteration`` parametrization forces many attempts per pytest
    run to make a missing lock visible.
    """
    config_path = tmp_path / f"config_{iteration}.toml"
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", config_path)

    base = _make_config()
    save_config(base, config_path)
    user_config_module.set_user_config_instance(base)

    barrier = threading.Barrier(2)

    def update_email() -> None:
        barrier.wait()
        merge_config({"userEmail": "thread_a@example.com"})

    def update_user_id() -> None:
        barrier.wait()
        merge_config({"userId": "thread_b_user_id"})

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(update_email), pool.submit(update_user_id)]
            for fut in futures:
                fut.result(timeout=10)

        final_singleton = user_config_module.get_user_config_instance()
        assert final_singleton.user_email == "thread_a@example.com"
        assert final_singleton.user_id == "thread_b_user_id"

        final_on_disk = user_config_module.load_config(config_path)
        assert final_on_disk.user_email == "thread_a@example.com"
        assert final_on_disk.user_id == "thread_b_user_id"
    finally:
        user_config_module.set_user_config_instance(None)
