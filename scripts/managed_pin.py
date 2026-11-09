"""Shared logic and per-tool specs for the managed-tool pin scripts.

Sculptor pins each managed tool to one exact version and bakes its own
per-platform sha256 digests into the tool's pin (``PI_PIN`` in
``sculptor/sculptor/services/managed_tools.py``, jj's digests in
``sculptor/sculptor/services/jj_version.py``); upstream's published digests
are only ever a cross-check, never the source of truth. The entry points
``compute_pin.py``, ``bump_pin.py`` and ``check_pin_freshness.py`` take a tool
name and look its ``ToolPinSpec`` up in ``TOOL_PIN_SPECS``; whatever differs
between tools lives in the spec, and the logic that does not lives here.

Stdlib-only: the scripts run under a bare interpreter in CI, so nothing here may
import the sculptor package.
"""

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from enum import auto
from pathlib import Path

_RELEASE_URL_TEMPLATE = "https://github.com/{repo}/releases/download/v{version}/{asset}"
_GITHUB_API_TIMEOUT_SECONDS = 30
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 30


class PinError(RuntimeError):
    """Raised when a pin cannot be read, computed, or rewritten safely."""


@dataclass(frozen=True)
class PlannedEdit:
    """One exact-string rewrite in one file, with its required occurrence count."""

    path: str
    old: str
    new: str
    count: int


class PublishedDigestSource(Enum):
    """Where upstream publishes a release's digests for the bump to cross-check against."""

    SHA256SUMS_ASSET = auto()
    RELEASE_API = auto()


@dataclass(frozen=True)
class ToolPinSpec:
    """Everything the pin scripts need to know about one managed tool.

    Paths are relative to the repository root. ``asset_name_for_platform`` takes
    ``(platform_key, version)``. ``baked_sha256_pattern_for_platform`` returns a
    regex whose one group captures that platform's digest in ``pin_file``, and
    ``format_pin_block`` renders the digests the way ``pin_file`` holds them.
    ``hardcoded_copy_edits`` takes ``(old_version, new_version, old_shas, new_shas)``
    and returns the rewrites for the copies of the version and digests hardcoded
    in tests, fixtures, docs and images; ``plan_edits`` adds the version constant
    and the baked digests. ``stale_pin_advice_template`` is formatted with
    ``latest`` and closes the staleness warning.
    """

    name: str
    github_repo: str
    version_file: str
    version_constant: str
    pin_file: str
    platform_keys: tuple[str, ...]
    asset_name_for_platform: Callable[[str, str], str]
    baked_sha256_pattern_for_platform: Callable[[str], str]
    format_pin_block: Callable[[Mapping[str, str]], str]
    published_digest_source: PublishedDigestSource
    hardcoded_copy_edits: Callable[[str, str, Mapping[str, str], Mapping[str, str]], tuple[PlannedEdit, ...]]
    stale_pin_advice_template: str


def release_url(spec: ToolPinSpec, version: str, asset: str) -> str:
    """Return the GitHub release download URL for an asset of a tool version."""
    return _RELEASE_URL_TEMPLATE.format(repo=spec.github_repo, version=version, asset=asset)


def compute_asset_sha256(url: str) -> str:
    """Stream the asset at ``url`` and return its hex sha256 digest."""
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
    except (urllib.error.URLError, TimeoutError) as error:
        raise PinError(f"Could not download release asset: {url}") from error
    return digest.hexdigest()


