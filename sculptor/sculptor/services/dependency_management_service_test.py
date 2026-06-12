import hashlib
import inspect
import io
import itertools
import tarfile
import threading
import time
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest

from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.sculptor.user_config import DependencyPaths
from imbue_core.sculptor.user_config import UserConfig
from imbue_core.subprocess_utils import FinishedProcess
from imbue_core.subprocess_utils import ProcessError
from imbue_core.subprocess_utils import ProcessTimeoutError
from sculptor.services.dependency_management_service import CLAUDE_VERSION_RANGE
from sculptor.services.dependency_management_service import Dependency
from sculptor.services.dependency_management_service import DependencyCheckResult
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import VersionRange
from sculptor.services.dependency_management_service import _parse_dependency_config
from sculptor.services.dependency_management_service import parse_pi_version
from sculptor.services.managed_tools import BlockedVersionRange
from sculptor.services.managed_tools import ClaudeManagedTool
from sculptor.services.managed_tools import PiManagedTool
from sculptor.services.managed_tools import PiPin
from sculptor.services.managed_tools import PlatformPin
from sculptor.services.managed_tools import get_managed_tool
from sculptor.web.data_types import BinaryMode
from sculptor.web.data_types import InstallProgress

# These tests exercise the real install/download orchestrator with httpx stubbed in
# each test, so they opt out of the conftest guard that otherwise blocks managed
# binary downloads during unit tests.
pytestmark = pytest.mark.allow_dependency_downloads

_RECOMMENDED = CLAUDE_VERSION_RANGE.recommended_version


def _make_user_config(
    user_email: str = "test@example.com",
    user_id: str = "user-1",
    organization_id: str = "org-1",
    instance_id: str = "inst-1",
    claude_binary_mode: str = "MANAGED",
    dependency_paths: DependencyPaths | None = None,
) -> UserConfig:
    # Build unified dependency_paths.claude from mode + optional custom path.
    # pi is pinned to the bare "pi" (CUSTOM/PATH) so these Claude-focused tests are
    # unaffected by pi's MANAGED default — exactly the pre-flip behaviour, where the
    # default was also "pi". pi-specific tests use _make_user_config_with_pi instead.
    if dependency_paths is None:
        dep_paths = DependencyPaths(claude=claude_binary_mode, pi="pi")
    else:
        claude_value = dependency_paths.claude if dependency_paths.claude else claude_binary_mode
        dep_paths = DependencyPaths(git=dependency_paths.git, claude=claude_value, pi="pi")
    return UserConfig(
        user_email=user_email,
        user_id=user_id,
        organization_id=organization_id,
        instance_id=instance_id,
        dependency_paths=dep_paths,
    )


def _make_manifest_json(
    version: str = _RECOMMENDED,
    platform_key: str = "darwin-arm64",
    binary_name: str = "claude",
    checksum: str = "abc123",
    size: int = 100,
) -> dict[str, object]:
    return {
        "version": version,
        "buildDate": "2025-01-01",
        "platforms": {
            platform_key: {
                "binary": binary_name,
                "checksum": checksum,
                "size": size,
            }
        },
    }


def _wait_for_install_complete(
    service: DependencyManagementService,
    timeout: float = 10.0,
    tool: Dependency = Dependency.CLAUDE,
) -> None:
    """Wait for *tool*'s background install thread to finish, including its trailing notify.

    Joining the thread — rather than polling ``_installing`` — ensures the thread's
    final ``_notify_observers()`` has returned before the caller leaves the
    ConcurrencyGroup block; polling the flag returns mid-finalization and races the
    group's teardown (FOLLOWUPS-10).
    """
    thread = service._install_thread.get(tool)
    if thread is not None:
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise TimeoutError("Install did not complete within timeout")
        return
    # No download thread was spawned (synchronous failure before the spawn); poll the flag.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with service._progress_lock:
            if not service._installing.get(tool, False):
                return
        time.sleep(0.05)
    raise TimeoutError("Install did not complete within timeout")


def _make_mock_cg(
    run_process_return_value: object = None,
    run_process_side_effect: object = None,
) -> MagicMock:
    """A MagicMock concurrency group whose start_new_thread actually spawns a daemon thread.

    Tests that exercise install_managed depend on the background thread actually
    running; production code now routes those threads through
    ``concurrency_group.start_new_thread`` (see SCU-1393), so a bare MagicMock
    would silently drop them.
    """
    mock_cg = MagicMock()
    if run_process_return_value is not None:
        mock_cg.run_process_to_completion.return_value = run_process_return_value
    if run_process_side_effect is not None:
        mock_cg.run_process_to_completion.side_effect = run_process_side_effect

    def _start_new_thread(
        target: Callable[..., object],
        args: tuple = (),
        kwargs: dict | None = None,
        name: str | None = None,
        daemon: bool = True,
        **_: object,
    ) -> threading.Thread:
        thread = threading.Thread(target=target, args=args, kwargs=kwargs or {}, name=name, daemon=daemon)
        thread.start()
        return thread

    mock_cg.start_new_thread.side_effect = _start_new_thread
    return mock_cg


