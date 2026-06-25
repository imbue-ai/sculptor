from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi import Request
from fastapi.testclient import TestClient

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.subprocess_utils import ProcessTimeoutError
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.dependency_management_service import Dependency
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.utils.build import get_sculptor_folder
from sculptor.web.data_types import RemoteRepo
from sculptor.web.remote_repos import _REMOTE_CLONE_TIMEOUT_SECONDS
from sculptor.web.remote_repos import _REMOTE_REPO_MAX_LIMIT
from sculptor.web.remote_repos import _REMOTE_REPO_MAX_SEARCH_PAGES
from sculptor.web.remote_repos import _build_remote_repos_api_path
from sculptor.web.remote_repos import _filter_remote_repos
from sculptor.web.remote_repos import _github_user_repos_page_path
from sculptor.web.remote_repos import _is_safe_clone_name
from sculptor.web.remote_repos import _is_safe_clone_url
from sculptor.web.remote_repos import _is_safe_repo_slug
from sculptor.web.remote_repos import _is_safe_target_path
from sculptor.web.remote_repos import _looks_like_already_exists
from sculptor.web.remote_repos import _parse_github_repos
from sculptor.web.remote_repos import _redact_url_credentials
from sculptor.web.remote_repos import _resolve_provider_cli
from sculptor.web.remote_repos import _search_github_user_repos


def _repo(full_name: str, description: str | None = None) -> RemoteRepo:
    return RemoteRepo(
        full_name=full_name,
        clone_url=f"https://example.com/{full_name}.git",
        ssh_url=f"git@example.com:{full_name}.git",
        is_private=False,
        pushed_at=None,
        description=description,
    )


# --- _build_remote_repos_api_path: GitHub (browse mode) ---


def test_github_browse_uses_display_limit_per_page() -> None:
    """Browse mode (empty query) asks for just enough rows for the dropdown."""
    path = _build_remote_repos_api_path(5)
    assert path == "/user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&per_page=5"


def test_github_browse_caps_per_page_at_api_max() -> None:
    path = _build_remote_repos_api_path(10_000)
    assert (
        path
        == f"/user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&per_page={_REMOTE_REPO_MAX_LIMIT}"
    )


# --- _github_user_repos_page_path (paginated search) ---


def test_github_page_path_first_page() -> None:
    assert (
        _github_user_repos_page_path(1)
        == "/user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&per_page=100&page=1"
    )


def test_github_page_path_later_page() -> None:
    """Pagination must increment ``page=`` while keeping per_page at the API max."""
    assert (
        _github_user_repos_page_path(3)
        == "/user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&per_page=100&page=3"
    )


def test_github_paged_search_stays_scoped_to_user_repos() -> None:
    """The path must not switch to /search/repositories — that would span all
    of GitHub, surfacing repos the user has no relationship with."""
    path = _github_user_repos_page_path(1)
    assert "/search/repositories" not in path
    assert "affiliation=owner,collaborator,organization_member" in path


# --- _filter_remote_repos ---


def test_filter_returns_all_on_empty_query() -> None:
    repos = [_repo("a/one"), _repo("b/two")]
    assert _filter_remote_repos(repos, None) == repos
    assert _filter_remote_repos(repos, "") == repos
    assert _filter_remote_repos(repos, "   ") == repos


def test_filter_matches_full_name_case_insensitively() -> None:
    repos = [_repo("sfcompute/cli"), _repo("imbue-ai/sculptor"), _repo("octocat/Hello-World")]
    matches = _filter_remote_repos(repos, "CLI")
    assert [r.full_name for r in matches] == ["sfcompute/cli"]


def test_filter_matches_description_substring() -> None:
    repos = [
        _repo("a/one", description="a command-line interface for foo"),
        _repo("b/two", description="unrelated"),
    ]
    matches = _filter_remote_repos(repos, "command-line")
    assert [r.full_name for r in matches] == ["a/one"]


def test_filter_matches_owner_slash_name_substring() -> None:
    """Typing ``sfcompute/cli`` should pick out that exact repo from a list."""
    repos = [_repo("sfcompute/cli"), _repo("sfcompute/other"), _repo("notsf/cli")]
    matches = _filter_remote_repos(repos, "sfcompute/cli")
    assert [r.full_name for r in matches] == ["sfcompute/cli"]


def test_filter_handles_none_description_without_crashing() -> None:
    """A repo with ``description=None`` (the API default) must not crash the
    substring filter — it should still match on ``full_name`` alone."""
    repos = [_repo("sfcompute/cli", description=None), _repo("other/repo", description=None)]
    matches = _filter_remote_repos(repos, "cli")
    assert [r.full_name for r in matches] == ["sfcompute/cli"]


# --- _search_github_user_repos (pagination orchestration) ---