def fetch_github_api_json(spec: ToolPinSpec, url: str) -> object:
    """GET a GitHub API URL, authenticating with ``GH_TOKEN`` or ``GITHUB_TOKEN`` when set.

    Anonymous requests work but are rate-limited per IP.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        # The GitHub API rejects requests that send no User-Agent.
        "User-Agent": f"sculptor-{spec.name}-pin",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_GITHUB_API_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise PinError(f"Could not fetch {url}: {error}") from error


def compute_platform_shas(spec: ToolPinSpec, version: str) -> dict[str, str]:
    """Download every supported-platform tarball and return ``{platform_key: sha256}``."""
    shas: dict[str, str] = {}
    for platform_key in spec.platform_keys:
        asset = spec.asset_name_for_platform(platform_key, version)
        print(f"Downloading {asset} ...", file=sys.stderr)
        shas[platform_key] = compute_asset_sha256(release_url(spec, version, asset))
    return shas


def read_pinned_version(spec: ToolPinSpec, repo_root: Path) -> str:
    """Extract the tool's pinned-version constant from its dependency-free module, textually.

    Parsing the source instead of importing it keeps these scripts runnable with
    a bare interpreter — the same reason the constant lives in an import-free
    module in the first place.
    """
    source = (repo_root / spec.version_file).read_text()
    pattern = re.compile(rf'^{re.escape(spec.version_constant)} = "([^"]+)"$', re.MULTILINE)
    match = pattern.search(source)
    if match is None:
        raise PinError(f"{spec.version_constant} not found in {spec.version_file}")
    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a strict ``MAJOR.MINOR.PATCH`` version for ordered comparison."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise PinError(f"Unexpected version format: {version!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_stale(pinned: str, latest: str) -> bool:
    """True when the latest release is strictly newer than the pin.

    Compares numerically, not lexically: ``0.80.10`` is newer than ``0.80.2``.
    """
    return parse_version(latest) > parse_version(pinned)


def read_baked_shas(spec: ToolPinSpec, repo_root: Path) -> dict[str, str]:
    """Read the current per-platform sha256 pins out of the tool's pin."""
    source = (repo_root / spec.pin_file).read_text()
    shas: dict[str, str] = {}
    for platform_key in spec.platform_keys:
        match = re.search(spec.baked_sha256_pattern_for_platform(platform_key), source)
        if match is None:
            raise PinError(f"Could not locate the {spec.name} {platform_key} pin in {spec.pin_file}")
        shas[platform_key] = match.group(1)
    return shas


def plan_edits(
    spec: ToolPinSpec, old_version: str, new_version: str, old_shas: Mapping[str, str], new_shas: Mapping[str, str]
) -> tuple[PlannedEdit, ...]:
    """Every file that carries the tool's version or its digests, as exact rewrites.

    The counts are load-bearing: a mismatch means a pinned literal moved or
    gained a copy, and the bump must stop so a human re-audits the tool's spec.
    """
    return (
        PlannedEdit(
            spec.version_file,
            f'{spec.version_constant} = "{old_version}"',
            f'{spec.version_constant} = "{new_version}"',
            1,
        ),
        *(
            PlannedEdit(spec.pin_file, f'"{old_shas[platform_key]}"', f'"{new_shas[platform_key]}"', 1)
            for platform_key in spec.platform_keys
        ),
        *spec.hardcoded_copy_edits(old_version, new_version, old_shas, new_shas),
    )


def apply_edits_in_memory(repo_root: Path, edits: Sequence[PlannedEdit]) -> dict[str, str]:
    """Apply every edit to in-memory copies, verifying each occurrence count.

    Nothing touches disk here, so a failing count leaves the checkout pristine.
    """
    contents: dict[str, str] = {}
    for edit in edits:
        if edit.path not in contents:
            contents[edit.path] = (repo_root / edit.path).read_text()
        occurrences = contents[edit.path].count(edit.old)
        if occurrences != edit.count:
            raise PinError(
                f"{edit.path}: expected {edit.count} occurrence(s) of {edit.old!r}, found {occurrences}. "
                + "The pinned literals have drifted; update the tool's spec in scripts/managed_pin.py."
            )
        contents[edit.path] = contents[edit.path].replace(edit.old, edit.new)
    return contents


def assert_no_stale_residue(contents: Mapping[str, str], replaced_pairs: Sequence[tuple[str, str]]) -> None:
    """After the rewrites, no touched file may still carry an old literal.

    Catches a hardcoded copy that the tool's spec does not know about yet — the
    counts only police the known copies. A pair whose old literal is a substring
    of its replacement is skipped, since the new text legitimately contains it
    (e.g. bumping 0.80.10 to 0.80.100).
    """
    for path, content in contents.items():
        for old_literal, new_literal in replaced_pairs:
            if old_literal in new_literal:
                continue
            if old_literal in content:
                raise PinError(
                    f"{path}: still contains {old_literal!r} after the bump; "
                    + "add the new copy to the tool's spec in scripts/managed_pin.py."
                )


def write_contents(repo_root: Path, contents: Mapping[str, str]) -> None:
    """Write the rewritten files back to the checkout."""
    for path, content in contents.items():
        (repo_root / path).write_text(content)


