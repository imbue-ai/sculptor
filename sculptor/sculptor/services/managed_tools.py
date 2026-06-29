"""Per-tool managed-install seam for the dependency-management service.

Holds the ``ManagedTool`` contract, the normalized ``ResolvedDistribution``
install currency, and the tool -> ``ManagedTool`` registry. This lives beside the
dependency service rather than on the harness so the seam never imports
``agents/``: ``agents/`` already imports the dependency service, so an import back
into ``agents/`` here would recreate an import cycle. The version-range value
types the service shares with the seam are defined here too, which keeps the
dependency edge one-directional (service -> managed_tools).
"""

import platform
import re
import stat
import sys
import tarfile
from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import httpx

from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.interfaces.environments.agent_execution_environment import Dependency


class BlockedVersionRange(FrozenModel):
    """A range of versions that are blocked. For a single version, min and max are the same."""

    min_version: str
    max_version: str


class VersionRange(FrozenModel):
    min_version: str
    max_version: str
    recommended_version: str
    blocked_versions: tuple[BlockedVersionRange, ...] = ()


class PlatformPin(FrozenModel):
    """One platform's pinned pi artifact: the release asset and its expected sha256."""

    asset: str
    sha256: str


class PiPin(FrozenModel):
    """The static, in-repo source of truth for the managed pi distribution.

    pi publishes no checksums, so Sculptor computes them per version
    (``scripts/compute_pi_pin.py``) and bakes them here; the install path verifies
    downloads against these pinned values.
    """

    version: str
    platforms: dict[str, PlatformPin]
    # Reserved slot, not read from user config: a constant sentinel until a pi
    # plugin set needs pinning.
    plugin_set_revision: str = "bundled"


# ``version`` is a literal, not an import of ``PI_VERSION_RANGE``: the dependency
# service imports this module, so importing it back would be a cycle. A unit test
# asserts the two stay equal.
PI_PIN = PiPin(
    version="0.78.0",
    platforms={
        "darwin-arm64": PlatformPin(
            asset="pi-darwin-arm64.tar.gz",
            sha256="68ebbe4f56a136a1c7bace3393eca4ad0aa1fd9f253b797fd370058bd39fe070",
        ),
        "darwin-x64": PlatformPin(
            asset="pi-darwin-x64.tar.gz",
            sha256="66074b271260068199f47738a172397f1e0b5a3334697dd2acea35bbd3470b1c",
        ),
        "linux-x64": PlatformPin(
            asset="pi-linux-x64.tar.gz",
            sha256="8ac03343d1e1228106e8172157f32d6b882829e46b34feaf577f171a5f1387cc",
        ),
    },
)


class ResolvedDistribution(FrozenModel):
    """A single platform's downloadable artifact, normalized across managed tools.

    The shared download/verify/stage orchestration consumes only this; each tool's
    raw remote schema (e.g. Claude's ``Manifest``) is adapted into it.
    """

    version: str
    url: str
    checksum_sha256: str
    size: int | None
    archive: Literal["single_binary", "tarball"]
    binary_subpath: str


class ManagedTool(ABC):
    """Contract for a tool whose binary Sculptor downloads, version-pins, and verifies.

    Each managed tool supplies one conformer with the per-tool parameters and the
    three hooks the shared install orchestration calls. Unmanaged tools (e.g.
    ``GIT``) have no conformer and no registry entry.
    """

    tool: Dependency
    version_range: VersionRange
    platform_keys: frozenset[str]
    retention_keep: int
    # Relative location of the executable inside an installed version dir. Statically
    # known per tool, so the offline binary-resolution read path can find a staged
    # binary without resolving a (possibly network-bound) distribution.
    binary_subpath: str

    @abstractmethod
    def resolve_distribution(self) -> ResolvedDistribution:
        """Resolve the artifact to install for the current platform."""

    @abstractmethod
    def stage(self, downloaded: Path, version_dir: Path) -> Path:
        """Install the downloaded artifact into the version directory and return the binary path."""

    def parse_version(self, output: str) -> str | None:
        """Extract the version string from the tool's ``--version`` output.

        Concrete default: a ``MAJOR.MINOR.PATCH`` (plus optional suffix) semver match,
        which both current conformers share. A future tool whose ``--version`` prints a
        different shape can override this.
        """
        match = re.search(r"(\d+\.\d+\.\d+\S*)", output)
        return match.group(1) if match else None


