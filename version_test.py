import pytest

from sculptor.version import VersionComponent
from sculptor.version import __version__
from sculptor.version import next_version
from sculptor.version import pep_440_to_semver


@pytest.mark.parametrize(
    ["current_version", "bump", "expected_next_version"],
    [
        ("1.2.3", VersionComponent.MAJOR, "2.0.0"),
        ("1.2.3", VersionComponent.MINOR, "1.3.0"),
        ("1.2.3", VersionComponent.PATCH, "1.2.4"),
        ("1.2.3", VersionComponent.PRE_RELEASE, "1.2.3rc1"),
        ("1.2.3", VersionComponent.STRIP_PRE_RELEASE, "1.2.3"),
        ("1.2.3", VersionComponent.POST_RELEASE, "1.2.3.post1"),
        ("2.0.0", VersionComponent.MAJOR, "3.0.0"),
        ("2.0.0", VersionComponent.MINOR, "2.1.0"),
        ("2.0.0", VersionComponent.PATCH, "2.0.1"),
        ("0.9.9", VersionComponent.PATCH, "0.9.10"),
        ("0.0.1rc1", VersionComponent.MAJOR, "1.0.0"),
        ("0.0.1rc1", VersionComponent.MINOR, "0.1.0"),
        ("0.0.1rc1", VersionComponent.PATCH, "0.0.2"),
        ("0.0.1rc1", VersionComponent.PRE_RELEASE, "0.0.1rc2"),
        ("0.0.1rc1", VersionComponent.STRIP_PRE_RELEASE, "0.0.1"),
        ("0.0.1rc1", VersionComponent.POST_RELEASE, ValueError),
        ("0.0.1.post1", VersionComponent.MAJOR, "1.0.0"),
        ("0.0.1.post1", VersionComponent.MINOR, "0.1.0"),
        ("0.0.1.post1", VersionComponent.PATCH, "0.0.2"),
        ("0.0.1.post1", VersionComponent.PRE_RELEASE, ValueError),
        ("0.0.1.post1", VersionComponent.STRIP_PRE_RELEASE, ValueError),
        ("0.0.1.post1", VersionComponent.POST_RELEASE, "0.0.1.post2"),
    ],
)
def test_next_version(current_version, bump, expected_next_version) -> None:
    """Test the next_version function with various inputs."""
    if isinstance(expected_next_version, str):
        assert next_version(current_version, bump) == expected_next_version
    else:
        with pytest.raises(expected_next_version):
            next_version(current_version, bump)


def test_current_version__is_dev() -> None:
    """The current version when running the unit tests should always be dev"""
    assert __version__.endswith("-dev"), __version__


@pytest.mark.parametrize(
    ["our_version", "expected"],
    [
        ("1.2.3", "1.2.3"),
        ("1.2.3rc1", "1.2.3-rc.1"),
        ("1.2.3.post1", ValueError),
    ],
)
def test_pep_440_to_semver(our_version, expected) -> None:
    """Test that the current version can be converted to semver."""
    if isinstance(expected, str):
        assert pep_440_to_semver(our_version) == expected
    else:
        with pytest.raises(expected):
            pep_440_to_semver(our_version)
