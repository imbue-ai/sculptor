"""Tests for the voice-models bundle install flow (multi-file download, aggregate progress).

The download orchestrator is exercised for real with ``httpx`` stubbed per test,
so the module opts out of the conftest guard that otherwise blocks managed
downloads during unit tests. No test reaches the network.
"""

import hashlib
import threading
from collections.abc import Callable
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest

from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.voice_models import VOICE_MODELS_PIN
from sculptor.services.voice_models import VOICE_MODELS_TOOL_NAME
from sculptor.services.voice_models import VoiceModelFile
from sculptor.services.voice_models import VoiceModelsPin

pytestmark = pytest.mark.allow_dependency_downloads


def _make_test_pin() -> tuple[VoiceModelsPin, dict[str, bytes]]:
    """A small three-file bundle pin plus the exact bytes each pinned URL serves."""
    content_by_url = {
        "https://example.invalid/config.json": b'{"model": "test"}',
        "https://example.invalid/encoder.onnx": b"encoder-bytes-payload",
        "https://example.invalid/vad.onnx": b"vad-bytes",
    }
    pin = VoiceModelsPin(
        version="1",
        files=(
            VoiceModelFile(
                serve_path="repo/resolve/main/config.json",
                url="https://example.invalid/config.json",
                sha256=hashlib.sha256(content_by_url["https://example.invalid/config.json"]).hexdigest(),
                size_bytes=len(content_by_url["https://example.invalid/config.json"]),
            ),
            VoiceModelFile(
                serve_path="repo/resolve/main/onnx/encoder.onnx",
                url="https://example.invalid/encoder.onnx",
                sha256=hashlib.sha256(content_by_url["https://example.invalid/encoder.onnx"]).hexdigest(),
                size_bytes=len(content_by_url["https://example.invalid/encoder.onnx"]),
            ),
            VoiceModelFile(
                serve_path="vad/vad.onnx",
                url="https://example.invalid/vad.onnx",
                sha256=hashlib.sha256(content_by_url["https://example.invalid/vad.onnx"]).hexdigest(),
                size_bytes=len(content_by_url["https://example.invalid/vad.onnx"]),
            ),
        ),
    )
    return pin, content_by_url


def _make_stream_factory(
    content_by_url: Mapping[str, bytes],
    chunk_size: int = 4,
    gate: threading.Event | None = None,
) -> Callable[..., MagicMock]:
    """A stand-in for ``httpx.stream`` that serves canned bytes per URL in small chunks."""

    def factory(_method: str, url: str, timeout: float = 300.0, follow_redirects: bool = False) -> MagicMock:
        content = content_by_url[url]
        chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]

        def iter_bytes(chunk_size: int = 65536) -> list[bytes]:
            if gate is not None:
                gate.wait(timeout=10)
            return chunks

        stream = MagicMock()
        stream.headers = {"content-length": str(len(content))}
        stream.raise_for_status.return_value = None
        stream.iter_bytes = iter_bytes
        context = MagicMock()
        context.__enter__ = MagicMock(return_value=stream)
        context.__exit__ = MagicMock(return_value=False)
        return context

    return factory


def _make_mock_cg() -> MagicMock:
    """A MagicMock concurrency group whose start_new_thread actually spawns a daemon thread."""
    mock_cg = MagicMock()
    mock_cg.run_process_to_completion.return_value = FinishedProcess(
        stdout="tool version 1.2.3", stderr="", returncode=0, command=("test",), is_output_already_logged=False
    )

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


