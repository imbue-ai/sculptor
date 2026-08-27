"""`sculpt extension` subgroup — develop and manage Sculptor extensions live.

Drives the per-workspace extension command endpoint, which fans a command out
over the user's WebSocket to every connected Sculptor window (renderer) and
collects one reply per renderer. The dev loop is: package a local extension
dir, upload it to the backend's dev tree (``install``), then tell the
renderers to ``load`` the resulting manifest URL. ``reload``/``unload``/
``remove`` round out the lifecycle; ``list``/``inspect``/``dir`` are read-only
introspection.

Multiple windows can be connected at once (e.g. an Electron app plus a browser
tab on a different origin), each with its own extension state. By default we
report the preferred (Electron) renderer's outcome and note the others;
``--all`` shows every renderer.
"""

import base64
import json
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any
from typing import NoReturn
from urllib.parse import urlparse

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.auth import get_default_base_url
from sculpt.client import AuthenticatedClient
from sculpt.client.api.default import get_local_extensions_directory as _get_local_extensions_directory
from sculpt.client.api.default import post_extension_command as _post_extension_command
from sculpt.client.api.default import post_extension_install as _post_extension_install
from sculpt.client.api.default import post_extension_remove as _post_extension_remove
from sculpt.client.models.extension_command_request import ExtensionCommandRequest
from sculpt.client.models.extension_command_request_op import ExtensionCommandRequestOp
from sculpt.client.models.extension_command_response import ExtensionCommandResponse
from sculpt.client.models.extension_command_result import ExtensionCommandResult
from sculpt.client.models.extension_file import ExtensionFile
from sculpt.client.models.extension_snapshot import ExtensionSnapshot
from sculpt.client.models.install_extension_request import InstallExtensionRequest
from sculpt.client.models.renderer_identity_environment import RendererIdentityEnvironment
from sculpt.client.types import UNSET
from sculpt.client.types import Unset
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error

extension_app = typer.Typer(help="Develop and manage extensions in the live Sculptor UI.")

# Cap the packaged upload so a stray build dir can't blow up the JSON body the
# backend has to parse. base64 inflates bytes ~4/3, so this is the encoded size.
_MAX_PACKAGE_BYTES = 5 * 1024 * 1024

# Directory/file names skipped when packaging — caches and VCS metadata that
# would bloat the upload and aren't part of the served extension.
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
    return urlparse(target).scheme in ("http", "https")


def _resolve_extension_dir(target: str, json_output: bool) -> Path:
    """Resolve a load target to the extension's root directory.

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
                detail="An extension directory must contain a manifest.json.",
                json_output=json_output,
                exit_code=2,
            )
        return path
    cli_error(
        f"not an extension path: {target}",
        detail="Pass an extension directory, a manifest.json, or an http(s) URL.",
        json_output=json_output,
        exit_code=2,
    )


def _read_extension_id(extension_dir: Path, json_output: bool) -> str:
    """Parse and return the ``id`` field from an extension dir's manifest.json."""
    manifest_path = extension_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        cli_error(
            f"could not read manifest.json in {extension_dir}",
            detail=str(e),
            json_output=json_output,
            exit_code=2,
        )
    extension_id = manifest.get("id") if isinstance(manifest, dict) else None
    if not isinstance(extension_id, str) or not extension_id:
        cli_error(
            f"manifest.json is missing a string 'id': {manifest_path}",
            json_output=json_output,
            exit_code=2,
        )
    return extension_id


def _is_skipped(relative: Path) -> bool:
    """Skip dotfiles/dirs and known cache dirs anywhere in the relative path."""
    return any(part.startswith(".") or part in _SKIP_DIR_NAMES for part in relative.parts)


