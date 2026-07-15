"""Unit tests for the schema subcommand."""

import json

from sculpt.commands.data_types import AgentShowOutput
from sculpt.commands.data_types import RunOutput
from sculpt.commands.data_types import WorkspaceCreateOutput
from sculpt.commands.schema import get_schema_names
from sculpt.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_schema_list_shows_all_available_schemas() -> None:
    """Running `sculpt schema` with no arguments lists all schemas."""
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    for name in get_schema_names():
        assert name in result.output


def test_schema_outputs_valid_json_for_each_command() -> None:
    """Every registered schema should be valid JSON when printed."""
    for name in get_schema_names():
        result = runner.invoke(app, ["schema", name])
        assert result.exit_code == 0, f"schema {name} failed: {result.output}"
        parsed = json.loads(result.stdout)
        assert "description" in parsed


def test_schema_unknown_command_exits_with_error() -> None:
    """Requesting a schema for an unknown command should exit with code 1."""
    result = runner.invoke(app, ["schema", "nonexistent.command"])
    assert result.exit_code == 1
    assert "Unknown schema" in result.output


def test_schema_derived_from_pydantic_models() -> None:
    """Schemas should match the fields defined in the Pydantic models."""
    ws_schema = WorkspaceCreateOutput.model_json_schema()
    assert "id" in ws_schema["properties"]
    assert "repo_id" in ws_schema["properties"]

    agent_schema = AgentShowOutput.model_json_schema()
    assert "status" in agent_schema["properties"]
    assert "workspace_id" in agent_schema["properties"]
    assert "current_activity" in agent_schema["properties"]

    run_schema = RunOutput.model_json_schema()
    assert "workspace_id" in run_schema["properties"]
    assert "agent_id" in run_schema["properties"]
    assert "prompt" in run_schema["properties"]
    assert "group_id" in run_schema["properties"]

    assert "group_id" in ws_schema["properties"]


def test_schema_models_produce_valid_json_roundtrip() -> None:
    """Output models should serialize and deserialize consistently."""
    output = WorkspaceCreateOutput(
        id="ws_abc123",
        repo_id="prj_def456",
        description="test",
        strategy="clone",
        source_branch="main",
        group_id=None,
    )
    roundtripped = WorkspaceCreateOutput.model_validate_json(output.model_dump_json())
    assert roundtripped == output
