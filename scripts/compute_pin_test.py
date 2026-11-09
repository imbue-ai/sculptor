"""Smoke tests for the compute_pin dev tool, colocated with the script.

Not part of `just test-unit`; run on demand with
`uv run python -m pytest scripts/compute_pin_test.py`. Covers the script's pure
helpers and arg parsing only -- fetching and hashing real release assets is manual.
"""

import pytest

import compute_pin
import managed_pin

_PI = managed_pin.PI_PIN_SPEC


def test_format_pin_block_renders_pasteable_platformpin_lines_for_every_platform() -> None:
    shas = {platform_key: platform_key.replace("-", "") for platform_key in _PI.platform_keys}
    block = _PI.format_pin_block(shas)
    assert block.startswith("    platforms={")
    assert block.rstrip().endswith("},")
    for platform_key, sha256 in shas.items():
        asset = f"pi-{platform_key}.tar.gz"
        assert f'"{platform_key}": PlatformPin(asset="{asset}", sha256="{sha256}"),' in block


def test_main_requires_a_version_argument() -> None:
    with pytest.raises(SystemExit):
        compute_pin.main(["pi"])


def test_main_rejects_an_unknown_tool() -> None:
    with pytest.raises(SystemExit):
        compute_pin.main(["not-a-tool", "0.78.0"])
