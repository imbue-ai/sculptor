import os
from pathlib import Path

import typer
from click import IntRange
from loguru import logger

from imbue_core.constants import DISCORD_URL
from imbue_core.processes.local_process import run_blocking
from imbue_core.pydantic_utils import model_update
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry import identify_posthog_user
from imbue_core.sculptor.telemetry import without_consent
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.sculptor.user_config import UserConfig
from imbue_core.subprocess_utils import ProcessError
from sculptor.config.user_config import InvalidConfigError
from sculptor.config.user_config import create_organization_id
from sculptor.config.user_config import create_user_id
from sculptor.config.user_config import get_config_path
from sculptor.config.user_config import get_default_user_config_instance
from sculptor.config.user_config import get_execution_instance_id
from sculptor.config.user_config import load_config
from sculptor.config.user_config import save_config
from sculptor.config.user_config import set_user_config_instance
from sculptor.config.user_config import update_user_consent_level
from sculptor.startup_checks import check_anthropic_api_key
from sculptor.startup_checks import check_default_git_settings
from sculptor.startup_checks import check_git_repo_is_not_empty
from sculptor.startup_checks import check_is_git_repo
from sculptor.startup_checks import check_is_user_email_field_valid
from sculptor.startup_checks import check_path_is_git_repo_root
from sculptor.startup_checks import is_valid_anthropic_api_key

_WELCOME_ASCII_MESSAGE = (
    r"""
    ____             _       _
   / ___|  ___ _   _| |_ __ | |_ ___  _ __
   \___ \ / __| | | | | '_ \| __/ _ \| '__|
    ___) | (__| |_| | | |_) | || (_) | |
   |____/ \___|\__,_|_| .__/ \__\___/|_|
                      |_|

        🎨 Welcome to Sculptor! 🎨
       Craft your code with artistry

    ┌─────────────────────────────────┐
    │ * Join our Discord community! * │
    │  """
    + DISCORD_URL
    + """  │
    └─────────────────────────────────┘
"""
)

_RESEARCH_PREVIEW_WARNING = r"""
                    🔬 RESEARCH PREVIEW
  ┌────────────────────────────────────────────────────┐
  │  This software is experimental and under active    │
  │  development. Features may change and data may be  │
  │  collected for research purposes.                  │
  │                                                    │
  │  By continuing you acknowledge that you have read  │
  │  and accepted our Research Preview Privacy Notice  │
  │  and Terms of Service.                             │
  └────────────────────────────────────────────────────┘

  🔒 Research Preview Privacy Notice: https://imbue.com/privacy
  📋 Research Preview Terms of Service: https://imbue.com/terms
"""

_INIT_GIT_COMMIT_MESSAGE = "Starting Sculptor..."


class EmailConfirmationData(PosthogEventPayload):
    email: str = without_consent(description="email user has entered for confirmation step in wizard")
    instance_id: str = without_consent(description="uvx session instance id")


def _check_and_fix_config_user_id_fields(user_config: UserConfig) -> UserConfig:
    """Validation for User and Org ID generated in config file.

    We assume that the email field read from the configuration file is correct.
    """
    correct_user_id = create_user_id(user_config.user_email)
    correct_organization_id = create_organization_id(user_config.user_email)
    if user_config.user_id != correct_user_id:
        logger.info("User ID modified!")
    if user_config.organization_id != correct_organization_id:
        logger.info("Organization ID modified!")
    return model_update(
        user_config,
        {
            "user_id": correct_user_id,
            "organization_id": correct_organization_id,
        },
    )


def _add_email_to_git_global_config_if_not_set(user_config: UserConfig) -> None:
    if check_is_user_email_field_valid(user_config):
        # Attempt to update the user git configurations if not set
        if not check_default_git_settings():
            # User has no default git configurations, help them set this
            try:
                run_blocking(
                    command=["git", "config", "--global", "user.name", user_config.user_git_username],
                )
                run_blocking(
                    command=["git", "config", "--global", "user.email", user_config.user_email],
                )
            except ProcessError as process_error:
                # Catch and log any exception, rely on failure of startup_checks to exit sculptor.
                logger.info("[git config] ProcessError: {}\n{}", process_error.stdout, process_error.stderr)


