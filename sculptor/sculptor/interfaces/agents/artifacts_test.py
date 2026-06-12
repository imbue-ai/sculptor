import json

from sculptor.interfaces.agents.artifacts import AgentTaskStatus
from sculptor.interfaces.agents.artifacts import Task
from sculptor.interfaces.agents.artifacts import TaskListArtifact


def test_task_defaults() -> None:
    task = Task(id="1", subject="Do the thing", status=AgentTaskStatus.PENDING)
    assert task.description == ""
    assert task.active_form is None
    assert task.blocks == []
    assert task.blocked_by == []
    assert task.owner is None
    assert task.metadata == {}


def test_task_list_artifact_defaults() -> None:
    artifact = TaskListArtifact(tasks=[])
    assert artifact.version == 2
    assert artifact.object_type == "TaskListArtifact"
    assert artifact.tasks == []


def test_task_serializes_with_camel_case_aliases() -> None:
    task = Task(
        id="1",
        subject="Investigate widget",
        description="Look at the widget logic",
        active_form="Investigating widget",
        status=AgentTaskStatus.IN_PROGRESS,
        blocks=["2"],
        blocked_by=["3"],
        owner="agent-a",
        metadata={"k": "v"},
    )
    artifact = TaskListArtifact(tasks=[task])
    data = json.loads(artifact.model_dump_json(by_alias=True))
    assert data["objectType"] == "TaskListArtifact"
    assert data["version"] == 2
    task_data = data["tasks"][0]
    assert task_data["id"] == "1"
    assert task_data["subject"] == "Investigate widget"
    assert task_data["description"] == "Look at the widget logic"
    assert task_data["activeForm"] == "Investigating widget"
    assert task_data["status"] == "in_progress"
    assert task_data["blocks"] == ["2"]
    assert task_data["blockedBy"] == ["3"]
    assert task_data["owner"] == "agent-a"
    assert task_data["metadata"] == {"k": "v"}
    assert "active_form" not in task_data
    assert "blocked_by" not in task_data


def test_task_list_artifact_round_trip_from_camel_case() -> None:
    task = Task(
        id="1",
        subject="Investigate widget",
        description="Look at the widget logic",
        active_form="Investigating widget",
        status=AgentTaskStatus.IN_PROGRESS,
        blocks=["2"],
        blocked_by=["3"],
        owner="agent-a",
        metadata={"k": "v"},
    )
    artifact = TaskListArtifact(tasks=[task])
    raw = artifact.model_dump_json(by_alias=True)
    restored = TaskListArtifact.model_validate_json(raw)
    assert restored == artifact
    assert restored.tasks[0].active_form == "Investigating widget"
    assert restored.tasks[0].blocked_by == ["3"]


def test_task_list_artifact_round_trip_from_snake_case() -> None:
    task = Task(
        id="1",
        subject="Investigate widget",
        active_form="Investigating widget",
        status=AgentTaskStatus.PENDING,
        blocked_by=["3"],
    )
    artifact = TaskListArtifact(tasks=[task])
    raw = artifact.model_dump_json()
    restored = TaskListArtifact.model_validate_json(raw)
    assert restored == artifact


def test_task_validation_accepts_camel_case_input() -> None:
    raw_task_json = json.dumps(
        {
            "id": "1",
            "subject": "Investigate widget",
            "description": "",
            "activeForm": "Investigating widget",
            "status": "pending",
            "blocks": [],
            "blockedBy": ["2"],
            "owner": None,
            "metadata": {},
        }
    )
    task = Task.model_validate_json(raw_task_json)
    assert task.active_form == "Investigating widget"
    assert task.blocked_by == ["2"]
