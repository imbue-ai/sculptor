import httpx
import typer

from sculpt.auth import MODEL_MAPPING
from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client.api.default import create_workspace_agent
from sculpt.client.api.default import create_workspace_v2
from sculpt.client.models.create_agent_request import CreateAgentRequest
from sculpt.client.models.create_workspace_request_v2 import CreateWorkspaceRequestV2
from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.commands._follow_helpers import follow_and_stream_messages
from sculpt.commands._workspace_helpers import STRATEGY_MAPPING
from sculpt.commands._workspace_helpers import resolve_requested_branch_name
from sculpt.commands._workspace_helpers import resolve_strategy
from sculpt.commands.data_types import RunOutput
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error
from sculpt.resolve import resolve_project


def run_cmd(
    prompt: str = typer.Argument(..., help="The task prompt"),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help=(
            "Path to the repository. If omitted, the project is taken from the"
            + " SCULPT_PROJECT_ID env var (set in every Sculptor workspace shell),"
            + " or matched against the current working directory."
        ),
    ),
    model: str = typer.Option(
        "opus", "--model", "-m", help="The model to use (haiku, sonnet, sonnet[1m], opus, opus[1m], fable)"
    ),
    strategy: str = typer.Option(
        "worktree",
        "--strategy",
        help=f"Initialization strategy ({', '.join(STRATEGY_MAPPING)})",
    ),
    branch: str | None = typer.Option(None, "--branch", help="Source branch"),
    branch_name: str | None = typer.Option(
        None,
        "--branch-name",
        help="New branch name (required for worktree; auto-generated if omitted)",
    ),
    target_branch: str | None = typer.Option(
        None,
        "--target-branch",
        help="Diff/merge target branch (auto-resolved from the repo if omitted)",
    ),
    name: str | None = typer.Option(None, "--name", help="Agent name"),
    file: list[str] | None = typer.Option(None, "--file", help="Files to include (repeatable)"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream the agent's response after creation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Create a workspace and agent in one step."""
    base_url = base_url or get_default_base_url()

    model_lower = model.lower()
    if model_lower not in MODEL_MAPPING:
        valid = ", ".join(MODEL_MAPPING.keys())
        cli_error(f"Invalid model '{model}'. Valid options: {valid}", json_output=json_output)

    llm_model = MODEL_MAPPING[model_lower]
    client = get_authenticated_client(base_url)
    project_id = resolve_project(repo, client)

    strategy_enum = resolve_strategy(strategy, json_output=json_output)

    resolved_branch_name = resolve_requested_branch_name(
        client=client,
        project_id=project_id,
        strategy=strategy_enum,
        branch_name=branch_name,
        workspace_name=name,
        json_output=json_output,
    )

    # Create workspace
    ws_request = CreateWorkspaceRequestV2(
        project_id=project_id,
        initialization_strategy=strategy_enum,
        source_branch=branch,
        description=name,
        requested_branch_name=resolved_branch_name,
        target_branch=target_branch,
    )

    try:
        ws_result = create_workspace_v2.sync(client=client, body=ws_request)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if ws_result is None:
        cli_error("Failed to create workspace", detail="No response from server", json_output=json_output)

    if isinstance(ws_result, HTTPValidationError):
        cli_error("Validation error", detail=str(ws_result), json_output=json_output)

    workspace_id = ws_result.object_id

    # Create agent
    agent_request = CreateAgentRequest(
        prompt=prompt,
        model=llm_model,
        interface="API",
        files=file or [],
        name=name,
        sent_via="sculpt",
    )

    try:
        agent_result = create_workspace_agent.sync(workspace_id=workspace_id, client=client, body=agent_request)
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if agent_result is None:
        cli_error("Failed to create agent", detail="No response from server", json_output=json_output)

    if isinstance(agent_result, HTTPValidationError):
        cli_error("Validation error", detail=str(agent_result), json_output=json_output)

    if json_output:
        output = RunOutput(
            workspace_id=workspace_id,
            agent_id=agent_result.id,
            strategy=ws_result.initialization_strategy.value,
            model=agent_result.model.value,
            prompt=prompt,
        )
        typer.echo(output.model_dump_json(indent=2))
    else:
        typer.echo(f"Workspace: {workspace_id}")
        typer.echo(f"Agent: {agent_result.id}")

    if follow:
        if not json_output:
            typer.echo(f"Following agent {agent_result.id}...", err=True)
        follow_and_stream_messages(base_url, agent_result.id, json_output=json_output)
