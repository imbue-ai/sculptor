"""`sculpt ui` subgroup — commands that update the user's UI view."""

import json
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any
from typing import Callable

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client import AuthenticatedClient
from sculpt.client.api.default import workspace_ui_open_file as _workspace_ui_open_file
from sculpt.client.api.default import workspace_ui_webview_navigate as _workspace_ui_webview_navigate
from sculpt.client.api.default import workspace_ui_webview_refresh as _workspace_ui_webview_refresh
from sculpt.client.models.open_file_ui_request import OpenFileUiRequest
from sculpt.client.models.open_file_ui_request_mode import OpenFileUiRequestMode
from sculpt.client.models.webview_navigate_request import WebviewNavigateRequest
from sculpt.client.types import Response
from sculpt.commands.agent import resolve_workspace
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

ui_app = typer.Typer(
    name="ui",
    help="Update the user's UI view.",
)

_MODE_VALUES = {m.value for m in OpenFileUiRequestMode}
_MAX_ERROR_DETAIL_LENGTH = 500


@ui_app.command("open-file")
def open_file(
    path: str = typer.Argument(
        ...,
        help="Path to open. Relative paths resolve against the agent's CWD; absolute paths are accepted, including paths outside the workspace clone.",
    ),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace ID (or set SCULPT_WORKSPACE_ID).",
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Tab kind: 'auto' (default; diff if uncommitted changes, else file-view), 'diff' (force a diff tab), or 'file' (force a read-only file-view tab).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL."),
) -> None:
    """Open a file as the active tab in the workspace's diff panel.

    Updates the target workspace's per-workspace diff panel state. Does NOT
    switch the user's foreground view across workspaces. Auto-expands the
    diff panel if it was collapsed.

    Exit codes:
      0  success
      2  bad usage (missing args, malformed flag)
      3  workspace not open (is_open=False)
      4  path not found / not readable
      5  backend unreachable (server not running, auth failure, 5xx)
    """
    if mode not in _MODE_VALUES:
        cli_error(
            f"Invalid --mode {mode!r}. Valid values: auto, diff, file.",
            json_output=json_output,
            exit_code=2,
        )

    if workspace is None and os.environ.get("SCULPT_WORKSPACE_ID") is None:
        cli_error(
            "--workspace is required (or set SCULPT_WORKSPACE_ID)",
            json_output=json_output,
            exit_code=2,
        )

    resolved_path = path if Path(path).is_absolute() else str((Path.cwd() / path).resolve())

    base_url = base_url or get_default_base_url()
    try:
        client = get_authenticated_client(base_url)
    except httpx.ConnectError:
        handle_connection_error(json_output, exit_code=5)
    except typer.Exit as e:
        raise typer.Exit(code=5) from e

    workspace_id = resolve_workspace(workspace, client, json_output)

    request = OpenFileUiRequest(
        file_path=resolved_path,
        mode=OpenFileUiRequestMode(mode),
    )

    try:
        response = _workspace_ui_open_file.sync_detailed(
            workspace_id=workspace_id,
            client=client,
            body=request,
        )
    except httpx.ConnectError:
        handle_connection_error(json_output, exit_code=5)

    _handle_response(response, workspace_id, resolved_path, json_output)


