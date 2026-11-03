"""Smoke tests for the shared managed_pin module, colocated with the script.

Not part of `just test-unit`; the pi-bump workflow runs them before trusting the
tooling, and they run on demand with
`uv run python -m pytest scripts/managed_pin_test.py`. Covers the pure helpers
and the pi spec; the cases marked as reading this checkout check the spec
against the real tree.
"""

from pathlib import Path

import pytest

import managed_pin

_PI = managed_pin.PI_PIN_SPEC
_REPO_ROOT = Path(__file__).resolve().parent.parent
_NEW_VERSION = "0.81.0"
_OLD_SHAS = {"darwin-arm64": "aa" * 32, "darwin-x64": "bb" * 32, "linux-x64": "cc" * 32}
_NEW_SHAS = {"darwin-arm64": "dd" * 32, "darwin-x64": "ee" * 32, "linux-x64": "ff" * 32}


def _write(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_tool_pin_specs_are_keyed_by_tool_name() -> None:
    assert managed_pin.TOOL_PIN_SPECS == {"pi": _PI}


def test_pi_platform_keys_are_the_three_pi_supports() -> None:
    assert set(_PI.platform_keys) == {"darwin-arm64", "darwin-x64", "linux-x64"}


def test_release_url_uses_the_pi_github_release_layout() -> None:
    url = managed_pin.release_url(_PI, "0.78.0", "pi-darwin-arm64.tar.gz")
    assert url == "https://github.com/earendil-works/pi/releases/download/v0.78.0/pi-darwin-arm64.tar.gz"


def test_pi_asset_name_for_platform_matches_pi_release_naming() -> None:
    for platform_key in _PI.platform_keys:
        assert _PI.asset_name_for_platform(platform_key) == f"pi-{platform_key}.tar.gz"


def test_read_pinned_version_extracts_the_constant(tmp_path: Path) -> None:
    _write(tmp_path, _PI.version_file, '"""The pin."""\n\nPI_PINNED_VERSION = "0.80.10"\n')
    assert managed_pin.read_pinned_version(_PI, tmp_path) == "0.80.10"


def test_read_pinned_version_rejects_a_module_without_the_constant(tmp_path: Path) -> None:
    _write(tmp_path, _PI.version_file, '"""No pin here."""\n')
    with pytest.raises(managed_pin.PinError, match="PI_PINNED_VERSION not found"):
        managed_pin.read_pinned_version(_PI, tmp_path)


def test_read_pinned_version_parses_the_real_module() -> None:
    """Reads this checkout."""
    managed_pin.parse_version(managed_pin.read_pinned_version(_PI, _REPO_ROOT))


def test_is_stale_compares_numerically_not_lexically() -> None:
    assert managed_pin.is_stale("0.80.2", "0.80.10")
    assert not managed_pin.is_stale("0.80.10", "0.80.2")
    assert not managed_pin.is_stale("0.80.10", "0.80.10")


def test_parse_version_rejects_a_suffixed_version() -> None:
    with pytest.raises(managed_pin.PinError, match="version format"):
        managed_pin.parse_version("0.80.10-rc1")


def test_parse_version_rejects_a_tag_with_the_v_prefix() -> None:
    with pytest.raises(managed_pin.PinError, match="version format"):
        managed_pin.parse_version("v0.80.10")


def test_read_baked_shas_reads_every_platform_pin(tmp_path: Path) -> None:
    platform_lines = "".join(
        f'        "{key}": PlatformPin(\n'
        + f'            asset="pi-{key}.tar.gz",\n'
        + f'            sha256="{_OLD_SHAS[key]}",\n'
        + "        ),\n"
        for key in _PI.platform_keys
    )
    _write(tmp_path, _PI.pin_file, "PI_PIN = PiPin(\n    platforms={\n" + platform_lines + "    },\n)\n")

    assert managed_pin.read_baked_shas(_PI, tmp_path) == _OLD_SHAS


def test_read_baked_shas_names_the_platform_it_cannot_find(tmp_path: Path) -> None:
    _write(tmp_path, _PI.pin_file, "PI_PIN = PiPin(platforms={})\n")
    with pytest.raises(managed_pin.PinError, match="darwin-arm64"):
        managed_pin.read_baked_shas(_PI, tmp_path)


def test_plan_edits_starts_with_the_version_constant_and_each_baked_digest() -> None:
    edits = managed_pin.plan_edits(_PI, "0.80.10", _NEW_VERSION, _OLD_SHAS, _NEW_SHAS)

    assert edits[0] == managed_pin.PlannedEdit(
        _PI.version_file, 'PI_PINNED_VERSION = "0.80.10"', f'PI_PINNED_VERSION = "{_NEW_VERSION}"', 1
    )
    assert edits[1 : 1 + len(_PI.platform_keys)] == tuple(
        managed_pin.PlannedEdit(_PI.pin_file, f'sha256="{_OLD_SHAS[key]}"', f'sha256="{_NEW_SHAS[key]}"', 1)
        for key in _PI.platform_keys
    )


def test_the_pi_edit_table_matches_the_real_checkout() -> None:
    """Every planned edit must name a live file and hit its literals exactly.

    The bump tests build their fixture out of the spec's own paths, so a pinned
    file renamed out from under the table leaves them green and breaks the bump
    only once the workflow runs it for real. This case reads this checkout.
    """
    current_version = managed_pin.read_pinned_version(_PI, _REPO_ROOT)
    old_shas = managed_pin.read_baked_shas(_PI, _REPO_ROOT)
    edits = managed_pin.plan_edits(_PI, current_version, _NEW_VERSION, old_shas, _NEW_SHAS)

    for edit in edits:
        path = _REPO_ROOT / edit.path
        assert path.exists(), f"{edit.path} no longer exists; update the pi spec in scripts/managed_pin.py"
        assert path.read_text().count(edit.old) == edit.count, (
            f"{edit.path}: expected {edit.count} occurrence(s) of {edit.old!r}"
        )
