import tempfile
from pathlib import Path
from typing import Any
from typing import Generator

import pytest

from imbue_core.pydantic_utils import model_update
from imbue_core.sculptor.user_config import UserConfig
from sculptor.config.user_config import create_organization_id
from sculptor.config.user_config import create_user_id
from sculptor.config.user_config import get_default_user_config_instance
from sculptor.config.user_config import get_execution_instance_id
from sculptor.config.user_config import get_user_config_instance
from sculptor.config.user_config import load_config
from sculptor.config.user_config import save_config
from sculptor.config.user_config import set_user_config_instance
from sculptor.config.user_config import update_user_consent_level
from sculptor.config.user_config_fixture import populate_config_file_for_test

_TEST_API_KEY = "sk-ant-api03-testingkey"
_TEST_USER_EMAIL = "test@example.com"
_TEST_USER_GIT_USERNAME = "testuser"


@pytest.fixture
def temp_config_path() -> Generator[Path, None, None]:
    """Create a temporary config path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as temp_file:
        config_path = Path(temp_file.name)
    # Remove the file, we just want the path, the actual file will be
    # written at a later time as part of tests.
    config_path.unlink()
    yield config_path
    # Cleanup
    if config_path.exists():
        config_path.unlink()


# Keep up to date with additional fields added in:
# generally_intelligent/imbue_core/imbue_core/sculptor/user_config.py
_TEST_USER_CONFIG = UserConfig(
    user_email=_TEST_USER_EMAIL,
    user_git_username=_TEST_USER_GIT_USERNAME,
    user_id=create_user_id(_TEST_USER_EMAIL),
    organization_id=create_organization_id(_TEST_USER_EMAIL),
    instance_id="test_instance_id",
    anonymous_access_token="test_token",
    is_error_reporting_enabled=True,
    is_product_analytics_enabled=True,
    is_llm_logs_enabled=True,
    is_session_recording_enabled=True,
    is_repo_backup_enabled=True,
    is_privacy_policy_consented=True,
    is_suggestion_beta_feature_on=True,
)


def _create_test_config_file(config_path: Path, override_fields: dict[str, Any] | None) -> UserConfig:
    """Helper function to create a test config file with specified parameters.

    Args:
        config_path: Path where the config file should be saved
        override_fields: Optional UserConfig parameters to override defaults

    Returns:
        The UserConfig object that was saved to file
    """
    # Update with any provided overrides
    if override_fields:
        config = model_update(_TEST_USER_CONFIG, override_fields)
        save_config(config, config_path)
        return config
    return _TEST_USER_CONFIG


def test_save_config_writes_user_config_to_file(temp_config_path: Path) -> None:
    """Test that save_config correctly writes a UserConfig object to file."""
    test_config = model_update(
        _TEST_USER_CONFIG,
        {
            "is_error_reporting_enabled": False,
            "is_product_analytics_enabled": True,
            "is_llm_logs_enabled": False,
            "is_session_recording_enabled": False,
            "is_repo_backup_enabled": True,
            "anthropic_api_key": _TEST_API_KEY,
            "is_privacy_policy_consented": False,
        },
    )

    # Save config to file
    save_config(test_config, temp_config_path)

    # Verify file was created
    assert temp_config_path.exists()

    # Read file contents and verify structure
    content = temp_config_path.read_text()
    assert f'user_email = "{_TEST_USER_EMAIL}"' in content
    assert f'user_git_username = "{_TEST_USER_GIT_USERNAME}"' in content
    assert f'user_id = "{create_user_id(_TEST_USER_EMAIL)}"' in content
    assert f'organization_id = "{create_organization_id(_TEST_USER_EMAIL)}"' in content
    assert "is_error_reporting_enabled = false" in content
    assert "is_product_analytics_enabled = true" in content
    assert "is_privacy_policy_consented = false" in content
    assert f'anthropic_api_key = "{_TEST_API_KEY}"' in content


def test_load_config_reads_user_config_from_file(temp_config_path: Path) -> None:
    """Test that load_config correctly reads a UserConfig object from file."""
    test_config = model_update(
        _TEST_USER_CONFIG,
        {
            "is_error_reporting_enabled": False,
            "is_product_analytics_enabled": True,
            "anthropic_api_key": _TEST_API_KEY,
        },
    )

    # Save config to file first
    save_config(test_config, temp_config_path)

    # Load config from file
    loaded_config = load_config(temp_config_path)

    # Verify loaded config matches saved config
    assert loaded_config.user_email == _TEST_USER_EMAIL
    assert loaded_config.user_git_username == _TEST_USER_GIT_USERNAME
    assert loaded_config.is_error_reporting_enabled is False
    assert loaded_config.is_product_analytics_enabled is True
    assert loaded_config.anthropic_api_key == _TEST_API_KEY


def test_parse_user_consent_toggle_from_level() -> None:
    """Test that parse_user_consent_toggle_from_level correctly sets consent flags."""
    base_config = _TEST_USER_CONFIG

    # Test level 0 (all disabled)
    result_0 = update_user_consent_level(base_config, 0)
    assert result_0.is_error_reporting_enabled is False
    assert result_0.is_product_analytics_enabled is False
    assert result_0.is_llm_logs_enabled is False
    assert result_0.is_session_recording_enabled is False

    # Test level 2 (error reporting and analytics enabled)
    result_2 = update_user_consent_level(base_config, 2)
    assert result_2.is_error_reporting_enabled is True
    assert result_2.is_product_analytics_enabled is True
    assert result_2.is_llm_logs_enabled is False
    assert result_2.is_session_recording_enabled is False

    # Test level 4 (All except session recording)
    result_4 = update_user_consent_level(base_config, 4)
    assert result_4.is_error_reporting_enabled is True
    assert result_4.is_product_analytics_enabled is True
    assert result_4.is_llm_logs_enabled is True
    assert result_4.is_session_recording_enabled is False


def test_config_instance_management() -> None:
    """Test that config instance getter/setter work correctly."""
    # Initially should be None
    # FIXME: stop using globals for state like this.
    if get_user_config_instance() is not None:
        set_user_config_instance(None)

    # Set a config instance
    test_config = _TEST_USER_CONFIG
    set_user_config_instance(test_config)

    # Verify it was set
    retrieved_config = get_user_config_instance()
    assert retrieved_config is not None
    assert retrieved_config.user_email == _TEST_USER_EMAIL


def test_get_default_user_config_instance() -> None:
    """Test that get_default_user_config_instance returns a valid default config."""
    default_config = get_default_user_config_instance()

    assert default_config is not None
    assert default_config.user_email == ""
    assert default_config.is_error_reporting_enabled is True
    assert default_config.is_privacy_policy_consented is False


def test_get_execution_instance_id() -> None:
    """Test that get_execution_instance_id returns a valid instance ID."""
    instance_id = get_execution_instance_id()

    assert instance_id is not None
    assert isinstance(instance_id, str)
    assert len(instance_id) > 0

    # Should return the same ID on subsequent calls
    assert get_execution_instance_id() == instance_id


def test_populate_config_file_for_test(temp_config_path: Path) -> None:
    """Test that populate_config_file_for_test creates a valid test config file."""
    populate_config_file_for_test(temp_config_path)

    # Verify config file was created
    assert temp_config_path.exists()

    # Load and verify the config
    config = load_config(temp_config_path)
    assert config.user_email == "test@imbue.com"
    assert config.is_privacy_policy_consented is True
    assert config.anthropic_api_key is not None


def test_create_user_id_and_organization_id() -> None:
    """Test that user ID and organization ID are created consistently."""
    email = "test@example.com"

    user_id = create_user_id(email)
    org_id = create_organization_id(email)

    # Should return consistent results
    assert create_user_id(email) == user_id
    assert create_organization_id(email) == org_id

    # Should be different for different emails
    other_email = "other@example.com"
    assert create_user_id(other_email) != user_id
    assert create_organization_id(other_email) != org_id

    # Should be different from each other
    assert user_id != org_id
