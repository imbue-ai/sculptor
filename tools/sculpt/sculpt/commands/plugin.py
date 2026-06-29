"""`sculpt plugin` subgroup — develop and manage frontend plugins live.

Drives the per-workspace plugin command endpoint, which fans a command out
over the user's WebSocket to every connected Sculptor window (renderer) and
collects one reply per renderer. The dev loop is: package a local plugin dir,
upload it to the backend's dev tree (``install``), then tell the renderers to
``load`` the resulting manifest URL. ``reload``/``unload``/``remove`` round out
the lifecycle; ``list``/``inspect``/``dir`` are read-only introspection.

Multiple windows can be connected at once (e.g. an Electron app plus a browser
tab on a different origin), each with its own plugin state. By default we report
the preferred (Electron) renderer's outcome and note the others; ``--all`` shows
every renderer.
"""

import base64
import json
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client import AuthenticatedClient
from sculpt.client.api.default import get_local_plugins_directory as _get_local_plugins_directory
from sculpt.client.api.default import post_plugin_command as _post_plugin_command
from sculpt.client.api.default import post_plugin_install as _post_plugin_install
from sculpt.client.api.default import post_plugin_remove as _post_plugin_remove
from sculpt.client.models.install_plugin_request import InstallPluginRequest
from sculpt.client.models.plugin_command_request import PluginCommandRequest
from sculpt.client.models.plugin_command_request_op import PluginCommandRequestOp
from sculpt.client.models.plugin_command_response import PluginCommandResponse
from sculpt.client.models.plugin_command_result import PluginCommandResult
from sculpt.client.models.plugin_file import PluginFile
from sculpt.client.models.plugin_snapshot import PluginSnapshot
from sculpt.client.models.renderer_identity_environment import RendererIdentityEnvironment
from sculpt.client.types import UNSET
from sculpt.client.types import Unset
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

plugin_app = typer.Typer(help="Develop and manage frontend plugins in the live Sculptor UI.")

# Cap the packaged upload so a stray build dir can't blow up the JSON body the
# backend has to parse. base64 inflates bytes ~4/3, so this is the encoded size.
_MAX_PACKAGE_BYTES = 5 * 1024 * 1024

# Directory/file names skipped when packaging — caches and VCS metadata that
# would bloat the upload and aren't part of the served plugin.
_SKIP_DIR_NAMES = {"node_modules", "__pycache__"}

# Short prefix used to label renderers in --all output.
_RENDERER_ID_DISPLAY_LENGTH = 8

_WORKSPACE_OPTION = typer.Option(None, "--workspace", "-w", help="Workspace ID (or set SCULPT_WORKSPACE_ID).")
_JSON_OPTION = typer.Option(False, "--json", help="Output the raw structured response as JSON (for agents).")
_ALL_OPTION = typer.Option(False, "--all", help="Show every connected window's outcome, not just the preferred one.")


def _resolve_workspace_id(workspace: str | None, json_output: bool) -> str:
    """Return the workspace id from --workspace or SCULPT_WORKSPACE_ID."""
    workspace_id = workspace or os.environ.get("SCULPT_WORKSPACE_ID")
    if not workspace_id:
        cli_error(
            "not running inside a Sculptor workspace; pass --workspace or set SCULPT_WORKSPACE_ID",
            json_output=json_output,
            exit_code=2,
        )
    return workspace_id


def _is_url(target: str) -> bool:
    """True if the target looks like an http(s) URL rather than a local path."""
    from urllib.parse import urlparse

    return urlparse(target).scheme in ("http", "https")


def _resolve_plugin_dir(target: str, json_output: bool) -> Path:
    """Resolve a load target to the plugin's root directory.

    Accepts a path to a ``manifest.json`` (uses its parent) or a directory that
    contains one.
    """
    path = Path(target).expanduser()
    if path.is_file() and path.name == "manifest.json":
        return path.parent
    if path.is_dir():
        if not (path / "manifest.json").is_file():
            cli_error(
                f"no manifest.json in {path}",
                detail="A plugin directory must contain a manifest.json.",
                json_output=json_output,
                exit_code=2,
            )
        return path
    cli_error(
        f"not a plugin path: {target}",
        detail="Pass a plugin directory, a manifest.json, or an http(s) URL.",
        json_output=json_output,
        exit_code=2,
    )