def _full_page(prefix: str, count: int = _REMOTE_REPO_MAX_LIMIT) -> list[RemoteRepo]:
    """A page filled to the API max so pagination won't stop on end-of-data."""
    return [_repo(f"{prefix}/repo-{i}") for i in range(count)]


def test_pagination_stops_when_enough_matches_in_first_page() -> None:
    """One full page with ≥ needed matches → only one fetch, no further pages."""
    calls: list[int] = []

    def fetch_page(page: int) -> list[RemoteRepo]:
        calls.append(page)
        # All 100 rows on page 1 match the query.
        return _full_page("matches-here")

    matches = _search_github_user_repos("matches-here", needed=5, fetch_page=fetch_page)
    assert calls == [1]
    assert len(matches) == _REMOTE_REPO_MAX_LIMIT  # all matched; caller slices to ``needed``


def test_pagination_keeps_pulling_until_enough_matches() -> None:
    """Page 1 has 0 matches, page 2 has 3, page 3 finally pushes us over 5."""
    pages = {
        1: _full_page("aaa"),  # nothing matches "needle"
        2: _full_page("aaa")[:97] + [_repo("needle/one"), _repo("needle/two"), _repo("needle/three")],
        3: _full_page("aaa")[:97] + [_repo("needle/four"), _repo("needle/five"), _repo("needle/six")],
    }
    calls: list[int] = []

    def fetch_page(page: int) -> list[RemoteRepo]:
        calls.append(page)
        return pages[page]

    matches = _search_github_user_repos("needle", needed=5, fetch_page=fetch_page)
    assert calls == [1, 2, 3]
    # All 6 matches across pages 2+3 returned; caller slices to ``needed``.
    assert [r.full_name for r in matches] == [
        "needle/one",
        "needle/two",
        "needle/three",
        "needle/four",
        "needle/five",
        "needle/six",
    ]


def test_pagination_stops_on_partial_last_page() -> None:
    """A short page (< 100) means GitHub has no more repos for this user, so
    don't keep paging — even if we don't have enough matches yet."""
    pages = {
        1: _full_page("aaa"),  # 100 rows, no matches
        2: [_repo("aaa/last1"), _repo("aaa/last2")],  # 2 rows, no matches → end of data
    }
    calls: list[int] = []

    def fetch_page(page: int) -> list[RemoteRepo]:
        calls.append(page)
        return pages[page]

    matches = _search_github_user_repos("needle", needed=5, fetch_page=fetch_page)
    assert calls == [1, 2]
    assert matches == []


def test_pagination_stops_at_page_cap_even_without_matches() -> None:
    """Bound subprocess fanout: never call gh more than ``_REMOTE_REPO_MAX_SEARCH_PAGES``
    times for a single query, even if every page is full and matchless."""
    calls: list[int] = []

    def fetch_page(page: int) -> list[RemoteRepo]:
        calls.append(page)
        return _full_page("aaa")  # always full, never matches "needle"

    matches = _search_github_user_repos("needle", needed=5, fetch_page=fetch_page)
    assert calls == list(range(1, _REMOTE_REPO_MAX_SEARCH_PAGES + 1))
    assert matches == []


def test_pagination_filters_each_page_with_query() -> None:
    """Per-page filtering: only the matching rows from each page accumulate."""
    # Pages 1+2 are full so pagination continues; the named repos sit among
    # ``aaa/repo-*`` filler that doesn't match the query.
    pages = {
        1: _full_page("aaa")[:99] + [_repo("sfcompute/cli")],
        2: _full_page("aaa")[:98] + [_repo("sfcompute/sdk"), _repo("sfcompute/cli-extras")],
        3: [_repo("unrelated/x")],  # partial → end of data; loop stops here
    }

    def fetch_page(page: int) -> list[RemoteRepo]:
        return pages[page]

    matches = _search_github_user_repos("sfcompute", needed=5, fetch_page=fetch_page)
    assert [r.full_name for r in matches] == ["sfcompute/cli", "sfcompute/sdk", "sfcompute/cli-extras"]


# --- _parse_github_repos ---


def test_parse_github_repos_raises_502_on_non_list_payload() -> None:
    """Anything other than a JSON array means GitHub returned something we
    don't understand — bail out with a 502 rather than coercing."""
    for payload in (None, {"items": []}, "oops", 42):
        with pytest.raises(HTTPException) as exc_info:
            _parse_github_repos(payload)
        assert exc_info.value.status_code == 502


def test_parse_github_repos_skips_non_dict_entries() -> None:
    payload = [None, "string", 42, {"full_name": "ok/repo", "clone_url": "https://example.com/ok/repo.git"}]
    repos = _parse_github_repos(payload)
    assert [r.full_name for r in repos] == ["ok/repo"]


