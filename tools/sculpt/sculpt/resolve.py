"""Repo resolution and prefix matching utilities for the sculpt CLI."""

import json
import os
import subprocess
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import TypeVar

import httpx
import typer

from sculpt.auth import get_authenticated_client
from sculpt.client import Client
from sculpt.client.api.default import initialize_project
from sculpt.client.api.default import list_projects
from sculpt.client.api.default import list_recent_workspaces
from sculpt.client.api.default import resolve_agent_by_prefix
from sculpt.client.models.http_validation_error import HTTPValidationError
from sculpt.client.models.project import Project
from sculpt.client.models.project_initialization_request import ProjectInitializationRequest
from sculpt.formatting import cli_error
from sculpt.formatting import handle_connection_error
from sculpt.formatting import truncate

T = TypeVar("T")


def _extract_detail(body: bytes) -> str | None:
    """Pull the FastAPI HTTPException `detail` out of an error response body."""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str):
            return detail
    return None


def resolve_agent_id(base_url: str, prefix_or_id: str, json_output: bool) -> str:
    """Resolve an agent prefix or full id to a full TaskID via the HTTP endpoint.

    Surfaces 404 as 'Agent not found', 409 as 'Ambiguous prefix', and
    connection errors via handle_connection_error. Returns the full id on 200.
    """
    if not prefix_or_id:
        # An empty prefix would resolve to `/api/v1/agents/by-prefix/`, which
        # doesn't match the typed route and falls through to the SPA static
        # handler (returns HTML 200). Short-circuit before the HTTP call.
        cli_error(f"Agent not found for '{prefix_or_id}'", json_output=json_output)
    client = get_authenticated_client(base_url, json_output)
    try:
        response = resolve_agent_by_prefix.sync_detailed(prefix=prefix_or_id, client=client)
    except httpx.ConnectError:
        handle_connection_error(json_output, base_url=base_url)
    if response.status_code == HTTPStatus.NOT_FOUND:
        cli_error(
            f"Agent not found for '{prefix_or_id}'",
            detail=wrong_id_kind_detail(prefix_or_id, "agent"),
            json_output=json_output,
        )
    if response.status_code == HTTPStatus.CONFLICT:
        # The server's detail string includes the matching ids; surface the full
        # message verbatim so the user can pick a longer prefix.
        cli_error(_extract_detail(response.content) or f"Ambiguous prefix '{prefix_or_id}'", json_output=json_output)
    if response.status_code != HTTPStatus.OK or response.parsed is None:
        cli_error(f"Failed to resolve agent prefix (status {response.status_code})", json_output=json_output)
    parsed = response.parsed
    if isinstance(parsed, HTTPValidationError):
        cli_error(f"Failed to resolve agent prefix '{prefix_or_id}'", json_output=json_output)
    return parsed.agent_id


def repo_path_from_url(url: str | None) -> str:
    """Strip the file:/// prefix from a user_git_repo_url to get the local path."""
    if url is None:
        return ""
    if url.startswith("file:///"):
        return url[len("file://") :]
    return url


def fetch_repo_path_lookup(client: Client) -> dict[str, str]:
    """Fetch all projects and return a mapping of project_id -> repo path."""
    projects = list_projects.sync(client=client)  # type: ignore[arg-type]
    if projects is None:
        return {}
    return {p.object_id: repo_path_from_url(p.user_git_repo_url) for p in projects}


