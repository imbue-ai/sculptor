#!/usr/bin/env python3
"""Apply a pi version bump to every file that pins or hardcodes the version.

``compute_pi_pin`` prints the sha block for a human to paste; this tool goes the
rest of the way. It downloads and hashes the target release's tarballs (reusing
``compute_pi_pin``), cross-checks the digests against the release's published
``SHA256SUMS`` when one exists, and rewrites the pin plus every hardcoded copy:
the version constant, the baked sha256s, the backend/frontend test literals, the
Storybook fixture, and the requirements doc.

Two tripwires keep a bump honest. Every rewrite asserts an exact occurrence
count, so a pinned literal that moves or multiplies fails the bump instead of
landing it half-applied. And after the rewrites, no touched file may still
contain an old version/digest literal, so a hardcoded copy this tool does not
know about yet surfaces as an error naming the file.

Usage:
    just bump-pi 0.81.0
    python3 scripts/bump_pi_pin.py 0.81.0

The ``pi-bump`` workflow runs this on its daily schedule (target version from
``check_pi_pin_freshness``) and opens a PR with the result. Network is
required. Stdlib-only, like its ``scripts/`` siblings.
"""

import argparse
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import check_pi_pin_freshness
import compute_pi_pin

_PI_VERSION_FILE = "sculptor/sculptor/services/pi_version.py"
_MANAGED_TOOLS_FILE = "sculptor/sculptor/services/managed_tools.py"
_MANAGED_TOOLS_TEST_FILE = "sculptor/sculptor/services/managed_tools_test.py"
_AGENT_WRAPPER_TEST_FILE = "sculptor/sculptor/agents/pi_agent/agent_wrapper_test.py"
_USE_MANAGED_DEPENDENCY_TEST_FILE = "sculptor/frontend/src/common/useManagedDependency.test.tsx"
_DEPENDENCIES_STORY_FILE = "sculptor/frontend/src/stories/custom/DependenciesSettingsSection.stories.tsx"
_REQUIREMENTS_FILE = "docs/specs/requirements.md"

_SHA256SUMS_ASSET = "SHA256SUMS"
_REQUEST_TIMEOUT_SECONDS = 30


class BumpError(RuntimeError):
    """Raised when the bump cannot be applied safely."""


@dataclass(frozen=True)
class PlannedEdit:
    """One exact-string rewrite in one file, with its required occurrence count."""

    path: str
    old: str
    new: str
    count: int