class TestResolveClaudePath:
    @pytest.fixture(autouse=True)
    def _clear_claude_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Remove the env-var override so tests exercise config-driven resolution."""
        monkeypatch.delenv("SCULPTOR_CLAUDE_BINARY_PATH_OVERRIDE", raising=False)

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_managed_mode_with_installed_version(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        # Create a version dir with binary
        version_dir = tmp_path / "dependencies" / "claude" / f"version-{_RECOMMENDED}"
        version_dir.mkdir(parents=True)
        (version_dir / "claude").touch()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result == str(version_dir / "claude")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_managed_mode_returns_highest_version(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        claude_dir = tmp_path / "dependencies" / "claude"
        for v in ["1.0.0", "2.0.0", "1.5.0"]:
            d = claude_dir / f"version-{v}"
            d.mkdir(parents=True)
            (d / "claude").touch()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result is not None
        assert "2.0.0" in result

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_managed_mode_no_installed_versions(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result is None

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_custom_mode_bare_name(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        """CUSTOM mode with a bare command name resolves via PATH."""
        mock_config.return_value = _make_user_config(
            claude_binary_mode="claude",
        )

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result == "/usr/bin/claude"
        mock_which.assert_called_once_with("claude")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/opt/claude")
    def test_custom_mode_absolute_path(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        """CUSTOM mode with an absolute path resolves via shutil.which (checks existence)."""
        mock_config.return_value = _make_user_config(
            claude_binary_mode="/opt/claude",
        )

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result == "/opt/claude"
        mock_which.assert_called_once_with("/opt/claude")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_legacy_path_mode_migrates_to_claude_command(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        """Legacy PATH value is migrated to bare 'claude' command by the config validator."""
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result == "/usr/bin/claude"
        mock_which.assert_called_once_with("claude")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    def test_custom_mode_invalid_path_returns_none(self, mock_config: MagicMock) -> None:
        """CUSTOM mode with an invalid value (spaces/slashes) returns None."""
        mock_config.return_value = _make_user_config(
            claude_binary_mode="some path with spaces",
        )

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.CLAUDE)

        assert result is None


class TestResolveGitPath:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_default_path(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.GIT)

        assert result == "/usr/bin/git"

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    def test_override_path(self, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(
            dependency_paths=DependencyPaths(git="/custom/git"),
        )

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.GIT)

        assert result == "/custom/git"


class TestVersionRange:
    def test_in_range(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range(_RECOMMENDED) is True

    def test_below_min(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("2.0.0") is False

    def test_above_max(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("3.0.0") is False

    def test_recommended_is_in_range(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range(CLAUDE_VERSION_RANGE.recommended_version) is True

    def test_invalid_version(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("not-a-version") is False

    @patch.object(
        ClaudeManagedTool,
        "version_range",
        VersionRange(
            min_version="2.0.0",
            max_version="2.99.99",
            recommended_version="2.1.89",
            blocked_versions=(BlockedVersionRange(min_version="2.1.101", max_version="2.1.101"),),
        ),
    )
    def test_single_blocked_version(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("2.1.101") is False
            assert service.is_version_in_range("2.1.100") is True
            assert service.is_version_in_range("2.1.102") is True

    @patch.object(
        ClaudeManagedTool,
        "version_range",
        VersionRange(
            min_version="2.0.0",
            max_version="2.99.99",
            recommended_version="2.1.89",
            blocked_versions=(BlockedVersionRange(min_version="2.1.100", max_version="2.1.105"),),
        ),
    )
    def test_blocked_version_range(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("2.1.99") is True
            assert service.is_version_in_range("2.1.100") is False
            assert service.is_version_in_range("2.1.103") is False
            assert service.is_version_in_range("2.1.105") is False
            assert service.is_version_in_range("2.1.106") is True

    @patch.object(
        ClaudeManagedTool,
        "version_range",
        VersionRange(
            min_version="2.0.0",
            max_version="2.99.99",
            recommended_version="2.1.89",
            blocked_versions=(
                BlockedVersionRange(min_version="2.1.50", max_version="2.1.50"),
                BlockedVersionRange(min_version="2.1.100", max_version="2.1.105"),
            ),
        ),
    )
    def test_multiple_blocked_ranges(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("2.1.50") is False
            assert service.is_version_in_range("2.1.51") is True
            assert service.is_version_in_range("2.1.103") is False
            assert service.is_version_in_range("2.1.89") is True


class TestInstallManaged:
    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_successful_install(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"fake-claude-binary"
        expected_checksum = hashlib.sha256(binary_content).hexdigest()

        manifest = _make_manifest_json(checksum=expected_checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream.headers = {"content-length": str(len(binary_content))}
        mock_stream.iter_bytes.return_value = [binary_content]
        mock_stream.raise_for_status.return_value = None
        mock_stream_context.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_context.__exit__ = MagicMock(return_value=False)

        version_result = FinishedProcess(
            stdout=f"claude {_RECOMMENDED}", stderr="", returncode=0, command=("test",), is_output_already_logged=False
        )

        mock_cg = _make_mock_cg(run_process_return_value=version_result)

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", return_value=mock_stream_context),
        ):
            service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
            result = service.install_managed(Dependency.CLAUDE)

            assert result.success is True
            assert result.in_progress is False  # newly started, not already running

            # Wait for background download to complete
            _wait_for_install_complete(service)

        # Verify final directory exists
        final_dir = tmp_path / "dependencies" / "claude" / f"version-{_RECOMMENDED}"
        assert final_dir.is_dir()

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_checksum_mismatch(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        manifest = _make_manifest_json(checksum="wrong-checksum", size=10)

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream.headers = {"content-length": "5"}
        mock_stream.iter_bytes.return_value = [b"hello"]
        mock_stream.raise_for_status.return_value = None
        mock_stream_context.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_context.__exit__ = MagicMock(return_value=False)

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)

            with (
                patch("httpx.get", return_value=mock_manifest_response),
                patch("httpx.stream", return_value=mock_stream_context),
            ):
                result = service.install_managed(Dependency.CLAUDE)
                assert result.success is True  # returns early after manifest

                # Wait for background download (which will fail on checksum)
                _wait_for_install_complete(service)

        # Temp dir should be cleaned up
        claude_dir = tmp_path / "dependencies" / "claude"
        if claude_dir.exists():
            tmp_dirs = [d for d in claude_dir.iterdir() if d.name.startswith("tmp-")]
            assert len(tmp_dirs) == 0

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_version_check_failure(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"bad-binary"
        checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream.headers = {"content-length": str(len(binary_content))}
        mock_stream.iter_bytes.return_value = [binary_content]
        mock_stream.raise_for_status.return_value = None
        mock_stream_context.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_context.__exit__ = MagicMock(return_value=False)

        mock_cg = _make_mock_cg(
            run_process_side_effect=ProcessError(("test",), "stdout", "stderr", returncode=1),
        )

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", return_value=mock_stream_context),
        ):
            service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
            result = service.install_managed(Dependency.CLAUDE)
            assert result.success is True  # returns early after manifest

            # Background thread will fail on version check
            _wait_for_install_complete(service)

    def test_unsupported_tool(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.install_managed(Dependency.GIT)

        assert result.success is False
        assert "not supported" in (result.error or "").lower()

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_manifest_fetch_failure(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)

            with patch("httpx.get", side_effect=httpx.HTTPError("Connection failed")):
                result = service.install_managed(Dependency.CLAUDE)

        assert result.success is False
        assert "manifest" in (result.error or "").lower()

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_initial_progress_set_on_install(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """install_managed sets initial install_progress before returning."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"fake-binary-content"
        checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        # Use a gate to block the download thread so we can inspect state
        # before the background thread completes.
        download_gate = threading.Event()

        def gated_stream_context(
            _method: str, _url: str, timeout: float = 300.0, follow_redirects: bool = False
        ) -> MagicMock:  # noqa: ARG001
            ctx = MagicMock()
            stream = MagicMock()
            stream.headers = {"content-length": str(len(binary_content))}
            stream.raise_for_status.return_value = None
            stream.iter_bytes = lambda chunk_size=65536: (download_gate.wait(timeout=10), [binary_content])[1]  # noqa: ARG005
            ctx.__enter__ = MagicMock(return_value=stream)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        version_result = FinishedProcess(
            stdout=f"claude {_RECOMMENDED}", stderr="", returncode=0, command=("test",), is_output_already_logged=False
        )

        mock_cg = _make_mock_cg(run_process_return_value=version_result)

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", side_effect=gated_stream_context),
        ):
            service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
            result = service.install_managed(Dependency.CLAUDE)
            assert result.success is True

            # Progress should be set immediately after install_managed returns.
            # The download thread is blocked by the gate so state is stable.
            with service._progress_lock:
                assert service._installing.get(Dependency.CLAUDE) is True
                progress = service._install_progress.get(Dependency.CLAUDE)
                assert progress is not None
                assert progress.tool == "CLAUDE"
                assert progress.bytes_downloaded == 0

            # Unblock the download and wait for completion
            download_gate.set()
            _wait_for_install_complete(service)

        # After completion, progress is cleared
        assert service._install_progress.get(Dependency.CLAUDE) is None