def _validate_and_maybe_request_user_email(config, repo_path) -> UserConfig:
    # First validate and ask user to re-input email address
    if not check_is_user_email_field_valid(config):
        logger.info("User email is empty or invalid!")
        config = _request_user_email_and_username(config, repo_path)
    # Validate correct IDs are generated for this user config
    # The order of these two calls is important:
    #   When we detect a valid email, we should also check user-id fields are correct
    #   When we detect an invalid email, we re-compute these id fields as part of the
    #   _request_user_email_and_username() call.
    config = _check_and_fix_config_user_id_fields(config)
    _add_email_to_git_global_config_if_not_set(config)
    return config


def _try_loading_config_file(config_path: Path, repo_path: Path) -> UserConfig:
    """Try to load user config from a config file. If we run into an exception, we raise to gather onboarding info"""
    try:
        assert config_path.exists()
        config = load_config(config_path)
        # Validate and ask user to re-input email address if needed
        config = _validate_and_maybe_request_user_email(config, repo_path)
        # Inject new instance_id into the configuration file read.
        # This actually doesn't need to be cached to disk, but today we're doing it
        # automatically whenever we put this field into UserConfig.
        config = model_update(config, {"instance_id": get_execution_instance_id()})
        typer.secho(f"Using existing config in {config_path}. Edit that file directly to make any changes.")
        return config
    except Exception as e:
        raise InvalidConfigError(e)


def _request_user_email_and_username(user_config: UserConfig, repo_path: Path) -> UserConfig:
    """Prompt the user to enter their email address and git username."""
    default_email = _get_git_email_or_empty(repo_path)
    user_email = typer.prompt("Email", default=default_email)

    # Ask user to confirm email if invalid (after first updating it!)
    user_config = model_update(user_config, {"user_email": user_email})
    while not check_is_user_email_field_valid(user_config):
        user_email = typer.prompt("Email invalid! Please re-enter your email", default=default_email)
        user_config = model_update(user_config, {"user_email": user_email})

    # Prompt for git username
    default_git_username = _get_git_username_or_empty(repo_path)
    if not default_git_username:
        # If no git username is configured, derive from email
        default_git_username = user_email.split("@")[0]
    user_git_username = typer.prompt("Git username", default=default_git_username)

    # Need to update user_config ids based on email
    user_id = create_user_id(user_email)
    organization_id = create_organization_id(user_email)

    # Update the UserConfig object with email and git username.
    return model_update(
        user_config,
        {
            "user_email": user_email,
            "user_git_username": user_git_username,
            "user_id": user_id,
            "organization_id": organization_id,
        },
    )


def _should_prompt_for_user_consent(user_config: UserConfig) -> bool:
    """We ask user for their consent levels when we detect misconfigured settings."""

    configured_fields = user_config.model_fields_set

    # disallow low config settings in alpha
    alpha_testers_settings_now_disallowed = (
        user_config.is_error_reporting_enabled is False or user_config.is_product_analytics_enabled is False
    )
    return (
        alpha_testers_settings_now_disallowed
        or "is_error_reporting_enabled" not in configured_fields
        or "is_product_analytics_enabled" not in configured_fields
        or "is_llm_logs_enabled" not in configured_fields
        or "is_session_recording_enabled" not in configured_fields
    )


def _request_user_telemetry_consent_level(user_config: UserConfig) -> UserConfig:
    """Prompt users for their telemetry consent levels."""
    typer.echo("Please consider enabling telemetry to help us improve Sculptor:")
    typer.echo("  0. Nothing at all (TEMPORARILY DISABLED FOR ALPHA TESTERS)")
    typer.echo("  1. Error reports only (TEMPORARILY DISABLED FOR ALPHA TESTERS)")
    typer.echo("  2. Error reports and product analytics")
    typer.echo("  3. Error reports, product analytics and LLM logs")
    typer.echo("  4. Error reports, product analytics, LLM logs and session recordings")
    telemetry_level = typer.prompt("Your choice", type=IntRange(2, 4), default=3)

    user_config = update_user_consent_level(user_config, telemetry_level)
    emit_posthog_event(
        PosthogEventModel(
            name=SculptorPosthogEvent.ONBOARDING_TELEMETRY_CONSENT, component=ProductComponent.ONBOARDING
        )
    )

    return user_config


