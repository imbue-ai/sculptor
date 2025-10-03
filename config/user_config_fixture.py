"""Fixtures and functions for working with the user_config module."""

import os
from pathlib import Path

from imbue_core.pydantic_utils import model_update
from imbue_core.sculptor.user_config import UserConfig
from sculptor.config import user_config


def _make_test_config_from_user_email(user_email: str) -> UserConfig:
    # Preserve the instance_id generated at the start of each uvx session
    instance_id = user_config._DEFAULT_CONFIG_INSTANCE.instance_id

    return UserConfig(
        user_email=user_email,
        user_git_username=user_email.split("@")[0],  # Default git username from email
        user_id=user_config.create_user_id(user_email),
        anonymous_access_token=user_config._create_random_hash(),
        organization_id=user_config.create_organization_id(user_email),
        # Instance id should be unique to each start of sculptor.
        instance_id=instance_id,
        is_error_reporting_enabled=True,
        is_product_analytics_enabled=True,
        is_llm_logs_enabled=True,
        is_session_recording_enabled=True,
        is_repo_backup_enabled=True,
        is_privacy_policy_consented=True,
        is_telemetry_level_set=True,
        has_seen_pairing_mode_modal=True,
        is_suggestion_beta_feature_on=True,
        is_forking_beta_feature_on=True,
    )


def populate_config_file_for_test(path: Path) -> None:
    config = _make_test_config_from_user_email("test@imbue.com")
    # Add a fake API key for testing that passes validation (must start with "sk-ant")
    fake_api_key = "sk-ant-fake-key-for-testing-purposes-only-123456789"
    # Take the environment key to avoid confirmation message blocking server setup (if available)
    config = model_update(
        config,
        {"anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", fake_api_key), "is_privacy_policy_consented": True},
    )
    user_config.save_config(config, path)
