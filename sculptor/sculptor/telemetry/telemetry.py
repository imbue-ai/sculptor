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

    # UserConfig can change independently of this model, which risks the two falling out of sync.
    user_config: UserConfig
    sculptor_version: str
    sculptor_execution_instance_id: str