_PI_MANAGED_TOOLS_TEST_FILE = "sculptor/sculptor/services/managed_tools_test.py"
_PI_AGENT_WRAPPER_TEST_FILE = "sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py"
_PI_USE_MANAGED_DEPENDENCY_TEST_FILE = "sculptor/frontend/src/pages/settings/hooks/useManagedDependency.test.tsx"
_PI_DEPENDENCIES_STORY_FILE = "sculptor/frontend/src/pages/settings/components/DependenciesSettingsSection.stories.tsx"
_PI_REQUIREMENTS_FILE = "docs/specs/requirements.md"


# Duplicated from ``PI_PIN.platforms``, since these scripts must not import the
# sculptor package. Keep the two sets in sync.
_PI_PLATFORM_KEYS = ("darwin-arm64", "darwin-x64", "linux-x64")


def _pi_asset(platform_key: str) -> str:
    """Return pi's release asset filename for a platform key (e.g. ``pi-darwin-arm64.tar.gz``).

    pi's asset names carry no version.
    """
    return f"pi-{platform_key}.tar.gz"


def _pi_baked_sha256_pattern(platform_key: str) -> str:
    asset = re.escape(_pi_asset(platform_key))
    return rf'"{re.escape(platform_key)}": PlatformPin\(\s*asset="{asset}",\s*sha256="([0-9a-f]{{64}})"'


def _format_pi_pin_block(shas: Mapping[str, str]) -> str:
    """Render ``PI_PIN``'s ``platforms={...}`` block."""
    lines = ["    platforms={"]
    for platform_key in _PI_PLATFORM_KEYS:
        asset = _pi_asset(platform_key)
        lines.append(f'        "{platform_key}": PlatformPin(asset="{asset}", sha256="{shas[platform_key]}"),')
    lines.append("    },")
    return "\n".join(lines)


def _pi_hardcoded_copy_edits(
    old_version: str, new_version: str, old_shas: Mapping[str, str], new_shas: Mapping[str, str]
) -> tuple[PlannedEdit, ...]:
    """The pi version and darwin-arm64 digest as the backend/frontend tests, the story and the spec hardcode them."""
    old_name = f"_PI_DARWIN_ARM64_SHA256_{old_version.replace('.', '_')}"
    new_name = f"_PI_DARWIN_ARM64_SHA256_{new_version.replace('.', '_')}"
    return (
        PlannedEdit(_PI_MANAGED_TOOLS_TEST_FILE, f"for pi {old_version};", f"for pi {new_version};", 1),
        PlannedEdit(_PI_MANAGED_TOOLS_TEST_FILE, old_name, new_name, 2),
        PlannedEdit(
            _PI_MANAGED_TOOLS_TEST_FILE,
            f'= "{old_shas["darwin-arm64"]}"',
            f'= "{new_shas["darwin-arm64"]}"',
            1,
        ),
        PlannedEdit(_PI_AGENT_WRAPPER_TEST_FILE, f'"pi {old_version}\\n"', f'"pi {new_version}\\n"', 2),
        PlannedEdit(
            _PI_AGENT_WRAPPER_TEST_FILE,
            f'pinned_version == "{old_version}"',
            f'pinned_version == "{new_version}"',
            1,
        ),
        PlannedEdit(
            _PI_USE_MANAGED_DEPENDENCY_TEST_FILE, f'version: "{old_version}",', f'version: "{new_version}",', 2
        ),
        PlannedEdit(
            _PI_DEPENDENCIES_STORY_FILE,
            f'minVersion: "{old_version}", maxVersion: "{old_version}", recommendedVersion: "{old_version}"',
            f'minVersion: "{new_version}", maxVersion: "{new_version}", recommendedVersion: "{new_version}"',
            1,
        ),
        PlannedEdit(_PI_REQUIREMENTS_FILE, f"pins **{old_version}**", f"pins **{new_version}**", 1),
    )


