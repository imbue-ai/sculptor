"""This module exposes telemetry data types shared across Sculptor.

The Sculptor backend no longer reports to PostHog or Sentry (SCU-1291). The
only remaining type here describes the telemetry info served to the frontend,
which owns telemetry reporting.
"""

from sculptor.config.user_config import UserConfig
from sculptor.foundation.pydantic_serialization import SerializableModel


class TelemetryInfo(SerializableModel):
    """Information needed for setting up telemetry.

    This data structure is generated once in the Sculptor server and served to
    the frontend (which owns telemetry reporting).
    """

    # Putting the User Config into this object is a smell. The UserConfig can and will change idependently of this
    # model, and that can lead to all sorts of issues. Consider refactoring this code.
    user_config: UserConfig
    sculptor_version: str
    sculptor_execution_instance_id: str
