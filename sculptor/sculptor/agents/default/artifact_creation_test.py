"""Unit tests for artifact_creation helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from sculptor.agents.default.artifact_creation import _make_file_artifact
from sculptor.agents.default.artifact_creation import _read_task_list_artifact
from sculptor.agents.default.artifact_creation import should_refresh_task_list
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.interfaces.agents.artifacts import AgentTaskStatus
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment


def _build_env(home: Path, artifacts_dir: Path | None = None) -> AgentExecutionEnvironment:
    """Mock the AgentExecutionEnvironment slice the reader/writer touches.

    The reader resolves the tasks directory via the harness, which only needs
    `get_user_home_directory()`; we mock that so the harness method computes
    `home / .claude / tasks / <session_id>`. write_file / get_artifacts_path
    remain mocked for the _make_file_artifact PLAN-branch test.
    """
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_user_home_directory.return_value = home

    def _write_file(path: str, content: str | bytes, mode: str = "w") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content if isinstance(content, str) else content.decode())

    env.write_file.side_effect = _write_file
    env.get_artifacts_path.return_value = artifacts_dir if artifacts_dir is not None else home / "artifacts"
    return env


def _write_task(tasks_dir: Path, payload: dict) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / f"{payload['id']}.json").write_text(json.dumps(payload))


def _make_env_and_dir(tmp_path: Path) -> tuple[AgentExecutionEnvironment, str, Path]:
    session_id = "00000000-0000-0000-0000-000000000001"
    env = _build_env(tmp_path)
    tasks_dir = tmp_path / ".claude" / "tasks" / session_id
    return env, session_id, tasks_dir


def test_should_refresh_task_list_only_for_task_create_and_update() -> None:
    assert should_refresh_task_list(AgentToolName.TASK_CREATE) is True
    assert should_refresh_task_list(AgentToolName.TASK_UPDATE) is True
    assert should_refresh_task_list(AgentToolName.TASK_LIST) is False
    assert should_refresh_task_list(AgentToolName.TASK_GET) is False
    assert should_refresh_task_list(AgentToolName.BASH) is False
    assert should_refresh_task_list("Bash") is False


def test_read_task_list_artifact_returns_version_2_with_single_task(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(
        tasks_dir,
        {
            "id": "1",
            "subject": "Investigate the bug",
            "description": "Look at it",
            "activeForm": "Investigating the bug",
            "status": "pending",
            "blocks": [],
            "blockedBy": [],
            "owner": None,
            "metadata": {},
        },
    )
    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    assert isinstance(artifact, TaskListArtifact)
    assert artifact.version == 2
    assert len(artifact.tasks) == 1
    task = artifact.tasks[0]
    assert task.id == "1"
    assert task.subject == "Investigate the bug"
    assert task.active_form == "Investigating the bug"
    assert task.status == AgentTaskStatus.PENDING


def test_read_task_list_artifact_preserves_dependency_edges(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(tasks_dir, {"id": "1", "subject": "A", "status": "completed", "blocks": ["3"]})
    _write_task(tasks_dir, {"id": "2", "subject": "B", "status": "completed", "blocks": ["3"]})
    _write_task(
        tasks_dir,
        {"id": "3", "subject": "C", "status": "in_progress", "blockedBy": ["1", "2"]},
    )

    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    by_id = {t.id: t for t in artifact.tasks}
    assert [t.id for t in artifact.tasks] == ["1", "2", "3"]
    assert by_id["1"].blocks == ["3"]
    assert by_id["2"].blocks == ["3"]
    assert by_id["3"].blocked_by == ["1", "2"]


def test_read_task_list_artifact_skips_malformed_json(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(tasks_dir, {"id": "1", "subject": "Good task", "status": "pending"})
    (tasks_dir / "2.json").write_text("not json")
    _write_task(tasks_dir, {"id": "3", "subject": "Another good", "status": "completed"})

    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    ids = [t.id for t in artifact.tasks]
    assert ids == ["1", "3"]


def test_read_task_list_artifact_skips_validation_errors(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(tasks_dir, {"id": "1", "subject": "Good task", "status": "pending"})
    # Missing required subject.
    (tasks_dir / "2.json").write_text(json.dumps({"id": "2", "status": "pending"}))
    _write_task(tasks_dir, {"id": "3", "subject": "Another good", "status": "completed"})

    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    assert [t.id for t in artifact.tasks] == ["1", "3"]


def test_read_task_list_artifact_empty_directory(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    assert artifact.tasks == []


def test_read_task_list_artifact_missing_directory(tmp_path: Path) -> None:
    env, session_id, _ = _make_env_and_dir(tmp_path)
    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    assert artifact.tasks == []


def test_read_task_list_artifact_none_session_id_returns_empty(tmp_path: Path) -> None:
    env, _, _ = _make_env_and_dir(tmp_path)
    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, None)
    assert artifact.tasks == []


def test_read_task_list_artifact_numeric_sort(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(tasks_dir, {"id": "1", "subject": "A", "status": "pending"})
    _write_task(tasks_dir, {"id": "10", "subject": "J", "status": "pending"})
    _write_task(tasks_dir, {"id": "2", "subject": "B", "status": "pending"})

    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    assert [t.id for t in artifact.tasks] == ["1", "2", "10"]


def test_read_task_list_artifact_round_trip_to_v2_json(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(
        tasks_dir,
        {
            "id": "1",
            "subject": "A",
            "status": "pending",
            "blockedBy": ["2"],
        },
    )
    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    raw = artifact.model_dump_json(by_alias=True)
    restored = TaskListArtifact.model_validate_json(raw)
    assert restored == artifact
    assert restored.version == 2


def test_read_task_list_artifact_skips_lock_and_non_json_entries(tmp_path: Path) -> None:
    env, session_id, tasks_dir = _make_env_and_dir(tmp_path)
    _write_task(tasks_dir, {"id": "1", "subject": "A", "status": "pending"})
    (tasks_dir / ".lock").write_text("")
    (tasks_dir / "readme.txt").write_text("notes")

    artifact = _read_task_list_artifact(env, CLAUDE_CODE_HARNESS, session_id)
    assert [t.id for t in artifact.tasks] == ["1"]


def test_make_file_artifact_plan_branch_writes_task_list(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    env = _build_env(tmp_path, artifacts_dir=artifacts_dir)
    session_id = "00000000-0000-0000-0000-000000000099"
    tasks_dir = tmp_path / ".claude" / "tasks" / session_id
    _write_task(tasks_dir, {"id": "1", "subject": "Investigate", "status": "in_progress"})
    _write_task(tasks_dir, {"id": "2", "subject": "Verify", "status": "pending", "blockedBy": ["1"]})

    target = _make_file_artifact(
        artifact_name=ArtifactType.PLAN.value,
        environment=env,
        harness=CLAUDE_CODE_HARNESS,
        session_id=session_id,
    )

    assert target.exists()
    written = json.loads(target.read_text())
    assert written["object_type"] == "TaskListArtifact"
    assert written["version"] == 2
    ids = [t["id"] for t in written["tasks"]]
    assert ids == ["1", "2"]


def test_make_file_artifact_plan_branch_handles_missing_session_id(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    env = _build_env(tmp_path, artifacts_dir=artifacts_dir)
    target = _make_file_artifact(
        artifact_name=ArtifactType.PLAN.value,
        environment=env,
        harness=CLAUDE_CODE_HARNESS,
        session_id=None,
    )
    assert target.exists()
    written = json.loads(target.read_text())
    assert written["object_type"] == "TaskListArtifact"
    assert written["tasks"] == []