def read_baked_shas(repo_root: Path) -> dict[str, str]:
    """Read the current per-platform sha256 pins out of ``PI_PIN``."""
    source = (repo_root / _MANAGED_TOOLS_FILE).read_text()
    shas: dict[str, str] = {}
    for platform_key in compute_pi_pin.SUPPORTED_PLATFORM_KEYS:
        asset = compute_pi_pin.asset_name_for_platform(platform_key)
        pattern = re.compile(
            rf'"{re.escape(platform_key)}": PlatformPin\(\s*asset="{re.escape(asset)}",\s*sha256="([0-9a-f]{{64}})"'
        )
        match = pattern.search(source)
        if match is None:
            raise BumpError(f"Could not locate the {platform_key} pin in {_MANAGED_TOOLS_FILE}")
        shas[platform_key] = match.group(1)
    return shas


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse ``sha256sum``-style output lines into ``{asset_name: digest}``."""
    digests: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            raise BumpError(f"Unexpected SHA256SUMS line: {line!r}")
        digest, asset = parts
        digests[asset] = digest
    return digests


def fetch_published_sha256sums(version: str) -> dict[str, str] | None:
    """Fetch upstream's ``SHA256SUMS`` for a release, or None when it publishes none."""
    url = compute_pi_pin.release_url(version, _SHA256SUMS_ASSET)
    request = urllib.request.Request(url, headers={"User-Agent": "sculptor-pi-bump"})
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            text = response.read().decode()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise BumpError(f"Could not download {url}: {error}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise BumpError(f"Could not download {url}: {error}") from error
    return parse_sha256sums(text)


def verify_computed_against_published(computed: Mapping[str, str], published: Mapping[str, str] | None) -> None:
    """Fail when upstream's published digests disagree with what we downloaded.

    A mismatch means the tarball we hashed is not the one upstream published —
    do not bake it. The repo's own computed digests stay the source of truth
    either way, so a release without ``SHA256SUMS`` just skips the cross-check.
    """
    if published is None:
        print("No published SHA256SUMS for this release; skipping the cross-check.")
        return
    for platform_key, digest in computed.items():
        asset = compute_pi_pin.asset_name_for_platform(platform_key)
        upstream_digest = published.get(asset)
        if upstream_digest is None:
            raise BumpError(f"Upstream SHA256SUMS is missing {asset}")
        if upstream_digest != digest:
            raise BumpError(f"Digest mismatch for {asset}: computed {digest}, upstream publishes {upstream_digest}")


def plan_edits(
    old_version: str, new_version: str, old_shas: Mapping[str, str], new_shas: Mapping[str, str]
) -> tuple[PlannedEdit, ...]:
    """Every file that carries the pi version or its digests, as exact rewrites.

    The counts are load-bearing: a mismatch means a pinned literal moved or
    gained a copy, and the bump must stop so a human re-audits this table.
    """
    old_name = f"_PI_DARWIN_ARM64_SHA256_{old_version.replace('.', '_')}"
    new_name = f"_PI_DARWIN_ARM64_SHA256_{new_version.replace('.', '_')}"
    return (
        PlannedEdit(
            _PI_VERSION_FILE,
            f'PI_PINNED_VERSION = "{old_version}"',
            f'PI_PINNED_VERSION = "{new_version}"',
            1,
        ),
        *(
            PlannedEdit(
                _MANAGED_TOOLS_FILE,
                f'sha256="{old_shas[platform_key]}"',
                f'sha256="{new_shas[platform_key]}"',
                1,
            )
            for platform_key in compute_pi_pin.SUPPORTED_PLATFORM_KEYS
        ),
        PlannedEdit(_MANAGED_TOOLS_TEST_FILE, f"for pi {old_version};", f"for pi {new_version};", 1),
        PlannedEdit(_MANAGED_TOOLS_TEST_FILE, old_name, new_name, 2),
        PlannedEdit(
            _MANAGED_TOOLS_TEST_FILE,
            f'= "{old_shas["darwin-arm64"]}"',
            f'= "{new_shas["darwin-arm64"]}"',
            1,
        ),
        PlannedEdit(_AGENT_WRAPPER_TEST_FILE, f'"pi {old_version}\\n"', f'"pi {new_version}\\n"', 2),
        PlannedEdit(
            _AGENT_WRAPPER_TEST_FILE,
            f'pinned_version == "{old_version}"',
            f'pinned_version == "{new_version}"',
            1,
        ),
        PlannedEdit(_USE_MANAGED_DEPENDENCY_TEST_FILE, f'version: "{old_version}",', f'version: "{new_version}",', 2),
        PlannedEdit(
            _DEPENDENCIES_STORY_FILE,
            f'minVersion: "{old_version}", maxVersion: "{old_version}", recommendedVersion: "{old_version}"',
            f'minVersion: "{new_version}", maxVersion: "{new_version}", recommendedVersion: "{new_version}"',
            1,
        ),
        PlannedEdit(_REQUIREMENTS_FILE, f"pins **{old_version}**", f"pins **{new_version}**", 1),
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
            raise BumpError(
                f"{edit.path}: expected {edit.count} occurrence(s) of {edit.old!r}, found {occurrences}. "
                "The pinned literals have drifted; update plan_edits in scripts/bump_pi_pin.py."
            )
        contents[edit.path] = contents[edit.path].replace(edit.old, edit.new)
    return contents


def assert_no_stale_residue(contents: Mapping[str, str], replaced_pairs: Sequence[tuple[str, str]]) -> None:
    """After the rewrites, no touched file may still carry an old literal.

    Catches a hardcoded copy that ``plan_edits`` does not know about yet — the
    counts only police the known copies. A pair whose old literal is a substring
    of its replacement is skipped, since the new text legitimately contains it
    (e.g. bumping 0.80.10 to 0.80.100).
    """
    for path, content in contents.items():
        for old_literal, new_literal in replaced_pairs:
            if old_literal in new_literal:
                continue
            if old_literal in content:
                raise BumpError(
                    f"{path}: still contains {old_literal!r} after the bump; "
                    "add the new copy to plan_edits in scripts/bump_pi_pin.py."
                )


def write_contents(repo_root: Path, contents: Mapping[str, str]) -> None:
    """Write the rewritten files back to the checkout."""
    for path, content in contents.items():
        (repo_root / path).write_text(content)


def main(argv: Sequence[str]) -> int:
    """Parse the target version, verify the digests, and rewrite the pinned copies."""
    parser = argparse.ArgumentParser(description="Apply a pi version bump across the repo's pinned copies.")
    parser.add_argument("version", help="pi version to pin, without a leading 'v' (e.g. 0.81.0)")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root to rewrite (defaults to this checkout)",
    )
    arguments = parser.parse_args(argv)
    target_version = arguments.version
    check_pi_pin_freshness.parse_version(target_version)

    current_version = check_pi_pin_freshness.read_pinned_version(arguments.repo_root)
    if current_version == target_version:
        print(f"pi is already pinned to {target_version}; nothing to do.")
        return 0
    if check_pi_pin_freshness.is_stale(target_version, current_version):
        print(f"Note: {target_version} is older than the current pin {current_version}; applying the downgrade.")

    print(f"Bumping pi {current_version} -> {target_version}")
    old_shas = read_baked_shas(arguments.repo_root)
    new_shas = compute_pi_pin.compute_platform_shas(target_version)
    verify_computed_against_published(new_shas, fetch_published_sha256sums(target_version))

    contents = apply_edits_in_memory(arguments.repo_root, plan_edits(current_version, target_version, old_shas, new_shas))
    replaced_pairs = [
        (current_version, target_version),
        (current_version.replace(".", "_"), target_version.replace(".", "_")),
        *((old_shas[platform_key], new_shas[platform_key]) for platform_key in compute_pi_pin.SUPPORTED_PLATFORM_KEYS),
    ]
    assert_no_stale_residue(contents, replaced_pairs)
    write_contents(arguments.repo_root, contents)
    for path in sorted(contents):
        print(f"rewrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
