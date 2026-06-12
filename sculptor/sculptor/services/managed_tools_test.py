import io
import tarfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.managed_tools import CLAUDE_VERSION_RANGE
from sculptor.services.managed_tools import ClaudeManagedTool
from sculptor.services.managed_tools import GCP_BUCKET_BASE_URL
from sculptor.services.managed_tools import ManagedDistributionError
from sculptor.services.managed_tools import ManagedTool
from sculptor.services.managed_tools import PI_PIN
from sculptor.services.managed_tools import PiManagedTool
from sculptor.services.managed_tools import PiPin
from sculptor.services.managed_tools import ResolvedDistribution
from sculptor.services.managed_tools import UnsupportedManagedPlatformError
from sculptor.services.managed_tools import _CLAUDE_PLATFORM_MAP
from sculptor.services.managed_tools import _PI_PLATFORM_MAP
from sculptor.services.managed_tools import get_managed_tool
from sculptor.services.managed_tools import get_managed_tools

# Verified darwin-arm64 sha256 for pi 0.78.0; regenerate with ``just compute-pi-pin 0.78.0``.
_PI_DARWIN_ARM64_SHA256_0_78_0 = "68ebbe4f56a136a1c7bace3393eca4ad0aa1fd9f253b797fd370058bd39fe070"


def _instantiate_with_no_arguments(candidate: Callable[[], object]) -> object:
    """Call a zero-argument constructor through a laundered static type.

    Lets the abstract-instantiation test observe the runtime ``TypeError`` without
    the type checker rejecting a direct ``ManagedTool()`` as an abstract class.
    """
    return candidate()


def test_resolved_distribution_constructs_from_valid_tarball_fields() -> None:
    distribution = ResolvedDistribution(
        version="0.78.0",
        url="https://example.invalid/pi-darwin-arm64.tar.gz",
        checksum_sha256="68ebbe4f56a136a1c7bace3393eca4ad0aa1fd9f253b797fd370058bd39fe070",
        size=1234,
        archive="tarball",
        binary_subpath="pi/pi",
    )

    assert distribution.archive == "tarball"
    assert distribution.binary_subpath == "pi/pi"
    assert distribution.size == 1234


def test_resolved_distribution_accepts_single_binary_archive_and_absent_size() -> None:
    distribution = ResolvedDistribution(
        version="2.1.156",
        url="https://example.invalid/claude",
        checksum_sha256="abc123",
        size=None,
        archive="single_binary",
        binary_subpath="claude",
    )

    assert distribution.archive == "single_binary"
    assert distribution.size is None


def test_resolved_distribution_rejects_unknown_archive_literal() -> None:
    with pytest.raises(ValidationError):
        ResolvedDistribution.model_validate(
            {
                "version": "0.78.0",
                "url": "https://example.invalid/pi.zip",
                "checksum_sha256": "abc123",
                "size": None,
                "archive": "zip",
                "binary_subpath": "pi/pi",
            }
        )


def test_managed_tool_cannot_be_instantiated_because_it_is_abstract() -> None:
    with pytest.raises(TypeError):
        _instantiate_with_no_arguments(ManagedTool)


def test_get_managed_tool_returns_none_for_unmanaged_git() -> None:
    assert get_managed_tool(Dependency.GIT) is None


def test_pi_pin_version_equals_recommended_version_of_pi_version_range() -> None:
    assert PI_PIN.version == PI_VERSION_RANGE.recommended_version


def test_pi_pin_covers_exactly_the_three_supported_platform_keys() -> None:
    assert set(PI_PIN.platforms) == {"darwin-arm64", "darwin-x64", "linux-x64"}


def test_pi_pin_asset_names_follow_the_pi_release_naming_for_each_platform() -> None:
    for platform_key, platform_pin in PI_PIN.platforms.items():
        assert platform_pin.asset == f"pi-{platform_key}.tar.gz"


def test_pi_pin_darwin_arm64_sha256_matches_the_verified_value() -> None:
    assert PI_PIN.platforms["darwin-arm64"].sha256 == _PI_DARWIN_ARM64_SHA256_0_78_0


def test_pi_pin_platform_sha256s_are_distinct_lowercase_hex_digests() -> None:
    digests = [platform_pin.sha256 for platform_pin in PI_PIN.platforms.values()]
    for digest in digests:
        assert len(digest) == 64
        assert all(character in "0123456789abcdef" for character in digest)
    assert len(set(digests)) == len(digests)


def test_pi_pin_plugin_set_revision_defaults_to_the_reserved_bundled_sentinel() -> None:
    assert PI_PIN.plugin_set_revision == "bundled"
    assert PiPin(version="0.0.0", platforms={}).plugin_set_revision == "bundled"