def fetch_projects(client: Client, json_output: bool = False) -> list[Project]:
    """Fetch all projects from the API."""
    try:
        result = list_projects.sync(client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to list repos", detail="No response from server", json_output=json_output)

    return result


def resolve_project(repo: str | None, client: Client, json_output: bool = False) -> str:
    """Resolve a project ID through the priority chain: --repo > env var > cwd.

    Args:
        repo: Explicit repo path from --repo flag, or None.
        client: An authenticated API client.
        json_output: Whether to format errors as JSON.

    Returns:
        The resolved project ID string.
    """
    if repo is not None:
        return _resolve_from_repo(repo, client, json_output)

    project_id = os.environ.get("SCULPT_PROJECT_ID")
    if project_id is not None:
        typer.echo("Using repo from SCULPT_PROJECT_ID", err=True)
        return project_id

    return _resolve_from_cwd(client, json_output)


def _resolve_from_repo(repo: str, client: Client, json_output: bool = False) -> str:
    absolute_path = os.path.abspath(repo)
    request = ProjectInitializationRequest(project_path=absolute_path)

    try:
        response = initialize_project.sync_detailed(
            client=client,  # type: ignore[arg-type]
            body=request,
        )
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if response.status_code == HTTPStatus.OK:
        parsed = response.parsed
        if isinstance(parsed, Project):
            typer.echo(f"Initialized repo for {absolute_path}", err=True)
            return parsed.object_id

    detail = _extract_detail(response.content)

    if response.status_code == HTTPStatus.CONFLICT and detail is not None and "already added" in detail:
        # The server has the repo registered under a (possibly worktree-resolved)
        # canonical path. Reuse it so `sculpt run --repo X` and
        # `sculpt workspace create --repo X` are idempotent — without this,
        # any agent running inside a Sculptor worktree is funneled into an
        # unrecoverable error.
        existing = _find_existing_project_for_path(client, absolute_path)
        if existing is not None:
            typer.echo(f"Using existing repo for {absolute_path}", err=True)
            return existing
        # No matching project in the listing — fall through and surface
        # the 'already added' detail so the user has something to debug.

    if response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
        parsed = response.parsed
        cli_error("Validation error", detail=str(parsed), json_output=json_output)

    if detail is not None:
        cli_error(detail, json_output=json_output)
    cli_error(f"Failed to initialize repo (status {response.status_code})", json_output=json_output)


def _find_existing_project_for_path(client: Client, absolute_path: str) -> str | None:
    """Look up the registered project that owns ``absolute_path``, handling worktrees.

    The server resolves a worktree path back to the main repo via
    ``resolve_worktree_to_main_repo`` and matches against existing projects'
    canonical paths, so a direct equality check against the original
    ``absolute_path`` is not enough — we also try the git-resolved canonical
    path for the same directory.
    """
    try:
        id_to_path = fetch_repo_path_lookup(client)
    except httpx.ConnectError:
        return None
    if not id_to_path:
        return None

    candidate_paths = {absolute_path}
    canonical = _git_canonical_repo_path(absolute_path)
    if canonical is not None:
        candidate_paths.add(canonical)

    for project_id, project_path in id_to_path.items():
        if project_path and project_path in candidate_paths:
            return project_id
    return None


def _git_canonical_repo_path(path: str) -> str | None:
    """Resolve ``path`` to its main-repo root via git, returning None on failure.

    For worktrees, ``git rev-parse --git-common-dir`` points at the main repo's
    ``.git`` directory, whose parent is the main repo root. For non-worktree
    checkouts this equals ``--show-toplevel``. Returning the realpath keeps the
    comparison consistent with the server's ``Path(...).absolute()``.
    """
    try:
        common_dir = subprocess.run(
            ["git", "-C", path, "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if not common_dir:
        return None
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = Path(path) / common_path
    resolved = common_path.resolve()
    if resolved.name == ".git":
        return str(resolved.parent)
    # Bare repository — the common dir is the repo itself.
    return str(resolved)


def _resolve_from_cwd(client: Client, json_output: bool = False) -> str:
    cwd = os.getcwd()
    cwd_uri = f"file:///{cwd.lstrip('/')}"

    projects = fetch_projects(client, json_output)

    for project in projects:
        if project.user_git_repo_url == cwd_uri:
            typer.echo(f"Using repo from current directory: {cwd}", err=True)
            return project.object_id

    cli_error(
        f"No repo found for {cwd}",
        detail="Use --repo to create one, or set SCULPT_PROJECT_ID to an existing project id.",
        json_output=json_output,
    )


def find_prefix_matches(prefix: str, candidates: list[T], id_getter: Callable[[T], str]) -> list[T]:
    """Return the candidates whose ID starts with ``prefix``.

    An exact ID match wins outright (returns just that candidate), so a full ID
    is never reported as ambiguous even when it is a prefix of another ID.
    """
    matches: list[T] = []
    for candidate in candidates:
        candidate_id = id_getter(candidate)
        if candidate_id == prefix:
            return [candidate]
        if candidate_id.startswith(prefix):
            matches.append(candidate)
    return matches


# ID-type prefixes and the resource noun + CLI command group each belongs to,
# used to catch e.g. a workspace ID passed where an agent ID is expected.
_ID_KIND_BY_PREFIX = {
    "tsk_": ("agent", "sculpt agent"),
    "ws_": ("workspace", "sculpt workspace"),
    "prj_": ("repo", "sculpt repo"),
}

# Ambiguous-prefix errors list at most this many matches before eliding.
_MAX_AMBIGUOUS_MATCHES_SHOWN = 10

_AMBIGUOUS_LABEL_MAX_LENGTH = 40


def wrong_id_kind_detail(prefix: str, resource_noun: str) -> str:
    """A redirect hint when ``prefix`` carries another resource kind's ID prefix.

    Returns an empty string when the prefix doesn't look like a known ID kind,
    or already matches the expected kind (a plain not-found, not a mix-up).
    """
    for id_prefix, (noun, command_group) in _ID_KIND_BY_PREFIX.items():
        if prefix.startswith(id_prefix) and noun != resource_noun:
            article = "an" if noun[0] in "aeiou" else "a"
            return f"'{prefix}' looks like {article} {noun} ID — try `{command_group} show {prefix}`"
    return ""


def resolve_by_prefix(
    prefix: str,
    candidates: list[T],
    id_getter: Callable[[T], str],
    *,
    resource_noun: str = "resource",
    json_output: bool = False,
    label_getter: Callable[[T], str | None] | None = None,
    scope_description: str = "",
) -> T:
    """Find a unique candidate matching the given ID prefix, or exit with an error.

    Args:
        prefix: The user-provided ID prefix.
        candidates: List of candidate objects to search.
        id_getter: Callable that extracts the ID string from a candidate.
        resource_noun: What the candidates are ("agent", "workspace", ...), for
            error messages.
        json_output: Whether to format errors as JSON.
        label_getter: Optional callable extracting a human label (title,
            description) shown next to each ID in ambiguity errors.
        scope_description: Where the search looked (e.g. "workspace ws_123"),
            appended to the not-found message so a scoped miss is
            distinguishable from the resource not existing at all.

    Returns:
        The unique matching candidate.
    """
    matches = find_prefix_matches(prefix, candidates, id_getter)

    if len(matches) == 1:
        return matches[0]

    if not matches:
        scope_suffix = f" in {scope_description}" if scope_description else ""
        cli_error(
            f"No {resource_noun} matches '{prefix}'{scope_suffix}",
            detail=wrong_id_kind_detail(prefix, resource_noun),
            json_output=json_output,
        )

    lines = []
    for match in matches[:_MAX_AMBIGUOUS_MATCHES_SHOWN]:
        label = label_getter(match) if label_getter is not None else None
        if label:
            lines.append(f"  {id_getter(match)}  {truncate(label, _AMBIGUOUS_LABEL_MAX_LENGTH)}")
        else:
            lines.append(f"  {id_getter(match)}")
    elided = len(matches) - _MAX_AMBIGUOUS_MATCHES_SHOWN
    if elided > 0:
        lines.append(f"  ... and {elided} more")
    cli_error(
        f"Ambiguous prefix '{prefix}' matches {len(matches)} {resource_noun}s",
        detail="\n".join(lines),
        json_output=json_output,
    )


def find_workspace_id(client: Client, workspace_id_or_prefix: str, json_output: bool = False) -> str | None:
    """Resolve a workspace ID prefix leniently: None on a miss instead of exiting.

    For scope hints like ``SCULPT_WORKSPACE_ID``, where a stale value (the
    workspace was deleted after the shell started) should mean "no scope"
    rather than a hard failure. Connection errors still exit.
    """
    try:
        result = list_recent_workspaces.sync(client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        return None

    matches = find_prefix_matches(workspace_id_or_prefix, result.workspaces, lambda w: w.object_id)
    if len(matches) == 1:
        return matches[0].object_id
    return None


def resolve_workspace_id(client: Client, workspace_id_or_prefix: str, json_output: bool = False) -> str:
    """Resolve a workspace ID prefix to a full workspace ID.

    Fetches all workspaces and uses prefix matching to find the unique workspace.

    Args:
        client: An authenticated API client.
        workspace_id_or_prefix: A full or prefix workspace ID.
        json_output: Whether to format errors as JSON.

    Returns:
        The full workspace ID string.
    """
    try:
        result = list_recent_workspaces.sync(client=client)  # type: ignore[arg-type]
    except httpx.ConnectError:
        handle_connection_error(json_output)

    if result is None:
        cli_error("Failed to list workspaces", detail="No response from server", json_output=json_output)

    ws = resolve_by_prefix(
        workspace_id_or_prefix,
        result.workspaces,
        lambda w: w.object_id,
        resource_noun="workspace",
        json_output=json_output,
        label_getter=lambda w: w.description,
    )
    return ws.object_id
