"""Why jj cannot be used right now, worded for the user from its readiness, and the error that carries it."""

from typing import assert_never

from sculptor.interfaces.environments.errors import EnvironmentFailure
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjNotRunnable
from sculptor.web.data_types import JjReadiness
from sculptor.web.data_types import JjUnsupportedVersion


class JjUnavailableError(EnvironmentFailure):
    """jj cannot be used right now; the message says why."""


def describe_jj_unavailability(readiness: JjReadiness) -> str | None:
    """Why jj cannot be used, composed from the readiness variant's data; None when it can."""
    match readiness:
        case JjAvailable():
            return None
        case JjNotInstalled():
            return "jj is not installed: install it or set its path on the Jujutsu settings page"
        case JjNotRunnable(error=error):
            return f"jj cannot run: {error}" if error else "jj cannot run"
        case JjUnsupportedVersion(path=path, version=version):
            return (
                f"jj {version or '(unknown version)'} at {path} is not supported:"
                + f" Sculptor needs jj {JJ_PINNED_VERSION} or a newer compatible version"
            )
        case JjNoIdentity():
            return "jj has no author identity: set its user.name and user.email on the Jujutsu settings page"
        case _ as unreachable:
            assert_never(unreachable)


def require_jj_available(readiness: JjReadiness) -> None:
    """Raise `JjUnavailableError` unless `readiness` says jj can be used."""
    reason = describe_jj_unavailability(readiness)
    if reason is not None:
        raise JjUnavailableError(reason)
