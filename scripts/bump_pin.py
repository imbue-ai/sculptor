#!/usr/bin/env python3
"""Apply a managed tool's version bump to every file that pins or hardcodes the version.

``compute_pin`` prints the sha block for a human to paste; this tool goes the
rest of the way. It downloads and hashes the target release's tarballs (reusing
``managed_pin``), cross-checks the digests against what upstream publishes (pi's
``SHA256SUMS`` asset when one exists; for jj, which publishes none, the GitHub
release API's per-asset digest), and rewrites the pin plus every hardcoded copy
the tool's spec lists in ``managed_pin``: for pi, the version constant, the
baked sha256s, the backend/frontend test literals, the Storybook fixture, and
the requirements doc; for jj, the version constant, the digests, and the
offload image's copy.

Two tripwires keep a bump honest. Every rewrite asserts an exact occurrence
count, so a pinned literal that moves or multiplies fails the bump instead of
landing it half-applied. And after the rewrites, no touched file may still
contain an old version/digest literal, so a hardcoded copy this tool does not
know about yet surfaces as an error naming the file.

Usage:
    just bump-pi 0.81.0
    just bump-jj 0.47.0
    python3 scripts/bump_pin.py pi 0.81.0

The ``pi-bump`` workflow runs this on its daily schedule (target version from
``check_pin_freshness``) and opens a PR with the result; jj is bumped by hand.
Network is required. Stdlib-only, like its ``scripts/`` siblings.
"""

import argparse
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

import managed_pin

_REQUEST_TIMEOUT_SECONDS = 30
_SHA256SUMS_ASSET = "SHA256SUMS"
_RELEASE_BY_TAG_API_URL_TEMPLATE = "https://api.github.com/repos/{repo}/releases/tags/v{version}"


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse ``sha256sum``-style output lines into ``{asset_name: digest}``."""
    digests: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            raise managed_pin.PinError(f"Unexpected SHA256SUMS line: {line!r}")
        digest, asset = parts
        digests[asset] = digest
    return digests


def fetch_published_sha256sums(spec: managed_pin.ToolPinSpec, version: str) -> dict[str, str] | None:
    """Fetch upstream's ``SHA256SUMS`` for a release, or None when it publishes none."""
    url = managed_pin.release_url(spec, version, _SHA256SUMS_ASSET)
    request = urllib.request.Request(url, headers={"User-Agent": f"sculptor-{spec.name}-bump"})
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            text = response.read().decode()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise managed_pin.PinError(f"Could not download {url}: {error}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise managed_pin.PinError(f"Could not download {url}: {error}") from error
    return parse_sha256sums(text)


def parse_release_api_digests(payload: object) -> dict[str, str]:
    """Map each release asset's name to the sha256 GitHub recorded for it.

    Assets GitHub has no digest for are left out, so the cross-check reports them
    as missing.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise managed_pin.PinError(f"Release response has no assets: {str(payload)[:200]}")
    digests: dict[str, str] = {}
    for asset in payload["assets"]:
        digest = asset.get("digest")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            digests[asset["name"]] = digest.removeprefix("sha256:")
    return digests


def fetch_release_api_digests(spec: managed_pin.ToolPinSpec, version: str) -> dict[str, str]:
    """Fetch the per-asset digests GitHub records for a release."""
    url = _RELEASE_BY_TAG_API_URL_TEMPLATE.format(repo=spec.github_repo, version=version)
    return parse_release_api_digests(managed_pin.fetch_github_api_json(spec, url))


def fetch_published_digests(spec: managed_pin.ToolPinSpec, version: str) -> dict[str, str] | None:
    """Fetch the digests upstream publishes for a release, or None when it publishes none."""
    match spec.published_digest_source:
        case managed_pin.PublishedDigestSource.SHA256SUMS_ASSET:
            return fetch_published_sha256sums(spec, version)
        case managed_pin.PublishedDigestSource.RELEASE_API:
            return fetch_release_api_digests(spec, version)
        case _ as unreachable:
            assert_never(unreachable)


def verify_computed_against_published(
    spec: managed_pin.ToolPinSpec,
    version: str,
    computed: Mapping[str, str],
    published: Mapping[str, str] | None,
) -> None:
    """Fail when upstream's published digests disagree with what we downloaded.

    A mismatch means the tarball we hashed is not the one upstream published —
    do not bake it. The repo's own computed digests stay the source of truth
    either way, so a release that publishes no digests just skips the cross-check.
    """
    if published is None:
        print(f"{spec.name} {version} publishes no digests; skipping the cross-check.")
        return
    for platform_key, digest in computed.items():
        asset = spec.asset_name_for_platform(platform_key, version)
        upstream_digest = published.get(asset)
        if upstream_digest is None:
            raise managed_pin.PinError(f"Upstream's published digests are missing {asset}")
        if upstream_digest != digest:
            raise managed_pin.PinError(
                f"Digest mismatch for {asset}: computed {digest}, upstream publishes {upstream_digest}"
            )


def main(argv: Sequence[str]) -> int:
    """Parse the tool and target version, verify the digests, and rewrite the pinned copies."""
    parser = argparse.ArgumentParser(
        description="Apply a managed tool's version bump across the repo's pinned copies."
    )
    parser.add_argument("tool", choices=sorted(managed_pin.TOOL_PIN_SPECS), help="managed tool to bump")
    parser.add_argument("version", help="version to pin, without a leading 'v' (e.g. 0.81.0)")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root to rewrite (defaults to this checkout)",
    )
    arguments = parser.parse_args(argv)
    spec = managed_pin.TOOL_PIN_SPECS[arguments.tool]
    target_version = arguments.version
    managed_pin.parse_version(target_version)

    current_version = managed_pin.read_pinned_version(spec, arguments.repo_root)
    if current_version == target_version:
        print(f"{spec.name} is already pinned to {target_version}; nothing to do.")
        return 0
    if managed_pin.is_stale(target_version, current_version):
        print(f"Note: {target_version} is older than the current pin {current_version}; applying the downgrade.")

    print(f"Bumping {spec.name} {current_version} -> {target_version}")
    old_shas = managed_pin.read_baked_shas(spec, arguments.repo_root)
    new_shas = managed_pin.compute_platform_shas(spec, target_version)
    verify_computed_against_published(
        spec, target_version, new_shas, fetch_published_digests(spec, target_version)
    )

    edits = managed_pin.plan_edits(spec, current_version, target_version, old_shas, new_shas)
    contents = managed_pin.apply_edits_in_memory(arguments.repo_root, edits)
    replaced_pairs = [
        (current_version, target_version),
        (current_version.replace(".", "_"), target_version.replace(".", "_")),
        *((old_shas[platform_key], new_shas[platform_key]) for platform_key in spec.platform_keys),
    ]
    managed_pin.assert_no_stale_residue(contents, replaced_pairs)
    managed_pin.write_contents(arguments.repo_root, contents)
    for path in sorted(contents):
        print(f"rewrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
