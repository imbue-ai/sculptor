"""Smoke tests for the check_pi_pin_freshness dev tool, colocated with the script.

Not part of `just test-unit`; the pi-bump workflow runs them before trusting the
tooling, and they run on demand with
`uv run python -m pytest scripts/check_pi_pin_freshness_test.py`. Covers the pure
helpers only -- the GitHub API call is exercised by the workflows themselves.
"""

from pathlib import Path

import pytest

import check_pi_pin_freshness


def _write_pi_version_module(repo_root: Path, content: str) -> None:
    module_path = repo_root / "sculptor" / "sculptor" / "services" / "pi_version.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(content)


def test_read_pinned_version_extracts_the_constant(tmp_path: Path) -> None:
    _write_pi_version_module(tmp_path, '"""The pin."""\n\nPI_PINNED_VERSION = "0.80.10"\n')
    assert check_pi_pin_freshness.read_pinned_version(tmp_path) == "0.80.10"


def test_read_pinned_version_rejects_a_module_without_the_constant(tmp_path: Path) -> None:
    _write_pi_version_module(tmp_path, '"""No pin here."""\n')
    with pytest.raises(check_pi_pin_freshness.FreshnessCheckError):
        check_pi_pin_freshness.read_pinned_version(tmp_path)


def test_read_pinned_version_parses_the_real_module() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    pinned = check_pi_pin_freshness.read_pinned_version(repo_root)
    check_pi_pin_freshness.parse_version(pinned)


def test_is_stale_compares_numerically_not_lexically() -> None:
    assert check_pi_pin_freshness.is_stale("0.80.2", "0.80.10")
    assert not check_pi_pin_freshness.is_stale("0.80.10", "0.80.2")
    assert not check_pi_pin_freshness.is_stale("0.80.10", "0.80.10")


def test_parse_version_rejects_a_suffixed_version() -> None:
    with pytest.raises(check_pi_pin_freshness.FreshnessCheckError):
        check_pi_pin_freshness.parse_version("0.80.10-rc1")


def test_parse_version_rejects_a_tag_with_the_v_prefix() -> None:
    with pytest.raises(check_pi_pin_freshness.FreshnessCheckError):
        check_pi_pin_freshness.parse_version("v0.80.10")


def test_format_github_output_renders_one_key_per_line() -> None:
    rendered = check_pi_pin_freshness.format_github_output("0.80.2", "0.80.10", True)
    assert rendered == "pinned=0.80.2\nlatest=0.80.10\nstale=true\n"


def test_warning_mode_never_fails_when_the_lookup_breaks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = check_pi_pin_freshness.main(["--emit-github-warning", "--repo-root", str(tmp_path)])
    assert exit_code == 0
    assert "::notice" in capsys.readouterr().out