class TestCleanup:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_keeps_newest_versions(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        claude_dir = tmp_path / "dependencies" / "claude"
        for v in ["1.0.0", "2.0.0", "3.0.0", "4.0.0"]:
            d = claude_dir / f"version-{v}"
            d.mkdir(parents=True)
            (d / "claude").touch()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            service.cleanup_old_versions(Dependency.CLAUDE, keep=2)

        remaining = sorted([d.name for d in claude_dir.iterdir() if d.is_dir()])
        assert remaining == ["version-3.0.0", "version-4.0.0"]

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_cleans_tmp_dirs(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        claude_dir = tmp_path / "dependencies" / "claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "tmp-abc123").mkdir()
        (claude_dir / "tmp-def456").mkdir()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            service.cleanup_old_versions(Dependency.CLAUDE, keep=2)

        tmp_dirs = [d for d in claude_dir.iterdir() if d.name.startswith("tmp-")]
        assert len(tmp_dirs) == 0

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_cleanup_stale_state(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        # Use CUSTOM mode to short-circuit _auto_install_if_needed — this test only
        # exercises _cleanup_stale_state, and MANAGED mode would spawn a real
        # background auto-install thread tracked by the concurrency group.
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        claude_dir = tmp_path / "dependencies" / "claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "tmp-stale").mkdir()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            service.start()

        assert not (claude_dir / "tmp-stale").exists()


class TestConcurrentInstall:
    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_concurrent_install_returns_in_progress(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A second install call while one is in progress returns in_progress=True."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"binary"
        checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        # Use an event to block the download so we can make a second call
        download_gate = threading.Event()

        def slow_stream_context(
            _method: str, _url: str, timeout: float = 300.0, follow_redirects: bool = False
        ) -> MagicMock:  # noqa: ARG001
            ctx = MagicMock()
            stream = MagicMock()
            stream.headers = {"content-length": str(len(binary_content))}
            stream.raise_for_status.return_value = None

            def slow_iter_bytes(chunk_size: int = 65536) -> list[bytes]:
                download_gate.wait(timeout=10)
                return [binary_content]

            stream.iter_bytes = slow_iter_bytes
            ctx.__enter__ = MagicMock(return_value=stream)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        version_result = FinishedProcess(
            stdout=f"claude {_RECOMMENDED}", stderr="", returncode=0, command=("test",), is_output_already_logged=False
        )

        mock_cg = _make_mock_cg(run_process_return_value=version_result)

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", side_effect=slow_stream_context),
        ):
            # First call starts the install
            result1 = service.install_managed(Dependency.CLAUDE)
            assert result1.success is True
            assert result1.in_progress is False

            # Give the background thread a moment to start
            time.sleep(0.1)

            # Second call while download is blocked should return in_progress
            result2 = service.install_managed(Dependency.CLAUDE)
            assert result2.success is True
            assert result2.in_progress is True

            # Unblock the download
            download_gate.set()
            _wait_for_install_complete(service)


class TestStop:
    """Cooperative cancellation via Service.stop() (SCU-1393)."""

    def test_stop_refuses_new_installs(self) -> None:
        """install_managed returns failure once stop() has been called."""
        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service.stop()

        result = service.install_managed(Dependency.CLAUDE)
        assert result.success is False
        assert "shutting down" in (result.error or "").lower()
        # No thread should have been spawned.
        mock_cg.start_new_thread.assert_not_called()

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_stop_signals_in_flight_install(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An install blocked in the download loop cancels at the next chunk after stop()."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"fake-binary"
        checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=checksum, size=len(binary_content) * 4)

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        # Block in iter_bytes until the test releases. Yield multiple chunks
        # so the cancellation check inside the loop has a real chance to fire.
        download_gate = threading.Event()
        chunks_written = 0

        def gated_stream_context(
            _method: str, _url: str, timeout: float = 300.0, follow_redirects: bool = False
        ) -> MagicMock:  # noqa: ARG001
            ctx = MagicMock()
            stream = MagicMock()
            stream.headers = {"content-length": str(len(binary_content) * 4)}
            stream.raise_for_status.return_value = None

            def slow_iter_bytes(chunk_size: int = 65536) -> Iterator[bytes]:  # noqa: ARG001
                nonlocal chunks_written
                download_gate.wait(timeout=10)
                for _ in range(4):
                    chunks_written += 1
                    yield binary_content

            stream.iter_bytes = slow_iter_bytes
            ctx.__enter__ = MagicMock(return_value=stream)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        # The finally block calls _get_status → check_installed → run_process_to_completion
        # for git (resolved via shutil.which on the host). Return a benign FinishedProcess
        # so the post-cancel cleanup completes without crashing.
        benign_version_result = FinishedProcess(
            stdout="version 1.2.3",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )
        mock_cg = _make_mock_cg(run_process_return_value=benign_version_result)

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", side_effect=gated_stream_context),
        ):
            service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
            result = service.install_managed(Dependency.CLAUDE)
            assert result.success is True
            assert service._install_thread.get(Dependency.CLAUDE) is not None

            # Request stop, then release the gate. The loop should observe
            # _stop_requested before iterating further chunks.
            service.stop()
            download_gate.set()

            install_thread = service._install_thread.get(Dependency.CLAUDE)
            assert install_thread is not None
            install_thread.join(timeout=5.0)
            assert not install_thread.is_alive()

        # Cleanup ran: state is reset.
        assert service._installing.get(Dependency.CLAUDE, False) is False
        assert service._install_progress.get(Dependency.CLAUDE) is None
        # Final version dir was never created — install never reached the rename step.
        final_dir = tmp_path / "dependencies" / "claude" / f"version-{_RECOMMENDED}"
        assert not final_dir.exists()
        # Temp dirs were cleaned up by _download_verify_stage's finally.
        claude_dir = tmp_path / "dependencies" / "claude"
        if claude_dir.exists():
            tmp_dirs = [d for d in claude_dir.iterdir() if d.name.startswith("tmp-")]
            assert tmp_dirs == []
        # The verify-step `binary --version` was never called — cancellation
        # caught us before it. The post-cleanup status push is skipped once
        # shutdown is requested, so no git/claude --version probes fire either.
        verify_calls = [
            c
            for c in mock_cg.run_process_to_completion.call_args_list
            if c.args and c.args[0] and "tmp-" in str(c.args[0][0])
        ]
        assert verify_calls == []

    def test_stop_is_idempotent_with_no_install(self) -> None:
        """stop() is safe to call when nothing is in flight."""
        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        # Should not raise or block.
        service.stop()
        service.stop()


class TestRunAuthLogin:
    @patch("sculptor.services.dependency_management_service.webbrowser")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_successful_auth(self, mock_which: MagicMock, mock_config: MagicMock, mock_browser: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        auth_result = FinishedProcess(
            stdout="",
            stderr="Visit: https://claude.ai/auth/callback?code=abc\nAuthenticated!",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )

        def fake_run_streaming(
            command: object,
            on_output: Callable[[str, bool], None],
            is_checked: object = True,
            timeout: object = None,
        ) -> FinishedProcess:
            # Simulate run_streaming calling the output callback for each stderr line
            on_output("Visit: https://claude.ai/auth/callback?code=abc", True)
            on_output("Authenticated!", True)
            return auth_result

        with patch("sculptor.services.dependency_management_service.run_streaming", side_effect=fake_run_streaming):
            with ConcurrencyGroup(name="test") as cg:
                service = DependencyManagementService(concurrency_group=cg)
                result = service.run_auth_login(Dependency.CLAUDE)

        assert result.success is True
        assert result.auth_url == "https://claude.ai/auth/callback?code=abc"
        mock_browser.open.assert_called_once_with("https://claude.ai/auth/callback?code=abc")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_auth_timeout(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        with patch(
            "sculptor.services.dependency_management_service.run_streaming",
            side_effect=ProcessTimeoutError(("claude", "auth", "login"), "", ""),
        ):
            with ConcurrencyGroup(name="test") as cg:
                service = DependencyManagementService(concurrency_group=cg)
                result = service.run_auth_login(Dependency.CLAUDE)

        assert result.success is False
        assert "timed out" in (result.error or "").lower()

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value=None)
    def test_not_installed(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.run_auth_login(Dependency.CLAUDE)

        assert result.success is False
        assert "not installed" in (result.error or "").lower()

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_auth_failure(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        auth_result = FinishedProcess(
            stdout="",
            stderr="Authentication failed",
            returncode=1,
            command=("test",),
            is_output_already_logged=False,
        )

        with patch("sculptor.services.dependency_management_service.run_streaming", return_value=auth_result):
            with ConcurrencyGroup(name="test") as cg:
                service = DependencyManagementService(concurrency_group=cg)
                result = service.run_auth_login(Dependency.CLAUDE)

        assert result.success is False

    def test_unsupported_tool(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.run_auth_login(Dependency.GIT)

        assert result.success is False
        assert "not supported" in (result.error or "").lower()


class TestCheckAuthenticated:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_authenticated(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        auth_result = FinishedProcess(
            stdout="Authenticated as user@example.com",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )

        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.return_value = auth_result

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        result = service.check_authenticated(Dependency.CLAUDE)

        assert result is True
        mock_cg.run_process_to_completion.assert_called_once_with(
            ["/usr/bin/claude", "auth", "status"],
            timeout=10.0,
        )

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_not_authenticated(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.side_effect = ProcessError(("test",), "stdout", "stderr", returncode=1)

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        result = service.check_authenticated(Dependency.CLAUDE)

        assert result is False

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value=None)
    def test_not_installed(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.check_authenticated(Dependency.CLAUDE)

        assert result is None

    def test_unsupported_tool(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.check_authenticated(Dependency.GIT)

        assert result is None

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_get_status_includes_auth(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config(claude_binary_mode="claude")

        version_result = FinishedProcess(
            stdout="claude 2.1.89",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )
        auth_result = FinishedProcess(
            stdout="Authenticated",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )

        mock_cg = MagicMock()
        # git version, claude version, pi version, claude auth status
        mock_cg.run_process_to_completion.side_effect = [version_result, version_result, version_result, auth_result]

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        status = service.get_status()

        assert status.claude.is_authenticated is True
        assert status.git.is_authenticated is None


class TestCheckInstalled:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/git")
    def test_git_installed(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config()

        version_result = FinishedProcess(
            stdout="git version 2.44.0",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )

        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.return_value = version_result

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        result = service.check_installed(Dependency.GIT)

        assert result.installed is True
        assert result.version == "2.44.0"
        assert result.path == "/usr/bin/git"

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value=None)
    def test_git_not_installed(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.check_installed(Dependency.GIT)

        assert result.installed is False


class TestInstallProgress:
    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_progress_cleared_after_completion(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Install progress is None after background install completes."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"fake-binary"
        expected_checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=expected_checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream.headers = {"content-length": str(len(binary_content))}
        mock_stream.iter_bytes.return_value = [binary_content]
        mock_stream.raise_for_status.return_value = None
        mock_stream_context.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_context.__exit__ = MagicMock(return_value=False)

        version_result = FinishedProcess(
            stdout=f"claude {_RECOMMENDED}", stderr="", returncode=0, command=("test",), is_output_already_logged=False
        )

        mock_cg = _make_mock_cg(run_process_return_value=version_result)

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", return_value=mock_stream_context),
        ):
            service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
            result = service.install_managed(Dependency.CLAUDE)
            assert result.success is True

            _wait_for_install_complete(service)

        # install_progress must be cleared after install
        assert service._install_progress.get(Dependency.CLAUDE) is None
        assert service._installing.get(Dependency.CLAUDE, False) is False
        # get_status should also have no install_progress for Claude
        status = service.get_status()
        assert status.claude.install_progress is None

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_get_status_surfaces_progress_on_claude_dependency(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A started Claude install's progress is surfaced on status.claude.install_progress (per-tool)."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            # Stand in for an in-flight Claude install: the per-tool progress map
            # carries the live progress that _get_status must surface on the
            # Claude DependencyInfo rather than a single top-level field.
            with service._progress_lock:
                service._install_progress[Dependency.CLAUDE] = InstallProgress(
                    tool=Dependency.CLAUDE.value, bytes_downloaded=42, total_bytes=100
                )
            status = service.get_status()

        assert status.claude.install_progress is not None
        assert status.claude.install_progress.bytes_downloaded == 42
        # The progress belongs to Claude alone — pi must not inherit it.
        assert status.pi.install_progress is None
        # Progress lives per-tool, never on a top-level status field.
        assert not hasattr(status, "install_progress")


class TestProgressNotifierThread:
    """Install-progress pushes come from a dedicated notifier thread, not the download thread.

    Computing status spawns subprocesses; doing that between chunk reads once
    collapsed download throughput from ~11 MB/s to ~70 KB/s. The download-thread
    callback must only record progress; the notifier owns all status pushes.
    """

    def test_progress_callback_records_without_notifying(self) -> None:
        """The download-thread hot path writes progress and does nothing else."""
        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        observer_queue: Queue = Queue()
        service.add_observer_queue(observer_queue)

        for tick in range(1, 21):
            service._on_install_progress(Dependency.CLAUDE, tick * 1024, 20 * 1024)

        mock_cg.run_process_to_completion.assert_not_called()
        mock_cg.start_new_thread.assert_not_called()
        assert observer_queue.empty(), "progress ticks must not push to observers"
        with service._progress_lock:
            progress = service._install_progress[Dependency.CLAUDE]
        assert progress.bytes_downloaded == 20 * 1024
        assert progress.total_bytes == 20 * 1024

    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_notifier_pushes_fresh_status_and_exits_when_install_finishes(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        git_version_result = FinishedProcess(
            stdout="git version 2.44.0", stderr="", returncode=0, command=("git",), is_output_already_logged=False
        )
        mock_cg = _make_mock_cg(run_process_return_value=git_version_result)
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        observer_queue: Queue = Queue()
        service.add_observer_queue(observer_queue)

        with patch.object(DependencyManagementService, "_PROGRESS_NOTIFY_INTERVAL_SECONDS", 0.01):
            with service._progress_lock:
                service._installing[Dependency.CLAUDE] = True
            service._on_install_progress(Dependency.CLAUDE, 1024, 4096)
            service._ensure_progress_notifier_running()
            notifier = service._progress_notifier_thread
            assert notifier is not None

            status = observer_queue.get(timeout=5.0)
            # Each push is a freshly computed status carrying the live progress.
            assert status.claude.install_progress is not None
            assert status.claude.install_progress.bytes_downloaded == 1024
            assert status.git.installed is True

            # A later write from the download thread shows up in a subsequent
            # push — no stale snapshot in between.
            service._on_install_progress(Dependency.CLAUDE, 2048, 4096)
            deadline = time.monotonic() + 5.0
            latest_bytes = None
            while time.monotonic() < deadline:
                latest = observer_queue.get(timeout=5.0)
                assert latest.claude.install_progress is not None
                latest_bytes = latest.claude.install_progress.bytes_downloaded
                if latest_bytes == 2048:
                    break
            assert latest_bytes == 2048

            # Once no install is active, the notifier exits and clears its handle.
            with service._progress_lock:
                service._installing[Dependency.CLAUDE] = False
            notifier.join(timeout=5.0)
            assert not notifier.is_alive()
            with service._progress_lock:
                assert service._progress_notifier_thread is None

    def test_notifier_survives_transient_notify_failure(self) -> None:
        """One failed status push drops that tick; the notifier keeps running."""
        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        notify_mock = MagicMock(side_effect=itertools.chain([RuntimeError("boom")], itertools.repeat(None)))
        with (
            patch.object(DependencyManagementService, "_PROGRESS_NOTIFY_INTERVAL_SECONDS", 0.01),
            patch.object(DependencyManagementService, "_notify_observers", notify_mock),
        ):
            with service._progress_lock:
                service._installing[Dependency.CLAUDE] = True
            service._ensure_progress_notifier_running()
            notifier = service._progress_notifier_thread
            assert notifier is not None

            deadline = time.monotonic() + 5.0
            while notify_mock.call_count < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert notify_mock.call_count >= 2, "notifier must keep pushing after a transient failure"
            assert notifier.is_alive()

            with service._progress_lock:
                service._installing[Dependency.CLAUDE] = False
            notifier.join(timeout=5.0)
            assert not notifier.is_alive()

    def test_ensure_notifier_is_singleton_and_stop_joins_it(self) -> None:
        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        # A long interval keeps the notifier parked in its wait, proving stop()
        # wakes it immediately rather than timing out the join.
        with patch.object(DependencyManagementService, "_PROGRESS_NOTIFY_INTERVAL_SECONDS", 60.0):
            with service._progress_lock:
                service._installing[Dependency.CLAUDE] = True
            service._ensure_progress_notifier_running()
            notifier = service._progress_notifier_thread
            assert notifier is not None
            assert notifier.is_alive()

            service._ensure_progress_notifier_running()
            assert service._progress_notifier_thread is notifier
            assert mock_cg.start_new_thread.call_count == 1

            service.stop()
            assert not notifier.is_alive()

    @patch("shutil.which", return_value="/usr/bin/git")
    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_install_managed_pushes_progress_via_notifier(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        """End-to-end: install_managed starts the notifier, which pushes while the download runs."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"fake-claude-binary"
        checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        # Block the download so every push after install_managed's single
        # synchronous notify can only come from the notifier thread.
        download_gate = threading.Event()

        def iter_gated_bytes(chunk_size: int = 65536) -> list[bytes]:  # noqa: ARG001
            # Raising (rather than proceeding) surfaces a never-released gate as
            # an install error, which the test asserts against below.
            if not download_gate.wait(timeout=10):
                raise TimeoutError("download gate was never released")
            return [binary_content]

        def gated_stream_context(
            _method: str, _url: str, timeout: float = 300.0, follow_redirects: bool = False
        ) -> MagicMock:  # noqa: ARG001
            ctx = MagicMock()
            stream = MagicMock()
            stream.headers = {"content-length": str(len(binary_content))}
            stream.raise_for_status.return_value = None
            stream.iter_bytes = iter_gated_bytes
            ctx.__enter__ = MagicMock(return_value=stream)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        version_result = FinishedProcess(
            stdout=f"claude {_RECOMMENDED}", stderr="", returncode=0, command=("test",), is_output_already_logged=False
        )
        mock_cg = _make_mock_cg(run_process_return_value=version_result)

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", side_effect=gated_stream_context),
            patch.object(DependencyManagementService, "_PROGRESS_NOTIFY_INTERVAL_SECONDS", 0.01),
        ):
            service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
            observer_queue: Queue = Queue()
            service.add_observer_queue(observer_queue)

            result = service.install_managed(Dependency.CLAUDE)
            assert result.success is True

            first = observer_queue.get(timeout=5.0)
            assert first.claude.install_progress is not None
            second = observer_queue.get(timeout=5.0)
            assert second.claude.install_progress is not None
            assert second.claude.install_progress.bytes_downloaded == 0

            download_gate.set()
            _wait_for_install_complete(service)
            with service._progress_lock:
                assert service._install_error.get(Dependency.CLAUDE) is None, "install must complete without error"

            # With the install finished, the notifier observes no active install
            # and winds down on its own.
            deadline = time.monotonic() + 5.0
            with service._progress_lock:
                notifier = service._progress_notifier_thread
            while notifier is not None and time.monotonic() < deadline:
                time.sleep(0.01)
                with service._progress_lock:
                    notifier = service._progress_notifier_thread
            assert notifier is None


class TestInstallErrorSurfacing:
    """SCU-1271: a failed managed install must surface its error in the status.

    Before this, a failed managed upgrade (e.g. the new recommended version
    fails to download) silently fell back to the stale binary on disk and the
    UI could only show a bare "version mismatch" with no explanation of why
    the update did not happen.
    """

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_download_failure_is_surfaced_in_status(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A background download that fails its checksum surfaces the error in get_status()."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        # The manifest advertises a checksum the downloaded bytes won't match,
        # mimicking a corrupted/partial download.
        manifest = _make_manifest_json(checksum="wrong-checksum", size=5)

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream.headers = {"content-length": "5"}
        mock_stream.iter_bytes.return_value = [b"hello"]
        mock_stream.raise_for_status.return_value = None
        mock_stream_context.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_context.__exit__ = MagicMock(return_value=False)

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)

            with (
                patch("httpx.get", return_value=mock_manifest_response),
                patch("httpx.stream", return_value=mock_stream_context),
            ):
                result = service.install_managed(Dependency.CLAUDE)
                # install_managed returns early after the manifest resolves; the
                # download (and its failure) happens on the background thread.
                assert result.success is True

                _wait_for_install_complete(service)

            status = service.get_status()

        assert status.claude.install_error is not None, "a failed managed install should surface an error in status"
        assert "checksum" in status.claude.install_error.lower()

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_startup_auto_install_failure_is_surfaced_in_status(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A startup auto-install that can't fetch the manifest surfaces the error in get_status()."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)

            # The startup auto-install can't even fetch the manifest (offline / server error).
            with patch("httpx.get", side_effect=httpx.HTTPError("Connection failed")):
                service._run_auto_install(Dependency.CLAUDE)

            status = service.get_status()

        assert status.claude.install_error is not None, (
            "a failed startup auto-install should surface an error in status"
        )
        assert "manifest" in status.claude.install_error.lower()

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_successful_install_clears_prior_error(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A later successful install clears a previously surfaced error."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        binary_content = b"fake-claude-binary"
        expected_checksum = hashlib.sha256(binary_content).hexdigest()
        manifest = _make_manifest_json(checksum=expected_checksum, size=len(binary_content))

        mock_manifest_response = MagicMock()
        mock_manifest_response.json.return_value = manifest
        mock_manifest_response.raise_for_status.return_value = None

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream.headers = {"content-length": str(len(binary_content))}
        mock_stream.iter_bytes.return_value = [binary_content]
        mock_stream.raise_for_status.return_value = None
        mock_stream_context.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_context.__exit__ = MagicMock(return_value=False)

        version_result = FinishedProcess(
            stdout=f"claude {_RECOMMENDED}", stderr="", returncode=0, command=("test",), is_output_already_logged=False
        )

        mock_cg = _make_mock_cg(run_process_return_value=version_result)

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        # Seed a stale error from a prior failed attempt.
        service._install_error[Dependency.CLAUDE] = "Download failed: boom"

        with (
            patch("httpx.get", return_value=mock_manifest_response),
            patch("httpx.stream", return_value=mock_stream_context),
        ):
            result = service.install_managed(Dependency.CLAUDE)
            assert result.success is True
            _wait_for_install_complete(service)

        assert service._install_error.get(Dependency.CLAUDE) is None

    @patch("sculptor.services.managed_tools._current_claude_platform_key", return_value="darwin-arm64")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_per_tool_install_errors_do_not_clobber(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A pi install error and a Claude install error are surfaced independently per-tool."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config(claude_binary_mode="MANAGED")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            # Two tools failing independently must each keep their own error;
            # a single shared field would let the second overwrite the first.
            with service._progress_lock:
                service._install_error[Dependency.CLAUDE] = "claude download failed"
                service._install_error[Dependency.PI] = "pi download failed"
            status = service.get_status()

        assert status.claude.install_error == "claude download failed"
        assert status.pi.install_error == "pi download failed"
        # Errors live per-tool, never on a top-level status field.
        assert not hasattr(status, "install_error")


_PI_RECOMMENDED = PI_VERSION_RANGE.recommended_version


def _make_user_config_with_pi(pi_path: str = "pi") -> UserConfig:
    return UserConfig(
        user_email="test@example.com",
        user_id="user-1",
        organization_id="org-1",
        instance_id="inst-1",
        dependency_paths=DependencyPaths(claude="MANAGED", pi=pi_path),
    )


def _make_managed_config(claude: str, pi: str, enable_multi_harness: bool = False) -> UserConfig:
    """A UserConfig with explicit claude + pi binary-mode values.

    ``enable_multi_harness`` gates pi auto-install on startup and defaults to off,
    matching the product default: a Claude-only user never auto-downloads pi.
    """
    return UserConfig(
        user_email="test@example.com",
        user_id="user-1",
        organization_id="org-1",
        instance_id="inst-1",
        dependency_paths=DependencyPaths(claude=claude, pi=pi),
        enable_multi_harness=enable_multi_harness,
    )


def _auto_install_spawn_args(mock_cg: MagicMock) -> list[tuple[Dependency, ...]]:
    """The ``(tool,)`` args of every startup auto-install ``start_new_thread`` call."""
    return [
        c.kwargs["args"]
        for c in mock_cg.start_new_thread.call_args_list
        if c.kwargs.get("name") == "dependency-management-auto-install"
    ]


class TestParsePiDependencyConfig:
    """The unified _parse_dependency_config applied to pi's field; there is no migration."""

    def test_default_unset_is_managed(self) -> None:
        # A fresh config with no pi value defaults to MANAGED (same grammar as claude).
        assert DependencyPaths().pi == "MANAGED"
        assert _parse_dependency_config(DependencyPaths().pi) == (BinaryMode.MANAGED, None)

    def test_managed_keyword(self) -> None:
        assert _parse_dependency_config("MANAGED") == (BinaryMode.MANAGED, None)

    def test_custom_keyword(self) -> None:
        assert _parse_dependency_config("CUSTOM") == (BinaryMode.CUSTOM, None)

    def test_absolute_path_is_custom(self) -> None:
        assert _parse_dependency_config("/abs/path/pi") == (BinaryMode.CUSTOM, "/abs/path/pi")

    def test_persisted_bare_pi_stays_custom(self) -> None:
        # REQ-MODE-4: no migration validator, so the old default "pi" stays CUSTOM
        # (resolved via PATH), never reinterpreted as MANAGED.
        assert _parse_dependency_config("pi") == (BinaryMode.CUSTOM, "pi")


class TestParsePiVersion:
    def test_parses_well_formed_output(self) -> None:
        assert parse_pi_version("pi 0.76.0") == "0.76.0"

    def test_parses_pre_release_suffix(self) -> None:
        assert parse_pi_version("pi 0.76.0-rc.1") == "0.76.0-rc.1"

    def test_returns_none_on_unparseable_input(self) -> None:
        assert parse_pi_version("not a version") is None


class TestResolvePiPath:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/local/bin/pi")
    def test_bare_command_resolves_via_path(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("pi")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.PI)

        assert result == "/usr/local/bin/pi"
        mock_which.assert_called_once_with("pi")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/opt/pi")
    def test_absolute_path_resolved(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("/opt/pi")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.PI)

        assert result == "/opt/pi"
        mock_which.assert_called_once_with("/opt/pi")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    def test_empty_value_returns_none(self, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.PI)

        assert result is None

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    def test_invalid_value_returns_none(self, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("path with spaces")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.PI)

        assert result is None

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_managed_mode_returns_staged_pi_binary(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """MANAGED pi resolves to the staged ``…/version-<v>/pi/pi`` (not PATH)."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config_with_pi("MANAGED")

        version_dir = tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}" / "pi"
        version_dir.mkdir(parents=True)
        (version_dir / "pi").touch()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.PI)

        assert result == str(version_dir / "pi")

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_managed_mode_with_no_install_returns_none(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config_with_pi("MANAGED")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.resolve_binary_path(Dependency.PI)

        assert result is None


class TestPiVersionRange:
    def test_recommended_in_range(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range(_PI_RECOMMENDED, Dependency.PI) is True

    def test_other_version_out_of_range(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("0.77.0", Dependency.PI) is False
            assert service.is_version_in_range("0.75.0", Dependency.PI) is False

    def test_invalid_version(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.is_version_in_range("not-a-version", Dependency.PI) is False


class TestPiCheckInstalled:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/pi")
    def test_installed_at_pinned_version(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("pi")

        version_result = FinishedProcess(
            stdout=f"pi {_PI_RECOMMENDED}",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )
        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.return_value = version_result

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        result = service.check_installed(Dependency.PI)

        assert result.installed is True
        assert result.version == _PI_RECOMMENDED
        assert result.path == "/usr/bin/pi"

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value=None)
    def test_binary_missing(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("pi")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.check_installed(Dependency.PI)

        assert result.installed is False

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/pi")
    def test_extracts_version_from_stderr_only_emission(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        """Real pi emits --version to stderr; check_installed must read both channels."""
        mock_config.return_value = _make_user_config_with_pi("pi")

        version_result = FinishedProcess(
            stdout="",
            stderr=f"{_PI_RECOMMENDED}\n",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )
        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.return_value = version_result

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        result = service.check_installed(Dependency.PI)

        assert result.installed is True
        assert result.version == _PI_RECOMMENDED
        assert result.path == "/usr/bin/pi"


class TestPiGetStatus:
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/pi")
    def test_status_reports_pi_in_range(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("pi")

        pi_version_result = FinishedProcess(
            stdout=f"pi {_PI_RECOMMENDED}",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )

        mock_cg = MagicMock()
        # git, claude (managed dir empty → installed=False, no subprocess), pi
        mock_cg.run_process_to_completion.return_value = pi_version_result

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        status = service.get_status()

        assert status.pi.installed is True
        assert status.pi.version == _PI_RECOMMENDED
        assert status.pi.is_version_in_range is True
        assert status.pi.version_range is not None
        assert status.pi.version_range.recommended_version == _PI_RECOMMENDED
        # Pi does not surface a CLI auth model.
        assert status.pi.is_authenticated is None

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("shutil.which", return_value="/usr/bin/pi")
    def test_status_reports_out_of_range(self, mock_which: MagicMock, mock_config: MagicMock) -> None:
        mock_config.return_value = _make_user_config_with_pi("pi")

        old_pi_version_result = FinishedProcess(
            stdout="pi 0.50.0",
            stderr="",
            returncode=0,
            command=("test",),
            is_output_already_logged=False,
        )

        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.return_value = old_pi_version_result

        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        status = service.get_status()

        assert status.pi.installed is True
        assert status.pi.version == "0.50.0"
        assert status.pi.is_version_in_range is False


class TestPiInstallManaged:
    """install_managed(PI) now runs the shared managed orchestrator (was deferred)."""

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_install_managed_starts_managed_flow(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """install_managed(PI) downloads/verifies/stages the pinned binary (not 'not supported')."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config_with_pi("MANAGED")
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        tar_bytes = _make_pi_tarball()
        pin = _pi_pin_with_sha(hashlib.sha256(tar_bytes).hexdigest())
        version_result = FinishedProcess(
            stdout="", stderr=_PI_RECOMMENDED, returncode=0, command=("test",), is_output_already_logged=False
        )
        mock_cg = _make_mock_cg(run_process_return_value=version_result)
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("sculptor.services.managed_tools.PI_PIN", pin),
            patch("httpx.stream", return_value=_pi_stream_context_for(tar_bytes)),
        ):
            result = service.install_managed(Dependency.PI)
            assert result.success is True
            assert result.error is None
            _wait_for_install_complete(service, tool=Dependency.PI)

        staged_binary = tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}" / "pi" / "pi"
        assert staged_binary.is_file()
        assert service._install_error.get(Dependency.PI) is None

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_install_managed_checksum_failure_surfaces_on_pi_status(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A failed managed pi install surfaces its error on status.pi.install_error (02_01)."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config_with_pi("MANAGED")
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        tar_bytes = _make_pi_tarball()
        pin = _pi_pin_with_sha("0" * 64)  # the pin advertises a checksum the bytes won't match
        # A benign --version result keeps get_status()'s git probe from choking on a
        # bare MagicMock; the failed install aborts before any binary --version itself.
        benign = FinishedProcess(stdout="", stderr="", returncode=0, command=("test",), is_output_already_logged=False)
        mock_cg = _make_mock_cg(run_process_return_value=benign)
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("sculptor.services.managed_tools.PI_PIN", pin),
            patch("httpx.stream", return_value=_pi_stream_context_for(tar_bytes)),
        ):
            result = service.install_managed(Dependency.PI)
            assert result.success is True  # returns after spawning; the failure is async
            _wait_for_install_complete(service, tool=Dependency.PI)
            status = service.get_status()

        assert status.pi.install_error is not None
        assert "checksum" in status.pi.install_error.lower()
        # The failure is isolated to pi — Claude carries no error.
        assert status.claude.install_error is None
        # Nothing was activated.
        assert not (tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}").exists()


class TestPiAuth:
    def test_check_authenticated_returns_none(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            assert service.check_authenticated(Dependency.PI) is None

    def test_run_auth_login_returns_not_supported(self) -> None:
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.run_auth_login(Dependency.PI)

        assert result.success is False
        assert result.error is not None
        assert "not supported" in result.error.lower()


def _make_pi_tarball(version: str = _PI_RECOMMENDED) -> bytes:
    """A minimal pi artifact: a ``pi/`` tree with the executable entrypoint at ``pi/pi``."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        entrypoint = f"#!/bin/sh\necho {version} 1>&2\n".encode()
        entry_info = tarfile.TarInfo(name="pi/pi")
        entry_info.size = len(entrypoint)
        entry_info.mode = 0o755
        tar.addfile(entry_info, io.BytesIO(entrypoint))
        sibling = b"theme-data"
        sibling_info = tarfile.TarInfo(name="pi/assets/native/node_modules/theme/index.js")
        sibling_info.size = len(sibling)
        tar.addfile(sibling_info, io.BytesIO(sibling))
    return buffer.getvalue()


def _pi_stream_context_for(tar_bytes: bytes) -> MagicMock:
    """A mock ``httpx.stream`` context that yields *tar_bytes* as the download body."""
    context = MagicMock()
    stream = MagicMock()
    stream.headers = {"content-length": str(len(tar_bytes))}
    stream.iter_bytes.return_value = [tar_bytes]
    stream.raise_for_status.return_value = None
    context.__enter__ = MagicMock(return_value=stream)
    context.__exit__ = MagicMock(return_value=False)
    return context


def _pi_pin_with_sha(sha256: str, version: str = _PI_RECOMMENDED) -> PiPin:
    """A PiPin covering all three platforms with the given checksum."""
    return PiPin(
        version=version,
        platforms={
            "darwin-arm64": PlatformPin(asset="pi-darwin-arm64.tar.gz", sha256=sha256),
            "darwin-x64": PlatformPin(asset="pi-darwin-x64.tar.gz", sha256=sha256),
            "linux-x64": PlatformPin(asset="pi-linux-x64.tar.gz", sha256=sha256),
        },
    )


class TestPiManagedInstallOrchestrator:
    """Drives the generic download/verify/stage orchestrator directly with PiManagedTool.

    Exercises the shared flow at the orchestrator level; the install_managed
    entrypoint that managed pi installs through is covered by its own tests
    (``TestPiInstallManaged``).
    """

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_install_success_stages_versioned_pi_binary(
        self,
        mock_folder: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        tar_bytes = _make_pi_tarball()
        pin = _pi_pin_with_sha(hashlib.sha256(tar_bytes).hexdigest())
        version_result = FinishedProcess(
            stdout="", stderr=_PI_RECOMMENDED, returncode=0, command=("test",), is_output_already_logged=False
        )
        mock_cg = _make_mock_cg(run_process_return_value=version_result)
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("sculptor.services.managed_tools.PI_PIN", pin),
            patch("httpx.stream", return_value=_pi_stream_context_for(tar_bytes)),
        ):
            result = service._download_verify_stage(PiManagedTool(), None)

        assert result.success is True
        assert result.version == _PI_RECOMMENDED
        staged_binary = tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}" / "pi" / "pi"
        assert staged_binary.is_file()
        assert result.path == str(staged_binary)
        # No temp dirs left behind on success.
        pi_dir = tmp_path / "dependencies" / "pi"
        assert [d for d in pi_dir.iterdir() if d.name.startswith("tmp-")] == []

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_download_follows_redirects(
        self,
        mock_folder: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        """The download must follow redirects: GitHub Releases URLs 302 to a CDN asset."""
        mock_folder.return_value = tmp_path
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        tar_bytes = _make_pi_tarball()
        pin = _pi_pin_with_sha(hashlib.sha256(tar_bytes).hexdigest())
        version_result = FinishedProcess(
            stdout="", stderr=_PI_RECOMMENDED, returncode=0, command=("test",), is_output_already_logged=False
        )
        mock_cg = _make_mock_cg(run_process_return_value=version_result)
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("sculptor.services.managed_tools.PI_PIN", pin),
            patch("httpx.stream", return_value=_pi_stream_context_for(tar_bytes)) as mock_stream,
        ):
            result = service._download_verify_stage(PiManagedTool(), None)

        assert result.success is True
        assert mock_stream.call_args.kwargs.get("follow_redirects") is True

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_checksum_mismatch_aborts_without_activation(
        self,
        mock_folder: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        tar_bytes = _make_pi_tarball()
        # The pin advertises a checksum the streamed bytes will not match.
        pin = _pi_pin_with_sha("0" * 64)
        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("sculptor.services.managed_tools.PI_PIN", pin),
            patch("httpx.stream", return_value=_pi_stream_context_for(tar_bytes)),
        ):
            result = service._download_verify_stage(PiManagedTool(), None)

        assert result.success is False
        assert result.error is not None
        assert "checksum" in result.error.lower()
        # No version dir was activated and the staged binary was never run.
        assert not (tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}").exists()
        mock_cg.run_process_to_completion.assert_not_called()
        # The temp dir was cleaned up.
        pi_dir = tmp_path / "dependencies" / "pi"
        if pi_dir.exists():
            assert [d for d in pi_dir.iterdir() if d.name.startswith("tmp-")] == []

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_unsupported_platform_returns_structured_failure(
        self,
        mock_folder: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_sys.platform = "win32"
        mock_platform.machine.return_value = "AMD64"

        mock_cg = _make_mock_cg()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        result = service._download_verify_stage(PiManagedTool(), None)

        assert result.success is False
        assert result.error is not None
        # Resolution failed before any download or binary execution.
        mock_cg.run_process_to_completion.assert_not_called()
        assert not (tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}").exists()

    @patch("sculptor.services.managed_tools.platform")
    @patch("sculptor.services.managed_tools.sys")
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_retention_keeps_only_the_newest_pi_version(
        self,
        mock_folder: MagicMock,
        mock_config: MagicMock,
        mock_sys: MagicMock,
        mock_platform: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_folder.return_value = tmp_path
        # Empty pi path → resolve_binary_path(PI) is None, so cleanup protects nothing.
        mock_config.return_value = _make_user_config_with_pi("")
        mock_sys.platform = "darwin"
        mock_platform.machine.return_value = "arm64"

        # Seed an older managed pi version that retention=1 must prune.
        pi_dir = tmp_path / "dependencies" / "pi"
        old_version_dir = pi_dir / "version-0.77.0" / "pi"
        old_version_dir.mkdir(parents=True)
        (old_version_dir / "pi").touch()

        tar_bytes = _make_pi_tarball()
        pin = _pi_pin_with_sha(hashlib.sha256(tar_bytes).hexdigest())
        version_result = FinishedProcess(
            stdout="", stderr=_PI_RECOMMENDED, returncode=0, command=("test",), is_output_already_logged=False
        )
        mock_cg = _make_mock_cg(run_process_return_value=version_result)
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        with (
            patch("sculptor.services.managed_tools.PI_PIN", pin),
            patch("httpx.stream", return_value=_pi_stream_context_for(tar_bytes)),
        ):
            result = service._download_verify_stage(PiManagedTool(), None)

        assert result.success is True
        remaining = sorted(d.name for d in pi_dir.iterdir() if d.is_dir() and d.name.startswith("version-"))
        assert remaining == [f"version-{_PI_RECOMMENDED}"]


class TestFindManagedBinary:
    """_find_managed_binary is generalized per-tool; Claude resolution is unchanged."""

    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_claude_prefers_recommended_over_higher_version(self, mock_folder: MagicMock, tmp_path: Path) -> None:
        """Regression: Claude still prefers the recommended version, then highest, at ``claude``."""
        mock_folder.return_value = tmp_path
        claude_dir = tmp_path / "dependencies" / "claude"
        recommended_dir = claude_dir / f"version-{_RECOMMENDED}"
        recommended_dir.mkdir(parents=True)
        (recommended_dir / "claude").touch()
        # A strictly-higher version is present but must NOT win over the recommended one.
        higher_dir = claude_dir / "version-2.99.0"
        higher_dir.mkdir(parents=True)
        (higher_dir / "claude").touch()

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        assert service._find_managed_binary(Dependency.CLAUDE) == str(recommended_dir / "claude")

    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_claude_falls_back_to_highest_version(self, mock_folder: MagicMock, tmp_path: Path) -> None:
        """Regression: with no recommended dir, Claude falls back to the highest installed."""
        mock_folder.return_value = tmp_path
        claude_dir = tmp_path / "dependencies" / "claude"
        for v in ("2.1.100", "2.1.130"):
            d = claude_dir / f"version-{v}"
            d.mkdir(parents=True)
            (d / "claude").touch()

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        assert service._find_managed_binary(Dependency.CLAUDE) == str(claude_dir / "version-2.1.130" / "claude")

    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_pi_uses_pi_subpath_and_pinned_version(self, mock_folder: MagicMock, tmp_path: Path) -> None:
        """pi resolves the pinned version at the ``pi/pi`` sub-path (whole-tree layout)."""
        mock_folder.return_value = tmp_path
        version_dir = tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}" / "pi"
        version_dir.mkdir(parents=True)
        (version_dir / "pi").touch()

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        assert service._find_managed_binary(Dependency.PI) == str(version_dir / "pi")


class TestGetManagedVersion:
    """_get_managed_version accepts a tool; the no-arg default stays Claude."""

    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_claude_default_and_explicit_report_highest(self, mock_folder: MagicMock, tmp_path: Path) -> None:
        """Regression: the no-arg default reports Claude's highest installed version."""
        mock_folder.return_value = tmp_path
        claude_dir = tmp_path / "dependencies" / "claude"
        for v in ("2.1.156", "2.1.200"):
            (claude_dir / f"version-{v}").mkdir(parents=True)

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        assert service._get_managed_version() == "2.1.200"
        assert service._get_managed_version(Dependency.CLAUDE) == "2.1.200"

    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_pi_reports_highest(self, mock_folder: MagicMock, tmp_path: Path) -> None:
        mock_folder.return_value = tmp_path
        pi_dir = tmp_path / "dependencies" / "pi"
        (pi_dir / f"version-{_PI_RECOMMENDED}").mkdir(parents=True)

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        assert service._get_managed_version(Dependency.PI) == _PI_RECOMMENDED


class TestCleanupStaleStatePi:
    """_cleanup_stale_state now also prunes pi (retention=1) on startup."""

    @patch("shutil.which", return_value=None)
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_cleans_pi_temp_and_applies_retention_one(
        self, mock_folder: MagicMock, mock_config: MagicMock, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_folder.return_value = tmp_path
        # CUSTOM/PATH modes so start()'s auto-install loop never spawns a real download.
        mock_config.return_value = _make_managed_config(claude="claude", pi="pi")

        pi_dir = tmp_path / "dependencies" / "pi"
        pi_dir.mkdir(parents=True)
        (pi_dir / "tmp-stale").mkdir()
        # Two managed pi versions; retention=1 must prune the older one.
        for v in ("0.77.0", _PI_RECOMMENDED):
            binary_dir = pi_dir / f"version-{v}" / "pi"
            binary_dir.mkdir(parents=True)
            (binary_dir / "pi").touch()

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            service.start()

        assert not (pi_dir / "tmp-stale").exists()
        remaining = sorted(d.name for d in pi_dir.iterdir() if d.is_dir() and d.name.startswith("version-"))
        assert remaining == [f"version-{_PI_RECOMMENDED}"]


class TestCheckInstalledConcurrently:
    """_check_installed_concurrently probes several tools' --version in parallel."""

    def test_probes_run_in_parallel_not_sequentially(self) -> None:
        """Each probe blocks on a shared barrier that only releases once all probes arrive,
        so this passes only if they run concurrently; a sequential probe would time out.
        """
        tools = (Dependency.CLAUDE, Dependency.PI)
        barrier = threading.Barrier(len(tools), timeout=5.0)

        def _barrier_probe(tool: Dependency) -> DependencyCheckResult:
            barrier.wait()
            return DependencyCheckResult(installed=True, path="/x", version="1.0.0")

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            # Patch the class, not the instance — patch.object can't cleanly tear down a pydantic-model attr.
            with patch.object(DependencyManagementService, "check_installed", side_effect=_barrier_probe):
                results = service._check_installed_concurrently(tools)

        assert set(results) == set(tools)
        assert all(result.installed for result in results.values())

    def test_returns_each_tools_own_check_result(self) -> None:
        """The returned mapping pairs each tool with the result of its own probe."""
        per_tool = {
            Dependency.CLAUDE: DependencyCheckResult(installed=True, version="2.1.156"),
            Dependency.PI: DependencyCheckResult(installed=False),
        }

        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            with patch.object(DependencyManagementService, "check_installed", side_effect=lambda tool: per_tool[tool]):
                results = service._check_installed_concurrently(tuple(per_tool))

        assert results == per_tool


class TestAutoInstallLoop:
    """_auto_install_if_needed loops over managed tools (Claude + pi).

    pi auto-install is additionally gated on the ``enable_multi_harness`` experiment:
    a flag-off user (the default) never auto-downloads pi, while Claude — which is not
    part of the experiment — auto-installs whenever it is MANAGED and missing. A manual
    install via ``install_managed`` is never gated (see TestPiInstallManaged).
    """

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_pi_managed_and_missing_is_auto_installed_when_multi_harness_enabled(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """pi MANAGED + missing + flag on auto-installs on startup; Claude (CUSTOM) does not."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_managed_config(claude="claude", pi="MANAGED", enable_multi_harness=True)
        mock_cg = MagicMock()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service._auto_install_if_needed()

        assert _auto_install_spawn_args(mock_cg) == [(Dependency.PI,)]

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_pi_managed_and_missing_is_not_auto_installed_when_multi_harness_disabled(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """pi MANAGED + missing but flag off must NOT auto-download pi — the default for a Claude-only user."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_managed_config(claude="claude", pi="MANAGED", enable_multi_harness=False)
        mock_cg = MagicMock()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service._auto_install_if_needed()

        assert _auto_install_spawn_args(mock_cg) == []

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_claude_managed_and_missing_is_auto_installed(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Regression: Claude still auto-installs when MANAGED + missing; pi (CUSTOM) does not."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_managed_config(claude="MANAGED", pi="pi")
        mock_cg = MagicMock()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service._auto_install_if_needed()

        assert _auto_install_spawn_args(mock_cg) == [(Dependency.CLAUDE,)]

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_claude_auto_installs_while_pi_is_gated_off(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Both MANAGED + missing but flag off: Claude installs, pi is skipped — the gate is pi-only."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_managed_config(claude="MANAGED", pi="MANAGED", enable_multi_harness=False)
        mock_cg = MagicMock()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service._auto_install_if_needed()

        assert _auto_install_spawn_args(mock_cg) == [(Dependency.CLAUDE,)]

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_both_auto_install_when_multi_harness_enabled(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """Both MANAGED + missing + flag on: Claude and pi both auto-install, in registry order."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_managed_config(claude="MANAGED", pi="MANAGED", enable_multi_harness=True)
        mock_cg = MagicMock()
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service._auto_install_if_needed()

        assert _auto_install_spawn_args(mock_cg) == [(Dependency.CLAUDE,), (Dependency.PI,)]

    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_pi_managed_and_in_range_is_not_auto_installed(
        self, mock_folder: MagicMock, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        """An already-installed, in-range managed pi is not re-installed (flag on so the gate is open)."""
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_managed_config(claude="claude", pi="MANAGED", enable_multi_harness=True)

        # Stage the pinned pi so check_installed(PI) reports installed + in range.
        version_dir = tmp_path / "dependencies" / "pi" / f"version-{_PI_RECOMMENDED}" / "pi"
        version_dir.mkdir(parents=True)
        (version_dir / "pi").touch()

        mock_cg = MagicMock()
        mock_cg.run_process_to_completion.return_value = FinishedProcess(
            stdout="", stderr=_PI_RECOMMENDED, returncode=0, command=("test",), is_output_already_logged=False
        )
        service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

        service._auto_install_if_needed()

        assert _auto_install_spawn_args(mock_cg) == []


class TestPiStatusMode:
    """status.pi.mode reflects the parsed pi binary mode."""

    @patch("shutil.which", return_value=None)
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_managed_mode_surfaced(
        self, mock_folder: MagicMock, mock_config: MagicMock, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_folder.return_value = tmp_path
        mock_config.return_value = _make_user_config_with_pi("MANAGED")

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        status = service.get_status()

        assert status.pi.mode == BinaryMode.MANAGED

    @patch("shutil.which", return_value=None)
    @patch("sculptor.services.dependency_management_service.get_user_config_instance")
    @patch("sculptor.services.dependency_management_service.get_internal_folder")
    def test_custom_mode_surfaced(
        self, mock_folder: MagicMock, mock_config: MagicMock, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_folder.return_value = tmp_path
        # The persisted bare "pi" parses as CUSTOM (no migration).
        mock_config.return_value = _make_user_config_with_pi("pi")

        service = DependencyManagementService.model_construct(concurrency_group=MagicMock())
        status = service.get_status()

        assert status.pi.mode == BinaryMode.CUSTOM


class TestInstallManagedRegistryDispatch:
    """install_managed routes purely through the ManagedTool registry — no per-tool branch (REQ-SVC-1)."""

    def test_install_managed_has_no_per_tool_special_casing(self) -> None:
        """The install entrypoint must not branch on the specific tool (no match / if tool ==)."""
        source = inspect.getsource(DependencyManagementService.install_managed)
        assert "match tool" not in source
        assert "if tool ==" not in source
        assert "Dependency.CLAUDE" not in source
        assert "Dependency.PI" not in source

    def test_claude_and_pi_both_resolve_through_the_registry(self) -> None:
        """Both managed tools have a conformer the shared install path routes through."""
        assert get_managed_tool(Dependency.CLAUDE) is not None
        assert get_managed_tool(Dependency.PI) is not None

    def test_unmanaged_git_is_reported_not_supported(self) -> None:
        """git has no conformer, so install_managed reports it unsupported instead of installing."""
        assert get_managed_tool(Dependency.GIT) is None
        with ConcurrencyGroup(name="test") as cg:
            service = DependencyManagementService(concurrency_group=cg)
            result = service.install_managed(Dependency.GIT)

        assert result.success is False
        assert "not supported" in (result.error or "").lower()
