#!/usr/bin/env python3
"""Recompute pi's per-platform sha256 pin for a given pi version.

pi publishes no checksums of its own, so Sculptor computes and bakes them into
``PI_PIN`` (``sculptor/services/managed_tools.py``). This dev tool downloads each
supported-platform release tarball, hashes it, and prints the ``platforms={...}``
block to paste into ``PI_PIN``. It is the single manual step at a pi version bump.

Usage:
    just compute-pi-pin 0.78.0
    uv run python scripts/compute_pi_pin.py 0.78.0

Network is required; the runtime install path never fetches checksums, only the
static values produced here.
"""

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from collections.abc import Sequence

# Duplicated from ``PI_PIN.platforms`` to keep this a standalone, dependency-free
# dev tool (it must not import the sculptor package). Keep the two sets in sync.
SUPPORTED_PLATFORM_KEYS: tuple[str, ...] = ("darwin-arm64", "darwin-x64", "linux-x64")

_RELEASE_URL_TEMPLATE = "https://github.com/earendil-works/pi/releases/download/v{version}/{asset}"
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 30


class PiAssetDownloadError(RuntimeError):
    """Raised when a pi release asset cannot be downloaded for hashing."""


def asset_name_for_platform(platform_key: str) -> str:
    """Return the release asset filename for a platform key (e.g. ``pi-darwin-arm64.tar.gz``)."""
    return f"pi-{platform_key}.tar.gz"


def release_url(version: str, asset: str) -> str:
    """Return the GitHub release download URL for an asset of a pi version."""
    return _RELEASE_URL_TEMPLATE.format(version=version, asset=asset)


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
        raise PiAssetDownloadError(f"Could not download pi asset: {url}") from error
    return digest.hexdigest()


def compute_platform_shas(version: str) -> dict[str, str]:
    """Download every supported-platform tarball and return ``{platform_key: sha256}``."""
    shas: dict[str, str] = {}
    for platform_key in SUPPORTED_PLATFORM_KEYS:
        asset = asset_name_for_platform(platform_key)
        url = release_url(version, asset)
        print(f"Downloading {asset} ...", file=sys.stderr)
        shas[platform_key] = compute_asset_sha256(url)
    return shas


def format_pin_block(shas: Mapping[str, str]) -> str:
    """Render the ``PI_PIN`` ``platforms={...}`` block from computed digests."""
    lines = ["    platforms={"]
    for platform_key in SUPPORTED_PLATFORM_KEYS:
        asset = asset_name_for_platform(platform_key)
        lines.append(f'        "{platform_key}": PlatformPin(asset="{asset}", sha256="{shas[platform_key]}"),')
    lines.append("    },")
    return "\n".join(lines)


def main(argv: Sequence[str]) -> int:
    """Parse the version argument, compute the digests, and print the pin block."""
    parser = argparse.ArgumentParser(description="Recompute pi's per-platform sha256 pin for PI_PIN.")
    parser.add_argument("version", help="pi version to pin, without a leading 'v' (e.g. 0.78.0)")
    arguments = parser.parse_args(argv)

    shas = compute_platform_shas(arguments.version)
    print(format_pin_block(shas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
