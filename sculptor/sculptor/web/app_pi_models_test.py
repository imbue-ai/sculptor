"""Tests for GET /api/v1/pi/models: the host-side pre-workspace pi catalog probe."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.state.messages import ModelOption

_OPUS = ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Claude Opus 4.8")
_SONNET = ModelOption(provider="anthropic", model_id="claude-sonnet-4-5", display_name="Claude Sonnet 4.5")


def test_pi_models_returns_probed_catalog(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DependencyManagementService, "resolve_binary_path", lambda self, tool: "/bin/pi")
    probe_mock = MagicMock(return_value=([_OPUS, _SONNET], _OPUS))
    monkeypatch.setattr("sculptor.web.app.probe_catalog_on_host", probe_mock)

    response = client.get("/api/v1/pi/models")
    assert response.status_code == 200

    body = response.json()
    assert [model["modelId"] for model in body["availableModels"]] == ["claude-opus-4-8", "claude-sonnet-4-5"]
    assert body["defaultModel"]["modelId"] == "claude-opus-4-8"
    assert body["defaultModel"]["provider"] == "anthropic"
    probe_mock.assert_called_once_with("/bin/pi")


def test_pi_models_returns_empty_catalog_when_binary_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(DependencyManagementService, "resolve_binary_path", lambda self, tool: None)
    probe_mock = MagicMock()
    monkeypatch.setattr("sculptor.web.app.probe_catalog_on_host", probe_mock)

    response = client.get("/api/v1/pi/models")
    assert response.status_code == 200
    assert response.json() == {"availableModels": [], "defaultModel": None}
    probe_mock.assert_not_called()


def test_pi_models_returns_empty_catalog_when_probe_finds_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unauthenticated user (or a best-effort probe failure) yields the designed
    empty catalog — a 200, never an error — driving the shared empty state."""
    monkeypatch.setattr(DependencyManagementService, "resolve_binary_path", lambda self, tool: "/bin/pi")
    monkeypatch.setattr("sculptor.web.app.probe_catalog_on_host", MagicMock(return_value=([], None)))

    response = client.get("/api/v1/pi/models")
    assert response.status_code == 200
    assert response.json() == {"availableModels": [], "defaultModel": None}
