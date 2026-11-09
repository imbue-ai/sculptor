#!/usr/bin/env python3
"""Recompute a managed tool's per-platform sha256 pin for a given version.

Sculptor bakes its own per-platform digests into each managed tool's pin (``PI_PIN``
in ``sculptor/services/managed_tools.py``); upstream's published digests are only
ever a cross-check, never the source of truth. This dev tool downloads each
supported-platform release tarball, hashes it, and prints the digests in the shape
the pin holds them, ready to paste. ``scripts/bump_pin.py`` (``just bump-pi``) wraps
it end-to-end at a version bump; run this directly to print the block without
editing files.

Usage:
    just compute-pi-pin 0.78.0
    uv run python scripts/compute_pin.py pi 0.78.0

Network is required; the runtime install path never fetches checksums, only the
static values produced here.
"""

import argparse
import sys
from collections.abc import Sequence

import managed_pin


def main(argv: Sequence[str]) -> int:
    """Parse the tool and version arguments, compute the digests, and print the pin block."""
    parser = argparse.ArgumentParser(description="Recompute a managed tool's per-platform sha256 pin.")
    parser.add_argument("tool", choices=sorted(managed_pin.TOOL_PIN_SPECS), help="managed tool to pin")
    parser.add_argument("version", help="version to pin, without a leading 'v' (e.g. 0.78.0)")
    arguments = parser.parse_args(argv)
    spec = managed_pin.TOOL_PIN_SPECS[arguments.tool]

    shas = managed_pin.compute_platform_shas(spec, arguments.version)
    print(spec.format_pin_block(shas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