def _package_extension_files(extension_dir: Path, json_output: bool) -> list[ExtensionFile]:
    """Walk an extension dir and base64-encode every file for upload.

    Paths are stored relative to the extension root, POSIX-style, so the
    backend can recreate the tree regardless of the local OS. Dotfiles and
    cache dirs are skipped; the total encoded size is capped.
    """
    files: list[ExtensionFile] = []
    total_encoded = 0
    for entry in sorted(extension_dir.rglob("*")):
        if not entry.is_file():
            continue
        relative = entry.relative_to(extension_dir)
        if _is_skipped(relative):
            continue
        encoded = base64.b64encode(entry.read_bytes()).decode("ascii")
        total_encoded += len(encoded)
        if total_encoded > _MAX_PACKAGE_BYTES:
            cli_error(
                f"extension package exceeds {_MAX_PACKAGE_BYTES // (1024 * 1024)} MB",
                detail="Trim the extension directory (a stray build/cache dir is the usual cause).",
                json_output=json_output,
                exit_code=2,
            )
        files.append(ExtensionFile(path=relative.as_posix(), content_base_64=encoded))
    if not files:
        cli_error(f"extension directory is empty: {extension_dir}", json_output=json_output, exit_code=2)
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


def _parse_structured_error(content: bytes) -> tuple[str | None, str | None]:
    """Extract ``(code, message)`` from a backend error body, if it has them.

    The backend raises HTTPExceptions with ``detail={"code": ..., "message":
    ...}``, which FastAPI serializes as ``{"detail": {"code": ..., "message":
    ...}}``. Returns ``(None, None)`` for anything else, so callers can fall
    back to the raw body.
    """
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, dict):
        return None, None
    code = detail.get("code")
    message = detail.get("message")
    return (code if isinstance(code, str) else None, message if isinstance(message, str) else None)


def _backend_error(action: str, response: Any, json_output: bool) -> NoReturn:
    """Report a non-2xx backend response and exit.

    Surfaces the backend's structured ``{code, message}`` when present (as the
    message plus a machine-readable ``code`` in ``--json`` output) instead of
    dumping the raw JSON body as an opaque string.
    """
    status = int(response.status_code)
    code, message = _parse_structured_error(response.content)
    if message is not None:
        cli_error(message, code=code, json_output=json_output)
    cli_error(
        f"{action} failed (HTTP {status})",
        detail=response.content.decode(errors="replace"),
        json_output=json_output,
    )


def _check_command_status(response: Any, json_output: bool) -> ExtensionCommandResponse:
    """Map a command-endpoint response's status to errors, or return its body."""
    status = int(response.status_code)
    if not (HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES):
        _backend_error("extension command", response, json_output)
    body = response.parsed
    if not isinstance(body, ExtensionCommandResponse):
        cli_error(
            "unexpected response from the extension command endpoint",
            detail=response.content.decode(errors="replace"),
            json_output=json_output,
        )
    return body


def _send_command(
    *,
    op: ExtensionCommandRequestOp,
    workspace_id: str,
    client: AuthenticatedClient,
    json_output: bool,
    extension_id: str | None = None,
    source: str | None = None,
) -> ExtensionCommandResponse:
    """POST one extension command and return the validated aggregate response."""
    request = ExtensionCommandRequest(
        op=op,
        extension_id=extension_id if extension_id is not None else UNSET,
        source=source if source is not None else UNSET,
    )
    try:
        response = _post_extension_command.sync_detailed(workspace_id=workspace_id, client=client, body=request)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    return _check_command_status(response, json_output)


def _results_or_exit(response: ExtensionCommandResponse, json_output: bool) -> list[ExtensionCommandResult]:
    """Return the per-renderer results, erroring if no window answered.

    An empty ``results`` and "no windows connected" are the same condition on
    the wire, so name it with an explicit code rather than leaving ``--json``
    consumers to guess from an empty array.
    """
    results = response.results
    if isinstance(results, Unset) or not results:
        cli_error(
            "No Sculptor window responded. Is Sculptor running with extensions enabled?",
            code="no_windows_connected",
            json_output=json_output,
        )
    return results


def _preferred_result(results: list[ExtensionCommandResult]) -> ExtensionCommandResult:
    """Pick the renderer to report by default: first Electron window, else first."""
    for result in results:
        if result.renderer.environment == RendererIdentityEnvironment.ELECTRON:
            return result
    return results[0]