def _make_pi_tarball() -> bytes:
    """A minimal pi artifact: a ``pi/`` tree with the executable entrypoint at ``pi/pi``."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        entrypoint = b"#!/bin/sh\necho 0.78.0 1>&2\n"
        entry_info = tarfile.TarInfo(name="pi/pi")
        entry_info.size = len(entrypoint)
        entry_info.mode = 0o755
        tar.addfile(entry_info, io.BytesIO(entrypoint))
        # A sibling the binary loads at runtime, proving the whole tree is kept.
        sibling = b"theme-data"
        sibling_info = tarfile.TarInfo(name="pi/assets/native/node_modules/theme/index.js")
        sibling_info.size = len(sibling)
        tar.addfile(sibling_info, io.BytesIO(sibling))
    return buffer.getvalue()


class TestPiManagedToolResolveDistribution:
    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    def test_each_supported_platform_resolves_from_the_pin(
        self, mock_sys: MagicMock, mock_platform: MagicMock
    ) -> None:
        cases = {
            ("darwin", "arm64"): "darwin-arm64",
            ("darwin", "x86_64"): "darwin-x64",
            ("linux", "x86_64"): "linux-x64",
        }
        for (system, machine), platform_key in cases.items():
            mock_sys.platform = system
            mock_platform.machine.return_value = machine

            distribution = PiManagedTool().resolve_distribution()

            pin = PI_PIN.platforms[platform_key]
            assert distribution.version == PI_PIN.version
            assert (
                distribution.url
                == f"https://github.com/earendil-works/pi/releases/download/v{PI_PIN.version}/{pin.asset}"
            )
            assert distribution.checksum_sha256 == pin.sha256
            assert distribution.size is None
            assert distribution.archive == "tarball"
            assert distribution.binary_subpath == "pi/pi"

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    def test_unsupported_platform_raises_structured_error(self, mock_sys: MagicMock, mock_platform: MagicMock) -> None:
        mock_sys.platform = "win32"
        mock_platform.machine.return_value = "AMD64"

        with pytest.raises(UnsupportedManagedPlatformError):
            PiManagedTool().resolve_distribution()


class TestPiManagedToolStage:
    def test_extracts_the_tree_and_returns_the_executable_binary(self, tmp_path: Path) -> None:
        downloaded = tmp_path / "pi-darwin-arm64.tar.gz"
        downloaded.write_bytes(_make_pi_tarball())
        version_dir = tmp_path / "version-0.78.0"

        binary = PiManagedTool().stage(downloaded, version_dir)

        assert binary == version_dir / "pi" / "pi"
        assert binary.is_file()
        # The whole tree is kept, not just the entrypoint.
        assert (version_dir / "pi" / "assets" / "native" / "node_modules" / "theme" / "index.js").is_file()
        # The entrypoint is runnable even if the archive dropped the execute bit.
        assert binary.stat().st_mode & 0o111


class TestPiManagedToolParseVersion:
    def test_parses_version_from_stderr_only_emission(self) -> None:
        assert PiManagedTool().parse_version("\n0.78.0\n") == "0.78.0"

    def test_parses_version_with_prefix(self) -> None:
        assert PiManagedTool().parse_version("pi 0.78.0") == "0.78.0"

    def test_returns_none_when_unparseable(self) -> None:
        assert PiManagedTool().parse_version("no version here") is None


class TestPiManagedToolRegistration:
    def test_registry_returns_a_pi_managed_tool(self) -> None:
        tool = get_managed_tool(Dependency.PI)
        assert isinstance(tool, PiManagedTool)
        assert tool.tool == Dependency.PI
        assert tool.retention_keep == 1
        assert tool.platform_keys == frozenset({"darwin-arm64", "darwin-x64", "linux-x64"})


def test_pi_managed_tool_version_range_equals_the_service_pi_version_range() -> None:
    # version_range is built from the pin (importing the service's PI_VERSION_RANGE
    # would cycle); this test keeps the two from drifting apart.
    assert PiManagedTool().version_range == PI_VERSION_RANGE


def test_pi_platform_map_values_match_the_advertised_platform_keys() -> None:
    # The running-platform map and the advertised platform_keys must agree, or a
    # platform could resolve a key that has no pin (or vice versa).
    assert set(_PI_PLATFORM_MAP.values()) == PiManagedTool().platform_keys


_CLAUDE_RECOMMENDED = CLAUDE_VERSION_RANGE.recommended_version


def _make_claude_manifest_response(
    version: str = _CLAUDE_RECOMMENDED,
    platform_key: str = "darwin-arm64",
    binary: str = "claude",
    checksum: str = "abc123",
    size: int = 100,
) -> MagicMock:
    """A mock ``httpx.get`` response carrying Claude's manifest.json shape."""
    response = MagicMock()
    response.json.return_value = {
        "version": version,
        "buildDate": "2025-01-01",
        "platforms": {platform_key: {"binary": binary, "checksum": checksum, "size": size}},
    }
    response.raise_for_status.return_value = None
    return response


