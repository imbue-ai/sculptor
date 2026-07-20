#!/usr/bin/env python3
"""Report whether the pinned pi version lags the latest upstream release.

Sculptor pins pi to one exact version (``PI_PINNED_VERSION`` in
``sculptor/sculptor/services/pi_version.py``) while upstream releases several
times a week, so the pin goes stale by design. This tool fetches the latest
``earendil-works/pi`` release tag from the GitHub API and compares it with the
pin. CI consumes it two ways:

- ``--emit-github-warning`` (the ``checks`` workflow): a stale pin prints a
  ``::warning::`` annotation and the step still succeeds — staleness is an
  early signal, never a gate. Any failure degrades to a ``::notice::``.
- ``--github-output`` (the ``pi-bump`` workflow): append ``pinned``, ``latest``,
  and ``stale`` to ``$GITHUB_OUTPUT`` so the bump job can decide whether to
  open a PR. Here errors do fail the step, so a broken scheduled run is
  visible in the Actions tab instead of silently never bumping again.

Reads ``GH_TOKEN`` or ``GITHUB_TOKEN`` for the API call when set; anonymous
works but is rate-limited per IP. Stdlib-only, like its ``scripts/`` siblings.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

_LATEST_RELEASE_API_URL = "https://api.github.com/repos/earendil-works/pi/releases/latest"
_REQUEST_TIMEOUT_SECONDS = 30
_PI_VERSION_FILE = Path("sculptor/sculptor/services/pi_version.py")
_PINNED_VERSION_PATTERN = re.compile(r'^PI_PINNED_VERSION = "([^"]+)"$', re.MULTILINE)


class FreshnessCheckError(RuntimeError):
    """Raised when the pinned or latest pi version cannot be determined."""


def read_pinned_version(repo_root: Path) -> str:
    """Extract ``PI_PINNED_VERSION`` from its dependency-free module, textually.

    Parsing the source instead of importing it keeps this script runnable with a
    bare interpreter — the same reason the constant lives in an import-free
    module in the first place.
    """
    source = (repo_root / _PI_VERSION_FILE).read_text()
    match = _PINNED_VERSION_PATTERN.search(source)
    if match is None:
        raise FreshnessCheckError(f"PI_PINNED_VERSION not found in {_PI_VERSION_FILE}")
    return match.group(1)


def fetch_latest_release_version() -> str:
    """Return the latest pi release version (its tag without the leading ``v``)."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        # The GitHub API rejects requests that send no User-Agent.
        "User-Agent": "sculptor-pi-pin-freshness",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(_LATEST_RELEASE_API_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise FreshnessCheckError(f"Could not fetch the latest pi release: {error}") from error
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise FreshnessCheckError(f"Latest-release response has no tag_name: {str(payload)[:200]}")
    return tag.removeprefix("v")


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a strict ``MAJOR.MINOR.PATCH`` pi version for ordered comparison."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise FreshnessCheckError(f"Unexpected pi version format: {version!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_stale(pinned: str, latest: str) -> bool:
    """True when the latest release is strictly newer than the pin.

    Compares numerically, not lexically: ``0.80.10`` is newer than ``0.80.2``.
    """
    return parse_version(latest) > parse_version(pinned)


def format_github_output(pinned: str, latest: str, stale: bool) -> str:
    """Render the ``$GITHUB_OUTPUT`` lines the pi-bump workflow reads."""
    return f"pinned={pinned}\nlatest={latest}\nstale={str(stale).lower()}\n"


def _run_warning_mode(repo_root: Path) -> int:
    """Annotate a stale pin without ever failing the calling check."""
    try:
        pinned = read_pinned_version(repo_root)
        latest = fetch_latest_release_version()
        stale = is_stale(pinned, latest)
    except Exception as error:  # noqa: BLE001 - the freshness signal must never break the build.
        print(f"::notice title=pi pin freshness::Skipped the staleness check: {error}")
        return 0
    if stale:
        print(
            f"::warning title=pi pin is stale::pi {latest} is released; Sculptor pins {pinned}. "
            f"The pi-bump workflow opens a bump PR daily, or run `just bump-pi {latest}`."
        )
    else:
        print(f"pi pin is fresh: pinned={pinned} latest={latest}")
    return 0


def main(argv: Sequence[str]) -> int:
    """Parse the mode flags and run the freshness comparison."""
    parser = argparse.ArgumentParser(description="Compare PI_PINNED_VERSION with the latest pi release.")
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

    if arguments.emit_github_warning:
        return _run_warning_mode(arguments.repo_root)

    pinned = read_pinned_version(arguments.repo_root)
    latest = fetch_latest_release_version()
    stale = is_stale(pinned, latest)
    if arguments.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            raise FreshnessCheckError("--github-output requires the GITHUB_OUTPUT environment variable")
        with open(output_path, "a") as output_file:
            output_file.write(format_github_output(pinned, latest, stale))
    print(f"pinned={pinned} latest={latest} stale={str(stale).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