def _request_user_repo_backup_consent(user_config: UserConfig) -> UserConfig:
    is_repo_backup_enabled = typer.confirm(
        "Enable repo backup and allow Imbue to improve code generation using the repo?", default=True
    )
    return model_update(user_config, {"is_repo_backup_enabled": is_repo_backup_enabled})


def _cache_anthropic_api_key(user_config: UserConfig) -> UserConfig:
    """Prompt users for ANTHROPIC_API_KEY if not yet set.

    Or read from configuration file if it exists.
    """
    if not check_anthropic_api_key():
        config_api_key = user_config.anthropic_api_key
        if config_api_key is not None and is_valid_anthropic_api_key(config_api_key):
            masked_key_string = config_api_key[:10] + "..." + config_api_key[-8:]
            typer.secho(
                "Reading ANTHROPIC_API_KEY from config file\n  Using key: {}".format(masked_key_string), fg="yellow"
            )
            session_anthropic_api_key = config_api_key
        else:
            typer.secho("No ANTHROPIC_API_KEY detected!")
            typer.secho(
                "If you need one, request from: https://research.typeform.com/to/QhLblRaV", fg="blue", bold=True
            )
            session_anthropic_api_key = typer.prompt("Please enter your ANTHROPIC_API_KEY")
            if typer.confirm("Caching ANTHROPIC_API_KEY into configuration file", default=True):
                user_config = model_update(user_config, {"anthropic_api_key": session_anthropic_api_key})
        # Finally export the ANTHROPIC_API_KEY for this session to the environment
        os.environ["ANTHROPIC_API_KEY"] = session_anthropic_api_key
    elif (
        not is_valid_anthropic_api_key(user_config.anthropic_api_key)
        or os.environ.get("ANTHROPIC_API_KEY", "") != user_config.anthropic_api_key
    ):
        # ANTHROPIC_API_KEY exists in the environment, but is either missing from config.toml
        # or different between environment and config
        env_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        masked_key_string = env_api_key[:10] + "..." + env_api_key[-8:]
        typer.secho("ANTHROPIC_API_KEY detected in ENV!\n  Using key: {}".format(masked_key_string), fg="yellow")
        if typer.confirm("  Key different than config.toml file, cache new key", default=True):
            user_config = model_update(user_config, {"anthropic_api_key": env_api_key})
    return user_config


def _export_gemini_api_key(user_config: UserConfig) -> bool:
    """If the user config contains a gemini api key, export it to the environment."""
    if user_config.gemini_api_key is not None:
        os.environ["GEMINI_API_KEY"] = user_config.gemini_api_key
        return True
    return False


def _request_user_privacy_consent(user_config: UserConfig) -> UserConfig:
    if user_config.is_privacy_policy_consented:
        return user_config
    typer.secho(_RESEARCH_PREVIEW_WARNING, fg="red")
    is_privacy_policy_consented = typer.confirm(
        "Proceed and acknowledge you accept the stipulated terms?", default=True
    )
    return model_update(user_config, {"is_privacy_policy_consented": is_privacy_policy_consented})


def _get_git_email_or_empty(repo_path: Path) -> str:
    try:
        result = run_blocking(
            command=["git", "config", "user.email"],
            cwd=repo_path,
        )
        return result.stdout.strip()
    except ProcessError:
        return ""


def _get_git_username_or_empty(repo_path: Path) -> str:
    try:
        result = run_blocking(
            command=["git", "config", "user.name"],
            cwd=repo_path,
        )
        return result.stdout.strip()
    except ProcessError:
        return ""


def _should_help_git_initial_setup(repo_path: Path) -> bool:
    # We should try helping the user set up their directory if either
    # they don't have a git repo yet or if no commits exist.
    # Nothing we can do but fail if the user's starting directory is not
    # at the repo root?
    return not check_is_git_repo(repo_path) or not check_git_repo_is_not_empty(repo_path)