def _renderer_label(result: ExtensionCommandResult) -> str:
    """A compact ``environment short-id origin[base]`` label for a renderer.

    The base is appended only when it isn't the root, so a window running an
    OpenHost preview bundle reads as ``…example.com/proxy/51042/`` while the
    deployed app stays ``…example.com`` (they share the origin by design).
    """
    renderer = result.renderer
    short_id = renderer.renderer_id[:_RENDERER_ID_DISPLAY_LENGTH]
    base = _opt_str(renderer.base)
    suffix = base if base is not None and base != "/" else ""
    return f"{renderer.environment.value} {short_id} {renderer.origin}{suffix}"


def _opt_str(value: None | str | Unset) -> str | None:
    """Collapse a generated optional (UNSET/None/str) to str | None."""
    if isinstance(value, Unset) or value is None:
        return None
    return value


def _print_snapshot(snapshot: ExtensionSnapshot, *, indent: str = "  ") -> None:
    """Render one extension snapshot. Only key NAMES are printed, never values."""
    typer.echo(f"{indent}{snapshot.extension_id}  [{snapshot.status.value}]  origin={snapshot.origin.value}")
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


def _print_result_extensions(result: ExtensionCommandResult) -> None:
    """Print the extension snapshots carried by a list/inspect result."""
    extensions = result.extensions
    if isinstance(extensions, Unset) or not extensions:
        typer.echo("  (no extensions)")
        return
    for snapshot in extensions:
        _print_snapshot(snapshot)


def _emit_json(response: ExtensionCommandResponse) -> None:
    """Dump the full aggregate response (all renderer results) as JSON."""
    typer.echo(json.dumps(response.to_dict()))


def _report_mutation(
    response: ExtensionCommandResponse,
    *,
    action: str,
    json_output: bool,
    show_all: bool,
) -> None:
    """Render load/reload/unload outcomes and exit non-zero on any failure.

    Default: report the preferred (Electron) renderer and note the rest.
    ``--all``: report every renderer and fail if any reports ``ok=False``.
    """
    # Check for the no-windows case BEFORE emitting: otherwise --json would
    # print the empty aggregate response AND then a second error document.
    results = _results_or_exit(response, json_output)
    if json_output:
        _emit_json(response)

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
    response: ExtensionCommandResponse,
    *,
    json_output: bool,
    show_all: bool,
) -> None:
    """Render list/inspect outcomes (read-only; never exits on ok=False)."""
    # No-windows check first, even for --json: a bare `"results": []` is
    # indistinguishable from success against zero windows, so name the
    # condition (and exit non-zero) instead of emitting it.
    results = _results_or_exit(response, json_output)
    if json_output:
        _emit_json(response)
        return

    if show_all:
        for result in results:
            typer.echo(_renderer_label(result))
            _print_result_extensions(result)
        return

    chosen = _preferred_result(results)
    typer.echo(_renderer_label(chosen))
    _print_result_extensions(chosen)
    if len(results) > 1:
        typer.echo(
            f"({len(results)} windows connected; showing {chosen.renderer.environment.value}; use --all to see all)"
        )


