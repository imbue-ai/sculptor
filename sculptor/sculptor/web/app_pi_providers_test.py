"""Tests for GET /api/v1/pi/providers/authenticated: the global read of the pi
provider catalog crossed with authentication status (auth.json + env detection).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from sculptor.agents.pi_agent.provider_catalog import get_provider_catalog


def _clear_all_catalog_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for entry in get_provider_catalog():
        for env_var_name in entry.env_var_names:
            monkeypatch.delenv(env_var_name, raising=False)


def test_authenticated_providers_reports_auth_json_membership(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(json.dumps({"anthropic": {"key": "x"}}), encoding="utf-8")

    response = client.get("/api/v1/pi/providers/authenticated")
    assert response.status_code == 200

    providers = {entry["providerId"]: entry for entry in response.json()["providers"]}
    assert providers["anthropic"]["inAuthJson"] is True
    assert providers["openai"]["inAuthJson"] is False


def test_authenticated_providers_reports_env_detection(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "x")

    response = client.get("/api/v1/pi/providers/authenticated")
    assert response.status_code == 200

    providers = {entry["providerId"]: entry for entry in response.json()["providers"]}
    assert providers["openai"]["envDetected"] is True
    assert providers["anthropic"]["envDetected"] is False


def test_authenticated_providers_cover_full_catalog_with_groups(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))

    response = client.get("/api/v1/pi/providers/authenticated")
    assert response.status_code == 200

    providers = response.json()["providers"]
    returned_ids = [entry["providerId"] for entry in providers]
    catalog_ids = [entry.provider_id for entry in get_provider_catalog()]
    assert returned_ids == catalog_ids

    by_id = {entry["providerId"]: entry for entry in providers}
    assert by_id["amazon-bedrock"]["group"] == "session_only"
    assert by_id["anthropic"]["group"] == "single_key"
    # Only anthropic supports pi's subscription (OAuth) login among catalog providers.
    assert by_id["anthropic"]["supportsSubscription"] is True
    assert by_id["openai"]["supportsSubscription"] is False


def test_paste_key_writes_entry_and_broadcasts(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    broadcast_mock = MagicMock(return_value=0)
    monkeypatch.setattr("sculptor.web.app.broadcast_pi_models_refresh", broadcast_mock)

    response = client.post(
        "/api/v1/pi/providers/paste-key",
        json={"providerId": "openrouter", "keyValue": "sk-or-abc"},
    )
    assert response.status_code == 204

    auth_json = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert auth_json["openrouter"] == {"type": "api_key", "key": "sk-or-abc"}
    broadcast_mock.assert_called_once()


def test_paste_key_rejects_session_only_provider(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    response = client.post(
        "/api/v1/pi/providers/paste-key",
        json={"providerId": "amazon-bedrock", "keyValue": "x"},
    )
    assert response.status_code == 400
    assert not (tmp_path / "auth.json").exists()


def test_paste_key_rejects_unknown_provider(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    response = client.post(
        "/api/v1/pi/providers/paste-key",
        json={"providerId": "does-not-exist", "keyValue": "x"},
    )
    assert response.status_code == 400
