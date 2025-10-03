from loguru import logger

from imbue_core.common import parse_bool_environment_variable
from imbue_core.sculptor.telemetry import TelemetryInfo
from imbue_core.sculptor.user_config import UserConfig
from sculptor import version
from sculptor.config.user_config import get_default_user_config_instance
from sculptor.config.user_config import get_user_config_instance
from sculptor.utils.build import get_build_metadata

# PostHog configuration constants
PROD_POSTHOG_TOKEN = "phc_j6fTwEMxoWfk3KLYQhhGkm6QpQWCtBXg7fXMxQgaSAd"
PROD_POSTHOG_HOST = "https://us.i.posthog.com"
DEV_POSTHOG_TOKEN = "phc_qOlmUqxdThj6MdTx7Qx1cYe9yJ40PwuCa9bjGBNpHIN"
DEV_POSTHOG_HOST = "https://us.i.posthog.com"

# Sentry configuration constants
PROD_SENTRY_DSN = "https://485610202dcd8c5251e4d8429ff244b3@o4504335315501056.ingest.us.sentry.io/4510007301111808"
DEV_SENTRY_DSN = "https://188a4c98df33ef883bac65ae8396ee7f@o4504335315501056.ingest.us.sentry.io/4509956912250880"


def _get_posthog_token_and_api_host(user_config: UserConfig) -> tuple[str, str]:
    # This controls whether we use production or development Posthog.

    # If the evironment variable USE_PROD_POSTHOG is set to "1" or "true",
    # we use the production Posthog instance. We will also use the production
    # Posthog instance if the user is not internal, as determined by the
    # user's email address (addresses ending in "@imbue.com" or
    # "@generallyintelligent.com" are considered internal).

    # The distributed version of Sculptor uses the production Posthog instance.
    # This is set in sculptor/sculptor/cli/main.py::entry_point().

    # By default we send logs to the development Posthog instance.

    # Note that if this function is called before the user config is initialized,
    # we won't have a user email address, so we will *only* use the environment
    # variable to determine which Posthog instance to use.

    # The key values are available on the project settings page in Posthog: https://us.posthog.com/project/settings
    # There's a selector to switch between "imbue.com" and "imbue.com (dev)"

    use_prod = parse_bool_environment_variable("USE_PROD_POSTHOG")

    # it's okay to hardcode these tokens, because they're append-only, and need to be distributed
    # in client code regardless.
    if use_prod:
        logger.info("Using production posthog instance.")
        return (PROD_POSTHOG_TOKEN, PROD_POSTHOG_HOST)
    else:
        logger.info("Using developer posthog instance.")
        return (DEV_POSTHOG_TOKEN, DEV_POSTHOG_HOST)


def _get_sentry_dsn() -> str:
    build_metadata = get_build_metadata(in_testing=False)
    imbue_cli_dsn = PROD_SENTRY_DSN if build_metadata.is_production else DEV_SENTRY_DSN
    return imbue_cli_dsn


def _get_telemetry_info_with_user_config(user_config: UserConfig) -> TelemetryInfo:
    api_key, api_host = _get_posthog_token_and_api_host(user_config)
    sentry_dsn = _get_sentry_dsn()

    return TelemetryInfo(
        user_config=user_config,
        sculptor_version=version.__version__,
        sculptor_git_sha=version.__git_sha__,
        posthog_token=api_key,
        posthog_api_host=api_host,
        sentry_dsn=sentry_dsn,
    )


def get_telemetry_info() -> TelemetryInfo | None:
    """Returns telemetry info object, based on a global user config variable.

    Returns None if the user config has not been initialized yet.
    """
    user_config = get_user_config_instance()
    if user_config is None:
        return None

    return _get_telemetry_info_with_user_config(user_config)


def get_onboarding_telemetry_info() -> TelemetryInfo:
    """Returns the default onboarding telemetry info object.

    This contains endpoint settings but a default user_config with
    anonymous UID.
    """
    return _get_telemetry_info_with_user_config(get_default_user_config_instance())