def _read_plugin_id(plugin_dir: Path, json_output: bool) -> str:
    """Parse and return the ``id`` field from a plugin dir's manifest.json."""
    manifest_path = plugin_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        cli_error(
            f"could not read manifest.json in {plugin_dir}",
            detail=str(e),
            json_output=json_output,
            exit_code=2,
        )
    plugin_id = manifest.get("id") if isinstance(manifest, dict) else None
    if not isinstance(plugin_id, str) or not plugin_id:
        cli_error(
            f"manifest.json is missing a string 'id': {manifest_path}",
            json_output=json_output,
            exit_code=2,
        )
    return plugin_id


def _is_skipped(relative: Path) -> bool:
    """Skip dotfiles/dirs and known cache dirs anywhere in the relative path."""
    return any(part.startswith(".") or part in _SKIP_DIR_NAMES for part in relative.parts)


def _package_plugin_files(plugin_dir: Path, json_output: bool) -> list[PluginFile]:
    """Walk a plugin dir and base64-encode every file for upload.

    Paths are stored relative to the plugin root, POSIX-style, so the backend
    can recreate the tree regardless of the local OS. Dotfiles and cache dirs
    are skipped; the total encoded size is capped.
    """
    files: list[PluginFile] = []
    total_encoded = 0
    for entry in sorted(plugin_dir.rglob("*")):
        if not entry.is_file():
            continue
        relative = entry.relative_to(plugin_dir)
        if _is_skipped(relative):
            continue
        encoded = base64.b64encode(entry.read_bytes()).decode("ascii")
        total_encoded += len(encoded)
        if total_encoded > _MAX_PACKAGE_BYTES:
            cli_error(
                f"plugin package exceeds {_MAX_PACKAGE_BYTES // (1024 * 1024)} MB",
                detail="Trim the plugin directory (a stray build/cache dir is the usual cause).",
                json_output=json_output,
                exit_code=2,
            )
        files.append(PluginFile(path=relative.as_posix(), content_base_64=encoded))
    if not files:
        cli_error(f"plugin directory is empty: {plugin_dir}", json_output=json_output, exit_code=2)
    return files


def _client_or_exit(json_output: bool) -> AuthenticatedClient:
    """Build an authenticated client, mapping connect failures to a clean exit."""
    base_url = get_default_base_url()
    try:
        return get_authenticated_client(base_url)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    except typer.Exit:
        raise


def _check_command_status(response: Any, json_output: bool) -> PluginCommandResponse:
    """Map a command-endpoint response's status to errors, or return its body.

    Distinguishes the 403 "agent plugin loading disabled" case so we can point
    the user at the setting that gates write ops.
    """
    status = int(response.status_code)
    if status == HTTPStatus.FORBIDDEN and b"agent_plugin_loading_disabled" in response.content:
        cli_error(
            "agent plugin loading is disabled",
            detail="Enable it in Sculptor under Settings -> Plugins, then try again.",
            json_output=json_output,
        )
    if not (HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES):
        cli_error(
            f"backend error (HTTP {status})",
            detail=response.content.decode(errors="replace"),
            json_output=json_output,
        )
    body = response.parsed
    if not isinstance(body, PluginCommandResponse):
        cli_error(
            "unexpected response from the plugin command endpoint",
            detail=response.content.decode(errors="replace"),
            json_output=json_output,
        )
    return body


def _send_command(
    *,
    op: PluginCommandRequestOp,
    workspace_id: str,
    client: AuthenticatedClient,
    json_output: bool,
    plugin_id: str | None = None,
    source: str | None = None,
) -> PluginCommandResponse:
    """POST one plugin command and return the validated aggregate response."""
    request = PluginCommandRequest(
        op=op,
        plugin_id=plugin_id if plugin_id is not None else UNSET,
        source=source if source is not None else UNSET,
    )
    try:
        response = _post_plugin_command.sync_detailed(workspace_id=workspace_id, client=client, body=request)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    return _check_command_status(response, json_output)


def _results_or_exit(response: PluginCommandResponse, json_output: bool) -> list[PluginCommandResult]:
    """Return the per-renderer results, erroring if no window answered."""
    results = response.results
    if isinstance(results, Unset) or not results:
        cli_error(
            "No Sculptor window responded. Is Sculptor running with frontend plugins enabled?",
            json_output=json_output,
        )
    return results


def _preferred_result(results: list[PluginCommandResult]) -> PluginCommandResult:
    """Pick the renderer to report by default: first Electron window, else first."""
    for result in results:
        if result.renderer.environment == RendererIdentityEnvironment.ELECTRON:
            return result
    return results[0]


