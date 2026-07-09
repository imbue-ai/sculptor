import httpx
import typer

from sculpt.auth import MODEL_MAPPING
from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client.api.default import create_workspace_agent
from sculpt.client.api.default import create_workspace_v2
from sculpt.client.models.agent_type_name import AgentTypeName
from sculpt.client.models.create_agent_request import CreateAgentRequest
from sculpt.client.models.create_workspace_request_v2 import CreateWorkspaceRequestV2
from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.client.types import UNSET
from sculpt.commands._follow_helpers import follow_and_stream_messages
from sculpt.commands._group_helpers import group_new_workspace_or_warn
from sculpt.commands._group_helpers import resolve_group_for_join
from sculpt.commands._harness_helpers import resolve_harness_selection
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
    harness: str | None = typer.Option(
        None,
        "--harness",
        help=(
            "Chat harness to run the prompt with: Claude or Pi. Terminal harnesses"
            + " can't take a prompt, so they're rejected here. If omitted, uses your"
            + " most-recently-used harness from the Sculptor app (falling back to"
            + " Claude when that is a terminal harness)."
        ),
    ),
    file: list[str] | None = typer.Option(None, "--file", help="Files to include (repeatable)"),
    group: str | None = typer.Option(
        None,
        "--group",
        help="Add the new workspace to this existing group (ID or prefix) instead of auto-creating one",
    ),
    no_group: bool = typer.Option(
        False,
        "--no-group",
        help="Skip the default auto-grouping and create the workspace loose",
    ),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream the agent's response after creation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL"),
) -> None:
    """Create a workspace and agent in one step."""
    base_url = base_url or get_default_base_url()

    if group is not None and no_group:
        cli_error("--group and --no-group are mutually exclusive", json_output=json_output)

    model_lower = model.lower()
    if model_lower not in MODEL_MAPPING:
        valid = ", ".join(MODEL_MAPPING.keys())
        cli_error(f"Invalid model '{model}'. Valid options: {valid}", json_output=json_output)

    llm_model = MODEL_MAPPING[model_lower]
    client = get_authenticated_client(base_url)

    # Resolve the harness up front so a bad or terminal choice fails before we
    # create a workspace. `run` always sends a prompt, so terminal harnesses
    # (which have no chat stream) are rejected; an omitted harness lets the
    # server apply the user's most-recently-used one.
    selection = resolve_harness_selection(harness, client, json_output)
    if selection is not None and selection.agent_type in (AgentTypeName.TERMINAL, AgentTypeName.REGISTERED):
        cli_error(
            "Terminal agents cannot be created with `sculpt run` because it always sends a prompt."
            + " Use `sculpt agent create --harness ...` to create a terminal agent.",
            json_output=json_output,
        )

    project_id = resolve_project(repo, client)

    # Resolve an explicit --group target before creating anything, so an
    # unknown group (or the disabled workspace-groups experiment) fails with
    # no side effects.
    target_group = None
    if group is not None:
        target_group = resolve_group_for_join(client, group, project_id=project_id, json_output=json_output)

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

    if no_group:
        group_id = None
    else:
        group_id = group_new_workspace_or_warn(
            client,
            project_id=project_id,
            workspace_id=workspace_id,
            target_group_id=target_group.object_id if target_group is not None else None,
            json_output=json_output,
        )

    # Create agent. An omitted --harness sends no agent type, so the server
    # applies the user's most-recently-used harness (the same default the app's
    # "+" button uses).
    agent_request = CreateAgentRequest(
        prompt=prompt,
        model=llm_model,
        interface="API",
        files=file or [],
        name=name,
        sent_via="sculpt",
        agent_type=selection.agent_type if selection is not None else UNSET,
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
            group_id=group_id,
        )
        typer.echo(output.model_dump_json(indent=2))
    else:
        typer.echo(f"Workspace: {workspace_id}")
        typer.echo(f"Agent: {agent_result.id}")
        if group_id is not None:
            typer.echo(f"Group: {group_id}")

    if follow:
        if not json_output:
            typer.echo(f"Following agent {agent_result.id}...", err=True)
        follow_and_stream_messages(base_url, agent_result.id, json_output=json_output)
