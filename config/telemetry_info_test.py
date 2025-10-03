"""Tests for telemetry_info module."""

import os
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from imbue_core.sculptor.user_config import UserConfig
from sculptor.config.telemetry_info import DEV_POSTHOG_HOST
from sculptor.config.telemetry_info import DEV_POSTHOG_TOKEN
from sculptor.config.telemetry_info import PROD_POSTHOG_HOST
from sculptor.config.telemetry_info import PROD_POSTHOG_TOKEN
from sculptor.config.telemetry_info import _get_posthog_token_and_api_host


@pytest.mark.parametrize("env_value", ["1", "true", "TRUE", "True"])
def test_uses_production_when_env_var_is_true(env_value) -> None:
    """Test that production instance is used when USE_PROD_POSTHOG=TRUE."""
    user_config = Mock(spec=UserConfig)
    user_config.user_email = "user@imbue.com"

    with patch.dict(os.environ, {"USE_PROD_POSTHOG": env_value}):
        token, host = _get_posthog_token_and_api_host(user_config)

    assert token == PROD_POSTHOG_TOKEN
    assert host == PROD_POSTHOG_HOST


@pytest.mark.parametrize("env_value", ["0", "false", "FALSE", "False"])
def test_uses_development_when_env_var_is_false(env_value) -> None:
    """Test that development instance is used when USE_PROD_POSTHOG=0"""
    user_config = Mock(spec=UserConfig)
    user_config.user_email = "user@imbue.com"

    with patch.dict(os.environ, {"USE_PROD_POSTHOG": env_value}):
        token, host = _get_posthog_token_and_api_host(user_config)

    assert token == DEV_POSTHOG_TOKEN
    assert host == DEV_POSTHOG_HOST


@pytest.mark.parametrize("env_value", ["2", "yes", "on", "1.0", ""])
def test_invalid_env_values_raise_assertion_error(env_value) -> None:
    """Test that invalid environment variable values raise AssertionError."""
    user_config = Mock(spec=UserConfig)
    user_config.user_email = "user@imbue.com"

    with patch.dict(os.environ, {"USE_PROD_POSTHOG": env_value}):
        with pytest.raises(AssertionError, match="USE_PROD_POSTHOG environment variable must be"):
            _get_posthog_token_and_api_host(user_config)


def test_empty_email_uses_development_when_env_var_not_set() -> None:
    """Test that development instance is used when user email is empty and USE_PROD_POSTHOG is not set."""
    user_config = Mock(spec=UserConfig)
    user_config.user_email = ""

    with patch.dict(os.environ, {}, clear=True):
        token, host = _get_posthog_token_and_api_host(user_config)

    assert token == DEV_POSTHOG_TOKEN
    assert host == DEV_POSTHOG_HOST


def test_empty_email_uses_prod_when_env_var_is_set() -> None:
    """Test that production instance is used when user email is empty and USE_PROD_POSTHOG is set."""
    user_config = Mock(spec=UserConfig)
    user_config.user_email = ""

    with patch.dict(os.environ, {"USE_PROD_POSTHOG": "1"}):
        token, host = _get_posthog_token_and_api_host(user_config)

    assert token == PROD_POSTHOG_TOKEN
    assert host == PROD_POSTHOG_HOST