def _renderer_label(result: PluginCommandResult) -> str:
    """A compact ``environment short-id origin`` label for a renderer."""
    renderer = result.renderer
    short_id = renderer.renderer_id[:_RENDERER_ID_DISPLAY_LENGTH]
    return f"{renderer.environment.value} {short_id} {renderer.origin}"


def _opt_str(value: None | str | Unset) -> str | None:
    """Collapse a generated optional (UNSET/None/str) to str | None."""
    if isinstance(value, Unset) or value is None:
        return None
    return value


def _print_snapshot(snapshot: PluginSnapshot, *, indent: str = "  ") -> None:
    """Render one plugin snapshot. Only key NAMES are printed, never values."""
    typer.echo(f"{indent}{snapshot.plugin_id}  [{snapshot.status.value}]  origin={snapshot.origin.value}")
    active_source = _opt_str(snapshot.active_source) or snapshot.source
    typer.echo(f"{indent}  source: {active_source}")
    error_message = _opt_str(snapshot.error_message)
    if error_message:
        phase = _opt_str(snapshot.error_phase)
        where = f" ({phase})" if phase else ""
        typer.echo(f"{indent}  error{where}: {error_message}")
    registrations = snapshot.registrations
    if registrations is not None and not isinstance(registrations, Unset):
        parts: list[str] = []
        panels = registrations.panels
        if not isinstance(panels, Unset) and panels:
            parts.append(f"panels={', '.join(panels)}")
        overlays = registrations.overlays
        if not isinstance(overlays, Unset) and overlays:
            parts.append(f"overlays={', '.join(overlays)}")
        if registrations.has_settings is True:
            parts.append("settings")
        if parts:
            typer.echo(f"{indent}  registrations: {'; '.join(parts)}")
    config_keys = snapshot.config_keys
    if not isinstance(config_keys, Unset) and config_keys:
        typer.echo(f"{indent}  config keys: {', '.join(config_keys)}")


def _print_result_plugins(result: PluginCommandResult) -> None:
    """Print the plugin snapshots carried by a list/inspect result."""
    plugins = result.plugins
    if isinstance(plugins, Unset) or not plugins:
        typer.echo("  (no plugins)")
        return
    for snapshot in plugins:
        _print_snapshot(snapshot)


def _emit_json(response: PluginCommandResponse) -> None:
    """Dump the full aggregate response (all renderer results) as JSON."""
    typer.echo(json.dumps(response.to_dict()))


def _report_mutation(
    response: PluginCommandResponse,
    *,
    action: str,
    json_output: bool,
    show_all: bool,
) -> None:
    """Render load/reload/unload outcomes and exit non-zero on any failure.

    Default: report the preferred (Electron) renderer and note the rest.
    ``--all``: report every renderer and fail if any reports ``ok=False``.
    """
    if json_output:
        _emit_json(response)
    results = _results_or_exit(response, json_output)

    if show_all:
        any_failed = False
        for result in results:
            ok = "ok" if result.ok else "FAILED"
            if not json_output:
                typer.echo(f"[{ok}] {_renderer_label(result)}")
                error = _opt_str(result.error)
                if error:
                    typer.echo(f"  error: {error}")
            any_failed = any_failed or not result.ok
        if any_failed:
            raise typer.Exit(code=1)
        return

    chosen = _preferred_result(results)
    if not json_output:
        status = "OK" if chosen.ok else "FAILED"
        typer.echo(f"{action}: {status} ({chosen.renderer.environment.value})")
        error = _opt_str(chosen.error)
        if error:
            typer.echo(f"  error: {error}")
        if len(results) > 1:
            typer.echo(
                f"({len(results)} windows connected; showing {chosen.renderer.environment.value}; use --all to see all)"
            )
    if not chosen.ok:
        raise typer.Exit(code=1)


def _report_snapshots(
    response: PluginCommandResponse,
    *,
    json_output: bool,
    show_all: bool,
) -> None:
    """Render list/inspect outcomes (read-only; never exits on ok=False)."""
    if json_output:
        _emit_json(response)
        return
    results = _results_or_exit(response, json_output)

    if show_all:
        for result in results:
            typer.echo(_renderer_label(result))
            _print_result_plugins(result)
        return

    chosen = _preferred_result(results)
    typer.echo(_renderer_label(chosen))
    _print_result_plugins(chosen)
    if len(results) > 1:
        typer.echo(
            f"({len(results)} windows connected; showing {chosen.renderer.environment.value}; use --all to see all)"
        )


