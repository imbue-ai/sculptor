"""Backend routes + helpers for the Add Repository → GitHub/GitLab flow.

Three FastAPI routes live here:

  * ``GET /api/v1/config/backend-capabilities`` — returns the absolute path
    of the default clones parent dir so the dialog's per-provider default
    can be built without hardcoding ``~/.sculptor/repos``.
  * ``GET /api/v1/remotes/{provider}/repos`` — searches the user's
    accessible repos on GitHub or GitLab via ``gh``/``glab``. GitHub +
    query paginates through ``/user/repos`` so older repos beyond the
    top-100 are still findable.
  * ``POST /api/v1/remotes/clone`` — clones a remote repo into
    ``target_dir/name`` using the provider CLI when available (so the
    user's stored credentials are honored) or falling back to ``git
    clone`` with ``GIT_TERMINAL_PROMPT=0`` when the CLI is missing.

Module-level helpers (``_parse_github_repos``, ``_search_github_user_repos``,
``_looks_like_already_exists`` etc.) are exercised directly from
``remote_repos_test.py`` — kept in this file so the test suite can import
them without dragging in ``app.py``'s wider dependency graph.
"""

import json
import os
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.subprocess_utils import ProcessTimeoutError
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.dependency_management_service import Dependency
from sculptor.utils.build import get_sculptor_folder
from sculptor.web.auth import UserSession
from sculptor.web.data_types import BackendCapabilities
from sculptor.web.data_types import RemoteCloneRequest
from sculptor.web.data_types import RemoteCloneResponse
from sculptor.web.data_types import RemoteRepo
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_root_concurrency_group
from sculptor.web.middleware import get_services_from_request_or_websocket
from sculptor.web.middleware import get_user_session

# Own router so app.py can include it without import gymnastics. Uses the
# same DecoratedAPIRouter as the main router so the logging context decorator
# fires consistently across every Sculptor route.
remote_repos_router = DecoratedAPIRouter(decorator=add_logging_context)


_REMOTE_REPO_LIST_TIMEOUT_SECONDS = 10.0
_REMOTE_REPO_DEFAULT_LIMIT = 50
_REMOTE_REPO_MAX_LIMIT = 100
# When the GitHub query needs filtering, we walk /user/repos one page at a
# time. Bound total subprocess fanout so a prolific user can't trigger N gh
# calls per keystroke. 5 pages × 100 = 500 repos searched in the worst case.
_REMOTE_REPO_MAX_SEARCH_PAGES = 5
_REMOTE_CLONE_TIMEOUT_SECONDS = 300.0
_REMOTE_PROVIDERS: tuple[str, ...] = ("github", "gitlab")


@remote_repos_router.get("/api/v1/config/backend-capabilities")
def get_backend_capabilities(
    user_session: UserSession = Depends(get_user_session),
) -> BackendCapabilities:
    """Return backend-owned capability values for the frontend.

    Today this only carries ``default_clones_dir`` (the parent of per-provider
    clone directories used by the Add Repository → GitHub/GitLab flow). Other
    capability flags remain frontend-resolved.
    """
    return BackendCapabilities(default_clones_dir=str(get_sculptor_folder() / "repos"))


def _resolve_provider_cli(request: Request, provider: str) -> tuple[str, Dependency]:
    """Resolve the gh/glab binary path for *provider*, raising HTTP 412 if missing or unauthenticated."""
    if provider not in _REMOTE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    tool = Dependency.GH if provider == "github" else Dependency.GLAB
    services = get_services_from_request_or_websocket(request)
    binary = services.dependency_management_service.resolve_binary_path(tool)
    if binary is None:
        raise HTTPException(status_code=412, detail=f"{tool.value} CLI not installed")
    if services.dependency_management_service.check_authenticated(tool) is False:
        raise HTTPException(status_code=412, detail=f"{tool.value} CLI not authenticated")
    return binary, tool


