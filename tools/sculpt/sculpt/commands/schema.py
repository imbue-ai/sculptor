"""JSON schema definitions for sculpt CLI commands.

Schemas are derived automatically from the Pydantic models in ``data_types.py``.
Use ``sculpt schema <command>`` to print the JSON Schema for that command's
output, making it easy to script with tools like ``jq``.
"""

import json
from typing import Any

import typer
from pydantic import BaseModel

from sculpt.commands.data_types import AgentCreateOutput
from sculpt.commands.data_types import AgentDeleteOutput
from sculpt.commands.data_types import AgentInterruptOutput
from sculpt.commands.data_types import AgentListItem
from sculpt.commands.data_types import AgentRenameOutput
from sculpt.commands.data_types import AgentSendOutput
from sculpt.commands.data_types import AgentShowOutput
from sculpt.commands.data_types import AgentStatusOutput
from sculpt.commands.data_types import ErrorOutput
from sculpt.commands.data_types import GroupAddOutput
from sculpt.commands.data_types import GroupCreateOutput
from sculpt.commands.data_types import GroupListItem
from sculpt.commands.data_types import GroupRemoveOutput
from sculpt.commands.data_types import GroupRenameOutput
from sculpt.commands.data_types import GroupShowOutput
from sculpt.commands.data_types import GroupUngroupOutput
from sculpt.commands.data_types import RepoItem
from sculpt.commands.data_types import RunOutput
from sculpt.commands.data_types import WorkspaceCreateOutput
from sculpt.commands.data_types import WorkspaceDeleteOutput
from sculpt.commands.data_types import WorkspaceListItem
from sculpt.commands.data_types import WorkspaceListProjectItem
from sculpt.commands.data_types import WorkspaceRenameOutput
from sculpt.commands.data_types import WorkspaceShowOutput

schema_app = typer.Typer(
    name="schema",
    help="Show JSON schemas for command outputs.",
)


def _object_schema(model: type[BaseModel], description: str) -> dict[str, Any]:
    """Generate a JSON Schema for a single-object output."""
    schema = model.model_json_schema()
    schema["description"] = description
    return schema


def _array_schema(item_model: type[BaseModel], description: str) -> dict[str, Any]:
    """Generate a JSON Schema for an array-of-objects output."""
    item_schema = item_model.model_json_schema()
    return {
        "description": description,
        "type": "array",
        "items": item_schema,
    }


_SCHEMAS: dict[str, dict[str, Any]] = {
    "workspace.create": _object_schema(
        WorkspaceCreateOutput,
        "Output of `sculpt workspace create --json`",
    ),
    "workspace.list": _array_schema(
        WorkspaceListItem,
        "Output of `sculpt workspace list --json --all`",
    ),
    "workspace.list-project": _array_schema(
        WorkspaceListProjectItem,
        "Output of `sculpt workspace list --json` (per-project, without --all)",
    ),
    "workspace.show": _object_schema(
        WorkspaceShowOutput,
        "Output of `sculpt workspace show --json`",
    ),
    "workspace.rename": _object_schema(
        WorkspaceRenameOutput,
        "Output of `sculpt workspace rename --json`",
    ),
    "workspace.delete": _object_schema(
        WorkspaceDeleteOutput,
        "Output of `sculpt workspace delete --json`",
    ),
    "repo.list": _array_schema(
        RepoItem,
        "Output of `sculpt repo list --json`",
    ),
    "repo.show": _object_schema(
        RepoItem,
        "Output of `sculpt repo show --json`",
    ),
    "agent.create": _object_schema(
        AgentCreateOutput,
        "Output of `sculpt agent create --json`",
    ),
    "agent.list": _array_schema(
        AgentListItem,
        "Output of `sculpt agent list --json`",
    ),
    "agent.show": _object_schema(
        AgentShowOutput,
        "Output of `sculpt agent show --json`",
    ),
    "agent.rename": _object_schema(
        AgentRenameOutput,
        "Output of `sculpt agent rename --json`",
    ),
    "agent.delete": _object_schema(
        AgentDeleteOutput,
        "Output of `sculpt agent delete --json`",
    ),
    "agent.send": _object_schema(
        AgentSendOutput,
        "Output of `sculpt agent send --json`",
    ),
    "agent.status": _object_schema(
        AgentStatusOutput,
        "Output of `sculpt agent status --json`",
    ),
    "agent.interrupt": _object_schema(
        AgentInterruptOutput,
        "Output of `sculpt agent interrupt --json`",
    ),
    "group.create": _object_schema(
        GroupCreateOutput,
        "Output of `sculpt group create --json`",
    ),
    "group.list": _array_schema(
        GroupListItem,
        "Output of `sculpt group list --json`",
    ),
    "group.show": _object_schema(
        GroupShowOutput,
        "Output of `sculpt group show --json`",
    ),
    "group.rename": _object_schema(
        GroupRenameOutput,
        "Output of `sculpt group rename --json`",
    ),
    "group.add": _object_schema(
        GroupAddOutput,
        "Output of `sculpt group add --json`",
    ),
    "group.remove": _object_schema(
        GroupRemoveOutput,
        "Output of `sculpt group remove --json`",
    ),
    "group.ungroup": _object_schema(
        GroupUngroupOutput,
        "Output of `sculpt group ungroup --json`",
    ),
    "run": _object_schema(
        RunOutput,
        "Output of `sculpt run --json`",
    ),
    "error": _object_schema(
        ErrorOutput,
        "Error output (written to stderr) when a command fails with --json",
    ),
}


def get_schema_names() -> list[str]:
    """Return sorted list of available schema names."""
    return sorted(_SCHEMAS.keys())


@schema_app.callback(invoke_without_command=True)
def schema_callback(
    ctx: typer.Context,
    command: str | None = typer.Argument(None, help="Command name (e.g. workspace.list, agent.show, run)"),
) -> None:
    """Show JSON schema for a command's --json output.

    Run without arguments to list all available schemas.

    Examples:
        sculpt schema                  # list available schemas
        sculpt schema workspace.list   # show schema for workspace list
        sculpt schema agent.show       # show schema for agent show
    """
    if command is None:
        typer.echo("Available schemas:\n")
        for name in get_schema_names():
            description = _SCHEMAS[name].get("description", "")
            typer.echo(f"  {name:25s} {description}")
        typer.echo("\nUse `sculpt schema <name>` to view a schema.")
        return

    schema = _SCHEMAS.get(command)
    if schema is None:
        available = ", ".join(get_schema_names())
        typer.echo(f"Unknown schema: {command}", err=True)
        typer.echo(f"Available: {available}", err=True)
        raise typer.Exit(code=1)

    typer.echo(json.dumps(schema, indent=2))
