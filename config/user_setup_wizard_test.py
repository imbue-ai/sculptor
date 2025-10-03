import os
import tempfile
from pathlib import Path
from typing import Any
from typing import Generator
from unittest.mock import patch

import pytest

from imbue_core.processes.local_process import run_blocking
from imbue_core.pydantic_utils import model_update
from imbue_core.sculptor.user_config import UserConfig
from imbue_core.subprocess_utils import ProcessError
from sculptor.config.user_config import create_organization_id
from sculptor.config.user_config import create_user_id
from sculptor.config.user_config import save_config
from sculptor.config.user_setup_wizard import _INIT_GIT_COMMIT_MESSAGE
from sculptor.config.user_setup_wizard import _setup_initial_git_commit
from sculptor.config.user_setup_wizard import _should_prompt_for_user_consent
from sculptor.config.user_setup_wizard import _try_loading_config_file
from sculptor.config.user_setup_wizard import run_config_wizard
from sculptor.startup_checks import check_anthropic_api_key
from sculptor.startup_checks import check_git_repo_is_not_empty
from sculptor.startup_checks import check_is_git_repo
from sculptor.startup_checks import check_path_is_git_repo_root

_TEST_API_KEY = "sk-ant-api03-testingkey"
_TEST_USER_EMAIL = "test@example.com"
_TEST_USER_GIT_USERNAME = "testuser"


@pytest.fixture
def temp_repo_path() -> Generator[Path, None, None]:
    """Create a temporary repository path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)
        _setup_initial_git_commit(repo_path)
        yield Path(temp_dir)


@pytest.fixture
def temp_config_path() -> Generator[Path, None, None]:
    """Create a temporary config path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as temp_file:
        config_path = Path(temp_file.name)
    # Remove the file, we just want the path, the actual file will be
    # written at a later time as part of run_config_wizard under test.
    config_path.unlink()
    yield config_path
    # Cleanup
    if config_path.exists():
        config_path.unlink()


@pytest.fixture
def mock_dependencies() -> Generator[dict[str, Any], None, None]:
    """Mock common dependencies used across run_config_wizard tests."""
    with (
        patch("typer.prompt") as mock_prompt,
        patch("typer.confirm") as mock_confirm,
        patch("sculptor.config.user_setup_wizard.emit_posthog_event") as mock_emit_posthog,
        patch("sculptor.config.user_setup_wizard.identify_posthog_user"),
        patch("sculptor.config.user_setup_wizard._get_git_email_or_empty", return_value="") as mock_git_email,
    ):
        yield {
            "typer.prompt": mock_prompt,
            "typer.confirm": mock_confirm,
            "emit_posthog_event": mock_emit_posthog,
            "_get_git_email_or_empty": mock_git_email,
        }


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


def test_should_prompt_for_user_consent_with_missing_fields() -> None:
    """Test that _should_prompt_for_user_consent returns True for config with missing fields."""
    config_missing_fields = UserConfig(
        user_email="test@example.com",
        user_git_username="test",
        user_id="test_id",
        anonymous_access_token="test_token",
        organization_id="test_org",
        instance_id="test_instance",
        is_suggestion_beta_feature_on=True,
    )
    assert _should_prompt_for_user_consent(config_missing_fields) is True


def test_should_not_prompt_for_user_consent_with_complete_config() -> None:
    """Test that _should_prompt_for_user_consent returns False for config with all fields set."""
    assert _should_prompt_for_user_consent(_TEST_USER_CONFIG) is False


