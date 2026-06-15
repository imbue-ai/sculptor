import hashlib
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomlkit
from loguru import logger
from pydantic import ValidationError

from sculptor.config.user_config import PrivacySettings
from sculptor.config.user_config import UserConfig
from sculptor.foundation.pydantic_utils import model_update
from sculptor.utils.build import get_internal_folder


class InvalidConfigError(Exception):
    """Exception raised when the configuration is invalid."""

    def __init__(self, error: Exception) -> None:
        """Wrap the underlying error in a user-facing config-load message."""
        self.message = f"Unhandled error loading your config file:\n{error}"
        super().__init__(self.message)


_CONFIG_INSTANCE: UserConfig | None = None


def get_user_config_instance() -> UserConfig:
    """Get the global config instance if one exists."""
    return _CONFIG_INSTANCE or get_default_user_config_instance()


def set_user_config_instance(config: UserConfig | None) -> None:
    """Set the global config instance."""
    # The file log sink captures DEBUG and is bundled into bug-report
    # diagnostics uploads — log only whether an email is set, never its value.
    logger.debug(
        "Setting global user config instance (has_email={})",
        bool(config.user_email) if config is not None else None,
    )
    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = config


def _create_random_hash() -> str:
    return hashlib.md5(os.urandom(64)).hexdigest()


_EXECUTION_INSTANCE_ID: str = _create_random_hash()


def get_execution_instance_id() -> str:
    """Get the current execution instance ID.

    It is used to identify this unique run of Sculptor and is additionally persisted as an installation identifier
    the first time we generate user config.
    """
    return _EXECUTION_INSTANCE_ID


# Telemetry consent is binary: either the SDK-facing flags are on (the default,
# stipulated by our terms and conditions) or everything is off. Session recording
# is always written as off — it has no user-facing toggle and the consent
# endpoints never enable it.
TELEMETRY_ENABLED_PRIVACY_SETTINGS = PrivacySettings(
    is_error_reporting_enabled=True,
    is_product_analytics_enabled=True,
    is_session_recording_enabled=False,
)
TELEMETRY_DISABLED_PRIVACY_SETTINGS = PrivacySettings(
    is_error_reporting_enabled=False,
    is_product_analytics_enabled=False,
    is_session_recording_enabled=False,
)


def get_privacy_settings_for_telemetry(is_enabled: bool) -> PrivacySettings:
    """Return the canonical privacy settings for the given telemetry consent."""
    return TELEMETRY_ENABLED_PRIVACY_SETTINGS if is_enabled else TELEMETRY_DISABLED_PRIVACY_SETTINGS


def canonicalize_telemetry_flags(config: UserConfig) -> UserConfig:
    """Collapse a mixed telemetry consent back to the canonical binary.

    The consent endpoints always write is_error_reporting_enabled and
    is_product_analytics_enabled together, so the flags can only diverge in
    old or hand-edited config files. Normalize in the conservative
    direction — everything off — so nobody gains tracking they didn't choose.

    Returns the input instance unchanged (identity-preserving) when the
    config is already canonical.
    """
    if config.is_error_reporting_enabled == config.is_product_analytics_enabled:
        return config
    return model_update(config, TELEMETRY_DISABLED_PRIVACY_SETTINGS.model_dump())


def _generate_default_config_path() -> Path:
    return get_internal_folder() / "config.toml"


_CONFIG_PATH = _generate_default_config_path()


def get_config_path() -> Path:
    """Get the path to the config file."""
    return _CONFIG_PATH


def load_config(config_path: Path) -> UserConfig:
    """Load and validate a UserConfig from the given TOML file."""
    assert config_path.exists(), f"Config file does not exist at {config_path}"

    try:
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)

            config_dict = dict(config_data)

            if "instance_id" not in config_dict:
                # populate the persistent instance id with the execution one if missing
                config_dict["instance_id"] = get_execution_instance_id()

            config = UserConfig(**config_dict)
            return config
    except ValidationError as e:
        raise InvalidConfigError(e) from e


def _sanitize_for_toml(data: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively convert None values to empty strings for TOML compatibility.

    model_dump(exclude_none=True) only excludes top-level None fields,
    not None values inside dict-typed fields. TOML cannot represent None,
    so we convert them to empty strings to preserve the "explicitly cleared" state.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            result[key] = ""
        elif isinstance(value, dict):
            # pyrefly: ignore [unsupported-operation]
            result[key] = _sanitize_for_toml(value)
        else:
            result[key] = value
    return result


def save_config(config: UserConfig, config_path: Path) -> None:
    """Writes the given config out to disk.

    Beware: Does not update the local configuration instance!"""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # atomically write the config file
    with open(config_path.with_suffix(".tmp"), "w") as f:
        tomlkit.dump(_sanitize_for_toml(config.model_dump(exclude_none=True)), f)
    config_path.with_suffix(".tmp").rename(config_path)


def _generate_default_user_config_instance() -> UserConfig:
    """Generates a default, anonymized user config instance.

    This spins up a fake user for onboarding purposes with an instance id.

    This will uses the minimal consent level we support at the given time.
    """

    return UserConfig(
        user_email="",
        user_id=get_execution_instance_id(),
        organization_id=get_execution_instance_id(),
        instance_id=get_execution_instance_id(),
        is_privacy_policy_consented=False,
        is_telemetry_level_set=False,
        **TELEMETRY_ENABLED_PRIVACY_SETTINGS.model_dump(),
    )


_DEFAULT_CONFIG_INSTANCE: UserConfig = _generate_default_user_config_instance()


def get_default_user_config_instance() -> UserConfig:
    """Return the process-wide default (anonymized) user config instance."""
    return _DEFAULT_CONFIG_INSTANCE


def initialize_from_file() -> bool:
    """Initializes the global singleton UserConfig instance from the default file location.

    Returns:
        True if we were able to successfully load from that file.
        If False, it indicates that onboarding is required due to a missing or corrupted file
    """
    config_path = get_config_path()
    if config_path.exists():
        try:
            config = load_config(config_path)
            canonical_config = canonicalize_telemetry_flags(config)
            if canonical_config is not config:
                logger.info("Normalized mixed telemetry consent flags to disabled")
                save_config(canonical_config, config_path)
            set_user_config_instance(canonical_config)
            return True
        except (ValidationError, InvalidConfigError) as e:
            logger.info("Failed to load config, will require onboarding: {}", e)
            return False
    else:
        logger.info("No config file found at {}, will require onboarding", config_path)
        return False
