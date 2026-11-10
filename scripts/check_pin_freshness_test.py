"""Smoke tests for the check_pin_freshness dev tool, colocated with the script.

Not part of `just test-unit`; the pi-bump workflow runs them before trusting the
tooling, and they run on demand with
`uv run python -m pytest scripts/check_pin_freshness_test.py`. Covers the pure
helpers only -- the GitHub API call is exercised by the workflows themselves.
"""

from pathlib import Path

import pytest

import check_pin_freshness
import managed_pin


def test_latest_release_api_url_uses_the_tool_repo() -> None:
    url = check_pin_freshness.latest_release_api_url(managed_pin.PI_PIN_SPEC)
    assert url == "https://api.github.com/repos/earendil-works/pi/releases/latest"


def test_latest_release_api_url_for_jj_uses_the_jj_repo() -> None:
    url = check_pin_freshness.latest_release_api_url(managed_pin.JJ_PIN_SPEC)
    assert url == "https://api.github.com/repos/jj-vcs/jj/releases/latest"


def test_jj_staleness_advice_names_the_bump_target() -> None:
    advice = managed_pin.JJ_PIN_SPEC.stale_pin_advice_template.format(latest="0.47.0")
    assert "just bump-jj 0.47.0" in advice


def test_format_github_output_renders_one_key_per_line() -> None:
    rendered = check_pin_freshness.format_github_output("0.80.2", "0.80.10", True)
    assert rendered == "pinned=0.80.2\nlatest=0.80.10\nstale=true\n"


def test_warning_mode_never_fails_when_the_lookup_breaks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = check_pin_freshness.main(["pi", "--emit-github-warning", "--repo-root", str(tmp_path)])
    assert exit_code == 0
    assert "::notice title=pi pin freshness::" in capsys.readouterr().out


def test_main_rejects_an_unknown_tool() -> None:
    with pytest.raises(SystemExit):
        check_pin_freshness.main(["not-a-tool", "--emit-github-warning"])
