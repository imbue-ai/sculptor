"""Unit tests for the authenticated-set computation: auth.json path resolution,
the best-effort auth.json reader, env detection, the combined set, and the
per-provider status helper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sculptor.agents.pi_agent.authenticated_providers import PiAuthJsonError
from sculptor.agents.pi_agent.authenticated_providers import compute_authenticated_provider_ids
from sculptor.agents.pi_agent.authenticated_providers import detect_env_authenticated_provider_ids
from sculptor.agents.pi_agent.authenticated_providers import get_provider_auth_statuses
from sculptor.agents.pi_agent.authenticated_providers import read_auth_json_provider_ids
from sculptor.agents.pi_agent.authenticated_providers import resolve_pi_auth_json_path
from sculptor.agents.pi_agent.authenticated_providers import write_auth_json_entry
from sculptor.agents.pi_agent.provider_catalog import get_provider_catalog


def test_resolve_path_honors_pi_coding_agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    assert resolve_pi_auth_json_path() == tmp_path / "auth.json"


def test_resolve_path_falls_back_to_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert resolve_pi_auth_json_path() == tmp_path / ".pi" / "agent" / "auth.json"


def test_reader_returns_top_level_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "anthropic": {"type": "api_key", "key": "sk-ant-x"},
                "openai": {"type": "api_key", "key": "sk-x"},
            }
        ),
        encoding="utf-8",
    )
    assert read_auth_json_provider_ids() == {"anthropic", "openai"}


def test_reader_missing_file_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    assert read_auth_json_provider_ids() == set()


def test_reader_malformed_json_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text("{not valid json", encoding="utf-8")
    assert read_auth_json_provider_ids() == set()


def test_reader_non_dict_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(json.dumps(["anthropic"]), encoding="utf-8")
    assert read_auth_json_provider_ids() == set()


def test_reader_presence_not_validity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(json.dumps({"anthropic": {"key": ""}}), encoding="utf-8")
    assert read_auth_json_provider_ids() == {"anthropic"}


def test_env_detection_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert "openai" in detect_env_authenticated_provider_ids()


def test_env_detection_uses_gemini_env_var_for_google(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    detected = detect_env_authenticated_provider_ids()
    assert "google" in detected


def test_env_detection_ignores_empty_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert "openai" not in detect_env_authenticated_provider_ids()


def test_combined_is_union_of_file_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(json.dumps({"anthropic": {"key": "x"}}), encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert compute_authenticated_provider_ids() == {"anthropic", "openai"}


def test_provider_statuses_annotate_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_catalog_env_vars(monkeypatch)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(json.dumps({"anthropic": {"key": "x"}}), encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "x")

    statuses = get_provider_auth_statuses()
    by_id = {status.provider_id: status for status in statuses}

    assert by_id["anthropic"].in_auth_json is True
    assert by_id["anthropic"].env_detected is False
    assert by_id["openai"].in_auth_json is False
    assert by_id["openai"].env_detected is True
    assert by_id["google"].in_auth_json is False
    assert by_id["google"].env_detected is False


def test_provider_statuses_cover_every_entry_once() -> None:
    statuses = get_provider_auth_statuses()
    status_ids = [status.provider_id for status in statuses]
    catalog_ids = [entry.provider_id for entry in get_provider_catalog()]
    assert sorted(status_ids) == sorted(catalog_ids)
    assert len(status_ids) == len(set(status_ids))


def test_write_creates_auth_json_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    write_auth_json_entry("openrouter", "sk-or-123")

    auth_json_path = tmp_path / "auth.json"
    assert json.loads(auth_json_path.read_text(encoding="utf-8")) == {
        "openrouter": {"type": "api_key", "key": "sk-or-123"}
    }
    assert (auth_json_path.stat().st_mode & 0o777) == 0o600


def test_write_merges_and_preserves_other_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text(
        json.dumps({"openai": {"type": "api_key", "key": "sk-x"}, "weird-oauth": {"type": "oauth", "token": "t"}}),
        encoding="utf-8",
    )

    write_auth_json_entry("anthropic", "sk-ant-y")

    data = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert data["openai"] == {"type": "api_key", "key": "sk-x"}
    assert data["weird-oauth"] == {"type": "oauth", "token": "t"}
    assert data["anthropic"] == {"type": "api_key", "key": "sk-ant-y"}


def test_write_stores_env_and_command_values_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    write_auth_json_entry("openai", "$MY_OPENAI_KEY")
    write_auth_json_entry("anthropic", "!op read 'op://vault/key'")

    data = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert data["openai"]["key"] == "$MY_OPENAI_KEY"
    assert data["anthropic"]["key"] == "!op read 'op://vault/key'"


def test_write_raises_on_garbled_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    (tmp_path / "auth.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(PiAuthJsonError):
        write_auth_json_entry("anthropic", "sk-ant-z")
    # The garbled file is left untouched (not clobbered).
    assert (tmp_path / "auth.json").read_text(encoding="utf-8") == "{not valid json"


def _clear_all_catalog_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for entry in get_provider_catalog():
        for env_var_name in entry.env_var_names:
            monkeypatch.delenv(env_var_name, raising=False)
