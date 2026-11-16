from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.jj_availability import JjUnavailableError
from sculptor.services.jj_availability import describe_jj_unavailability
from sculptor.services.jj_availability import prepare_jj_for_launch
from sculptor.services.jj_availability import require_jj_available
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.sculptor_folder import isolated_sculptor_folder  # noqa: F401
from sculptor.utils.build import get_jj_bin_dir
from sculptor.utils.build import link_jj_bin
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjNotRunnable
from sculptor.web.data_types import JjReadiness
from sculptor.web.data_types import JjUnsupportedVersion

_IDENTITY = JjIdentity(name="Jordan Bookmarker", email="jordan@example.com")


@pytest.mark.parametrize(
    ("readiness", "expected_reason"),
    [
        pytest.param(
            JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED),
            "jj is not installed: install it or set its path on the Jujutsu settings page",
            id="not-installed",
        ),
        pytest.param(
            JjNotRunnable(blocker=JjBlocker.NOT_RUNNABLE, error="dyld: Library not loaded"),
            "jj cannot run: dyld: Library not loaded",
            id="not-runnable",
        ),
        pytest.param(
            JjNotRunnable(blocker=JjBlocker.NOT_RUNNABLE, error=None), "jj cannot run", id="not-runnable-quiet"
        ),
        pytest.param(
            JjUnsupportedVersion(blocker=JjBlocker.UNSUPPORTED_VERSION, path="/opt/jj", version="0.28.2"),
            f"jj 0.28.2 at /opt/jj is not supported: Sculptor needs jj {JJ_PINNED_VERSION} or a newer compatible version",
            id="unsupported-version",
        ),
        pytest.param(
            JjNoIdentity(blocker=JjBlocker.NO_IDENTITY, suggested_identity=_IDENTITY),
            "jj has no author identity: set its user.name and user.email on the Jujutsu settings page",
            id="no-identity",
        ),
    ],
)
def test_an_unavailable_jj_is_described_from_its_readiness_and_refused(
    readiness: JjReadiness, expected_reason: str
) -> None:
    assert describe_jj_unavailability(readiness) == expected_reason
    with pytest.raises(JjUnavailableError) as raised:
        require_jj_available(readiness)
    assert str(raised.value) == expected_reason


def test_an_available_jj_has_no_unavailability_to_describe() -> None:
    readiness = JjAvailable(blocker=None, identity=_IDENTITY)

    assert describe_jj_unavailability(readiness) is None
    require_jj_available(readiness)


@pytest.fixture
def dependency_management_service(jj_isolated_env: JjIsolatedEnv) -> Iterator[DependencyManagementService]:
    with ConcurrencyGroup(name="dependency_management_service") as concurrency_group:
        yield DependencyManagementService(concurrency_group=concurrency_group)
    set_user_config_instance(None)


def _resolve_jj_to(jj_path: Path) -> None:
    set_user_config_instance(
        UserConfig(
            user_email="test@example.com",
            user_id=uuid4().hex,
            organization_id=uuid4().hex,
            instance_id=uuid4().hex,
            dependency_paths=DependencyPaths(jj=str(jj_path)),
        )
    )


def test_preparing_a_launch_points_jj_bin_at_the_resolved_jj_when_it_passes_readiness(
    dependency_management_service: DependencyManagementService,
    jj_binary: JjBinary,
    isolated_sculptor_folder: Path,  # noqa: F811
) -> None:
    _resolve_jj_to(jj_binary.path)

    prepare_jj_for_launch(dependency_management_service)

    assert (get_jj_bin_dir() / "jj").readlink() == jj_binary.path


def test_preparing_a_launch_refuses_a_jj_version_sculptor_does_not_support_and_leaves_jj_bin_as_it_was(
    dependency_management_service: DependencyManagementService,
    jj_binary: JjBinary,
    isolated_sculptor_folder: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    link_jj_bin(jj_binary.path)
    old_jj = tmp_path / "jj"
    old_jj.write_text(f'#!/bin/sh\necho "jj 0.28.2-{uuid4().hex}"\n')
    old_jj.chmod(0o755)
    _resolve_jj_to(old_jj)

    with pytest.raises(JjUnavailableError) as raised:
        prepare_jj_for_launch(dependency_management_service)

    assert str(raised.value).startswith(f"jj 0.28.2 at {old_jj} is not supported")
    assert (get_jj_bin_dir() / "jj").readlink() == jj_binary.path
