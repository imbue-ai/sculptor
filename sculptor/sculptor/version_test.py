import pytest

from sculptor.version import VersionComponent
from sculptor.version import is_devrelease
from sculptor.version import is_prerelease
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
        ("2.0.0", VersionComponent.MAJOR, "3.0.0"),
        ("2.0.0", VersionComponent.MINOR, "2.1.0"),
        ("2.0.0", VersionComponent.PATCH, "2.0.1"),
        ("0.9.9", VersionComponent.PATCH, "0.9.10"),
        ("0.0.1rc1", VersionComponent.MAJOR, "1.0.0"),
        ("0.0.1rc1", VersionComponent.MINOR, "0.1.0"),
        ("0.0.1rc1", VersionComponent.PATCH, "0.0.2"),
        ("0.0.1rc1", VersionComponent.PRE_RELEASE, "0.0.1rc2"),
        ("0.0.1rc1", VersionComponent.STRIP_PRE_RELEASE, "0.0.1"),
        ("0.0.1.post1", VersionComponent.MAJOR, "1.0.0"),
        ("0.0.1.post1", VersionComponent.MINOR, "0.1.0"),
        ("0.0.1.post1", VersionComponent.PATCH, "0.0.2"),
        ("0.0.1.post1", VersionComponent.PRE_RELEASE, ValueError),
        ("0.0.1.post1", VersionComponent.STRIP_PRE_RELEASE, ValueError),
    ],
)
def test_next_version(current_version, bump, expected_next_version) -> None:
    """Test the next_version function with various inputs."""
    if isinstance(expected_next_version, str):
        assert next_version(current_version, bump) == expected_next_version
    else:
        with pytest.raises(expected_next_version):
            next_version(current_version, bump)


@pytest.mark.parametrize(
    ("version_string", "expected"),
    [
        ("1.2.3", False),
        ("1.2.3rc1", True),
        ("2.0.0-beta", True),
        ("0.9.0-alpha.2", True),
        ("1.0.0.post1", False),
    ],
)
def test_is_prerelease(version_string, expected) -> None:
    """Test the is_prerelease function with various inputs."""

    assert is_prerelease(version_string) == expected


@pytest.mark.parametrize(
    ("version_string", "expected"),
    [
        ("1.2.3", False),
        ("1.2.3.dev1", True),
        ("2.0.0-dev", True),
        ("0.9.0-alpha.2", False),
        ("1.0.0.post1", False),
    ],
)
def test_is_devrelease(version_string, expected) -> None:
    """Test the is_devrelease function with various inputs."""
    assert is_devrelease(version_string) == expected


@pytest.mark.parametrize(
    ["our_version", "expected"],
    [
        ("1.2.3", "1.2.3"),
        ("1.2.3rc1", "1.2.3-rc.1"),
        ("0.10.0.dev0", "0.10.0-dev.0"),
        ("0.10.0.dev20260303001234", "0.10.0-dev.20260303001234"),
        ("1.0.0.dev1", "1.0.0-dev.1"),
        ("1.0.0rc1.dev2", ValueError),
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
