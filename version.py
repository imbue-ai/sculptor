"""Version is the exposed interface for making available the version of this
project to internal files.
"""

import tomllib
from enum import IntEnum
from functools import cache
from importlib import resources

from packaging.version import Version

from imbue_core.processes.local_process import run_blocking


def dev_git_sha() -> str:
    """Return the Git SHA that this version came from.

    Can only be run in dev mode!
    """
    # We want to run this on the local machine, at build time.
    return run_blocking(command=["git", "rev-parse", "--short", "HEAD"]).stdout.strip()


@cache
def dev_semver() -> str:
    """Return the Sculptor version.

    Only call this function when running in dev mode.
    """
    pyproject = resources.files("sculptor").joinpath("../pyproject.toml")

    with resources.as_file(pyproject) as path, path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


class VersionComponent(IntEnum):
    """Enum for the version components."""

    MAJOR = 0
    MINOR = 1
    PATCH = 2
    PRE_RELEASE = 3
    STRIP_PRE_RELEASE = -3
    POST_RELEASE = 4


def next_version(version: str, index: VersionComponent) -> str:
    """Given an existing version and an index to bump, return the next version.

    The index is 0 for major, 1 for minor, 2 for patch, 3 for rc and 4 for post release.
    An index of -3 will strip the pre-release information.
    """
    v = Version(version)
    major, minor, patch, pre, post = v.major, v.minor, v.micro, v.pre, v.post

    if index == VersionComponent.MAJOR:
        major += 1
        minor = 0
        patch = 0
        pre = None
        post = None
    elif index == VersionComponent.MINOR:
        minor += 1
        patch = 0
        pre = None
        post = None

    elif index == VersionComponent.PATCH:
        patch += 1
        pre = None
        post = None
    elif index == VersionComponent.PRE_RELEASE:
        if post is not None:
            raise ValueError("Pre releases cannot be bumped with a post-release index")
        if pre is None:
            pre = ("rc", 1)
        else:
            pre = (pre[0], pre[1] + 1)
    elif index == VersionComponent.STRIP_PRE_RELEASE:
        if pre is not None:
            pre = None
        if post is not None:
            raise ValueError("Attempted to strip pre-release information, but post-release information is present")
    elif index == VersionComponent.POST_RELEASE:
        if pre is not None:
            raise ValueError("Post releases cannot be bumped with a pre-release index")
        if post is None:
            post = 1
        else:
            post += 1
        pre = None

    return str(
        Version(f"{major}.{minor}.{patch}{''.join(map(str, pre)) if pre else ''}{'post' + str(post) if post else ''}")
    )


def pep_440_to_semver(version: str) -> str:
    """Convert a version string to a semver-compatible version string, for use by Electron.

    This will convert the rc tag to a pre-release tag. This will fail for post because semver does not properly support it.
    """
    v = Version(version)
    major, minor, patch, pre, post = v.major, v.minor, v.micro, v.pre, v.post

    if post is not None:
        raise ValueError("Post releases cannot be converted to semver")

    pre_component = f"-{pre[0]}.{pre[1]}" if pre else ""

    return f"{major}.{minor}.{patch}{pre_component}"


def _get_version_and_sha():
    try:
        return dev_semver() + "-dev", dev_git_sha()
    except FileNotFoundError:
        # Production mode: trust built _version.py
        from sculptor import _version  # type: ignore[reportMissingImports]

        return _version.__version__, _version.__git_sha__


__version__, __git_sha__ = _get_version_and_sha()