def test_should_prompt_for_user_consent_with_disabled_error_reporting() -> None:
    """Test that _should_prompt_for_user_consent returns True for config with disabled error reporting (alpha tester restriction)."""
    config_disabled_error = model_update(_TEST_USER_CONFIG, {"is_error_reporting_enabled": False})
    assert _should_prompt_for_user_consent(config_disabled_error) is True


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_user_config_wizard_no_config_file(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Tests configuration flow when no config file is found.

    end-to-end test for run_config_wizard.
    """
    mock_dependencies["_get_git_email_or_empty"].return_value = "test@example.com"

    # Mock user inputs
    mock_dependencies["typer.prompt"].side_effect = [
        "test@example.com",
        _TEST_USER_GIT_USERNAME,
        3,
    ]  # email, git user, telemetry level
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # privacy consent
        True,  # repo backup
        True,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify config was created with expected values
    assert result.user_email == "test@example.com"
    assert result.user_git_username == _TEST_USER_GIT_USERNAME
    assert result.anthropic_api_key == _TEST_API_KEY
    assert result.is_error_reporting_enabled is True
    assert result.is_product_analytics_enabled is True
    assert result.is_llm_logs_enabled is True
    assert result.is_session_recording_enabled is False
    assert result.is_repo_backup_enabled is True
    assert temp_config_path.exists()


@pytest.mark.parametrize(
    "config_file_contents",
    [
        "",  # Empty file config
        "invalid",  # invalid contents
    ],
)
@patch.dict("os.environ", {}, clear=True)
def test_user_config_initial_onboarding_flow(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any], config_file_contents: str
) -> None:
    """Tests initial onboarding flow from empty config."""
    # Load initial config file state
    temp_config_path.write_text(config_file_contents)

    # Mock user inputs
    mock_dependencies["typer.prompt"].side_effect = [
        "user@example.com",  # email
        _TEST_USER_GIT_USERNAME,  # user git username
        3,  # telemetry level
        _TEST_API_KEY,  # API key
    ]
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # privacy consent
        True,  # repo backup
        True,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify email and API key are set
    assert result.user_email == "user@example.com"
    # These will alert us with a failing test if we ever change the
    # way ids are generated (currently from md5 hashing).
    assert result.user_git_username == _TEST_USER_GIT_USERNAME
    assert result.user_id == "b58996c504c5638798eb6b511e6f49af"
    assert result.organization_id == "0ea5d41d06ca3af0ff220011da73905c"
    assert result.anthropic_api_key == _TEST_API_KEY
    assert os.environ.get("ANTHROPIC_API_KEY") == _TEST_API_KEY
    assert result.is_product_analytics_enabled is True

    # Verify config file was saved
    assert temp_config_path.exists()

    # The next time we execute run_config_wizard, it should not prompt
    # for the API key!

    # Mock user inputs (no inputs should be necessary)
    mock_dependencies["typer.prompt"].side_effect = []
    mock_dependencies["typer.confirm"].side_effect = []

    result = run_config_wizard(temp_repo_path, temp_config_path)
    assert result.user_email == "user@example.com"
    assert result.anthropic_api_key == _TEST_API_KEY, "second time user starts sculptor"


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_api_key_caching_config_api_key_empty(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test API key caching when environment variable differs from config file."""
    config_api_key = ""

    # Create a config file with an API key
    saved_config = _create_test_config_file(temp_config_path, {"anthropic_api_key": config_api_key})
    assert saved_config.anthropic_api_key == config_api_key

    # User confirms caching the new environment key
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify the environment API key was cached
    assert result.anthropic_api_key == _TEST_API_KEY
    # Verify config was saved with new key
    saved_config = _try_loading_config_file(temp_config_path, temp_repo_path)
    assert saved_config.anthropic_api_key == _TEST_API_KEY
    # Verify posthog events were emitted
    assert mock_dependencies["emit_posthog_event"].call_count >= 1


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_api_key_caching_env_different_from_config(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test API key caching when environment variable differs from config file."""
    config_api_key = "sk-ant-api03-configkey"

    # Create a config file with an API key
    _create_test_config_file(temp_config_path, {"anthropic_api_key": config_api_key})

    # User confirms caching the new environment key
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify the environment API key was cached
    assert result.anthropic_api_key == _TEST_API_KEY
    # Verify config was saved with new key
    saved_config = _try_loading_config_file(temp_config_path, temp_repo_path)
    assert saved_config.anthropic_api_key == _TEST_API_KEY
    # Verify posthog events were emitted
    assert mock_dependencies["emit_posthog_event"].call_count >= 1


@patch.dict("os.environ", {}, clear=True)
def test_api_key_caching_user_declines_to_cache(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test API key behavior when user declines to cache the API key."""
    # Create existing config file without API key
    _create_test_config_file(temp_config_path, {"anthropic_api_key": None})

    # Mock user inputs - only API key prompt and cache confirmation
    mock_dependencies["typer.prompt"].side_effect = [_TEST_API_KEY]  # API key
    mock_dependencies["typer.confirm"].side_effect = [
        False,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify API key is not saved to config but is set in environment
    assert result.anthropic_api_key is None
    assert os.environ.get("ANTHROPIC_API_KEY") == _TEST_API_KEY


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_api_key_caching_env_matches_config(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test API key behavior when environment and config match."""
    # Create a config file with matching API key
    _create_test_config_file(temp_config_path, {"anthropic_api_key": _TEST_API_KEY})

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify API key remains the same
    assert result.anthropic_api_key == _TEST_API_KEY

    # Verify config save was called and key remains the same
    saved_config = _try_loading_config_file(temp_config_path, temp_repo_path)
    assert saved_config.anthropic_api_key == _TEST_API_KEY


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_api_key_in_env_is_valid() -> None:
    """Test API key is valid when environment variable is set."""
    # Verify environment sets API KEY
    assert check_anthropic_api_key() is True


@patch.dict("os.environ", {}, clear=True)
def test_privacy_policy_prompted_when_false(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Tests that a user is always asked for privacy consent when set to False."""
    # Mock user inputs
    mock_dependencies["typer.prompt"].side_effect = [
        "user@example.com",  # email
        _TEST_USER_GIT_USERNAME,  # git username
    ]
    mock_dependencies["typer.confirm"].side_effect = [
        False,  # privacy consent
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify email and API key are set
    assert result.user_email == "user@example.com"
    assert result.user_git_username == _TEST_USER_GIT_USERNAME
    assert result.is_privacy_policy_consented is False

    # Verify no config file was saved
    assert temp_config_path.exists() is False

    # The next time we execute run_config_wizard, we should still
    # prompt the user for privacy consent!

    # Mock user inputs (since no configuration file was saved, all inputs necessary)
    mock_dependencies["typer.prompt"].side_effect = [
        "user@example.com",  # email
        _TEST_USER_GIT_USERNAME,  # git username
        3,  # telemetry level
        _TEST_API_KEY,  # API key
    ]
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # privacy consent
        True,  # repo backup
        True,  # cache API key
    ]

    result = run_config_wizard(temp_repo_path, temp_config_path)
    assert temp_config_path.exists()

    assert result.user_email == "user@example.com"
    assert result.user_git_username == _TEST_USER_GIT_USERNAME
    assert result.anthropic_api_key == _TEST_API_KEY, "second time user starts sculptor"
    assert result.is_privacy_policy_consented is True

    # Finally the next user flow should be entirely smooth
    mock_dependencies["typer.prompt"].side_effect = []
    mock_dependencies["typer.confirm"].side_effect = []

    result = run_config_wizard(temp_repo_path, temp_config_path)
    assert result.user_email == "user@example.com"
    assert result.anthropic_api_key == _TEST_API_KEY, "second time user starts sculptor"
    assert result.is_privacy_policy_consented is True


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_git_initial_repo_setup_from_empty_dir(temp_config_path: Path, mock_dependencies: dict[str, Any]) -> None:
    """Test successful git init and commit on empty directory."""
    # Create an empty directory to test git initialization
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_repo_path = Path(temp_dir)

        # Create a config file with matching API key
        _create_test_config_file(temp_config_path, {"anthropic_api_key": _TEST_API_KEY})

        mock_dependencies["typer.confirm"].side_effect = [
            True,  # create git init commit
        ]

        # Run the wizard
        _ = run_config_wizard(temp_repo_path, temp_config_path)

        # Verify config file successfully saved
        assert temp_config_path.exists()

        # Verify git repository exists and an initial commit has been made.
        assert check_git_repo_is_not_empty(temp_repo_path)
        assert check_is_git_repo(temp_repo_path)
        assert check_path_is_git_repo_root(temp_repo_path)

        # Verify the initial git commit message is valid
        git_log_result = run_blocking(
            command=["git", "log"],
            cwd=temp_repo_path,
        )
        assert _INIT_GIT_COMMIT_MESSAGE in git_log_result.stdout


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_git_initial_repo_setup_from_empty_dir_raises_exception(
    temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test we can catch and gracefully handle raised exceptions from git init setup."""
    # Create an empty directory to test git initialization
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_repo_path = Path(temp_dir)

        # Create a config file with matching API key
        _create_test_config_file(temp_config_path, {"anthropic_api_key": _TEST_API_KEY})

        mock_dependencies["typer.confirm"].side_effect = [
            True,  # create git init commit
        ]

        with patch("sculptor.config.user_setup_wizard.run_blocking") as mock_run_command:
            mock_run_command.side_effect = ProcessError(("git", "init"), 1, "", "git init failed")

            # Run the wizard
            _ = run_config_wizard(temp_repo_path, temp_config_path)

            # Verify config file successfully saved
            assert temp_config_path.exists()

            # Verify git repository does not exist due to the exception
            assert check_git_repo_is_not_empty(temp_repo_path) is False
            assert check_is_git_repo(temp_repo_path) is False
            assert check_path_is_git_repo_root(temp_repo_path) is False


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_modified_user_id_gets_corrected(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test API key behavior when environment and config match."""
    # Create a config file with matching API key
    _create_test_config_file(
        temp_config_path,
        {
            "user_id": "modified incorrect user id",
            "organization_id": "modified incorrect organization id",
            "anthropic_api_key": _TEST_API_KEY,
        },
    )

    # Running configuration wizard should load up and self-correct modified IDs
    result = run_config_wizard(temp_repo_path, temp_config_path)

    assert result.user_id == create_user_id(_TEST_USER_EMAIL)
    assert result.organization_id == create_organization_id(_TEST_USER_EMAIL)


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
@pytest.mark.parametrize("invalid_email", ["", "@@@.@", "invalid_email.com", "@invalid_email.com"])
def test_invalid_email_requires_user_prompt(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any], invalid_email: str
) -> None:
    """Test that an improperly specified email address will require an additional user prompt."""
    # Mock user inputs
    mock_dependencies["typer.prompt"].side_effect = [
        invalid_email,  # first invalid email
        _TEST_USER_EMAIL,  # this is a valid email
        _TEST_USER_GIT_USERNAME,  # user git username
        3,  # telemetry level
    ]
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # privacy consent
        True,  # repo backup
        True,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify config was created with expected values
    assert result.user_email == _TEST_USER_EMAIL
    assert result.user_git_username == _TEST_USER_GIT_USERNAME
    assert result.anthropic_api_key == _TEST_API_KEY
    assert result.is_error_reporting_enabled is True
    assert result.is_product_analytics_enabled is True
    assert result.is_llm_logs_enabled is True
    assert result.is_session_recording_enabled is False
    assert result.is_repo_backup_enabled is True
    assert temp_config_path.exists()


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": _TEST_API_KEY})
def test_invalid_email_prompts_until_valid(
    temp_repo_path: Path, temp_config_path: Path, mock_dependencies: dict[str, Any]
) -> None:
    """Test that an improperly specified email address will require an additional user prompt."""
    # Mock user inputs
    mock_dependencies["typer.prompt"].side_effect = [
        "",  # first invalid email
        "invalid",  # another invalid email
        _TEST_USER_EMAIL,  # finally a valid email
        _TEST_USER_GIT_USERNAME,  # git username
        3,  # telemetry level
    ]
    mock_dependencies["typer.confirm"].side_effect = [
        True,  # privacy consent
        True,  # repo backup
        True,  # cache API key
    ]

    # Run the wizard
    result = run_config_wizard(temp_repo_path, temp_config_path)

    # Verify config was created with expected values
    assert result.user_email == _TEST_USER_EMAIL
    assert result.user_git_username == _TEST_USER_GIT_USERNAME
    assert result.anthropic_api_key == _TEST_API_KEY
    assert result.is_error_reporting_enabled is True
    assert result.is_product_analytics_enabled is True
    assert result.is_llm_logs_enabled is True
    assert result.is_session_recording_enabled is False
    assert result.is_repo_backup_enabled is True
    assert temp_config_path.exists()