def test_parse_github_repos_maps_every_field_from_input() -> None:
    """Pin the field mapping so a future rename on GitHub's side gets caught."""
    payload = [
        {
            "full_name": "octocat/Hello-World",
            "clone_url": "https://github.com/octocat/Hello-World.git",
            "ssh_url": "git@github.com:octocat/Hello-World.git",
            "private": True,
            "pushed_at": "2024-01-15T10:30:00Z",
            "description": "My first repository",
        }
    ]
    repos = _parse_github_repos(payload)
    assert len(repos) == 1
    repo = repos[0]
    assert repo.full_name == "octocat/Hello-World"
    assert repo.clone_url == "https://github.com/octocat/Hello-World.git"
    assert repo.ssh_url == "git@github.com:octocat/Hello-World.git"
    assert repo.is_private is True
    assert repo.pushed_at == "2024-01-15T10:30:00Z"
    assert repo.description == "My first repository"


def test_parse_github_repos_defaults_optional_fields_to_none() -> None:
    """``pushed_at`` and ``description`` are nullable on the model and on the
    API response — missing keys must land as ``None`` rather than ``""``."""
    payload = [
        {
            "full_name": "a/b",
            "clone_url": "https://github.com/a/b.git",
            "ssh_url": "git@github.com:a/b.git",
            "private": False,
        }
    ]
    repos = _parse_github_repos(payload)
    assert len(repos) == 1
    assert repos[0].pushed_at is None
    assert repos[0].description is None


def test_parse_github_repos_defaults_missing_url_fields_to_empty_string() -> None:
    """The parser uses ``.get("full_name", "")`` etc., so a degenerate entry
    with no identifying fields becomes a row of empty strings rather than
    crashing. Documenting this so a future reader doesn't assume those fields
    are guaranteed non-empty downstream."""
    repos = _parse_github_repos([{}])
    assert len(repos) == 1
    repo = repos[0]
    assert repo.full_name == ""
    assert repo.clone_url == ""
    assert repo.ssh_url == ""
    assert repo.is_private is False
    assert repo.pushed_at is None
    assert repo.description is None


# --- clone-source validation / log redaction (argument-injection hardening) ---


def test_is_safe_clone_url_accepts_known_schemes() -> None:
    for url in (
        "https://github.com/owner/repo.git",
        "http://example.com/owner/repo",
        "ssh://git@github.com/owner/repo.git",
        "git://github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
    ):
        assert _is_safe_clone_url(url) is True


def test_is_safe_clone_url_rejects_leading_dash_and_unknown_schemes() -> None:
    """A leading ``-`` would be parsed by git/gh as an option, not a repo —
    this is the argument-injection surface the validator closes."""
    for url in (
        "--upload-pack=touch /tmp/pwn",
        "-oProxyCommand=evil",
        "file:///etc/passwd",
        "",
        "   ",
        "not a url",
    ):
        assert _is_safe_clone_url(url) is False


def test_is_safe_repo_slug_accepts_owner_repo() -> None:
    for slug in ("owner/repo", "octocat/Hello-World", "my-org/sub.repo"):
        assert _is_safe_repo_slug(slug) is True


def test_is_safe_repo_slug_rejects_dashes_and_non_slugs() -> None:
    for slug in ("-owner/repo", "owner", "--flag", "owner repo", ""):
        assert _is_safe_repo_slug(slug) is False


def test_is_safe_clone_name_accepts_plain_directory_names() -> None:
    for name in ("repo", "Hello-World", "my.repo", "sub_repo", "repo.js"):
        assert _is_safe_clone_name(name) is True


def test_is_safe_clone_name_rejects_separators_and_traversal() -> None:
    """A name with a path separator or ``..`` could redirect the clone outside
    ``target_dir`` (``target_dir / name``), so it must be rejected."""
    for name in ("../escape", "a/b", "a\\b", "..", ".", "", "   "):
        assert _is_safe_clone_name(name) is False


def test_is_safe_target_path_accepts_normal_destinations() -> None:
    for path in ("/Users/dev/code/github/repo", "repos/github/repo", "~/code/repo"):
        assert _is_safe_target_path(Path(path)) is True


def test_is_safe_target_path_rejects_leading_dash() -> None:
    """A destination rendering to a leading ``-`` would be parsed as an option by
    gh/git. ``gh repo clone``'s ``--`` forwards to ``git clone`` rather than
    shielding the directory positional, so the rendered path is validated here."""
    for path in ("-help/repo", "--upload-pack/repo", "-oProxyCommand"):
        assert _is_safe_target_path(Path(path)) is False


