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
from sculptor.services.jj_version import JJ_PINNED_SHA256_BY_TARGET_TRIPLE
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.services.pi_version import PI_PINNED_VERSION


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
    """One platform's pinned release artifact: the asset name and its expected sha256."""

    asset: str
    sha256: str


class ReleasePin(FrozenModel):
    """The static, in-repo source of truth for a tool published as per-platform release assets.

    Sculptor computes the digests itself per version (``just bump-pi`` / ``just bump-jj``,
    which cross-check what upstream publishes) and bakes them in; the install path
    verifies downloads against these pinned values only.
    """

    version: str
    platforms: dict[str, PlatformPin]


class PiPin(ReleasePin):
    """The managed pi distribution's pin."""

    # Reserved slot, not read from user config: a constant sentinel until a pi
    # plugin set needs pinning.
    plugin_set_revision: str = "bundled"


PI_PIN = PiPin(
    version=PI_PINNED_VERSION,
    platforms={
        "darwin-arm64": PlatformPin(
            asset="pi-darwin-arm64.tar.gz",
            sha256="1f9ae61cdeae04dd68caf1a1e8ab8ec9b292062f6ccb3252e0a9cbe93b5b16f1",
        ),
        "darwin-x64": PlatformPin(
            asset="pi-darwin-x64.tar.gz",
            sha256="9ff562e2e439f50971b1f6bd9b62b30946600d9e9baa4ea19635cf630a553066",
        ),
        "linux-x64": PlatformPin(
            asset="pi-linux-x64.tar.gz",
            sha256="24f5be328b66d4da36876296989501974f43ab8434fbb57c35c523a3ea505ded",
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
    # Whether startup auto-install may download this tool when no managed copy exists
    # yet. A required tool (Claude) bootstraps itself on first run; an optional one
    # (pi) is first installed only by explicit user action, and startup merely
    # refreshes an already-downloaded copy that has fallen out of the pinned range.
    installs_on_startup_when_missing: bool

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

# Defined here, not in the dependency service, so ``PiManagedTool`` can reference it
# without importing the service (which imports this module — a cycle). The service
# re-exports it.
PI_VERSION_RANGE = VersionRange(
    min_version=PI_PINNED_VERSION,
    max_version=PI_PINNED_VERSION,
    recommended_version=PI_PINNED_VERSION,
)


def _current_pi_platform_key() -> str:
    """Map the running platform to a pinned-pi platform key, or raise a structured error."""
    return _resolve_platform_key(_PI_PLATFORM_MAP, "pi")


class PiManagedTool(ManagedTool):
    """Managed-install conformer for pi.

    pi publishes per-platform tarballs; the distribution descriptor is built
    entirely from the static ``PI_PIN`` (no network to resolve it) and verified
    against the baked sha256 at download time.
    """

    tool = Dependency.PI
    version_range = PI_VERSION_RANGE
    platform_keys = frozenset({"darwin-arm64", "darwin-x64", "linux-x64"})
    retention_keep = 1
    # pi keeps its whole extracted tree and runs from ``pi/pi``.
    binary_subpath = "pi/pi"
    # pi is an optional harness: its managed copy is downloaded only when the user
    # asks for it (onboarding or Settings), never by startup.
    installs_on_startup_when_missing = False

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


# jj names its release assets after Rust target triples; the Linux builds are the static
# musl ones, so they run on any distribution.
_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY: dict[str, str] = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x64": "x86_64-apple-darwin",
    "linux-x64": "x86_64-unknown-linux-musl",
    "linux-arm64": "aarch64-unknown-linux-musl",
}

# The digests live in the import-free ``jj_version`` module, which ``just install-jj``
# and the offload image check also read, so the pin is assembled from it here.
JJ_PIN = ReleasePin(
    version=JJ_PINNED_VERSION,
    platforms={
        platform_key: PlatformPin(
            asset=f"jj-v{JJ_PINNED_VERSION}-{target_triple}.tar.gz",
            sha256=JJ_PINNED_SHA256_BY_TARGET_TRIPLE[target_triple],
        )
        for platform_key, target_triple in _JJ_TARGET_TRIPLE_BY_PLATFORM_KEY.items()
    },
)

_JJ_PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "darwin-arm64",
    ("darwin", "x86_64"): "darwin-x64",
    ("linux", "x86_64"): "linux-x64",
    ("linux", "aarch64"): "linux-arm64",
}

_JJ_RELEASE_BASE_URL = "https://github.com/jj-vcs/jj/releases/download"

# The pin is also the floor, and any later 0.x is accepted so a system jj from a
# package manager keeps working; bumping the pin raises the floor.
JJ_VERSION_RANGE = VersionRange(
    min_version=JJ_PINNED_VERSION,
    max_version="0.999.999",
    recommended_version=JJ_PINNED_VERSION,
)

# `jj --version` prints `jj 0.46.0-<40-hex commit hash>`; the shared parser would keep
# the hash suffix, which ``packaging.Version`` rejects.
_JJ_VERSION_LINE_PATTERN = re.compile(r"^jj (\d+\.\d+\.\d+)(?:-\S+)?$", re.MULTILINE)


class JjManagedTool(ManagedTool):
    """Managed-install conformer for jj (Jujutsu).

    Like pi, the distribution is built from the static ``JJ_PIN`` and the managed copy
    is downloaded only on explicit user action.
    """

    tool = Dependency.JJ
    version_range = JJ_VERSION_RANGE
    platform_keys = frozenset(_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY)
    retention_keep = 1
    binary_subpath = "jj"
    installs_on_startup_when_missing = False

    def resolve_distribution(self) -> ResolvedDistribution:
        platform_key = _resolve_platform_key(_JJ_PLATFORM_MAP, "jj")
        pin = JJ_PIN.platforms[platform_key]
        return ResolvedDistribution(
            version=JJ_PIN.version,
            url=f"{_JJ_RELEASE_BASE_URL}/v{JJ_PIN.version}/{pin.asset}",
            checksum_sha256=pin.sha256,
            size=None,
            archive="tarball",
            binary_subpath=self.binary_subpath,
        )

    def stage(self, downloaded: Path, version_dir: Path) -> Path:
        # The tarball holds ``./jj`` beside its LICENSE and README; only the binary is kept.
        version_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(downloaded, "r:gz") as tar:
            tar.extract("./jj", version_dir, filter="data")
        binary = version_dir / self.binary_subpath
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    def parse_version(self, output: str) -> str | None:
        match = _JJ_VERSION_LINE_PATTERN.search(output)
        return match.group(1) if match else None


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
    # Keep the floor at recommended: an in-range managed binary is never upgraded to
    # recommended (auto-install and the "up to date" status both gate on range, not
    # recommended), so a lower floor strands old installs.
    min_version="2.1.306",
    max_version="2.99.99",
    # Recommended is the latest validated release. It has to be one whose model table
    # carries every `--model` id the picker offers, which is ahead of the `stable`
    # channel whenever a new model generation has just shipped.
    recommended_version="2.1.306",
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
    # Claude is required, so a missing MANAGED binary is installed on startup.
    installs_on_startup_when_missing = True

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


# Unmanaged tools (e.g. ``GIT``) stay absent so ``get_managed_tool`` returns None for them.
_MANAGED_TOOL_REGISTRY: dict[Dependency, ManagedTool] = {
    Dependency.CLAUDE: ClaudeManagedTool(),
    Dependency.PI: PiManagedTool(),
    Dependency.JJ: JjManagedTool(),
}


def get_managed_tool(tool: Dependency) -> ManagedTool | None:
    """Return the ``ManagedTool`` for a dependency, or None when it is unmanaged."""
    return _MANAGED_TOOL_REGISTRY.get(tool)


def get_managed_tools() -> tuple[Dependency, ...]:
    """The dependencies that have a managed-install conformer, in registry order."""
    return tuple(_MANAGED_TOOL_REGISTRY)
