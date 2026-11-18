import pytest

from sculptor.services.jj_availability import JjUnavailableError
from sculptor.services.jj_availability import describe_jj_unavailability
from sculptor.services.jj_availability import require_jj_available
from sculptor.services.jj_version import JJ_PINNED_VERSION
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
