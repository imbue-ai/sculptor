"""Unit tests for _get_typed_artifact_data dispatch + legacy fallback."""

import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.interfaces.agents.artifacts import AgentTaskStatus
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.agents.artifacts import Task
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.web import app as app_module


def _invoke(monkeypatch: pytest.MonkeyPatch, raw: str) -> object:
    monkeypatch.setattr(app_module, "_get_artifact_data", lambda *args, **kwargs: raw)
    return app_module._get_typed_artifact_data(
        artifact_name=ArtifactType.PLAN.value,
        services=MagicMock(),
        task_id_str="task",
        user_session=MagicMock(),
    )


def test_returns_task_list_artifact_for_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    task = Task(id="1", subject="Investigate", status=AgentTaskStatus.PENDING, blocked_by=["2"])
    artifact = TaskListArtifact(tasks=[task])
    raw = artifact.model_dump_json()

    result = _invoke(monkeypatch, raw)
    assert isinstance(result, TaskListArtifact)
    assert result.version == 2
    assert len(result.tasks) == 1
    assert result.tasks[0].subject == "Investigate"
    assert result.tasks[0].blocked_by == ["2"]


def test_returns_empty_task_list_for_legacy_todo_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    # A pre-cutover artifact on disk written by the deprecated
    # TodoListArtifact path; constructed via the literal JSON shape since the
    # Python class no longer exists.
    raw = json.dumps(
        {
            "object_type": "TodoListArtifact",
            "todos": [{"id": "1", "content": "legacy", "status": "pending"}],
        }
    )

    result = _invoke(monkeypatch, raw)
    assert isinstance(result, TaskListArtifact)
    assert result.version == 2
    assert result.tasks == []


def test_returns_empty_task_list_for_unsupported_version(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps({"object_type": "TaskListArtifact", "version": 1, "tasks": []})

    result = _invoke(monkeypatch, raw)
    assert isinstance(result, TaskListArtifact)
    assert result.version == 2
    assert result.tasks == []


def test_returns_empty_task_list_when_version_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps({"object_type": "TaskListArtifact", "tasks": []})

    result = _invoke(monkeypatch, raw)
    assert isinstance(result, TaskListArtifact)
    assert result.version == 2
    assert result.tasks == []


def test_diff_artifact_still_routes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    diff = DiffArtifact()
    raw = diff.model_dump_json()
    monkeypatch.setattr(app_module, "_get_artifact_data", lambda *args, **kwargs: raw)
    result = app_module._get_typed_artifact_data(
        artifact_name=ArtifactType.DIFF.value,
        services=MagicMock(),
        task_id_str="task",
        user_session=MagicMock(),
    )
    assert isinstance(result, DiffArtifact)


def test_unknown_object_type_still_raises_500(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps({"object_type": "SomeNewArtifact"})
    with expect_exact_logged_errors(["Unknown object_type: {}"]):
        with pytest.raises(HTTPException) as exc:
            _invoke(monkeypatch, raw)
    assert exc.value.status_code == 500
    assert "SomeNewArtifact" in str(exc.value.detail)
