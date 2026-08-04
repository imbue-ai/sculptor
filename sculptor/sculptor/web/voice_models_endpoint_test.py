"""Tests for the voice-models serving endpoint and its install trigger.

Covers GET /api/v1/voice-models/{path} (allowlist, 404-when-not-installed,
ETag/304 caching) and the VOICE_MODELS branch of POST /api/v1/dependencies/install.
No test reaches the network.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.dependency_management_service import InstallResult
from sculptor.services.voice_models import VOICE_MODELS_PIN
from sculptor.services.voice_models import find_voice_model_file

_VAD_SERVE_PATH = "vad/silero_vad_v5.onnx"
_TOKENIZER_SERVE_PATH = "onnx-community/moonshine-base-ONNX/resolve/main/tokenizer.json"


@pytest.fixture
def voice_models_version_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the service's managed-artifact storage at a temp dir and return the bundle's version dir."""
    monkeypatch.setattr(
        "sculptor.services.dependency_management_service.get_internal_folder",
        lambda: tmp_path,
    )
    return tmp_path / "dependencies" / "voice_models" / f"version-{VOICE_MODELS_PIN.version}"


def _install_file(version_dir: Path, serve_path: str, content: bytes) -> None:
    file_path = version_dir / serve_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)


def test_get_voice_model_file_rejects_paths_outside_the_pinned_allowlist(
    client: TestClient, voice_models_version_dir: Path
) -> None:
    _install_file(voice_models_version_dir, _VAD_SERVE_PATH, b"model-bytes")

    for bad_path in (
        "onnx-community/moonshine-base-ONNX/resolve/main/README.md",
        "vad/other.onnx",
        "etc/passwd",
        "vad/%2E%2E/secret",
    ):
        response = client.get(f"/api/v1/voice-models/{bad_path}")
        assert response.status_code == 404, bad_path


def test_get_voice_model_file_returns_404_when_bundle_not_installed(
    client: TestClient, voice_models_version_dir: Path
) -> None:
    response = client.get(f"/api/v1/voice-models/{_VAD_SERVE_PATH}")
    assert response.status_code == 404


def test_get_voice_model_file_serves_content_with_etag_and_cache_headers(
    client: TestClient, voice_models_version_dir: Path
) -> None:
    content = b"vad-model-bytes"
    _install_file(voice_models_version_dir, _VAD_SERVE_PATH, content)
    pinned = find_voice_model_file(_VAD_SERVE_PATH)
    assert pinned is not None

    response = client.get(f"/api/v1/voice-models/{_VAD_SERVE_PATH}")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["etag"] == f'"{pinned.sha256}"'
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert response.headers["content-type"] == "application/octet-stream"


def test_get_voice_model_file_serves_json_files_with_json_media_type(
    client: TestClient, voice_models_version_dir: Path
) -> None:
    _install_file(voice_models_version_dir, _TOKENIZER_SERVE_PATH, b"{}")

    response = client.get(f"/api/v1/voice-models/{_TOKENIZER_SERVE_PATH}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


def test_get_voice_model_file_honors_if_none_match_with_304(
    client: TestClient, voice_models_version_dir: Path
) -> None:
    _install_file(voice_models_version_dir, _VAD_SERVE_PATH, b"model-bytes")
    pinned = find_voice_model_file(_VAD_SERVE_PATH)
    assert pinned is not None
    etag = f'"{pinned.sha256}"'

    for matching_header in (etag, f"W/{etag}", f'"other-etag", {etag}', "*"):
        response = client.get(
            f"/api/v1/voice-models/{_VAD_SERVE_PATH}",
            headers={"If-None-Match": matching_header},
        )
        assert response.status_code == 304, matching_header
        assert response.content == b""
        assert response.headers["etag"] == etag

    mismatch = client.get(
        f"/api/v1/voice-models/{_VAD_SERVE_PATH}",
        headers={"If-None-Match": '"some-stale-etag"'},
    )
    assert mismatch.status_code == 200
    assert mismatch.content == b"model-bytes"


def test_install_endpoint_accepts_voice_models_tool(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    install_calls: list[str] = []

    def fake_install(self: DependencyManagementService) -> InstallResult:
        install_calls.append("voice_models")
        return InstallResult(success=True)

    monkeypatch.setattr(DependencyManagementService, "install_voice_models", fake_install)

    response = client.post("/api/v1/dependencies/install", params={"tool": "VOICE_MODELS"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert install_calls == ["voice_models"]


def test_install_endpoint_still_rejects_unknown_tools(client: TestClient) -> None:
    response = client.post("/api/v1/dependencies/install", params={"tool": "NOT_A_TOOL"})
    assert response.status_code == 400