def _run_bundle_download(
    service: DependencyManagementService,
    progress_events: list[tuple[int, int | None]] | None = None,
) -> Any:
    events = progress_events if progress_events is not None else []
    return service._download_verify_stage_voice_models(lambda done, total: events.append((done, total)))


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_bundle_install_stages_every_file_at_its_serve_path_and_activates(
    mock_folder: MagicMock, tmp_path: Path, test_root_concurrency_group: Any
) -> None:
    mock_folder.return_value = tmp_path
    pin, content_by_url = _make_test_pin()

    service = DependencyManagementService(concurrency_group=test_root_concurrency_group)
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=_make_stream_factory(content_by_url)),
    ):
        result = _run_bundle_download(service)

    assert result.success is True
    assert result.version == "1"
    version_dir = tmp_path / "dependencies" / "voice_models" / "version-1"
    for file in pin.files:
        assert (version_dir / file.serve_path).read_bytes() == content_by_url[file.url]
    tmp_dirs = [d for d in version_dir.parent.iterdir() if d.name.startswith("tmp-")]
    assert tmp_dirs == []


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_bundle_progress_aggregates_cumulative_bytes_against_pinned_total(
    mock_folder: MagicMock, tmp_path: Path, test_root_concurrency_group: Any
) -> None:
    mock_folder.return_value = tmp_path
    pin, content_by_url = _make_test_pin()
    progress_events: list[tuple[int, int | None]] = []

    service = DependencyManagementService(concurrency_group=test_root_concurrency_group)
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=_make_stream_factory(content_by_url)),
    ):
        result = _run_bundle_download(service, progress_events)

    assert result.success is True
    assert all(total == pin.total_size_bytes for _, total in progress_events)
    cumulative_bytes = [done for done, _ in progress_events]
    assert cumulative_bytes == sorted(cumulative_bytes)
    assert cumulative_bytes[-1] == pin.total_size_bytes


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_bundle_checksum_mismatch_fails_without_activating(
    mock_folder: MagicMock, tmp_path: Path, test_root_concurrency_group: Any
) -> None:
    mock_folder.return_value = tmp_path
    pin, content_by_url = _make_test_pin()
    corrupted = dict(content_by_url)
    corrupted["https://example.invalid/encoder.onnx"] = b"tampered-bytes-payload"

    service = DependencyManagementService(concurrency_group=test_root_concurrency_group)
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=_make_stream_factory(corrupted)),
    ):
        result = _run_bundle_download(service)

    assert result.success is False
    assert "repo/resolve/main/onnx/encoder.onnx" in (result.error or "")
    assert "Checksum mismatch" in (result.error or "")
    bundle_dir = tmp_path / "dependencies" / "voice_models"
    assert not (bundle_dir / "version-1").exists()
    tmp_dirs = [d for d in bundle_dir.iterdir() if d.name.startswith("tmp-")]
    assert tmp_dirs == []


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_bundle_download_http_error_fails_with_download_error(
    mock_folder: MagicMock, tmp_path: Path, test_root_concurrency_group: Any
) -> None:
    mock_folder.return_value = tmp_path
    pin, _ = _make_test_pin()

    service = DependencyManagementService(concurrency_group=test_root_concurrency_group)
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=httpx.HTTPError("Connection failed")),
    ):
        result = _run_bundle_download(service)

    assert result.success is False
    assert "Download failed" in (result.error or "")


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_bundle_install_cancels_at_chunk_boundary_when_stop_requested(
    mock_folder: MagicMock, tmp_path: Path, test_root_concurrency_group: Any
) -> None:
    mock_folder.return_value = tmp_path
    pin, content_by_url = _make_test_pin()

    service = DependencyManagementService(concurrency_group=test_root_concurrency_group)
    service._stop_requested.set()
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=_make_stream_factory(content_by_url)),
    ):
        result = _run_bundle_download(service)

    assert result.success is False
    assert "cancelled" in (result.error or "").lower()
    assert not (tmp_path / "dependencies" / "voice_models" / "version-1").exists()


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_install_voice_models_seeds_aggregate_progress_and_gates_reentry(
    mock_folder: MagicMock, tmp_path: Path
) -> None:
    mock_folder.return_value = tmp_path
    pin, content_by_url = _make_test_pin()
    download_gate = threading.Event()

    mock_cg = _make_mock_cg()
    service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=_make_stream_factory(content_by_url, gate=download_gate)),
    ):
        first = service.install_voice_models()
        assert first.success is True
        assert first.in_progress is False

        # The download thread is blocked on the gate, so the seeded state is stable.
        with service._progress_lock:
            assert service._voice_models_installing is True
            progress = service._voice_models_progress
            assert progress is not None
            assert progress.tool == VOICE_MODELS_TOOL_NAME
            assert progress.bytes_downloaded == 0
            assert progress.total_bytes == pin.total_size_bytes

        second = service.install_voice_models()
        assert second.success is True
        assert second.in_progress is True

        download_gate.set()
        thread = service._voice_models_thread
        assert thread is not None
        thread.join(timeout=10)
        assert not thread.is_alive()

    with service._progress_lock:
        assert service._voice_models_installing is False
        assert service._voice_models_progress is None
        assert service._voice_models_error is None
    with patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin):
        assert service._is_voice_models_installed() is True


def test_install_voice_models_refused_after_stop() -> None:
    mock_cg = _make_mock_cg()
    service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    service.stop()

    result = service.install_voice_models()

    assert result.success is False
    assert "shutting down" in (result.error or "").lower()
    mock_cg.start_new_thread.assert_not_called()


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_background_install_failure_records_install_error(mock_folder: MagicMock, tmp_path: Path) -> None:
    mock_folder.return_value = tmp_path
    pin, _ = _make_test_pin()

    mock_cg = _make_mock_cg()
    service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    with (
        patch("sculptor.services.dependency_management_service.VOICE_MODELS_PIN", pin),
        patch("httpx.stream", side_effect=httpx.HTTPError("Connection failed")),
    ):
        result = service.install_voice_models()
        assert result.success is True

        thread = service._voice_models_thread
        assert thread is not None
        thread.join(timeout=10)

    with service._progress_lock:
        assert service._voice_models_installing is False
        assert "Download failed" in (service._voice_models_error or "")


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_is_voice_models_installed_requires_every_pinned_file(mock_folder: MagicMock, tmp_path: Path) -> None:
    mock_folder.return_value = tmp_path
    version_dir = tmp_path / "dependencies" / "voice_models" / f"version-{VOICE_MODELS_PIN.version}"

    mock_cg = _make_mock_cg()
    service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    assert service._is_voice_models_installed() is False

    # All files but one: still not installed.
    for file in VOICE_MODELS_PIN.files[:-1]:
        path = version_dir / file.serve_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert service._is_voice_models_installed() is False

    last = version_dir / VOICE_MODELS_PIN.files[-1].serve_path
    last.parent.mkdir(parents=True, exist_ok=True)
    last.touch()
    assert service._is_voice_models_installed() is True


@patch("sculptor.services.dependency_management_service.get_internal_folder")
def test_resolve_voice_model_path_rejects_unpinned_paths_and_missing_installs(
    mock_folder: MagicMock, tmp_path: Path
) -> None:
    mock_folder.return_value = tmp_path
    mock_cg = _make_mock_cg()
    service = DependencyManagementService.model_construct(concurrency_group=mock_cg)

    serve_path = "vad/silero_vad_v5.onnx"
    assert service.resolve_voice_model_path("not/pinned.onnx") is None
    # Pinned but not installed yet.
    assert service.resolve_voice_model_path(serve_path) is None

    on_disk = tmp_path / "dependencies" / "voice_models" / f"version-{VOICE_MODELS_PIN.version}" / serve_path
    on_disk.parent.mkdir(parents=True)
    on_disk.write_bytes(b"model-bytes")
    assert service.resolve_voice_model_path(serve_path) == on_disk