class UnsupportedManagedPlatformError(Exception):
    """The running platform has no pinned distribution for a managed tool."""


def _resolve_platform_key(platform_map: Mapping[tuple[str, str], str], label: str) -> str:
    """Map the running platform to a managed tool's release platform key, or raise.

    Shared lookup boilerplate; each tool passes its own (Claude/pi differ in which
    platform keys exist) map and a label for the structured error message.
    """
    key = (sys.platform, platform.machine())
    result = platform_map.get(key)
    if result is None:
        raise UnsupportedManagedPlatformError(
            f"Unsupported platform for managed {label}: {sys.platform}/{platform.machine()}"
        )
    return result


# pi ships a ``darwin-x64`` build that ``_CLAUDE_PLATFORM_MAP`` deliberately omits, so
# managed pi resolves the running platform against its own (broader) map. The maps live
# in the seam (not the service) so platform resolution never imports the service — the
# reverse of the service -> managed_tools edge, which would be an import cycle.
_PI_PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "darwin-arm64",
    ("darwin", "x86_64"): "darwin-x64",
    ("linux", "x86_64"): "linux-x64",
}

_PI_RELEASE_BASE_URL = "https://github.com/earendil-works/pi/releases/download"

# Built from the pin rather than imported from the service's ``PI_VERSION_RANGE`` (that
# reverse import would cycle); a unit test asserts the two stay equal.
_PI_VERSION_RANGE = VersionRange(
    min_version=PI_PIN.version,
    max_version=PI_PIN.version,
    recommended_version=PI_PIN.version,
)


def _current_pi_platform_key() -> str:
    """Map the running platform to a pinned-pi platform key, or raise a structured error."""
    return _resolve_platform_key(_PI_PLATFORM_MAP, "pi")


class PiManagedTool(ManagedTool):
    """Managed-install conformer for pi.

    pi publishes per-platform tarballs and no checksums of its own, so the
    distribution descriptor is built entirely from the static ``PI_PIN`` (no network
    to resolve it) and verified against the baked sha256 at download time.
    """

    tool = Dependency.PI
    version_range = _PI_VERSION_RANGE
    platform_keys = frozenset({"darwin-arm64", "darwin-x64", "linux-x64"})
    retention_keep = 1
    # pi keeps its whole extracted tree and runs from ``pi/pi``.
    binary_subpath = "pi/pi"

    def resolve_distribution(self) -> ResolvedDistribution:
        platform_key = _current_pi_platform_key()
        pin = PI_PIN.platforms[platform_key]
        return ResolvedDistribution(
            version=PI_PIN.version,
            url=f"{_PI_RELEASE_BASE_URL}/v{PI_PIN.version}/{pin.asset}",
            checksum_sha256=pin.sha256,
            # pi publishes no size; the download's content-length drives progress.
            size=None,
            archive="tarball",
            binary_subpath="pi/pi",
        )

    def stage(self, downloaded: Path, version_dir: Path) -> Path:
        # The whole ``pi/`` tree is kept — the binary loads sibling assets at runtime.
        # The tarball is checksum-verified by the orchestrator before this runs.
        version_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(downloaded, "r:gz") as tar:
            tar.extractall(version_dir)
        binary = version_dir / "pi" / "pi"
        # The archive's mode bits aren't guaranteed across mirrors; ensure the
        # entrypoint is runnable before the orchestrator gates on ``--version``.
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary


GCP_BUCKET_BASE_URL = (
    "https://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"
)

# Timeout for the single HTTP fetch of Claude's release manifest.
_CLAUDE_MANIFEST_FETCH_TIMEOUT_SECONDS = 30.0

# Claude's supported version window. Defined here (not in the dependency service) so
# ``ClaudeManagedTool`` can read it without importing the service — the reverse of
# the existing service -> managed_tools edge, which would be an import cycle. The
# service re-imports this constant for its status / version-range logic.
CLAUDE_VERSION_RANGE = VersionRange(
    min_version="2.1.195",
    max_version="2.99.99",
    recommended_version="2.1.195",
    # Blocked versions create background tool invocations that are missing events
    # describing them.
    blocked_versions=(BlockedVersionRange(min_version="2.1.101", max_version="2.1.101"),),
)


class ManifestPlatformInfo(FrozenModel):
    binary: str
    checksum: str
    size: int


