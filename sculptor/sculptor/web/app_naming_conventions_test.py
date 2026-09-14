"""Endpoint tests for reading and writing the naming-convention docs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.database.models import Project
from sculptor.web import app as app_module

_ENDPOINT = "/api/v1/naming-conventions"


def _use_temp_sculptor_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the endpoints' user-tier lookups at a throwaway folder instead of the real Sculptor folder."""
    home = tmp_path / "sculptor_home"
    home.mkdir()
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: home)
    return home


def test_get_lists_the_global_file_and_each_projects_two_files(
    client: TestClient, test_project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _use_temp_sculptor_folder(monkeypatch, tmp_path)
    (home / "naming.md").write_text("global rules", encoding="utf-8")
    shared = test_project.get_local_user_path() / ".sculptor" / "naming.md"
    shared.parent.mkdir(exist_ok=True)
    shared.write_text("shared rules", encoding="utf-8")

    response = client.get(_ENDPOINT)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["globalFile"]["content"] == "global rules"
    assert body["globalFile"]["path"] == str(home / "naming.md")
    assert body["template"].startswith("# Naming conventions")
    [project] = [entry for entry in body["projects"] if entry["projectId"] == str(test_project.object_id)]
    assert project["projectName"] == test_project.name
    assert project["shared"]["content"] == "shared rules"
    assert project["local"]["content"] is None
    assert project["local"]["path"].endswith(".sculptor/naming.local.md")


def test_put_creates_a_project_file(
    client: TestClient, test_project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_temp_sculptor_folder(monkeypatch, tmp_path)

    response = client.put(
        _ENDPOINT, json={"tier": "local", "projectId": str(test_project.object_id), "content": "my overrides\n"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "my overrides\n"
    local = test_project.get_local_user_path() / ".sculptor" / "naming.local.md"
    assert local.read_text(encoding="utf-8") == "my overrides\n"


def test_put_with_blank_content_deletes_the_file(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _use_temp_sculptor_folder(monkeypatch, tmp_path)
    (home / "naming.md").write_text("global rules", encoding="utf-8")

    response = client.put(_ENDPOINT, json={"tier": "user", "content": "   \n"})

    assert response.status_code == 200, response.text
    assert response.json()["content"] is None
    assert not (home / "naming.md").exists()


def test_put_project_tier_requires_a_project(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_temp_sculptor_folder(monkeypatch, tmp_path)

    response = client.put(_ENDPOINT, json={"tier": "project", "content": "x"})

    assert response.status_code == 400, response.text