def test_redact_url_credentials_strips_userinfo() -> None:
    assert _redact_url_credentials("https://user:token@github.com/o/r.git") == "https://github.com/o/r.git"
    # No credentials → unchanged. The scp-form "git@" is a username, not a secret.
    assert _redact_url_credentials("https://github.com/o/r.git") == "https://github.com/o/r.git"
    assert _redact_url_credentials("git@github.com:o/r.git") == "git@github.com:o/r.git"


# --- _looks_like_already_exists ---


def test_already_exists_matches_real_git_clone_stderr() -> None:
    """Real ``git clone`` stderr when the destination directory is non-empty."""
    stderr = "fatal: destination path 'foo' already exists and is not an empty directory."
    assert _looks_like_already_exists(stderr) is True


def test_already_exists_matches_real_gh_repo_clone_stderr() -> None:
    """``gh repo clone`` shells out to ``git clone`` under the hood, so the
    failing stderr ends with the same ``already exists and is not an empty
    directory`` phrasing, prefixed by gh's own framing."""
    stderr = (
        "Cloning into 'foo'...\n"
        "fatal: destination path 'foo' already exists and is not an empty directory.\n"
        "exit status 128"
    )
    assert _looks_like_already_exists(stderr) is True


def test_already_exists_is_case_insensitive() -> None:
    """Regression for the ``.lower()`` — match regardless of how the tool
    capitalizes its error message."""
    assert _looks_like_already_exists("Already Exists") is True
    assert _looks_like_already_exists("ALREADY EXISTS") is True
    assert _looks_like_already_exists("Destination is Not An Empty Directory") is True


def test_already_exists_returns_false_for_empty_string() -> None:
    assert _looks_like_already_exists("") is False


def test_already_exists_returns_false_for_unrelated_clone_errors() -> None:
    """Auth, network, and permission failures must NOT be misclassified as
    destination conflicts — those need a 4xx that lets the user retry, not a
    409 that suggests the path is taken."""
    assert _looks_like_already_exists("Permission denied (publickey).") is False
    assert _looks_like_already_exists("ssh: connect to host github.com port 22: Network is unreachable") is False
    assert (
        _looks_like_already_exists(
            "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
        )
        is False
    )


# ---------------------------------------------------------------------------
# Route-level tests for POST /api/v1/remotes/clone
#
# These exercise clone_remote_repo end-to-end through FastAPI but stub the
# subprocess boundary (gh / git) so no real network or git CLI is
# touched. We mock the dependency-management probes (resolve_binary_path /
# check_authenticated) per-test to walk every branch of _resolve_clone_command
# and the route handler, and we patch ConcurrencyGroup.run_process_to_completion
# at the class level because the route obtains its concurrency_group lazily
# via root_concurrency_group.make_concurrency_group(...).
# ---------------------------------------------------------------------------


def _clone_payload(
    target_dir: Path,
    *,
    name: str = "my-repo",
    provider: str = "github",
    url: str = "https://github.com/owner/my-repo.git",
    full_name: str | None = None,
) -> dict[str, str]:
    payload: dict[str, str] = {
        "provider": provider,
        "url": url,
        "target_dir": str(target_dir),
        "name": name,
    }
    if full_name is not None:
        payload["full_name"] = full_name
    return payload


def _ok_process(command: list[str]) -> FinishedProcess:
    return FinishedProcess(
        returncode=0,
        stdout="",
        stderr="",
        command=tuple(command),
        is_output_already_logged=False,
    )


def _mock_binary_lookup(
    *,
    gh: str | None = "/fake/bin/gh",
    git: str | None = "/fake/bin/git",
):
    """Return a side_effect for resolve_binary_path keyed on Dependency."""

    def _side_effect(tool: Dependency) -> str | None:
        if tool == Dependency.GH:
            return gh
        if tool == Dependency.GIT:
            return git
        return None

    return _side_effect


def _mock_auth_lookup(
    *,
    gh: bool | None = True,
):
    """Return a side_effect for check_authenticated keyed on Dependency."""

    def _side_effect(tool: Dependency) -> bool | None:
        if tool == Dependency.GH:
            return gh
        return None

    return _side_effect


def _resolve_for_self(inner):
    """Wrap a single-arg side_effect so it works with ``autospec=True``.

    ``patch.object(SomeClass, "method", autospec=True, side_effect=...)`` calls
    the side_effect with ``self`` as the first positional argument. Pydantic
    instances reject normal ``patch.object(instance, "method", ...)`` because
    the model validates attribute writes — so we have to patch on the class
    and accept the extra ``self`` here. Both ``resolve_binary_path`` and
    ``check_authenticated`` take a single ``tool: Dependency`` argument."""

    def _wrapped(_self: object, tool: Dependency) -> object:
        return inner(tool)

    return _wrapped


