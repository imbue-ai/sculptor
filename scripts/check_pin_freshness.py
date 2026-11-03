#!/usr/bin/env python3
"""Report whether a managed tool's pinned version lags its latest upstream release.

Sculptor pins each managed tool to one exact version (for pi, ``PI_PINNED_VERSION``
in ``sculptor/sculptor/services/pi_version.py``) while upstream keeps releasing,
so the pin goes stale by design. This tool fetches the tool's latest release tag
from the GitHub API and compares it with the pin. CI consumes it two ways:

- ``--emit-github-warning`` (the ``checks`` workflow): a stale pin prints a
  ``::warning::`` annotation and the step still succeeds — staleness is an
  early signal, never a gate. Any failure degrades to a ``::notice::``.
- ``--github-output`` (the ``pi-bump`` workflow): append ``pinned``, ``latest``,
  and ``stale`` to ``$GITHUB_OUTPUT`` so the bump job can decide whether to
  open a PR. Here errors do fail the step, so a broken scheduled run is
  visible in the Actions tab instead of silently never bumping again.

Usage:
    python3 scripts/check_pin_freshness.py pi --emit-github-warning

Reads ``GH_TOKEN`` or ``GITHUB_TOKEN`` for the API call when set; anonymous
works but is rate-limited per IP. Stdlib-only, like its ``scripts/`` siblings.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

import managed_pin

_LATEST_RELEASE_API_URL_TEMPLATE = "https://api.github.com/repos/{repo}/releases/latest"
_REQUEST_TIMEOUT_SECONDS = 30


def latest_release_api_url(spec: managed_pin.ToolPinSpec) -> str:
    """Return the GitHub API URL for the tool's latest release."""
    return _LATEST_RELEASE_API_URL_TEMPLATE.format(repo=spec.github_repo)


def fetch_latest_release_version(spec: managed_pin.ToolPinSpec) -> str:
    """Return the tool's latest release version (its tag without the leading ``v``)."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        # The GitHub API rejects requests that send no User-Agent.
        "User-Agent": f"sculptor-{spec.name}-pin-freshness",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(latest_release_api_url(spec), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise managed_pin.PinError(f"Could not fetch the latest {spec.name} release: {error}") from error
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise managed_pin.PinError(f"Latest-release response has no tag_name: {str(payload)[:200]}")
    return tag.removeprefix("v")


def format_github_output(pinned: str, latest: str, stale: bool) -> str:
    """Render the ``$GITHUB_OUTPUT`` lines the bump workflow reads."""
    return f"pinned={pinned}\nlatest={latest}\nstale={str(stale).lower()}\n"


def _run_warning_mode(spec: managed_pin.ToolPinSpec, repo_root: Path) -> int:
    """Annotate a stale pin without ever failing the calling check."""
    try:
        pinned = managed_pin.read_pinned_version(spec, repo_root)
        latest = fetch_latest_release_version(spec)
        stale = managed_pin.is_stale(pinned, latest)
    except Exception as error:  # noqa: BLE001 - the freshness signal must never break the build.
        print(f"::notice title={spec.name} pin freshness::Skipped the staleness check: {error}")
        return 0
    if stale:
        print(
            f"::warning title={spec.name} pin is stale::{spec.name} {latest} is released; Sculptor pins {pinned}. "
            + spec.stale_pin_advice_template.format(latest=latest)
        )
    else:
        print(f"{spec.name} pin is fresh: pinned={pinned} latest={latest}")
    return 0


def main(argv: Sequence[str]) -> int:
    """Parse the tool and mode flags and run the freshness comparison."""
    parser = argparse.ArgumentParser(description="Compare a managed tool's pinned version with its latest release.")
    parser.add_argument("tool", choices=sorted(managed_pin.TOOL_PIN_SPECS), help="managed tool to check")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root containing the pinned-version module (defaults to this checkout)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--emit-github-warning",
        action="store_true",
        help="print a ::warning:: annotation when stale and always exit 0",
    )
    mode.add_argument(
        "--github-output",
        action="store_true",
        help="append pinned/latest/stale to $GITHUB_OUTPUT",
    )
    arguments = parser.parse_args(argv)
    spec = managed_pin.TOOL_PIN_SPECS[arguments.tool]

    if arguments.emit_github_warning:
        return _run_warning_mode(spec, arguments.repo_root)

    pinned = managed_pin.read_pinned_version(spec, arguments.repo_root)
    latest = fetch_latest_release_version(spec)
    stale = managed_pin.is_stale(pinned, latest)
    if arguments.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            raise managed_pin.PinError("--github-output requires the GITHUB_OUTPUT environment variable")
        with open(output_path, "a") as output_file:
            output_file.write(format_github_output(pinned, latest, stale))
    print(f"pinned={pinned} latest={latest} stale={str(stale).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