class TestClaudeManagedToolResolveDistribution:
    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("httpx.get")
    def test_adapts_the_manifest_into_a_single_binary_distribution(
        self, mock_get: MagicMock, mock_sys: MagicMock, mock_platform: MagicMock
    ) -> None:
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"
        mock_get.return_value = _make_claude_manifest_response(checksum="deadbeef", size=4096)

        distribution = ClaudeManagedTool().resolve_distribution()

        assert distribution.version == _CLAUDE_RECOMMENDED
        assert distribution.archive == "single_binary"
        assert distribution.binary_subpath == "claude"
        assert distribution.checksum_sha256 == "deadbeef"
        assert distribution.size == 4096
        assert distribution.url == f"{GCP_BUCKET_BASE_URL}/{_CLAUDE_RECOMMENDED}/darwin-arm64/claude"

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    def test_unsupported_platform_raises_structured_error(self, mock_sys: MagicMock, mock_platform: MagicMock) -> None:
        mock_sys.platform = "win32"
        mock_platform.machine.return_value = "AMD64"

        with pytest.raises(UnsupportedManagedPlatformError):
            ClaudeManagedTool().resolve_distribution()

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("httpx.get", side_effect=httpx.HTTPError("offline"))
    def test_manifest_fetch_failure_raises_managed_distribution_error(
        self, mock_get: MagicMock, mock_sys: MagicMock, mock_platform: MagicMock
    ) -> None:
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        with pytest.raises(ManagedDistributionError, match="manifest"):
            ClaudeManagedTool().resolve_distribution()

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("httpx.get")
    def test_platform_absent_from_manifest_raises(
        self, mock_get: MagicMock, mock_sys: MagicMock, mock_platform: MagicMock
    ) -> None:
        mock_sys.platform = "linux"
        mock_platform.machine.return_value = "x86_64"
        # The manifest advertises only darwin-arm64, so linux-x64 has no entry.
        mock_get.return_value = _make_claude_manifest_response(platform_key="darwin-arm64")

        with pytest.raises(ManagedDistributionError, match="linux-x64"):
            ClaudeManagedTool().resolve_distribution()


class TestClaudeManagedToolStage:
    def test_places_the_single_binary_and_makes_it_executable(self, tmp_path: Path) -> None:
        downloaded = tmp_path / "claude"
        downloaded.write_bytes(b"#!/bin/sh\necho 2.1.156\n")
        # Strip the execute bits to prove stage restores them before the --version gate.
        downloaded.chmod(0o644)
        version_dir = tmp_path / "version-2.1.156"

        binary = ClaudeManagedTool().stage(downloaded, version_dir)

        assert binary == version_dir / "claude"
        assert binary.is_file()
        assert binary.stat().st_mode & 0o111
        # The raw download was moved into the version dir, not left behind.
        assert not downloaded.exists()


class TestClaudeManagedToolParseVersion:
    def test_parses_version_from_stdout(self) -> None:
        assert ClaudeManagedTool().parse_version("claude 2.1.156") == "2.1.156"

    def test_returns_none_when_unparseable(self) -> None:
        assert ClaudeManagedTool().parse_version("no version here") is None


class TestClaudeManagedToolRegistration:
    def test_registry_returns_a_claude_managed_tool(self) -> None:
        tool = get_managed_tool(Dependency.CLAUDE)
        assert isinstance(tool, ClaudeManagedTool)
        assert tool.tool == Dependency.CLAUDE
        assert tool.retention_keep == 2
        assert tool.platform_keys == frozenset({"darwin-arm64", "linux-x64"})

    def test_version_range_is_the_claude_version_range(self) -> None:
        assert ClaudeManagedTool().version_range == CLAUDE_VERSION_RANGE


def test_claude_platform_map_values_match_the_advertised_platform_keys() -> None:
    # The running-platform map and the advertised platform_keys must agree, or a
    # platform could resolve a key the manifest never lists (or vice versa).
    assert set(_CLAUDE_PLATFORM_MAP.values()) == ClaudeManagedTool().platform_keys


def test_get_managed_tools_lists_exactly_claude_and_pi() -> None:
    assert set(get_managed_tools()) == {Dependency.CLAUDE, Dependency.PI}