class Manifest(FrozenModel):
    """Claude's raw remote release manifest (GCP ``manifest.json``).

    The single remote schema ``ClaudeManagedTool.resolve_distribution`` parses before
    adapting the chosen platform into a normalized ``ResolvedDistribution``.
    """

    version: str
    build_date: str
    platforms: dict[str, ManifestPlatformInfo]


class ManagedDistributionError(Exception):
    """A managed tool's remote distribution could not be resolved (fetch / parse / platform)."""


# Claude ships only darwin-arm64 + linux-x64 (no darwin-x64), so it resolves the
# running platform against its own map rather than pi's broader one. Kept in the seam
# for the same reason as ``_PI_PLATFORM_MAP``: platform resolution must not import the
# service, which would reverse the service -> managed_tools edge.
_CLAUDE_PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "darwin-arm64",
    ("linux", "x86_64"): "linux-x64",
}


def _current_claude_platform_key() -> str:
    """Map the running platform to a Claude release platform key, or raise a structured error."""
    return _resolve_platform_key(_CLAUDE_PLATFORM_MAP, "claude")


class ClaudeManagedTool(ManagedTool):
    """Managed-install conformer for Claude.

    Claude publishes a per-version ``manifest.json`` on GCP listing one single binary
    per platform with its sha256; ``resolve_distribution`` fetches and adapts that
    manifest, and ``stage`` drops the verified binary into the version dir.
    """

    tool = Dependency.CLAUDE
    version_range = CLAUDE_VERSION_RANGE
    platform_keys = frozenset({"darwin-arm64", "linux-x64"})
    retention_keep = 2
    # Claude's single binary sits directly at ``claude`` in the version dir.
    binary_subpath = "claude"

    def resolve_distribution(self) -> ResolvedDistribution:
        platform_key = _current_claude_platform_key()
        version = CLAUDE_VERSION_RANGE.recommended_version
        manifest_url = f"{GCP_BUCKET_BASE_URL}/{version}/manifest.json"

        try:
            resp = httpx.get(manifest_url, timeout=_CLAUDE_MANIFEST_FETCH_TIMEOUT_SECONDS)
            resp.raise_for_status()
            manifest_data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ManagedDistributionError(f"Failed to fetch manifest: {e}") from e

        try:
            manifest = Manifest(
                version=manifest_data["version"],
                build_date=manifest_data["buildDate"],
                platforms={
                    k: ManifestPlatformInfo(binary=v["binary"], checksum=v["checksum"], size=v["size"])
                    for k, v in manifest_data["platforms"].items()
                },
            )
        except (KeyError, TypeError) as e:
            raise ManagedDistributionError(f"Invalid manifest format: {e}") from e

        if platform_key not in manifest.platforms:
            raise ManagedDistributionError(f"Platform {platform_key} not found in manifest")

        platform_info = manifest.platforms[platform_key]
        # The download URL targets the manifest's own version, not the requested
        # recommended_version.
        return ResolvedDistribution(
            version=manifest.version,
            url=f"{GCP_BUCKET_BASE_URL}/{manifest.version}/{platform_key}/{platform_info.binary}",
            checksum_sha256=platform_info.checksum,
            size=platform_info.size,
            archive="single_binary",
            binary_subpath=platform_info.binary,
        )

    def stage(self, downloaded: Path, version_dir: Path) -> Path:
        # Single binary: place it directly at version_dir/<binary_name>. The download's
        # filename is the manifest binary name, which is also the
        # ResolvedDistribution.binary_subpath the orchestrator activates.
        version_dir.mkdir(parents=True, exist_ok=True)
        # The download's mode bits aren't guaranteed executable; chmod before the
        # orchestrator gates on ``--version``.
        downloaded.chmod(downloaded.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        staged = version_dir / downloaded.name
        downloaded.rename(staged)
        return staged


# Both Claude and pi conform to the seam; unmanaged tools (e.g. ``GIT``) stay absent
# so ``get_managed_tool`` returns None for them.
_MANAGED_TOOL_REGISTRY: dict[Dependency, ManagedTool] = {
    Dependency.CLAUDE: ClaudeManagedTool(),
    Dependency.PI: PiManagedTool(),
}


def get_managed_tool(tool: Dependency) -> ManagedTool | None:
    """Return the ``ManagedTool`` for a dependency, or None when it is unmanaged."""
    return _MANAGED_TOOL_REGISTRY.get(tool)


def get_managed_tools() -> tuple[Dependency, ...]:
    """The dependencies that have a managed-install conformer, in registry order."""
    return tuple(_MANAGED_TOOL_REGISTRY)