PI_PIN_SPEC = ToolPinSpec(
    name="pi",
    github_repo="earendil-works/pi",
    version_file="sculptor/sculptor/services/pi_version.py",
    version_constant="PI_PINNED_VERSION",
    pin_file="sculptor/sculptor/services/managed_tools.py",
    platform_keys=_PI_PLATFORM_KEYS,
    asset_name_for_platform=lambda platform_key, version: _pi_asset(platform_key),
    baked_sha256_pattern_for_platform=_pi_baked_sha256_pattern,
    format_pin_block=_format_pi_pin_block,
    published_digest_source=PublishedDigestSource.SHA256SUMS_ASSET,
    hardcoded_copy_edits=_pi_hardcoded_copy_edits,
    stale_pin_advice_template="The pi-bump workflow opens a bump PR daily, or run `just bump-pi {latest}`.",
)


_JJ_VERSION_FILE = "sculptor/sculptor/services/jj_version.py"
_JJ_OFFLOAD_DOCKERFILE = ".devcontainer/Dockerfile"

# Duplicated from ``_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY`` in managed_tools.py, since these
# scripts must not import the sculptor package. Ordered as jj_version.py lists them.
_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x64": "x86_64-apple-darwin",
    "linux-arm64": "aarch64-unknown-linux-musl",
    "linux-x64": "x86_64-unknown-linux-musl",
}


def _jj_asset_name_for_platform(platform_key: str, version: str) -> str:
    """Return jj's release asset filename (e.g. ``jj-v0.46.0-aarch64-apple-darwin.tar.gz``)."""
    return f"jj-v{version}-{_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY[platform_key]}.tar.gz"


def _jj_baked_sha256_pattern(platform_key: str) -> str:
    return rf'"{re.escape(_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY[platform_key])}": "([0-9a-f]{{64}})"'


def _format_jj_pin_block(shas: Mapping[str, str]) -> str:
    """Render jj_version.py's ``JJ_PINNED_SHA256_BY_TARGET_TRIPLE`` dict."""
    lines = ["JJ_PINNED_SHA256_BY_TARGET_TRIPLE = {"]
    for platform_key, target_triple in _JJ_TARGET_TRIPLE_BY_PLATFORM_KEY.items():
        lines.append(f'    "{target_triple}": "{shas[platform_key]}",')
    lines.append("}")
    return "\n".join(lines)


def _jj_hardcoded_copy_edits(
    old_version: str, new_version: str, old_shas: Mapping[str, str], new_shas: Mapping[str, str]
) -> tuple[PlannedEdit, ...]:
    """The offload image's own copy of the version and the Linux digests."""
    return (
        PlannedEdit(_JJ_OFFLOAD_DOCKERFILE, f"ARG JJ_VERSION={old_version}\n", f"ARG JJ_VERSION={new_version}\n", 1),
        PlannedEdit(
            _JJ_OFFLOAD_DOCKERFILE,
            f"ARG JJ_SHA256_X86_64={old_shas['linux-x64']}\n",
            f"ARG JJ_SHA256_X86_64={new_shas['linux-x64']}\n",
            1,
        ),
        PlannedEdit(
            _JJ_OFFLOAD_DOCKERFILE,
            f"ARG JJ_SHA256_AARCH64={old_shas['linux-arm64']}\n",
            f"ARG JJ_SHA256_AARCH64={new_shas['linux-arm64']}\n",
            1,
        ),
    )


JJ_PIN_SPEC = ToolPinSpec(
    name="jj",
    github_repo="jj-vcs/jj",
    version_file=_JJ_VERSION_FILE,
    version_constant="JJ_PINNED_VERSION",
    pin_file=_JJ_VERSION_FILE,
    platform_keys=tuple(_JJ_TARGET_TRIPLE_BY_PLATFORM_KEY),
    asset_name_for_platform=_jj_asset_name_for_platform,
    baked_sha256_pattern_for_platform=_jj_baked_sha256_pattern,
    format_pin_block=_format_jj_pin_block,
    # jj publishes no SHA256SUMS; GitHub records a digest for every release asset.
    published_digest_source=PublishedDigestSource.RELEASE_API,
    hardcoded_copy_edits=_jj_hardcoded_copy_edits,
    stale_pin_advice_template=(
        "Bumps are manual: run `just bump-jj {latest}`. The pin is also the oldest jj Sculptor accepts, "
        + "so a bump raises the floor for anyone using their own jj."
    ),
)

TOOL_PIN_SPECS: Mapping[str, ToolPinSpec] = {PI_PIN_SPEC.name: PI_PIN_SPEC, JJ_PIN_SPEC.name: JJ_PIN_SPEC}
