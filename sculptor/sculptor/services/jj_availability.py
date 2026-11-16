"""Why jj cannot be used right now, worded for the user from its readiness, the error that carries it, and the
step that lets a process launch in a jj workspace."""

from pathlib import Path
from typing import assert_never

from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.interfaces.environments.errors import EnvironmentFailure
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.utils.build import link_jj_bin
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjNotRunnable
from sculptor.web.data_types import JjReadiness
from sculptor.web.data_types import JjShadowed
from sculptor.web.data_types import JjUnsupportedVersion

_NOT_INSTALLED_REASON = "jj is not installed: install it or set its path on the Jujutsu settings page"


class JjUnavailableError(EnvironmentFailure):
    """jj cannot be used right now; the message says why."""


def describe_jj_unavailability(readiness: JjReadiness) -> str | None:
    """Why jj cannot be used, composed from the readiness variant's data; None when it can."""
    match readiness:
        case JjAvailable():
            return None
        case JjNotInstalled():
            return _NOT_INSTALLED_REASON
        case JjNotRunnable(error=error):
            return f"jj cannot run: {error}" if error else "jj cannot run"
        case JjUnsupportedVersion(path=path, version=version):
            return (
                f"jj {version or '(unknown version)'} at {path} is not supported:"
                + f" Sculptor needs jj {JJ_PINNED_VERSION} or a newer compatible version"
            )
        case JjNoIdentity():
            return "jj has no author identity: set its user.name and user.email on the Jujutsu settings page"
        case JjShadowed(path=path, version=version):
            return (
                f"your login shell runs jj {version or '(unknown version)'} at {path}, but Sculptor needs"
                + f" jj {JJ_PINNED_VERSION} or a newer compatible version, because the repository is shared"
                + " with the jj you run yourself: upgrade or remove that jj, or stop your shell profile putting its"
                + " directory first on PATH"
            )
        case _ as unreachable:
            assert_never(unreachable)


def require_jj_available(readiness: JjReadiness) -> None:
    """Raise `JjUnavailableError` unless `readiness` says jj can be used."""
    reason = describe_jj_unavailability(readiness)
    if reason is not None:
        raise JjUnavailableError(reason)


def prepare_jj_for_launch(dependency_management_service: DependencyManagementService) -> None:
    """Raise `JjUnavailableError` while jj is unusable, leaving jj-bin as it was; otherwise point jj-bin at the ready jj.

    Run it only right before launching a process in a jj workspace, never from a
    poller or a read, so nothing else can change which jj a running agent finds.
    """
    require_jj_available(dependency_management_service.probe_jj_readiness())
    binary = dependency_management_service.resolve_binary_path(Dependency.JJ)
    if binary is None:
        raise JjUnavailableError(_NOT_INSTALLED_REASON)
    link_jj_bin(Path(binary))
