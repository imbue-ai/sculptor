"""Contract tests for the demo pipeline's gh shim (marketing/gh_shim/gh).

Sculptor's PR polling (sculptor/sculptor/web/pr_status.py) shells out to
``gh api graphql`` and reacts badly to certain failure shapes: a non-zero exit
whose stderr looks like a rate limit (see ``classify_cli_error``) puts the
poller into a long cooldown. The shim's load-bearing contract is therefore:
always exit 0 with valid JSON, never emit rate-limit-ish stderr, answer the
open-PR ``search(`` query from fixtures, and serve merged/closed PRs only
through the ``repository(owner:`` fallback lookup.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SHIM_PATH = Path(__file__).resolve().parents[3] / "marketing" / "gh_shim" / "gh"

pytestmark = pytest.mark.skipif(not _SHIM_PATH.is_file(), reason="marketing gh shim is not present in this checkout")

# Minimal stand-ins for the two query shapes pr_status.py sends; the shim
# dispatches on the ``search(`` / ``repository(owner:`` substrings.
_SEARCH_QUERY = "query($q: String!) { search(query: $q, type: ISSUE, first: 100) { nodes } rateLimit { remaining } }"
_REPOSITORY_QUERY = (
    "query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { pullRequests { nodes } } }"
)

_FIXTURES = {
    "owner": "imbue-ai",
    "branches": {
        "feat/open-pr": {
            "repo": "sculptor",
            "number": 1342,
            "title": "Add semantic search to the command palette",
            "state": "OPEN",
            "checks": "SUCCESS",
            "approvals": [{"login": "alice", "approved": True}],
        },
        "feat/merged-pr": {
            "repo": "sculptor",
            "number": 1338,
            "title": "Stream terminal output incrementally",
            "state": "MERGED",
        },
    },
}


def _run_shim(args: list[str], fixtures_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, SCULPTOR_DEMO_GH_FIXTURES=str(fixtures_path))
    return subprocess.run(
        [sys.executable, str(_SHIM_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _search(fixtures_path: Path) -> subprocess.CompletedProcess[str]:
    return _run_shim(["api", "graphql", "-f", f"query={_SEARCH_QUERY}"], fixtures_path)


def _repository_lookup(fixtures_path: Path, branch: str) -> subprocess.CompletedProcess[str]:
    # Mirror the full argv shape pr_status.py sends (query, owner/name
    # placeholders, branch, limit) so the shim's tolerance of every flag is
    # pinned, not just the ones it dispatches on.
    args = [
        "api",
        "graphql",
        "-f",
        f"query={_REPOSITORY_QUERY}",
        "-F",
        "owner={owner}",
        "-F",
        "name={repo}",
        "-f",
        f"branch={branch}",
        "-F",
        "limit=20",
    ]
    return _run_shim(args, fixtures_path)


def _assert_contract(result: subprocess.CompletedProcess[str]) -> dict:
    """Assert the always-safe part of the contract and return the parsed stdout payload."""
    assert result.returncode == 0
    for keyword in ("rate limit", "ratelimit", "secondary rate"):
        # The stderr shapes classify_cli_error would classify as a rate limit.
        assert keyword not in result.stderr.lower()
    return json.loads(result.stdout)


def _write_fixtures(tmp_path: Path, fixtures: dict) -> Path:
    path = tmp_path / "gh_fixtures.json"
    path.write_text(json.dumps(fixtures))
    return path


def test_search_returns_open_pr_envelope(tmp_path: Path) -> None:
    payload = _assert_contract(_search(_write_fixtures(tmp_path, _FIXTURES)))

    search = payload["data"]["search"]
    assert search["pageInfo"]["hasNextPage"] is False
    (node,) = search["nodes"]
    assert node["headRefName"] == "feat/open-pr"
    assert node["repository"]["nameWithOwner"] == "imbue-ai/sculptor"
    assert node["state"] == "OPEN"
    assert node["number"] == 1342

    rate_limit = payload["data"]["rateLimit"]
    assert 0 < rate_limit["remaining"] <= rate_limit["limit"]


def test_repository_lookup_serves_merged_pr_absent_from_search(tmp_path: Path) -> None:
    fixtures_path = _write_fixtures(tmp_path, _FIXTURES)

    search_payload = _assert_contract(_search(fixtures_path))
    search_branches = [node["headRefName"] for node in search_payload["data"]["search"]["nodes"]]
    assert "feat/merged-pr" not in search_branches

    repo_payload = _assert_contract(_repository_lookup(fixtures_path, "feat/merged-pr"))
    (node,) = repo_payload["data"]["repository"]["pullRequests"]["nodes"]
    assert node["state"] == "MERGED"
    assert node["number"] == 1338


def test_malformed_fixture_entry_degrades_gracefully(tmp_path: Path) -> None:
    fixtures = {
        "owner": "imbue-ai",
        "branches": {
            **_FIXTURES["branches"],
            "feat/broken": {"number": 7},  # missing repo/title/state
            "feat/very-broken": "not even a dict",
        },
    }
    fixtures_path = _write_fixtures(tmp_path, fixtures)

    # The well-formed open entry still renders; the malformed ones are skipped.
    search_payload = _assert_contract(_search(fixtures_path))
    search_branches = [node["headRefName"] for node in search_payload["data"]["search"]["nodes"]]
    assert search_branches == ["feat/open-pr"]

    # A direct lookup of a malformed entry degrades to "no PR".
    broken_payload = _assert_contract(_repository_lookup(fixtures_path, "feat/broken"))
    assert broken_payload["data"]["repository"]["pullRequests"]["nodes"] == []


def test_missing_fixtures_file_fails_soft(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"

    search_payload = _assert_contract(_search(missing))
    assert search_payload["data"]["search"]["nodes"] == []

    repo_payload = _assert_contract(_repository_lookup(missing, "any-branch"))
    assert repo_payload["data"]["repository"]["pullRequests"]["nodes"] == []


def test_unparseable_fixtures_file_fails_soft(tmp_path: Path) -> None:
    path = tmp_path / "gh_fixtures.json"
    path.write_text("{this is not json")

    payload = _assert_contract(_search(path))
    assert payload["data"]["search"]["nodes"] == []
