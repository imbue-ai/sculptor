"""This module contains checks that we want to run on startup in sculptor.

This allows us to detect conditions where sculptor might not safely run, and ask the user to fix this.

The design is decoupled: check execution is separate from result presentation, allowing
for flexible handling (CLI errors now, web modals in the future).
"""

import json
import os
import platform
import re
import shutil
import sys
from functools import partial
from functools import wraps
from pathlib import Path

from loguru import logger

from imbue_core.processes.local_process import run_blocking
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import without_consent
from imbue_core.sculptor.user_config import UserConfig
from imbue_core.subprocess_utils import ProcessError


class CheckResult(SerializableModel):
    """Result of running a single startup check."""

    name: str
    passed: bool
    error_message: str


class CheckResultPayload(PosthogEventPayload):
    """Payload wrapper for checking results."""

    results: list[CheckResult] = without_consent()


def run_all_checks(repo_path: Path, user_config: UserConfig) -> list[CheckResult]:
    """Run all the checks we have configured for this application on startup.

    Returns structured results for flexible handling. Does not handle presentation
    or exit behavior - that's the responsibility of the caller.

    Args:
        repo_path: Path to the git repository
        user_config: UserConfig instance

    Returns:
        CheckResults containing all individual check results
    """
    check_functions = [
        check_anthropic_api_key,
        check_git_installed,
        partial_wrap(check_is_git_repo)(repo_path),
        partial_wrap(check_git_repo_is_not_empty)(repo_path),
        partial_wrap(check_path_is_git_repo_root)(repo_path),
        check_default_git_settings,
        check_docker_installed,
        check_mac_docker_file_sharing_settings,
        check_is_mutagen_installed,
        partial_wrap(check_is_privacy_policy_consented)(user_config),
        partial_wrap(check_is_user_email_field_valid)(user_config),
    ]

    results = []
    for check_fn in check_functions:
        try:
            passed = check_fn()
            error_message = "" if passed else check_fn.__doc__ or "Check failed"
            results.append(CheckResult(name=check_fn.__name__, passed=passed, error_message=error_message))
        except Exception as e:
            logger.error("Unexpected error running check {}: {}", check_fn.__name__, e)
            results.append(CheckResult(name=check_fn.__name__, passed=False, error_message=f"Unexpected error: {e}"))

    return results


def partial_wrap(func):
    """Decorator to allow partial application of a function."""
    # Munctional: the following esoteric code avoids using args/kwargs, but also
    # preserves the original function signature with partial application.
    # TODO(danver): Rewrite this without the lambda for aura points
    return lambda repo_path: wraps(func)(partial(func, repo_path))


def handle_check_results_cli(results: list[CheckResult]) -> None:
    """Handle check results for CLI: print errors and exit if any failed.

    This maintains the same behavior as sculptor_v0: show all failed checks
    and exit with code 78 (EX_CONFIG) if any failed.

    Args:
        results: The check results to handle
    """
    if all(result.passed for result in results):
        # No failures, nothing to do
        return

    # Print all failed check messages
    for result in results:
        if not result.passed:
            logger.error(result.error_message)

    # Print onboarding guidelines link if any checks failed
    logger.error(
        "For help with setting up Sculptor, please see the onboarding guidelines: https://imbue-ai.notion.site/A-Guide-to-Sculptor-22aa550faf95801b8639dd3288e21974?source=copy_link"
    )

    # Exit with standard misconfiguration code
    sys.exit(78)  # 78 is EX_CONFIG, which is the standard exit code for misconfiguration.


def is_valid_anthropic_api_key(anthropic_api_key: str | None = None) -> bool:
    if anthropic_api_key is None:
        return False
    # Note: the error that Anthropic returns when the API key is non-ascii is really confusing and hard to debug
    if not anthropic_api_key.isascii():
        return False
    # All ANTHROPIC_API_KEY should start with "sk-ant"
    return anthropic_api_key.startswith("sk-ant")


def check_anthropic_api_key() -> bool:
    """Please set the environment variable ANTHROPIC_API_KEY, and make sure that all characters are ASCII: `export ANTHROPIC_API_KEY=...`"""
    return is_valid_anthropic_api_key(os.environ.get("ANTHROPIC_API_KEY", None))


def check_docker_installed() -> bool:
    """Please install the version of docker that is appropriate for your platform: osx, https://docs.docker.com/desktop/setup/install/mac-install/  , or linux, `sudo apt install -y docker.io`."""
    return shutil.which("docker") is not None


def check_docker_running() -> bool:
    """Please ensure that your docker daemon is running and accessible as a non-root user. Hint: if you normally need to run as root, try `sudo usermod -aG docker $USER && newgrp docker`."""
    try:
        result = run_blocking(
            command=["docker", "ps"],
            is_output_traced=False,
            timeout=30.0,
        )
        # This will always return true since run_blocking().check() will raise an error.
        return result.returncode == 0
    except ProcessError:
        return False


def check_git_installed() -> bool:
    """Please install git to allow sculptor to work with your repository."""
    return shutil.which("git") is not None