def _make_fake_run(
    *,
    raises: BaseException | None = None,
    capture: dict[str, object] | None = None,
):
    """Build an autospec-compatible side_effect for ``ConcurrencyGroup.run_process_to_completion``.

    If ``raises`` is set, that exception is raised. Otherwise returns a successful
    ``FinishedProcess`` echoing the command. When ``capture`` is provided, the
    captured command and env are stored under ``"command"`` and ``"env"`` keys."""

    def _fake_run(
        _self: ConcurrencyGroup,
        command,
        timeout: float | None = None,
        is_checked_after: bool = True,
        on_output=None,
        cwd=None,
        trace_log_context=None,
        env=None,
        shutdown_event=None,
        progress_handle=None,
        log_command: bool = True,
    ) -> FinishedProcess:
        if capture is not None:
            capture["command"] = list(command)
            capture["env"] = env
        if raises is not None:
            raise raises
        return _ok_process(list(command))

    return _fake_run


def test_clone_happy_path_uses_gh_repo_clone_and_returns_project_path(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """gh is installed + authed → command is ``gh repo clone <url> <target>`` and
    the response carries ``target_dir/name`` as the project path."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir, name="sculptor")
    captured: dict[str, object] = {}

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(capture=captured),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    expected_path = str(target_dir / "sculptor")
    assert body["projectPath"] == expected_path
    # The CLI command must lead with the gh binary and the clone subcommand,
    # and pass the URL + destination path in that order.
    assert captured["command"] == [
        "/fake/bin/gh",
        "repo",
        "clone",
        "https://github.com/owner/my-repo.git",
        expected_path,
    ]


def test_clone_with_full_name_passes_slug_to_gh_so_configured_protocol_is_honored(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """Picker selections include ``full_name``; the route must pass that
    slug — not the HTTPS URL — to ``gh repo clone`` so ``gh`` picks the
    protocol from the user's CLI config rather than the one embedded in the
    URL."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(
        target_dir,
        name="hw1",
        url="https://github.com/sigmachirality/hw1.git",
        full_name="sigmachirality/hw1",
    )
    captured: dict[str, object] = {}

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(capture=captured),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 200, response.text
    expected_path = str(target_dir / "hw1")
    assert captured["command"] == [
        "/fake/bin/gh",
        "repo",
        "clone",
        "sigmachirality/hw1",
        expected_path,
    ]