@plugin_app.command("load")
def load(
    target: str = typer.Argument(..., help="Local plugin directory / manifest.json, or an http(s) manifest URL."),
    persist: bool = typer.Option(
        False, "--persist", help="Install permanently (top-level) rather than as a workspace-scoped dev install."
    ),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Package and load a plugin into the live UI.

    A local path is packaged and uploaded to the backend, then loaded from the
    resulting manifest URL. An http(s) URL is loaded directly (no packaging).
    """
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)

    if _is_url(target):
        source = target
    else:
        plugin_dir = _resolve_plugin_dir(target, json_output)
        plugin_id = _read_plugin_id(plugin_dir, json_output)
        files = _package_plugin_files(plugin_dir, json_output)
        install_request = InstallPluginRequest(plugin_id=plugin_id, files=files, persist=persist)
        try:
            install_response = _post_plugin_install.sync_detailed(
                workspace_id=workspace_id, client=client, body=install_request
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            handle_connection_error(json_output)
        install_status = int(install_response.status_code)
        if not (HTTPStatus.OK <= install_status < HTTPStatus.MULTIPLE_CHOICES) or install_response.parsed is None:
            cli_error(
                f"upload failed (HTTP {install_status})",
                detail=install_response.content.decode(errors="replace"),
                json_output=json_output,
            )
        source = install_response.parsed.manifest_url

    response = _send_command(
        op=PluginCommandRequestOp.LOAD,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        source=source,
    )
    _report_mutation(response, action="load", json_output=json_output, show_all=show_all)


@plugin_app.command("reload")
def reload(
    plugin_id: str = typer.Argument(..., help="ID of the loaded plugin to reload (cache-busts its source)."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Reload an already-loaded plugin, re-fetching its source."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=PluginCommandRequestOp.RELOAD,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        plugin_id=plugin_id,
    )
    _report_mutation(response, action="reload", json_output=json_output, show_all=show_all)


@plugin_app.command("unload")
def unload(
    plugin_id: str = typer.Argument(..., help="ID of the loaded plugin to unload from the UI."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Unload a plugin from the live UI (leaves any installed files in place)."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=PluginCommandRequestOp.UNLOAD,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        plugin_id=plugin_id,
    )
    _report_mutation(response, action="unload", json_output=json_output, show_all=show_all)


@plugin_app.command("remove")
def remove(
    plugin_id: str = typer.Argument(..., help="ID of the dev-installed plugin to unload and delete."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
) -> None:
    """Unload a plugin and delete its workspace-scoped dev install files."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)

    # Best-effort unload first so the live UI drops the plugin before its files
    # vanish; a failure here (e.g. it wasn't loaded) shouldn't block cleanup.
    try:
        unload_request = PluginCommandRequest(op=PluginCommandRequestOp.UNLOAD, plugin_id=plugin_id)
        _post_plugin_command.sync_detailed(workspace_id=workspace_id, client=client, body=unload_request)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)

    try:
        remove_response = _post_plugin_remove.sync_detailed(
            workspace_id=workspace_id, plugin_id=plugin_id, client=client
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    status = int(remove_response.status_code)
    if not (HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES):
        cli_error(
            f"remove failed (HTTP {status})",
            detail=remove_response.content.decode(errors="replace"),
            json_output=json_output,
        )
    if json_output:
        typer.echo(json.dumps({"ok": True, "plugin_id": plugin_id}))
    else:
        typer.echo(f"removed dev install: {plugin_id}")


@plugin_app.command("list")
def list_plugins(
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """List the plugins each connected window currently knows about."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=PluginCommandRequestOp.LIST,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
    )
    _report_snapshots(response, json_output=json_output, show_all=show_all)


@plugin_app.command("inspect")
def inspect(
    plugin_id: str = typer.Argument(..., help="ID of the plugin to inspect."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Show one plugin's status, registrations, and config key names."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=PluginCommandRequestOp.INSPECT,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        plugin_id=plugin_id,
    )
    _report_snapshots(response, json_output=json_output, show_all=show_all)


@plugin_app.command("dir")
def dir_command(
    json_output: bool = _JSON_OPTION,
) -> None:
    """Print the directory Sculptor scans for drop-in (persistent) plugins."""
    client = _client_or_exit(json_output)
    try:
        response = _get_local_plugins_directory.sync_detailed(client=client)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    status = int(response.status_code)
    if not (HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES) or response.parsed is None:
        cli_error(
            f"backend error (HTTP {status})",
            detail=response.content.decode(errors="replace"),
            json_output=json_output,
        )
    if json_output:
        typer.echo(json.dumps({"path": response.parsed.path}))
    else:
        typer.echo(response.parsed.path)