def check_is_git_repo(repo_path: Path) -> bool:
    """Please provide a valid git repository, or run `git init .` in the provided path."""
    try:
        result = run_blocking(
            command=["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
            is_output_traced=False,
            cwd=Path(repo_path),
        )
        # This will always return true since run_blocking().check() will raise an error.
        return result.returncode == 0
    except ProcessError:
        return False


def check_git_repo_is_not_empty(repo_path: Path) -> bool:
    """Please make at least one commit to main in your repository, e.g. `git commit --allow-empty -m "Initial commit"`."""
    try:
        result = run_blocking(
            command=["git", "-C", str(repo_path), "rev-parse", "--verify", "HEAD"],
            is_output_traced=False,
            cwd=Path(repo_path),
        )
        # This will always return true since run_blocking().check() will raise an error.
        return result.returncode == 0
    except ProcessError:
        return False


def check_path_is_git_repo_root(repo_path: Path) -> bool:
    """Please ensure that the repo_path variable points to the root directory of your git repository."""
    repo_path = Path(repo_path).resolve()
    try:
        result = run_blocking(
            command=["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
            is_output_traced=False,
            cwd=Path(repo_path),
        )
        repo_root = Path(result.stdout.strip()).resolve()
        return repo_root.samefile(repo_path)
    except ProcessError:
        return False


def check_is_mutagen_installed() -> bool:
    """Please run `brew install mutagen-io/mutagen/mutagen` to allow sculptor to work with your repository."""
    return shutil.which("mutagen") is not None


def check_default_git_settings() -> bool:
    """Please configure your global git user.name and user.email: `git config --global user.name '<name>'` and then `git config --global user.email '<email>'`."""
    try:
        name_result = run_blocking(
            command=["git", "config", "--global", "user.name"],
            is_output_traced=False,
        )
        email_result = run_blocking(
            command=["git", "config", "--global", "user.email"],
            is_output_traced=False,
        )

        name = name_result.stdout.strip()
        email = email_result.stdout.strip()

        return bool(name) and bool(email)
    except ProcessError:
        # Note that this test will only fail if the user has not yet set their git config email
        # NOT when the user specifically set their config email to empty.
        return False


def check_mac_docker_file_sharing_settings() -> bool:
    """On macOS with Docker Desktop, please enable 'Docker VMM' + VirtioFS in Docker Desktop settings under Settings -> General -> 'Virtual Machine Options'. Apple Virtualization Framework and QEMU are both not recommended for sculptor."""
    # Skip this check if SCULPTOR_ALLOW_ALL_DOCKER_SETTINGS is set
    if os.environ.get("SCULPTOR_ALLOW_ALL_DOCKER_SETTINGS"):
        logger.debug("WARNING: Allowing nonstandard Docker settings because SCULPTOR_ALLOW_ALL_DOCKER_SETTINGS is set")
        return True

    # Skip this check on non-Mac platforms
    if platform.system() != "Darwin":
        logger.debug("Skipping docker check on non-Mac platform")
        return True

    try:
        # First check if Docker is installed
        docker_path = shutil.which("docker")
        if not docker_path:
            # Docker not installed, let the other check handle this
            return True

        # Check which Docker implementation is actually being used by checking the docker symlink
        # Resolve symlinks to find the actual docker binary
        docker_real_path = Path(docker_path).resolve()
        docker_path_str = str(docker_real_path)

        # Check if the docker command is coming from Docker Desktop
        if "Docker.app" in docker_path_str or "com.docker" in docker_path_str:
            # It's Docker Desktop, so continue to checking
            pass
        elif "rancher-desktop" in docker_path_str.lower() or "rancher desktop" in docker_path_str.lower():
            # Rancher Desktop is fine, no need to check further
            logger.debug("Skipping docker check on Rancher Desktop")
            return True
        else:
            # For other cases, fall back to checking if Docker Desktop app exists
            docker_desktop_paths = [
                "/Applications/Docker.app",
                "/System/Volumes/Data/Applications/Docker.app",
            ]
            is_docker_desktop = any(Path(path).exists() for path in docker_desktop_paths)
            if not is_docker_desktop:
                # (Apparently) no Docker Desktop installed, so no need to check VirtioFS settings
                logger.debug("Skipping docker check, docker desktop not detected")
                return True

        # Check Docker Desktop settings for file sharing implementation
        # Docker Desktop stores settings in ~/Library/Group Containers/group.com.docker/[settings.json, settings-store.json]
        # `settings-store.json` is the newer format for Docker Desktop > 4.35, but `settings.json` is still supported.
        # Ref: https://docs.docker.com/desktop/settings-and-maintenance/settings/
        settings_path = Path.home() / "Library" / "Group Containers" / "group.com.docker" / "settings-store.json"

        if not settings_path.exists():
            settings_path = Path.home() / "Library" / "Group Containers" / "group.com.docker" / "settings.json"

        if not settings_path.exists():
            # Can't find settings file, assume it's okay (user can just encounter issues if not)
            logger.debug("Docker Desktop settings file not found at expected location {}", str(settings_path))
            return True

        with open(settings_path, "r") as f:
            settings = json.load(f)

        # Check that Apple Virtualization Framework is disabled
        if settings.get("UseVirtualizationFramework", True) is True:  # docker defaults it to true
            logger.debug(
                "Docker Desktop is using Apple Virtualization Framework (found UseVirtualizationFramework=true) but should not be! (causes hangs)"
            )
            return False

        # Check that Docker VMMM is enabled
        if settings.get("UseLibkrun", False) is False:
            logger.debug(
                "Docker Desktop is not using Docker VMMM (found UseLibkrun=false) but should be! (its faster than QEMU + osxfs)"
            )
            return False

        return True

    except Exception as e:
        logger.debug("Error checking Docker Desktop settings: {}", e)
        # If we can't determine the settings, assume it's okay
        return True


def check_is_privacy_policy_consented(user_config: UserConfig) -> bool:
    """Please consent to our research preview privacy notice and terms of service."""
    return user_config.is_privacy_policy_consented


def check_is_user_email_field_valid(config: UserConfig) -> bool:
    """Please enter a valid email address."""
    # Matches things like .@..., <some string>@<another>.<last one>
    # which excludes '@' from each of the string parts but allow all other characters
    # including special characters and '.' a dot itself.
    pattern = r"^[^@]+@[^@]+\.[^@]+$"
    if re.match(pattern, config.user_email):
        return True
    else:
        return False