def _handle_response(response: Response[Any], workspace_id: str, file_path: str, json_output: bool) -> None:
    status = int(response.status_code)
    if HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
        if json_output:
            typer.echo(json.dumps({"opened": True, "workspace_id": workspace_id, "file_path": file_path}))
        return

    detail = _parse_detail(response.content)
    code = detail.get("code") if isinstance(detail, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else None

    if status == HTTPStatus.CONFLICT and code == "workspace_not_open":
        cli_error(
            message or f"workspace {workspace_id} is not open",
            json_output=json_output,
            exit_code=3,
        )
    if status == HTTPStatus.NOT_FOUND and code == "file_not_found":
        cli_error(
            f"file not found: {message or file_path}",
            json_output=json_output,
            exit_code=4,
        )
    if status == HTTPStatus.BAD_REQUEST and code == "file_not_absolute":
        cli_error(
            message or f"path not absolute: {file_path}",
            json_output=json_output,
            exit_code=4,
        )

    cli_error(
        f"backend error (HTTP {status})",
        detail=str(detail or response.content)[:_MAX_ERROR_DETAIL_LENGTH],
        json_output=json_output,
        exit_code=5,
    )


def _call_webview_endpoint(
    *,
    workspace: str | None,
    json_output: bool,
    base_url: str | None,
    send: Callable[[AuthenticatedClient, str], Response[Any]],
    success_payload_extras: dict[str, Any],
) -> None:
    """Shared boilerplate for the two `sculpt ui webview-*` commands.

    Handles the workspace-required check, auth, ConnectError mapping to exit
    code 5, workspace resolution, and the success/error response handoff.
    `send` is called with (client, resolved_workspace_id) and returns the raw
    sync_detailed response. `success_payload_extras` is merged with
    `workspace_id` for --json output.
    """
    if workspace is None and os.environ.get("SCULPT_WORKSPACE_ID") is None:
        cli_error(
            "--workspace is required (or set SCULPT_WORKSPACE_ID)",
            json_output=json_output,
            exit_code=2,
        )

    base_url = base_url or get_default_base_url()
    try:
        client = get_authenticated_client(base_url)
    except httpx.ConnectError:
        handle_connection_error(json_output, exit_code=5)
    except typer.Exit as e:
        raise typer.Exit(code=5) from e

    workspace_id = resolve_workspace(workspace, client, json_output)
    try:
        response = send(client, workspace_id)
    except httpx.ConnectError:
        handle_connection_error(json_output, exit_code=5)

    _handle_webview_response(
        response=response,
        workspace_id=workspace_id,
        json_output=json_output,
        success_payload={**success_payload_extras, "workspace_id": workspace_id},
    )


@ui_app.command("webview-navigate")
def webview_navigate(
    url: str = typer.Argument(
        ...,
        help="URL to load in the in-app Browser panel (file://..., http://..., https://...).",
    ),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace ID (or set SCULPT_WORKSPACE_ID).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL."),
) -> None:
    """Point the in-app Browser panel at a URL.

    Example: sculpt ui webview-navigate file:///workspace/code/report.html

    Exit codes:
      0  success
      2  bad usage (missing args, malformed flag)
      3  workspace not open (is_open=False)
      4  workspace not found
      5  backend unreachable (server not running, auth failure, 5xx)
    """
    _call_webview_endpoint(
        workspace=workspace,
        json_output=json_output,
        base_url=base_url,
        send=lambda client, ws_id: _workspace_ui_webview_navigate.sync_detailed(
            workspace_id=ws_id,
            client=client,
            body=WebviewNavigateRequest(url=url),
        ),
        success_payload_extras={"navigated": True, "url": url},
    )


@ui_app.command("webview-refresh")
def webview_refresh(
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace ID (or set SCULPT_WORKSPACE_ID).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="The Sculptor server URL."),
) -> None:
    """Reload the in-app Browser panel at its current URL.

    Use after editing the HTML the webview is showing.

    Exit codes:
      0  success
      2  bad usage (missing args, malformed flag)
      3  workspace not open (is_open=False)
      4  workspace not found
      5  backend unreachable (server not running, auth failure, 5xx)
    """
    _call_webview_endpoint(
        workspace=workspace,
        json_output=json_output,
        base_url=base_url,
        send=lambda client, ws_id: _workspace_ui_webview_refresh.sync_detailed(
            workspace_id=ws_id,
            client=client,
        ),
        success_payload_extras={"refreshed": True},
    )


def _handle_webview_response(
    response: Response[Any],
    workspace_id: str,
    json_output: bool,
    success_payload: dict[str, Any],
) -> None:
    status = int(response.status_code)
    if HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
        if json_output:
            typer.echo(json.dumps(success_payload))
        return

    detail = _parse_detail(response.content)
    code = detail.get("code") if isinstance(detail, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else None

    if status == HTTPStatus.CONFLICT and code == "workspace_not_open":
        cli_error(
            message or f"workspace {workspace_id} is not open",
            json_output=json_output,
            exit_code=3,
        )
    if status == HTTPStatus.NOT_FOUND and code == "workspace_not_found":
        cli_error(
            message or f"workspace {workspace_id} not found",
            json_output=json_output,
            exit_code=4,
        )

    cli_error(
        f"backend error (HTTP {status})",
        detail=str(detail or response.content)[:_MAX_ERROR_DETAIL_LENGTH],
        json_output=json_output,
        exit_code=5,
    )


def _parse_detail(content: bytes | str) -> dict[str, Any] | str:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    if isinstance(parsed, dict) and "detail" in parsed:
        return parsed["detail"]
    return parsed