@extension_app.command("load")
def load(
    target: str = typer.Argument(..., help="Local extension directory / manifest.json, or an http(s) manifest URL."),
    persist: bool = typer.Option(
        False,
        "--persist",
        help="For a local path: install permanently (top-level) instead of as a workspace-scoped dev install. No effect for a URL, which is always a persistent source.",
    ),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Package and load an extension into the live UI.

    A local path is packaged and uploaded to the backend, then loaded from the
    resulting manifest URL. An http(s) URL is loaded directly (no packaging) and
    is always registered as a persistent source, so ``--persist`` only affects
    the local-path case.
    """
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)

    if _is_url(target):
        source = target
    else:
        extension_dir = _resolve_extension_dir(target, json_output)
        extension_id = _read_extension_id(extension_dir, json_output)
        files = _package_extension_files(extension_dir, json_output)
        install_request = InstallExtensionRequest(extension_id=extension_id, files=files, persist=persist)
        try:
            install_response = _post_extension_install.sync_detailed(
                workspace_id=workspace_id, client=client, body=install_request
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            handle_connection_error(json_output)
        install_status = int(install_response.status_code)
        if not (HTTPStatus.OK <= install_status < HTTPStatus.MULTIPLE_CHOICES) or install_response.parsed is None:
            _backend_error("upload", install_response, json_output)
        source = install_response.parsed.manifest_url

    response = _send_command(
        op=ExtensionCommandRequestOp.LOAD,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        source=source,
    )
    _report_mutation(response, action="load", json_output=json_output, show_all=show_all)


@extension_app.command("reload")
def reload(
    extension_id: str = typer.Argument(..., help="ID of the loaded extension to reload (cache-busts its source)."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Reload an already-loaded extension, re-fetching its source."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=ExtensionCommandRequestOp.RELOAD,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        extension_id=extension_id,
    )
    _report_mutation(response, action="reload", json_output=json_output, show_all=show_all)


@extension_app.command("unload")
def unload(
    extension_id: str = typer.Argument(..., help="ID of the loaded extension to unload from the UI."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Unload an extension from the live UI (leaves any installed files in place)."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=ExtensionCommandRequestOp.UNLOAD,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        extension_id=extension_id,
    )
    _report_mutation(response, action="unload", json_output=json_output, show_all=show_all)


@extension_app.command("remove")
def remove(
    extension_id: str = typer.Argument(..., help="ID of the dev-installed extension to unload and delete."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
) -> None:
    """Unload an extension and delete its workspace-scoped dev install files."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)

    # Best-effort unload first so the live UI drops the extension before its
    # files vanish; a failure here (e.g. it wasn't loaded) shouldn't block
    # cleanup.
    try:
        unload_request = ExtensionCommandRequest(op=ExtensionCommandRequestOp.UNLOAD, extension_id=extension_id)
        _post_extension_command.sync_detailed(workspace_id=workspace_id, client=client, body=unload_request)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)

    try:
        remove_response = _post_extension_remove.sync_detailed(
            workspace_id=workspace_id, extension_id=extension_id, client=client
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    status = int(remove_response.status_code)
    if not (HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES):
        _backend_error("remove", remove_response, json_output)
    if json_output:
        typer.echo(json.dumps({"ok": True, "extension_id": extension_id}))
    else:
        typer.echo(f"removed dev install: {extension_id}")


@extension_app.command("list")
def list_extensions(
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """List the extensions each connected window currently knows about."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=ExtensionCommandRequestOp.LIST,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
    )
    _report_snapshots(response, json_output=json_output, show_all=show_all)


@extension_app.command("inspect")
def inspect(
    extension_id: str = typer.Argument(..., help="ID of the extension to inspect."),
    workspace: str | None = _WORKSPACE_OPTION,
    json_output: bool = _JSON_OPTION,
    show_all: bool = _ALL_OPTION,
) -> None:
    """Show one extension's status, registrations, and config key names."""
    workspace_id = _resolve_workspace_id(workspace, json_output)
    client = _client_or_exit(json_output)
    response = _send_command(
        op=ExtensionCommandRequestOp.INSPECT,
        workspace_id=workspace_id,
        client=client,
        json_output=json_output,
        extension_id=extension_id,
    )
    _report_snapshots(response, json_output=json_output, show_all=show_all)


@extension_app.command("dir")
def dir_command(
    json_output: bool = _JSON_OPTION,
) -> None:
    """Print the directory Sculptor scans for drop-in (persistent) extensions."""
    client = _client_or_exit(json_output)
    try:
        response = _get_local_extensions_directory.sync_detailed(client=client)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        handle_connection_error(json_output)
    status = int(response.status_code)
    if not (HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES) or response.parsed is None:
        _backend_error("extensions directory lookup", response, json_output)
    if json_output:
        typer.echo(json.dumps({"path": response.parsed.path}))
    else:
        typer.echo(response.parsed.path)