def test_clone_returns_409_when_target_path_already_exists_without_spawning_subprocess(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """Pre-flight check: if ``target_dir/name`` already exists we 409 before
    even resolving a clone command — saves the user a hung subprocess."""
    target_dir = tmp_path / "clones"
    target_dir.mkdir()
    (target_dir / "sculptor").mkdir()  # The conflict.
    payload = _clone_payload(target_dir, name="sculptor")

    fake_run = patch.object(
        ConcurrencyGroup, "run_process_to_completion", autospec=True, side_effect=AssertionError("should not run")
    )
    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        fake_run,
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 409, response.text
    assert "already exists" in response.json()["detail"]


def test_clone_returns_400_when_target_dir_cannot_be_created(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """``mkdir(parents=True, exist_ok=True)`` raising OSError surfaces as 400
    with the underlying OS error in the detail. We force the failure by
    rooting target_dir under a regular file rather than a directory."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("regular file")
    target_dir = blocker / "under-a-file"
    payload = _clone_payload(target_dir)

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(ConcurrencyGroup, "run_process_to_completion", autospec=True),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 400, response.text
    # The detail surfaces both the path and the OSError message so the user
    # can tell what failed without spelunking the logs.
    detail = response.json()["detail"]
    assert "Could not create target directory" in detail
    assert str(target_dir) in detail


def test_clone_rejects_name_with_path_traversal(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """A ``name`` containing ``..``/separators would redirect the clone outside
    ``target_dir``. The handler rejects it with 400 before spawning any
    subprocess, so no binary mocking is needed."""
    payload = _clone_payload(tmp_path / "clones", name="../escape")

    response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 400, response.text
    assert "clone directory name" in response.json()["detail"].lower()


def test_clone_falls_back_to_git_when_gh_unauthenticated(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """``check_authenticated(GH) is False`` → skip ``gh repo clone``, use
    ``git clone`` with ``GIT_TERMINAL_PROMPT=0`` so it fails fast instead of
    hanging on a credentials prompt."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir, name="repo")
    captured: dict[str, object] = {}

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup(gh=False)),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(capture=captured),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 200, response.text
    expected_path = str(target_dir / "repo")
    assert captured["command"] == [
        "/fake/bin/git",
        "clone",
        "--",
        "https://github.com/owner/my-repo.git",
        expected_path,
    ]
    # GIT_TERMINAL_PROMPT must be off so a private-repo clone fails fast
    # rather than hanging on stdin.
    env = captured["env"]
    assert isinstance(env, dict)
    assert env.get("GIT_TERMINAL_PROMPT") == "0"


def test_clone_uses_cli_when_auth_probe_returns_none(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """Regression for the ``None`` policy in _resolve_clone_command:
    ``check_authenticated(GH)`` returning ``None`` (probe couldn't determine
    auth state) must route through ``gh repo clone``, NOT fall back to
    ``git clone`` — falling back silently fails private-repo clones because
    ``GIT_TERMINAL_PROMPT=0`` blocks credentials."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir, name="private-repo")
    captured: dict[str, object] = {}

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup(gh=None)),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(capture=captured),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 200, response.text
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == "/fake/bin/gh"
    assert command[1:3] == ["repo", "clone"]


def test_clone_returns_412_when_neither_provider_cli_nor_git_is_installed(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """No gh + no git → 412 ``git CLI not installed``. The frontend uses
    412 to surface a "install git" CTA distinct from clone-time failures."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir)

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup(gh=None, git=None)),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=AssertionError("should not run"),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 412, response.text
    assert response.json()["detail"] == "git CLI not installed"


def test_clone_maps_already_exists_stderr_to_409(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """Post-clone TOCTOU recovery: if the subprocess fails because the path
    materialized between the pre-flight check and the clone, the stderr
    pattern ``destination path '...' already exists`` must surface as 409."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir, name="repo")
    stderr = "fatal: destination path 'repo' already exists and is not an empty directory."
    fake_clone_error = ProcessError(
        command=("/fake/bin/gh", "repo", "clone"),
        stdout="",
        stderr=stderr,
        returncode=128,
    )

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(raises=fake_clone_error),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 409, response.text
    assert "already exists" in response.json()["detail"]


def test_clone_maps_unrelated_process_error_to_400(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """Generic clone failures (permission, network, auth) become 400 with the
    stderr passed through. They must NOT be misclassified as 409."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir)
    fake_clone_error = ProcessError(
        command=("/fake/bin/gh", "repo", "clone"),
        stdout="",
        stderr="Permission denied (publickey).",
        returncode=128,
    )

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(raises=fake_clone_error),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 400, response.text
    assert "Permission denied" in response.json()["detail"]


def test_clone_returns_504_on_subprocess_timeout(
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """``ProcessTimeoutError`` → 504 with the timeout value in the detail so
    the frontend can show the user how long we waited before giving up."""
    target_dir = tmp_path / "clones"
    payload = _clone_payload(target_dir)
    fake_timeout = ProcessTimeoutError(
        command=("/fake/bin/gh", "repo", "clone"),
        stdout="",
        stderr="",
    )

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch.object(
            ConcurrencyGroup,
            "run_process_to_completion",
            autospec=True,
            side_effect=_make_fake_run(raises=fake_timeout),
        ),
    ):
        response = client.post("/api/v1/remotes/clone", json=payload)

    assert response.status_code == 504, response.text
    expected_timeout = int(_REMOTE_CLONE_TIMEOUT_SECONDS)
    assert f"{expected_timeout}s" in response.json()["detail"]


# ---------------------------------------------------------------------------
# _resolve_provider_cli
#
# Pure helper that maps a provider string to a (binary, Dependency) tuple by
# probing DependencyManagementService. Raises 400 for unknown providers, 412
# for missing/unauth CLIs. We call it directly with a fake Request whose
# `state.services` returns a MagicMock-ish service collection — the helper
# only touches `services.dependency_management_service.{resolve_binary_path,
# check_authenticated}`, so a lightweight mock is enough.
# ---------------------------------------------------------------------------


def _fake_request_with_services(services_mock: MagicMock) -> Request:
    """Build a minimal Request whose `get_services_from_request_or_websocket`
    can resolve `services_mock`. The helper reads via `request.state.services`
    in practice; in tests we patch the resolver instead."""
    scope = {"type": "http", "headers": [], "state": {}}
    return Request(scope)  # pyright: ignore[reportArgumentType]


def test_resolve_provider_cli_returns_400_for_unknown_provider() -> None:
    """The route should fast-fail on a typo'd provider before the dependency
    probes run. Pinning this so a future enum change doesn't silently start
    returning 412 instead."""
    services = MagicMock()
    with (
        patch("sculptor.web.remote_repos.get_services_from_request_or_websocket", return_value=services),
        pytest.raises(HTTPException) as exc_info,
    ):
        _resolve_provider_cli(_fake_request_with_services(services), "bitbucket")
    assert exc_info.value.status_code == 400
    assert "bitbucket" in exc_info.value.detail


def test_resolve_provider_cli_returns_412_when_cli_missing() -> None:
    """No gh on PATH → 412 ``gh CLI not installed``. The frontend keys off
    this exact string to surface the NotConfiguredSection install link."""
    services = MagicMock()
    services.dependency_management_service.resolve_binary_path.return_value = None
    with (
        patch("sculptor.web.remote_repos.get_services_from_request_or_websocket", return_value=services),
        pytest.raises(HTTPException) as exc_info,
    ):
        _resolve_provider_cli(_fake_request_with_services(services), "github")
    assert exc_info.value.status_code == 412
    assert exc_info.value.detail == "GH CLI not installed"


def test_resolve_provider_cli_returns_412_when_explicitly_unauthenticated() -> None:
    """``check_authenticated`` returning ``False`` (not ``None``) is the
    explicit "signed out" signal. The frontend's NotConfiguredSection footer
    references this 412 detail string for the auth-CTA copy."""
    services = MagicMock()
    services.dependency_management_service.resolve_binary_path.return_value = "/fake/bin/gh"
    services.dependency_management_service.check_authenticated.return_value = False
    with (
        patch("sculptor.web.remote_repos.get_services_from_request_or_websocket", return_value=services),
        pytest.raises(HTTPException) as exc_info,
    ):
        _resolve_provider_cli(_fake_request_with_services(services), "github")
    assert exc_info.value.status_code == 412
    assert exc_info.value.detail == "GH CLI not authenticated"


def test_resolve_provider_cli_returns_binary_when_authenticated() -> None:
    services = MagicMock()
    services.dependency_management_service.resolve_binary_path.return_value = "/fake/bin/gh"
    services.dependency_management_service.check_authenticated.return_value = True
    with patch("sculptor.web.remote_repos.get_services_from_request_or_websocket", return_value=services):
        binary, tool = _resolve_provider_cli(_fake_request_with_services(services), "github")
    assert binary == "/fake/bin/gh"
    assert tool == Dependency.GH


def test_resolve_provider_cli_treats_none_auth_probe_as_authenticated() -> None:
    """Mirrors the `_resolve_clone_command` policy (`is not False`): a probe
    timeout / can't-determine result still routes through the CLI, because the
    common case (CLI is installed + user is signed in) shouldn't break just
    because the auth subprocess hung. The clone happy path depends on this."""
    services = MagicMock()
    services.dependency_management_service.resolve_binary_path.return_value = "/fake/bin/gh"
    services.dependency_management_service.check_authenticated.return_value = None
    with patch("sculptor.web.remote_repos.get_services_from_request_or_websocket", return_value=services):
        binary, tool = _resolve_provider_cli(_fake_request_with_services(services), "github")
    assert binary == "/fake/bin/gh"
    assert tool == Dependency.GH


# ---------------------------------------------------------------------------
# Route: GET /api/v1/config/clone-defaults
# ---------------------------------------------------------------------------


def test_clone_defaults_returns_repos_under_sculptor_folder(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """The dialog appends ``/{provider}`` to ``default_clones_dir``, so it must
    be ``<sculptor_folder>/repos``. Pin the shape — anything else and clones
    would land in the wrong parent directory."""
    response = client.get("/api/v1/config/clone-defaults")
    assert response.status_code == 200, response.text
    assert response.json()["defaultClonesDir"] == str(get_sculptor_folder() / "repos")


# ---------------------------------------------------------------------------
# Route: GET /api/v1/remotes/{provider}/repos
#
# We patch _fetch_repos rather than ConcurrencyGroup.run_process_to_completion
# so the search-vs-browse mode selection and 412 routing get exercised
# without dragging in JSON parsing.
# ---------------------------------------------------------------------------


def test_list_remote_repos_returns_412_when_gh_unauthenticated(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """Delegates to ``_resolve_provider_cli`` — verify the 412 surfaces with
    the auth-not-configured detail string the frontend expects."""
    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup(gh=False)),
        ),
    ):
        response = client.get("/api/v1/remotes/github/repos")
    assert response.status_code == 412, response.text
    assert response.json()["detail"] == "GH CLI not authenticated"


def test_list_remote_repos_uses_paginated_search_for_github_with_query(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """GitHub + query → the route walks pages via ``_search_github_user_repos``.
    Patch ``_search_github_user_repos`` directly to assert the route selects
    that branch (vs. the single-fetch one used for empty queries)."""
    fake_match = RemoteRepo(
        full_name="owner/cli",
        clone_url="https://github.com/owner/cli.git",
        ssh_url="git@github.com:owner/cli.git",
        is_private=False,
        pushed_at=None,
        description=None,
    )

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch("sculptor.web.remote_repos._search_github_user_repos", return_value=[fake_match]) as search_mock,
        patch("sculptor.web.remote_repos._fetch_repos", side_effect=AssertionError("browse mode should not run")),
    ):
        response = client.get("/api/v1/remotes/github/repos", params={"q": "cli", "limit": 10})

    assert response.status_code == 200, response.text
    assert response.json()[0]["fullName"] == "owner/cli"
    # The query string is forwarded; the helper takes (q, needed, fetch_page).
    search_args = search_mock.call_args.args
    assert search_args[0] == "cli"


def test_list_remote_repos_uses_single_fetch_in_browse_mode(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """Empty query → the route hits ``_fetch_repos`` once with the browse-mode
    API path. We patch ``_fetch_repos`` to short-circuit the JSON parse and
    assert the search helper is never called."""
    fake_repo = RemoteRepo(
        full_name="owner/everything",
        clone_url="https://github.com/owner/everything.git",
        ssh_url="git@github.com:owner/everything.git",
        is_private=False,
        pushed_at=None,
        description=None,
    )

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch("sculptor.web.remote_repos._fetch_repos", return_value=[fake_repo]) as fetch_mock,
        patch(
            "sculptor.web.remote_repos._search_github_user_repos", side_effect=AssertionError("search should not run")
        ),
    ):
        response = client.get("/api/v1/remotes/github/repos")

    assert response.status_code == 200, response.text
    assert response.json()[0]["fullName"] == "owner/everything"
    # api_path is the third positional arg in _fetch_repos(binary, cg, api_path).
    call_kwargs = fetch_mock.call_args
    api_path = call_kwargs.args[2]
    assert "/user/repos" in api_path
    # `&page=` is the paginated-search marker — must be absent in browse mode.
    # (Plain ``page=`` would false-positive on ``per_page=``.)
    assert "&page=" not in api_path


def test_list_remote_repos_surfaces_502_from_fetch_without_500_wrapping(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """``_fetch_repos`` raises HTTP 502 for gh subprocess / JSON failures. Because
    that raise happens inside the concurrency-group ``with``, the route must
    capture it and re-raise after the block — otherwise ConcurrencyExceptionGroup
    wraps it on ``__exit__`` and FastAPI surfaces a generic 500."""
    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch(
            "sculptor.web.remote_repos._fetch_repos",
            side_effect=HTTPException(status_code=502, detail="gh api failed with exit code 1"),
        ),
    ):
        response = client.get("/api/v1/remotes/github/repos")

    assert response.status_code == 502, response.text
    assert response.json()["detail"] == "gh api failed with exit code 1"


def test_list_remote_repos_caps_limit_at_max(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """Callers asking for ``limit=10_000`` must be capped at ``_REMOTE_REPO_MAX_LIMIT``
    so we never page through GitHub at silly sizes."""
    captured: dict[str, object] = {}

    def fetch_and_capture(binary: str, cg, api_path: str) -> list[RemoteRepo]:
        captured["api_path"] = api_path
        return []

    with (
        patch.object(
            DependencyManagementService,
            "resolve_binary_path",
            autospec=True,
            side_effect=_resolve_for_self(_mock_binary_lookup()),
        ),
        patch.object(
            DependencyManagementService,
            "check_authenticated",
            autospec=True,
            side_effect=_resolve_for_self(_mock_auth_lookup()),
        ),
        patch("sculptor.web.remote_repos._fetch_repos", side_effect=fetch_and_capture),
    ):
        response = client.get("/api/v1/remotes/github/repos", params={"limit": 10_000})

    assert response.status_code == 200, response.text
    api_path = captured["api_path"]
    assert isinstance(api_path, str)
    assert f"per_page={_REMOTE_REPO_MAX_LIMIT}" in api_path


# ---------------------------------------------------------------------------
# DependencyManagementService.check_authenticated — timeout → None
# (covered indirectly by dependency_management_service_test.py for the gh
# happy path; this pins the timeout-returns-None contract that the clone-route
# `is not False` policy depends on.)
# ---------------------------------------------------------------------------


@patch("shutil.which", return_value="/fake/bin/gh")
def test_check_authenticated_returns_none_on_subprocess_timeout(_mock_which: MagicMock) -> None:
    """``check_authenticated`` must surface a hung ``gh auth status`` as
    ``None``, NOT ``False``. ``False`` is reserved for "explicitly signed
    out" (the CLI ran to completion with a non-zero exit). ``None`` lets the
    clone route fall through its ``is not False`` policy and still try the
    CLI rather than silently downgrading to ``git clone``."""
    mock_cg = MagicMock()
    mock_cg.run_process_to_completion.side_effect = ProcessTimeoutError(
        command=("/fake/bin/gh", "auth", "status"),
        stdout="",
        stderr="",
    )
    service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    assert service.check_authenticated(Dependency.GH) is None
