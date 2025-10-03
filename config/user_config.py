import hashlib
import os
import tomllib
from pathlib import Path
from typing import Literal
from typing import Mapping

import tomlkit
from loguru import logger
from pydantic import ValidationError

from imbue_core.pydantic_utils import model_update
from imbue_core.sculptor.user_config import PrivacySettings
from imbue_core.sculptor.user_config import UserConfig
from sculptor.utils.build import get_sculptor_folder


class InvalidConfigError(Exception):
    """Exception raised when the configuration is invalid."""

    def __init__(self, error: Exception) -> None:
        """Initialize with validation errors.

        Args:
            errors: List of validation errors
        """
        self.message = f"Unhandled error loading your config file:\n{error}"
        super().__init__(self.message)


_CONFIG_INSTANCE: UserConfig | None = None


def get_user_config_instance() -> UserConfig | None:
    """Get the global config instance if one exists."""
    return _CONFIG_INSTANCE


def set_user_config_instance(config: UserConfig) -> None:
    """Set the global config instance."""
    logger.debug("Setting global user config instance (email={})", config.user_email if config is not None else None)
    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = config


def _create_random_hash() -> str:
    return hashlib.md5(os.urandom(64)).hexdigest()


# TODO(PROD-1347): Need to pass instance_id into task docker containers as well.
_EXECUTION_INSTANCE_ID: str = _create_random_hash()


def get_execution_instance_id() -> str:
    """Get the current execution instance ID."""
    return _EXECUTION_INSTANCE_ID


# We support the following Telemetry Levels
TelemetryLevel = Literal[0, 1, 2, 3, 4]

# Our terms and conditions stipulate that using Sculptor start settings at level 2
MINIMUM_TELEMETRY_LEVEL = 2


# This is the source of truth for what settings should be for a given TelemetryLevel
TELEMETRY_LEVEL_TO_PRIVACY_SETTINGS: Mapping[TelemetryLevel, PrivacySettings] = {
    0: PrivacySettings(
        is_error_reporting_enabled=False,
        is_product_analytics_enabled=False,
        is_llm_logs_enabled=False,
        is_session_recording_enabled=False,
        is_repo_backup_enabled=False,
        is_full_contribution=False,
    ),
    1: PrivacySettings(
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=False,
        is_llm_logs_enabled=False,
        is_session_recording_enabled=False,
        is_repo_backup_enabled=False,
        is_full_contribution=False,
    ),
    2: PrivacySettings(
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_llm_logs_enabled=False,
        is_session_recording_enabled=False,
        is_repo_backup_enabled=False,
        is_full_contribution=False,
    ),
    3: PrivacySettings(
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_llm_logs_enabled=True,
        is_session_recording_enabled=False,
        is_repo_backup_enabled=False,
        is_full_contribution=False,
    ),
    4: PrivacySettings(
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_llm_logs_enabled=True,
        # Still not enabled for the following
        is_session_recording_enabled=False,
        is_repo_backup_enabled=False,
        is_full_contribution=True,
    ),
}


def update_user_consent_level(user_config: UserConfig, telemetry_level: TelemetryLevel) -> UserConfig:
    """Given a TelemetryLevel, determine the concrete inner fields we need to set."""
    return model_update(user_config, TELEMETRY_LEVEL_TO_PRIVACY_SETTINGS[telemetry_level].model_dump())


def _generate_default_config_path() -> Path:
    config_dir = get_sculptor_folder()
    config_dir.mkdir(exist_ok=True)
    return config_dir / "config.toml"


_CONFIG_PATH = _generate_default_config_path()


def get_config_path() -> Path:
    """Get the path to the config file."""
    return _CONFIG_PATH


def _create_hash_from_string_seed(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()


def create_user_id(email: str) -> str:
    return _create_hash_from_string_seed(email)


def create_organization_id(email: str) -> str:
    return _create_hash_from_string_seed(f"organization:{email}")


def load_config(config_path: Path) -> UserConfig:
    assert config_path.exists(), f"Config file does not exist at {config_path}"

    try:
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)

            config_dict = dict(config_data)

            if "anonymous_access_token" not in config_dict:
                config_dict["anonymous_access_token"] = _create_random_hash()

            if "instance_id" not in config_dict:
                config_dict["instance_id"] = _EXECUTION_INSTANCE_ID

            config = UserConfig(**config_dict)
            return config
    except ValidationError as e:
        raise InvalidConfigError(e)


def save_config(config: UserConfig, config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # atomically write the config file
    with open(config_path.with_suffix(".tmp"), "w") as f:
        tomlkit.dump(config.model_dump(exclude_none=True), f)
    config_path.with_suffix(".tmp").rename(config_path)


def _generate_default_user_config_instance() -> UserConfig:
    """Generates a default, anonymized user config instance.

    This spins up a fake user for onboarding purposes with an instance id.

    This will uses the minimal consent level we support at the given time.
    """

    return UserConfig(
        user_email="",
        user_git_username="",
        user_id=_EXECUTION_INSTANCE_ID,
        anonymous_access_token=_create_random_hash(),
        organization_id=_EXECUTION_INSTANCE_ID,
        instance_id=_EXECUTION_INSTANCE_ID,
        is_privacy_policy_consented=False,
        is_telemetry_level_set=False,
        **TELEMETRY_LEVEL_TO_PRIVACY_SETTINGS[MINIMUM_TELEMETRY_LEVEL].model_dump(),
    )


_DEFAULT_CONFIG_INSTANCE: UserConfig = _generate_default_user_config_instance()


def get_default_user_config_instance() -> UserConfig:
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
            set_user_config_instance(load_config(config_path))
            return True
        except ValidationError as e:
            logger.info("Failed to load config, will require onboarding: {}", e)
            return False
    else:
        logger.info("No config file found at {}, will require onboarding", config_path)
        return False
