from sculptor.foundation.telemetry import TelemetryInfo
from sculptor.foundation.user_config import UserConfig
from sculptor import version
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import get_execution_instance_id
from sculptor.services.user_config.user_config import get_user_config_instance


def _get_telemetry_info_with_user_config(user_config: UserConfig) -> TelemetryInfo:
    return TelemetryInfo(
        user_config=user_config,
        sculptor_version=version.__version__,
        sculptor_execution_instance_id=get_execution_instance_id(),
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

    This contains a default user_config with an anonymous UID.
    """
    return _get_telemetry_info_with_user_config(get_default_user_config_instance())