def _setup_initial_git_commit(repo_path: Path, create_repo: bool = True) -> None:
    if create_repo:
        run_blocking(
            command=["git", "init"],
            cwd=repo_path,
        )
    # Create initial empty commit
    run_blocking(
        command=["git", "commit", "--allow-empty", "-m", _INIT_GIT_COMMIT_MESSAGE],
        cwd=repo_path,
    )


def _maybe_setup_git_initial_commit(repo_path: Path) -> bool:
    try:
        if not check_is_git_repo(repo_path):
            _setup_initial_git_commit(repo_path)
            return True
        elif check_path_is_git_repo_root(repo_path):
            if not check_git_repo_is_not_empty(repo_path):
                # Help user create first init commit
                _setup_initial_git_commit(repo_path, create_repo=False)
                return True
            else:
                return False
        else:
            return False
    except ProcessError as process_error:
        # Catch and log any exception, rely on failure of startup_checks to exit sculptor.
        logger.info("[git init] ProcessError: {}\n{}", process_error.stdout, process_error.stderr)
        return False


def run_config_wizard(repo_path: Path, config_path: Path | None = None) -> UserConfig:
    emit_posthog_event(
        PosthogEventModel(
            name=SculptorPosthogEvent.ONBOARDING_CONFIGURATION_WIZARD, component=ProductComponent.ONBOARDING
        )
    )

    typer.secho(_WELCOME_ASCII_MESSAGE)
    typer.secho(f"Starting from the following repo: {repo_path}")

    # Load default anonymous session user config.
    config = get_default_user_config_instance()
    creating_new_config = False

    # Load default config path if not specified.
    if config_path is None:
        config_path = get_config_path()

    try:
        # Attempt to load the configuration file, exits program if it fails.
        config = _try_loading_config_file(config_path, repo_path)
    except InvalidConfigError as e:
        creating_new_config = True
        typer.secho(f"Valid config file not found at {config_path}")
        logger.trace("Configuration Loading error: {}".format(e))
        typer.secho("\nPlease provide the following details (press enter to accept):", fg="blue")
        config = _validate_and_maybe_request_user_email(config, repo_path)

    # At this point, we assume the user's email address was successfully configured!
    emit_posthog_event(
        PosthogEventModel(
            name=SculptorPosthogEvent.ONBOARDING_EMAIL_CONFIRMATION,
            component=ProductComponent.ONBOARDING,
            payload=EmailConfirmationData(email=config.user_email, instance_id=config.instance_id),
        )
    )
    # Identify the current Posthog Instance with a user.
    identify_posthog_user(config)

    # Ask for user privacy consent up-front
    if creating_new_config or not config.is_privacy_policy_consented:
        config = _request_user_privacy_consent(config)
        if not config.is_privacy_policy_consented:
            # Early escape and quit configuration wizard if user does not consent to
            # privacy & terms of service.
            # This will trigger a failure on the startup_checks and exits sculptor.
            return config

    # Prompt for user consent
    # Note: privacy consent is asked for last, if the user does not
    #       agree, it flows more smoothly if the application then exits.
    if creating_new_config:
        config = _request_user_telemetry_consent_level(config)
        config = _request_user_repo_backup_consent(config)
    else:
        # Question: should we ask for repo backup consent each time?
        #           if the user hasn't yet consented.
        if _should_prompt_for_user_consent(config):
            config = _request_user_telemetry_consent_level(config)

    # Cache Anthropic API Key
    config = _cache_anthropic_api_key(config)

    # Set the Gemini API Key environment variable if it exists in the config
    # this is for an exploratory feature which uses Gemini's relatively cheap 1M token model
    _export_gemini_api_key(config)

    save_config(config=config, config_path=config_path)
    typer.secho("Configuration saved successfully!", fg="green", bold=True)

    if (
        _should_help_git_initial_setup(repo_path)
        and typer.confirm("Improper git repository configuration found. Initialize new git repository?")
        and _maybe_setup_git_initial_commit(repo_path)
    ):
        typer.secho("Created initial commit in empty directory!", fg="green", bold=True)

    set_user_config_instance(config)
    return config
