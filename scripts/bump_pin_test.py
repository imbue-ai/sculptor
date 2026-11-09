"""Smoke tests for the bump_pin dev tool, colocated with the script.

Not part of `just test-unit`; the pi-bump workflow runs them before trusting the
tooling, and they run on demand with
`uv run python -m pytest scripts/bump_pin_test.py`. The end-to-end cases run
against a miniature repo copy with the network stubbed out; hashing real release
assets stays with the workflow itself. `managed_pin_test.py` checks the pi edit
table against this checkout.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest

import bump_pin
import managed_pin

_PI = managed_pin.PI_PIN_SPEC
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
    _write(repo_root, _PI.version_file, f'PI_PINNED_VERSION = "{version}"\n')
    platform_lines = "".join(
        f'        "{key}": PlatformPin(\n'
        + f'            asset="pi-{key}.tar.gz",\n'
        + f'            sha256="{_OLD_SHAS[key]}",\n'
        + "        ),\n"
        for key in _PI.platform_keys
    )
    _write(
        repo_root,
        _PI.pin_file,
        "PI_PIN = PiPin(\n    version=PI_PINNED_VERSION,\n    platforms={\n" + platform_lines + "    },\n)\n",
    )
    _write(
        repo_root,
        managed_pin._PI_MANAGED_TOOLS_TEST_FILE,
        f"# Verified darwin-arm64 sha256 for pi {version}; ``just bump-pi <version>`` refreshes it.\n"
        + f'_PI_DARWIN_ARM64_SHA256_{underscored} = "{_OLD_SHAS["darwin-arm64"]}"\n'
        + "\n"
        + f"value = _PI_DARWIN_ARM64_SHA256_{underscored}\n",
    )
    _write(
        repo_root,
        managed_pin._PI_AGENT_WRAPPER_TEST_FILE,
        f'    version_result.stderr = "pi {version}\\n"\n'
        + f'    other_result.stderr = "pi {version}\\n"\n'
        + f'    assert exc_info.value.pinned_version == "{version}"\n',
    )
    _write(
        repo_root,
        managed_pin._PI_USE_MANAGED_DEPENDENCY_TEST_FILE,
        f'          version: "{version}",\n          version: "{version}",\n',
    )
    _write(
        repo_root,
        managed_pin._PI_DEPENDENCIES_STORY_FILE,
        f'  versionRange: {{ minVersion: "{version}", maxVersion: "{version}", recommendedVersion: "{version}" }},\n',
    )
    _write(
        repo_root,
        managed_pin._PI_REQUIREMENTS_FILE,
        f"- **REQ-COMPAT-022 (SHOULD).** The **Pi** harness pins **{version}**; platforms\n",
    )


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    _make_mini_repo(tmp_path, _OLD_VERSION)
    return tmp_path


def _stub_network(monkeypatch: pytest.MonkeyPatch, new_shas: Mapping[str, str]) -> None:
    monkeypatch.setattr(managed_pin, "compute_platform_shas", lambda spec, version: dict(new_shas))
    monkeypatch.setattr(
        bump_pin,
        "fetch_published_sha256sums",
        lambda spec, version: {f"pi-{key}.tar.gz": sha for key, sha in new_shas.items()},
    )


def test_main_rewrites_every_pinned_copy(mini_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_network(monkeypatch, _NEW_SHAS)

    assert bump_pin.main(["pi", _NEW_VERSION, "--repo-root", str(mini_repo)]) == 0

    assert _read(mini_repo, _PI.version_file) == f'PI_PINNED_VERSION = "{_NEW_VERSION}"\n'
    managed_tools = _read(mini_repo, _PI.pin_file)
    for sha in _NEW_SHAS.values():
        assert sha in managed_tools
    for sha in _OLD_SHAS.values():
        assert sha not in managed_tools
    managed_tools_test = _read(mini_repo, managed_pin._PI_MANAGED_TOOLS_TEST_FILE)
    assert f"for pi {_NEW_VERSION};" in managed_tools_test
    assert managed_tools_test.count("_PI_DARWIN_ARM64_SHA256_0_81_0") == 2
    assert _NEW_SHAS["darwin-arm64"] in managed_tools_test
    agent_wrapper_test = _read(mini_repo, managed_pin._PI_AGENT_WRAPPER_TEST_FILE)
    assert agent_wrapper_test.count(f'"pi {_NEW_VERSION}\\n"') == 2
    assert f'pinned_version == "{_NEW_VERSION}"' in agent_wrapper_test
    assert _read(mini_repo, managed_pin._PI_USE_MANAGED_DEPENDENCY_TEST_FILE).count(f'version: "{_NEW_VERSION}",') == 2
    assert _read(mini_repo, managed_pin._PI_DEPENDENCIES_STORY_FILE).count(f'"{_NEW_VERSION}"') == 3
    assert f"pins **{_NEW_VERSION}**" in _read(mini_repo, managed_pin._PI_REQUIREMENTS_FILE)
    assert _OLD_VERSION not in agent_wrapper_test


def test_main_is_a_no_op_when_already_pinned(mini_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_download(spec: managed_pin.ToolPinSpec, version: str) -> dict[str, str]:
        raise AssertionError("no network access expected for a no-op bump")

    monkeypatch.setattr(managed_pin, "compute_platform_shas", _must_not_download)
    before = _read(mini_repo, _PI.version_file)

    assert bump_pin.main(["pi", _OLD_VERSION, "--repo-root", str(mini_repo)]) == 0
    assert _read(mini_repo, _PI.version_file) == before


def test_main_rejects_a_malformed_version(mini_repo: Path) -> None:
    with pytest.raises(Exception, match="version format"):
        bump_pin.main(["pi", "not-a-version", "--repo-root", str(mini_repo)])


def test_main_rejects_an_unknown_tool(mini_repo: Path) -> None:
    with pytest.raises(SystemExit):
        bump_pin.main(["not-a-tool", _NEW_VERSION, "--repo-root", str(mini_repo)])


def test_main_fails_loudly_when_a_pinned_literal_drifts(mini_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_network(monkeypatch, _NEW_SHAS)
    _write(mini_repo, managed_pin._PI_USE_MANAGED_DEPENDENCY_TEST_FILE, f'          version: "{_OLD_VERSION}",\n')
    before = _read(mini_repo, _PI.version_file)

    with pytest.raises(managed_pin.PinError, match="expected 2"):
        bump_pin.main(["pi", _NEW_VERSION, "--repo-root", str(mini_repo)])
    assert _read(mini_repo, _PI.version_file) == before


def test_main_fails_when_a_touched_file_hides_an_unknown_copy(
    mini_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_network(monkeypatch, _NEW_SHAS)
    agent_wrapper_path = managed_pin._PI_AGENT_WRAPPER_TEST_FILE
    _write(
        mini_repo, agent_wrapper_path, _read(mini_repo, agent_wrapper_path) + f'stray = "pi {_OLD_VERSION} lingers"\n'
    )
    before = _read(mini_repo, _PI.version_file)

    with pytest.raises(managed_pin.PinError, match="still contains"):
        bump_pin.main(["pi", _NEW_VERSION, "--repo-root", str(mini_repo)])
    assert _read(mini_repo, _PI.version_file) == before


def test_main_allows_a_bump_where_the_old_version_prefixes_the_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_mini_repo(tmp_path, "0.80.10")
    _stub_network(monkeypatch, _NEW_SHAS)

    assert bump_pin.main(["pi", "0.80.100", "--repo-root", str(tmp_path)]) == 0
    assert _read(tmp_path, _PI.version_file) == 'PI_PINNED_VERSION = "0.80.100"\n'


def test_parse_sha256sums_maps_assets_to_digests() -> None:
    text = f"{_NEW_SHAS['darwin-arm64']}  pi-darwin-arm64.tar.gz\n\n{_NEW_SHAS['linux-x64']}  pi-linux-x64.tar.gz\n"
    assert bump_pin.parse_sha256sums(text) == {
        "pi-darwin-arm64.tar.gz": _NEW_SHAS["darwin-arm64"],
        "pi-linux-x64.tar.gz": _NEW_SHAS["linux-x64"],
    }


def test_parse_sha256sums_rejects_a_malformed_line() -> None:
    with pytest.raises(managed_pin.PinError, match="Unexpected SHA256SUMS line"):
        bump_pin.parse_sha256sums("only-one-column\n")


def test_verify_accepts_matching_published_digests() -> None:
    published = {f"pi-{key}.tar.gz": sha for key, sha in _NEW_SHAS.items()}
    bump_pin.verify_computed_against_published(_PI, _NEW_VERSION, _NEW_SHAS, published)


def test_verify_rejects_a_digest_mismatch() -> None:
    published = {f"pi-{key}.tar.gz": sha for key, sha in _NEW_SHAS.items()}
    published["pi-linux-x64.tar.gz"] = "00" * 32
    with pytest.raises(managed_pin.PinError, match="Digest mismatch"):
        bump_pin.verify_computed_against_published(_PI, _NEW_VERSION, _NEW_SHAS, published)


def test_verify_rejects_a_missing_asset() -> None:
    published = {"pi-darwin-arm64.tar.gz": _NEW_SHAS["darwin-arm64"]}
    with pytest.raises(managed_pin.PinError, match="missing"):
        bump_pin.verify_computed_against_published(_PI, _NEW_VERSION, _NEW_SHAS, published)


def test_verify_skips_the_cross_check_when_upstream_publishes_no_sums() -> None:
    bump_pin.verify_computed_against_published(_PI, _NEW_VERSION, _NEW_SHAS, None)


_JJ = managed_pin.JJ_PIN_SPEC
_JJ_OLD_VERSION = "0.46.0"
_JJ_NEW_VERSION = "0.47.0"
_JJ_TARGET_TRIPLES = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x64": "x86_64-apple-darwin",
    "linux-x64": "x86_64-unknown-linux-musl",
    "linux-arm64": "aarch64-unknown-linux-musl",
}
_JJ_OLD_SHAS = {key: f"{index}a" * 32 for index, key in enumerate(_JJ_TARGET_TRIPLES)}
_JJ_NEW_SHAS = {key: f"{index}b" * 32 for index, key in enumerate(_JJ_TARGET_TRIPLES)}


def _jj_release_api_digests(version: str, shas: Mapping[str, str]) -> dict[str, str]:
    return {f"jj-v{version}-{_JJ_TARGET_TRIPLES[key]}.tar.gz": sha for key, sha in shas.items()}


@pytest.fixture
def mini_jj_repo(tmp_path: Path) -> Path:
    """jj's version module and the offload image's copy of the Linux pin, as they appear in the real files."""
    _write(
        tmp_path,
        _JJ.version_file,
        f'"""The pin."""\n\nJJ_PINNED_VERSION = "{_JJ_OLD_VERSION}"\n\n' + _JJ.format_pin_block(_JJ_OLD_SHAS) + "\n",
    )
    _write(
        tmp_path,
        managed_pin._JJ_OFFLOAD_DOCKERFILE,
        f"ARG JJ_VERSION={_JJ_OLD_VERSION}\n"
        + f"ARG JJ_SHA256_X86_64={_JJ_OLD_SHAS['linux-x64']}\n"
        + f"ARG JJ_SHA256_AARCH64={_JJ_OLD_SHAS['linux-arm64']}\n",
    )
    return tmp_path


def test_main_rewrites_every_pinned_jj_copy(mini_jj_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(managed_pin, "compute_platform_shas", lambda spec, version: dict(_JJ_NEW_SHAS))
    monkeypatch.setattr(
        bump_pin,
        "fetch_release_api_digests",
        lambda spec, version: _jj_release_api_digests(version, _JJ_NEW_SHAS),
    )

    assert bump_pin.main(["jj", _JJ_NEW_VERSION, "--repo-root", str(mini_jj_repo)]) == 0

    assert managed_pin.read_pinned_version(_JJ, mini_jj_repo) == _JJ_NEW_VERSION
    assert managed_pin.read_baked_shas(_JJ, mini_jj_repo) == _JJ_NEW_SHAS
    assert _read(mini_jj_repo, managed_pin._JJ_OFFLOAD_DOCKERFILE) == (
        f"ARG JJ_VERSION={_JJ_NEW_VERSION}\n"
        + f"ARG JJ_SHA256_X86_64={_JJ_NEW_SHAS['linux-x64']}\n"
        + f"ARG JJ_SHA256_AARCH64={_JJ_NEW_SHAS['linux-arm64']}\n"
    )


def test_main_refuses_a_jj_bump_the_release_api_disagrees_with(
    mini_jj_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(managed_pin, "compute_platform_shas", lambda spec, version: dict(_JJ_NEW_SHAS))
    monkeypatch.setattr(
        bump_pin,
        "fetch_release_api_digests",
        lambda spec, version: _jj_release_api_digests(version, _JJ_OLD_SHAS),
    )

    with pytest.raises(managed_pin.PinError, match="Digest mismatch"):
        bump_pin.main(["jj", _JJ_NEW_VERSION, "--repo-root", str(mini_jj_repo)])
    assert managed_pin.read_pinned_version(_JJ, mini_jj_repo) == _JJ_OLD_VERSION


def test_parse_release_api_digests_strips_the_algorithm_and_skips_undigested_assets() -> None:
    payload = {
        "assets": [
            {"name": "jj-v0.47.0-aarch64-apple-darwin.tar.gz", "digest": f"sha256:{'ab' * 32}"},
            {"name": "jj-v0.47.0-docs-html.tar.gz", "digest": None},
        ]
    }
    assert bump_pin.parse_release_api_digests(payload) == {"jj-v0.47.0-aarch64-apple-darwin.tar.gz": "ab" * 32}


def test_parse_release_api_digests_rejects_a_payload_without_assets() -> None:
    with pytest.raises(managed_pin.PinError, match="assets"):
        bump_pin.parse_release_api_digests({"message": "Not Found"})
