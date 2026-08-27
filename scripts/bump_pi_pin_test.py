"""Smoke tests for the bump_pi_pin dev tool, colocated with the script.

Not part of `just test-unit`; the pi-bump workflow runs them before trusting the
tooling, and they run on demand with
`uv run python -m pytest scripts/bump_pi_pin_test.py`. The end-to-end cases run
against a miniature repo copy with the network stubbed out; hashing real release
assets stays with the workflow itself.
"""

from pathlib import Path

import pytest

import bump_pi_pin
import compute_pi_pin

_OLD_VERSION = "0.80.10"
_NEW_VERSION = "0.81.0"
_OLD_SHAS = {"darwin-arm64": "aa" * 32, "darwin-x64": "bb" * 32, "linux-x64": "cc" * 32}
_NEW_SHAS = {"darwin-arm64": "dd" * 32, "darwin-x64": "ee" * 32, "linux-x64": "ff" * 32}


def _write(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _read(repo_root: Path, relative_path: str) -> str:
    return (repo_root / relative_path).read_text()


def _make_mini_repo(repo_root: Path, version: str) -> None:
    """Lay out every pinned copy exactly as it appears in the real files."""
    underscored = version.replace(".", "_")
    _write(repo_root, bump_pi_pin._PI_VERSION_FILE, f'PI_PINNED_VERSION = "{version}"\n')
    platform_lines = "".join(
        f'        "{key}": PlatformPin(\n'
        + f'            asset="pi-{key}.tar.gz",\n'
        + f'            sha256="{_OLD_SHAS[key]}",\n'
        + "        ),\n"
        for key in compute_pi_pin.SUPPORTED_PLATFORM_KEYS
    )
    _write(
        repo_root,
        bump_pi_pin._MANAGED_TOOLS_FILE,
        "PI_PIN = PiPin(\n    version=PI_PINNED_VERSION,\n    platforms={\n" + platform_lines + "    },\n)\n",
    )
    _write(
        repo_root,
        bump_pi_pin._MANAGED_TOOLS_TEST_FILE,
        f"# Verified darwin-arm64 sha256 for pi {version}; ``just bump-pi <version>`` refreshes it.\n"
        + f'_PI_DARWIN_ARM64_SHA256_{underscored} = "{_OLD_SHAS["darwin-arm64"]}"\n'
        + "\n"
        + f"value = _PI_DARWIN_ARM64_SHA256_{underscored}\n",
    )
    _write(
        repo_root,
        bump_pi_pin._AGENT_WRAPPER_TEST_FILE,
        f'    version_result.stderr = "pi {version}\\n"\n'
        + f'    other_result.stderr = "pi {version}\\n"\n'
        + f'    assert exc_info.value.pinned_version == "{version}"\n',
    )
    _write(
        repo_root,
        bump_pi_pin._USE_MANAGED_DEPENDENCY_TEST_FILE,
        f'          version: "{version}",\n          version: "{version}",\n',
    )
    _write(
        repo_root,
        bump_pi_pin._DEPENDENCIES_STORY_FILE,
        f'  versionRange: {{ minVersion: "{version}", maxVersion: "{version}", recommendedVersion: "{version}" }},\n',
    )
    _write(
        repo_root,
        bump_pi_pin._REQUIREMENTS_FILE,
        f"- **REQ-COMPAT-022 (SHOULD).** The **Pi** harness pins **{version}**; platforms\n",
    )


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    _make_mini_repo(tmp_path, _OLD_VERSION)
    return tmp_path


def _stub_network(monkeypatch: pytest.MonkeyPatch, new_shas: dict[str, str]) -> None:
    monkeypatch.setattr(compute_pi_pin, "compute_platform_shas", lambda version: dict(new_shas))
    monkeypatch.setattr(
        bump_pi_pin,
        "fetch_published_sha256sums",
        lambda version: {f"pi-{key}.tar.gz": sha for key, sha in new_shas.items()},
    )


def test_main_rewrites_every_pinned_copy(mini_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_network(monkeypatch, _NEW_SHAS)

    assert bump_pi_pin.main([_NEW_VERSION, "--repo-root", str(mini_repo)]) == 0

    assert _read(mini_repo, bump_pi_pin._PI_VERSION_FILE) == f'PI_PINNED_VERSION = "{_NEW_VERSION}"\n'
    managed_tools = _read(mini_repo, bump_pi_pin._MANAGED_TOOLS_FILE)
    for sha in _NEW_SHAS.values():
        assert sha in managed_tools
    for sha in _OLD_SHAS.values():
        assert sha not in managed_tools
    managed_tools_test = _read(mini_repo, bump_pi_pin._MANAGED_TOOLS_TEST_FILE)
    assert f"for pi {_NEW_VERSION};" in managed_tools_test
    assert managed_tools_test.count("_PI_DARWIN_ARM64_SHA256_0_81_0") == 2
    assert _NEW_SHAS["darwin-arm64"] in managed_tools_test
    agent_wrapper_test = _read(mini_repo, bump_pi_pin._AGENT_WRAPPER_TEST_FILE)
    assert agent_wrapper_test.count(f'"pi {_NEW_VERSION}\\n"') == 2
    assert f'pinned_version == "{_NEW_VERSION}"' in agent_wrapper_test
    assert _read(mini_repo, bump_pi_pin._USE_MANAGED_DEPENDENCY_TEST_FILE).count(f'version: "{_NEW_VERSION}",') == 2
    assert _read(mini_repo, bump_pi_pin._DEPENDENCIES_STORY_FILE).count(f'"{_NEW_VERSION}"') == 3
    assert f"pins **{_NEW_VERSION}**" in _read(mini_repo, bump_pi_pin._REQUIREMENTS_FILE)
    assert _OLD_VERSION not in agent_wrapper_test


def test_main_is_a_no_op_when_already_pinned(mini_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_download(version: str) -> dict[str, str]:
        raise AssertionError("no network access expected for a no-op bump")

    monkeypatch.setattr(compute_pi_pin, "compute_platform_shas", _must_not_download)
    before = _read(mini_repo, bump_pi_pin._PI_VERSION_FILE)

    assert bump_pi_pin.main([_OLD_VERSION, "--repo-root", str(mini_repo)]) == 0
    assert _read(mini_repo, bump_pi_pin._PI_VERSION_FILE) == before


def test_main_rejects_a_malformed_version(mini_repo: Path) -> None:
    with pytest.raises(Exception, match="version format"):
        bump_pi_pin.main(["not-a-version", "--repo-root", str(mini_repo)])


def test_main_fails_loudly_when_a_pinned_literal_drifts(mini_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_network(monkeypatch, _NEW_SHAS)
    _write(mini_repo, bump_pi_pin._USE_MANAGED_DEPENDENCY_TEST_FILE, f'          version: "{_OLD_VERSION}",\n')
    before = _read(mini_repo, bump_pi_pin._PI_VERSION_FILE)

    with pytest.raises(bump_pi_pin.BumpError, match="expected 2"):
        bump_pi_pin.main([_NEW_VERSION, "--repo-root", str(mini_repo)])
    assert _read(mini_repo, bump_pi_pin._PI_VERSION_FILE) == before


def test_main_fails_when_a_touched_file_hides_an_unknown_copy(
    mini_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_network(monkeypatch, _NEW_SHAS)
    agent_wrapper_path = bump_pi_pin._AGENT_WRAPPER_TEST_FILE
    _write(mini_repo, agent_wrapper_path, _read(mini_repo, agent_wrapper_path) + f'stray = "pi {_OLD_VERSION} lingers"\n')
    before = _read(mini_repo, bump_pi_pin._PI_VERSION_FILE)

    with pytest.raises(bump_pi_pin.BumpError, match="still contains"):
        bump_pi_pin.main([_NEW_VERSION, "--repo-root", str(mini_repo)])
    assert _read(mini_repo, bump_pi_pin._PI_VERSION_FILE) == before


def test_main_allows_a_bump_where_the_old_version_prefixes_the_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_mini_repo(tmp_path, "0.80.10")
    _stub_network(monkeypatch, _NEW_SHAS)

    assert bump_pi_pin.main(["0.80.100", "--repo-root", str(tmp_path)]) == 0
    assert _read(tmp_path, bump_pi_pin._PI_VERSION_FILE) == 'PI_PINNED_VERSION = "0.80.100"\n'


def test_read_baked_shas_reads_all_three_platform_pins(mini_repo: Path) -> None:
    assert bump_pi_pin.read_baked_shas(mini_repo) == _OLD_SHAS


def test_parse_sha256sums_maps_assets_to_digests() -> None:
    text = f"{_NEW_SHAS['darwin-arm64']}  pi-darwin-arm64.tar.gz\n\n{_NEW_SHAS['linux-x64']}  pi-linux-x64.tar.gz\n"
    assert bump_pi_pin.parse_sha256sums(text) == {
        "pi-darwin-arm64.tar.gz": _NEW_SHAS["darwin-arm64"],
        "pi-linux-x64.tar.gz": _NEW_SHAS["linux-x64"],
    }


def test_parse_sha256sums_rejects_a_malformed_line() -> None:
    with pytest.raises(bump_pi_pin.BumpError, match="Unexpected SHA256SUMS line"):
        bump_pi_pin.parse_sha256sums("only-one-column\n")


def test_verify_accepts_matching_published_digests() -> None:
    published = {f"pi-{key}.tar.gz": sha for key, sha in _NEW_SHAS.items()}
    bump_pi_pin.verify_computed_against_published(_NEW_SHAS, published)


def test_verify_rejects_a_digest_mismatch() -> None:
    published = {f"pi-{key}.tar.gz": sha for key, sha in _NEW_SHAS.items()}
    published["pi-linux-x64.tar.gz"] = "00" * 32
    with pytest.raises(bump_pi_pin.BumpError, match="Digest mismatch"):
        bump_pi_pin.verify_computed_against_published(_NEW_SHAS, published)


def test_verify_rejects_a_missing_asset() -> None:
    published = {"pi-darwin-arm64.tar.gz": _NEW_SHAS["darwin-arm64"]}
    with pytest.raises(bump_pi_pin.BumpError, match="missing"):
        bump_pi_pin.verify_computed_against_published(_NEW_SHAS, published)


def test_verify_skips_the_cross_check_when_upstream_publishes_no_sums() -> None:
    bump_pi_pin.verify_computed_against_published(_NEW_SHAS, None)