def _parse_github_repos(payload: Any) -> list[RemoteRepo]:
    """Convert the GitHub ``/user/repos`` JSON response into ``RemoteRepo`` rows."""
    if not isinstance(payload, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub response shape")
    repos: list[RemoteRepo] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        repos.append(
            RemoteRepo(
                full_name=str(entry.get("full_name", "")),
                clone_url=str(entry.get("clone_url", "")),
                ssh_url=str(entry.get("ssh_url", "")),
                is_private=bool(entry.get("private", False)),
                pushed_at=entry.get("pushed_at"),
                description=entry.get("description"),
            )
        )
    return repos


def _parse_gitlab_repos(payload: Any) -> list[RemoteRepo]:
    """Convert the GitLab ``/projects`` JSON response into ``RemoteRepo`` rows."""
    if not isinstance(payload, list):
        raise HTTPException(status_code=502, detail="Unexpected GitLab response shape")
    repos: list[RemoteRepo] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        repos.append(
            RemoteRepo(
                full_name=str(entry.get("path_with_namespace", "")),
                clone_url=str(entry.get("http_url_to_repo", "")),
                ssh_url=str(entry.get("ssh_url_to_repo", "")),
                is_private=str(entry.get("visibility", "")).lower() == "private",
                pushed_at=entry.get("last_activity_at"),
                description=entry.get("description"),
            )
        )
    return repos


def _filter_remote_repos(repos: list[RemoteRepo], query: str | None) -> list[RemoteRepo]:
    """Case-insensitive substring filter over ``full_name`` and ``description``."""
    if not query or not query.strip():
        return repos
    needle = query.strip().lower()
    matches: list[RemoteRepo] = []
    for repo in repos:
        haystack = f"{repo.full_name} {repo.description or ''}".lower()
        if needle in haystack:
            matches.append(repo)
    return matches


def _build_remote_repos_api_path(tool: Dependency, q: str | None, display_limit: int) -> str:
    """Build the ``gh``/``glab api`` path for the single-fetch case.

    Used for:
      * Empty query on either provider (browse mode).
      * GitLab + query (server-side ``?search=`` handles filtering).

    GitHub + query is paginated separately — see ``_search_github_user_repos``.
    """
    capped_display = max(1, min(display_limit, _REMOTE_REPO_MAX_LIMIT))

    if tool == Dependency.GH:
        return f"/user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&per_page={capped_display}"

    # gitlab.com returns HTTP 500 for ``/projects?membership=true&order_by=last_activity_at``
    # when no ``search=`` filter narrows the membership set — the cross-table
    # sort over every member project is too expensive. ``order_by=created_at``
    # is cheap on the same scope (the projects table is already indexed that
    # way), so use it in browse mode and only ask for ``last_activity_at``
    # ordering when ``search=`` bounds the set being sorted.
    if q and q.strip():
        encoded_query = urllib.parse.quote(q.strip(), safe="")
        return f"/projects?membership=true&order_by=last_activity_at&per_page={capped_display}&search={encoded_query}"
    return f"/projects?membership=true&order_by=created_at&per_page={capped_display}"


def _github_user_repos_page_path(page: int) -> str:
    """One page of ``/user/repos`` at the API's max page size."""
    return f"/user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&per_page={_REMOTE_REPO_MAX_LIMIT}&page={page}"


def _fetch_repos(
    binary: str,
    concurrency_group: ConcurrencyGroup,
    api_path: str,
    tool: Dependency,
) -> list[RemoteRepo]:
    """Run ``gh``/``glab api <api_path>``, parse, return repos.

    Wraps subprocess and JSON failures as HTTP 502 so upstream errors surface
    in the combobox instead of bubbling as 500s.
    """
    try:
        result = concurrency_group.run_process_to_completion(
            [binary, "api", api_path],
            timeout=_REMOTE_REPO_LIST_TIMEOUT_SECONDS,
        )
    except ProcessError as e:
        detail = e.stderr.strip() or f"{tool.value} api failed with exit code {e.returncode}"
        raise HTTPException(status_code=502, detail=detail) from e
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Invalid JSON from {tool.value}: {e}") from e
    parser = _parse_github_repos if tool == Dependency.GH else _parse_gitlab_repos
    return parser(payload)


def _search_github_user_repos(
    query: str,
    needed: int,
    fetch_page: Callable[[int], list[RemoteRepo]],
) -> list[RemoteRepo]:
    """Paginate ``/user/repos`` until enough matches accumulate or data runs out.

    Stops on the first of:
      * ``needed`` matches accumulated (return early so we don't spam ``gh``).
      * Last page came back smaller than ``_REMOTE_REPO_MAX_LIMIT`` (end of data).
      * ``_REMOTE_REPO_MAX_SEARCH_PAGES`` reached (page cap).

    ``fetch_page`` is injected so the pagination logic stays unit-testable
    without a live ``gh`` process.
    """
    matches: list[RemoteRepo] = []
    for page in range(1, _REMOTE_REPO_MAX_SEARCH_PAGES + 1):
        page_repos = fetch_page(page)
        matches.extend(_filter_remote_repos(page_repos, query))
        if len(matches) >= needed:
            break
        if len(page_repos) < _REMOTE_REPO_MAX_LIMIT:
            break
    return matches


@remote_repos_router.get("/api/v1/remotes/{provider}/repos")
def list_remote_repos(
    provider: str,
    request: Request,
    q: str | None = None,
    limit: int = _REMOTE_REPO_DEFAULT_LIMIT,
    user_session: UserSession = Depends(get_user_session),
) -> list[RemoteRepo]:
    """Search the user's accessible repos on GitHub or GitLab via ``gh``/``glab``.

    Scope is always ``affiliation=owner,collaborator,organization_member`` on
    GitHub and ``membership=true`` on GitLab — we never reach into repos the
    user can't already see. GitHub + query paginates so older repos (beyond
    the top-100 by recency) are still findable.
    """
    binary, tool = _resolve_provider_cli(request, provider)
    capped_limit = max(1, min(limit, _REMOTE_REPO_MAX_LIMIT))
    has_query = bool(q and q.strip())

    logger.debug("Listing remote repos via {} for provider={}", tool.value, provider)
    root_concurrency_group = get_root_concurrency_group(request)
    with root_concurrency_group.make_concurrency_group(name="list_remote_repos") as concurrency_group:
        if tool == Dependency.GH and has_query:
            assert q is not None

            def fetch_page(page: int) -> list[RemoteRepo]:
                return _fetch_repos(binary, concurrency_group, _github_user_repos_page_path(page), tool)

            repos = _search_github_user_repos(q, capped_limit, fetch_page)
        else:
            api_path = _build_remote_repos_api_path(tool, q, capped_limit)
            repos = _fetch_repos(binary, concurrency_group, api_path, tool)

    return repos[:capped_limit]


def _resolve_clone_command(
    services: CompleteServiceCollection,
    provider: str,
    url: str,
    full_name: str | None,
    target_path: Path,
) -> tuple[list[str], dict[str, str]]:
    """Build the clone command + env for *provider*.

    Prefer the provider's own CLI so the call inherits the user's existing
    auth session. Without that, `git clone https://...` would prompt for a
    username/password and hang indefinitely on private repos. As a final
    fallback, `git clone` runs with ``GIT_TERMINAL_PROMPT=0`` so it fails
    fast instead of hanging when no credentials are configured.

    When ``full_name`` is supplied (picker flow), pass the ``owner/repo`` slug
    instead of the URL. ``glab repo clone <https-url>`` forces git into an
    HTTPS auth flow that fails for users whose ``glab`` is configured for
    SSH; passing the slug lets ``glab`` honor its configured protocol. The
    manual-URL flow has no slug, so we still pass the URL.
    """
    cli_tool = Dependency.GH if provider == "github" else Dependency.GLAB
    cli_binary = services.dependency_management_service.resolve_binary_path(cli_tool)
    # Treat `None` (probe timed out / couldn't determine) the same as
    # `_resolve_provider_cli` does: assume the CLI is usable. Falling back to
    # `git clone` on `None` silently fails private-repo clones because
    # `GIT_TERMINAL_PROMPT=0` blocks the credential prompt — and we already
    # let the user list those repos via the same `None` policy, so a clone
    # refusal here would be a surprising regression.
    if cli_binary is not None and services.dependency_management_service.check_authenticated(cli_tool) is not False:
        clone_source = full_name if full_name else url
        return [cli_binary, "repo", "clone", clone_source, str(target_path)], {}

    git_binary = services.dependency_management_service.resolve_binary_path(Dependency.GIT)
    if git_binary is None:
        raise HTTPException(status_code=412, detail="git CLI not installed")
    return [git_binary, "clone", url, str(target_path)], {"GIT_TERMINAL_PROMPT": "0"}


def _looks_like_already_exists(stderr: str) -> bool:
    """Heuristic: does this clone-failure stderr indicate a destination conflict?"""
    lowered = stderr.lower()
    return "already exists" in lowered or "not an empty directory" in lowered


@remote_repos_router.post("/api/v1/remotes/clone")
def clone_remote_repo(
    clone_request: RemoteCloneRequest,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> RemoteCloneResponse:
    """Clone a remote git repository into ``target_dir/name``."""
    services = get_services_from_request_or_websocket(request)

    target_dir = Path(clone_request.target_dir).expanduser()
    target_path = target_dir / clone_request.name

    # Pre-flight check: bail out fast with a 409 if the destination already
    # exists. Without this we spawn the clone subprocess, gh / git eventually
    # fails with "destination already exists", and the user waits — or, if
    # the subprocess hangs for another reason, the browser fetch times out
    # and surfaces a generic "Failed to fetch" that hides the real cause.
    # There's a tiny TOCTOU window between this and the clone, but the
    # post-clone stderr check below still maps any "already exists" report
    # back to 409, so the race is recoverable.
    if target_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"{target_path} already exists.",
        )

    # Always create the parent. The user typed or accepted this path in the
    # Add Repository dialog, so creating it on their behalf is the expected
    # outcome — and the previous "must sit under ~/.sculptor/repos" guard
    # rejected legitimate paths in dev mode, where get_sculptor_folder()
    # returns the repo-local .dev_sculptor/ rather than the frontend's
    # ~/.sculptor/repos literal.
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not create target directory {target_dir}: {e}",
        ) from e

    command, extra_env = _resolve_clone_command(
        services, clone_request.provider, clone_request.url, clone_request.full_name, target_path
    )
    logger.info("Cloning {} into {} via {}", clone_request.url, target_path, command[0])
    root_concurrency_group = get_root_concurrency_group(request)
    # Capture the failure inside the `with` and raise the HTTPException after
    # it exits. Raising inside lets ConcurrencyExceptionGroup wrap the
    # HTTPException on __exit__, which FastAPI surfaces as a 500 instead of
    # the intended 4xx/5xx status code.
    clone_error: tuple[int, str, Exception] | None = None
    result = None
    with root_concurrency_group.make_concurrency_group(name="clone_remote_repo") as concurrency_group:
        try:
            result = concurrency_group.run_process_to_completion(
                command,
                timeout=_REMOTE_CLONE_TIMEOUT_SECONDS,
                env={**os.environ, **extra_env} if extra_env else None,
            )
        except ProcessTimeoutError as e:
            # Must come before ProcessError — ProcessTimeoutError ⊂ ProcessError,
            # so the broader arm would otherwise catch timeouts as 400.
            timeout_seconds = int(_REMOTE_CLONE_TIMEOUT_SECONDS)
            clone_error = (
                504,
                f"Clone timed out after {timeout_seconds}s. If the repo is private, check that gh/glab is signed in.",
                e,
            )
        except ProcessError as e:
            detail = e.stderr.strip() or f"clone failed with exit code {e.returncode}"
            status_code = 409 if _looks_like_already_exists(detail) else 400
            clone_error = (status_code, detail, e)

    if clone_error is not None:
        status_code, detail, cause = clone_error
        raise HTTPException(status_code=status_code, detail=detail) from cause

    assert result is not None
    if result.stderr:
        logger.debug("clone stderr: {}", result.stderr.strip())

    return RemoteCloneResponse(project_path=str(target_path))
