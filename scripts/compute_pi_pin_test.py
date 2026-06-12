"""Smoke tests for the compute_pi_pin dev tool, colocated with the script.

Not part of `just test-unit`; run on demand with
`uv run python -m pytest scripts/compute_pi_pin_test.py`. Covers the script's pure
helpers and arg parsing only -- fetching and hashing real release assets is manual.
"""

import pytest

import compute_pi_pin


def test_supported_platform_keys_are_the_three_pi_supports() -> None:
    assert set(compute_pi_pin.SUPPORTED_PLATFORM_KEYS) == {"darwin-arm64", "darwin-x64", "linux-x64"}


def test_release_url_uses_the_pi_github_release_layout() -> None:
    url = compute_pi_pin.release_url("0.78.0", "pi-darwin-arm64.tar.gz")
    assert url == "https://github.com/earendil-works/pi/releases/download/v0.78.0/pi-darwin-arm64.tar.gz"


def test_asset_name_for_platform_matches_pi_release_naming() -> None:
    for platform_key in compute_pi_pin.SUPPORTED_PLATFORM_KEYS:
        assert compute_pi_pin.asset_name_for_platform(platform_key) == f"pi-{platform_key}.tar.gz"


def test_format_pin_block_renders_pasteable_platformpin_lines_for_every_platform() -> None:
    shas = {platform_key: platform_key.replace("-", "") for platform_key in compute_pi_pin.SUPPORTED_PLATFORM_KEYS}
    block = compute_pi_pin.format_pin_block(shas)
    assert block.startswith("    platforms={")
    assert block.rstrip().endswith("},")
    for platform_key, sha256 in shas.items():
        asset = f"pi-{platform_key}.tar.gz"
        assert f'"{platform_key}": PlatformPin(asset="{asset}", sha256="{sha256}"),' in block


def test_main_requires_a_version_argument() -> None:
    with pytest.raises(SystemExit):
        compute_pi_pin.main([])
