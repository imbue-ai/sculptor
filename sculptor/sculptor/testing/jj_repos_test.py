"""Self-tests for the jj fixtures and helpers, run against the real jj binary.

The resolver tests use fake ``jj`` scripts that only answer ``--version``; every other
test runs the jj that ``jj_binary`` resolves.
"""

import re
import subprocess
from pathlib import Path

import pytest

from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import describe_jj_for_report_header
from sculptor.testing.jj_repos import make_github_looking_origin
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import require_jj_binary
from sculptor.testing.jj_repos import resolve_jj_binary
from sculptor.testing.jj_repos import run_jj

_OLD_JJ_VERSION_OUTPUT = "jj 0.28.2-b9ebe2f03c976515d2a155a411a368ae773c5493"
_PINNED_JJ_VERSION_OUTPUT = f"jj {JJ_PINNED_VERSION}-7d382314f9420b4b8d932245b49c99492c812b9f"


def _write_fake_jj(path: Path, version_output: str, exit_code: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho '{version_output}'\nexit {exit_code}\n")
    path.chmod(0o755)
    return path


def _run_git(args: tuple[str, ...], cwd: Path) -> str:
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_resolver_skips_a_jj_older_than_the_pin(tmp_path: Path) -> None:
    old_jj = _write_fake_jj(tmp_path / "old" / "jj", _OLD_JJ_VERSION_OUTPUT)
    pinned_jj = _write_fake_jj(tmp_path / "pinned" / "jj", _PINNED_JJ_VERSION_OUTPUT)

    assert resolve_jj_binary((old_jj, pinned_jj)) == JjBinary(path=pinned_jj, version=JJ_PINNED_VERSION)


def test_resolver_compares_versions_numerically(tmp_path: Path) -> None:
    newer_jj = _write_fake_jj(tmp_path / "jj", "jj 0.100.0-7d382314f9420b4b8d932245b49c99492c812b9f")

    assert resolve_jj_binary((newer_jj,)) == JjBinary(path=newer_jj, version="0.100.0")


def test_resolver_takes_the_first_qualifying_candidate(tmp_path: Path) -> None:
    first_jj = _write_fake_jj(tmp_path / "first" / "jj", _PINNED_JJ_VERSION_OUTPUT)
    second_jj = _write_fake_jj(tmp_path / "second" / "jj", "jj 0.47.0-7d382314f9420b4b8d932245b49c99492c812b9f")

    assert resolve_jj_binary((first_jj, second_jj)) == JjBinary(path=first_jj, version=JJ_PINNED_VERSION)


def test_resolver_ignores_missing_failing_and_unparseable_candidates(tmp_path: Path) -> None:
    missing_jj = tmp_path / "missing" / "jj"
    failing_jj = _write_fake_jj(tmp_path / "failing" / "jj", _PINNED_JJ_VERSION_OUTPUT, exit_code=1)
    unparseable_jj = _write_fake_jj(tmp_path / "unparseable" / "jj", "jujutsu, some version")

    assert resolve_jj_binary((missing_jj, failing_jj, unparseable_jj)) is None


def test_require_jj_binary_fails_with_the_install_hint_when_only_an_old_jj_exists(tmp_path: Path) -> None:
    old_jj = _write_fake_jj(tmp_path / "jj", _OLD_JJ_VERSION_OUTPUT)

    with pytest.raises(
        pytest.fail.Exception, match=re.escape(f"jj >= {JJ_PINNED_VERSION} not found; run `just install-jj`")
    ):
        require_jj_binary((tmp_path / "missing" / "jj", old_jj))


def test_report_header_names_the_resolved_jj(tmp_path: Path) -> None:
    pinned_jj = _write_fake_jj(tmp_path / "jj", _PINNED_JJ_VERSION_OUTPUT)

    assert describe_jj_for_report_header((pinned_jj,)) == f"jj: {pinned_jj} ({JJ_PINNED_VERSION})"


def test_report_header_points_at_install_jj_when_no_jj_qualifies(tmp_path: Path) -> None:
    old_jj = _write_fake_jj(tmp_path / "jj", _OLD_JJ_VERSION_OUTPUT)

    assert (
        describe_jj_for_report_header((old_jj,)) == f"jj: none at or above {JJ_PINNED_VERSION}; run `just install-jj`"
    )


def test_jj_binary_reports_the_resolved_version(jj_binary: JjBinary) -> None:
    version_output = subprocess.run(
        (str(jj_binary.path), "--version"), capture_output=True, text=True, check=True
    ).stdout

    assert version_output.startswith(f"jj {jj_binary.version}")


def test_isolated_env_points_jj_at_an_empty_user_config(
    jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv, tmp_path: Path
) -> None:
    user_config_path = run_jj(jj_binary, ("config", "path", "--user"), cwd=tmp_path).strip()

    assert Path(user_config_path) == jj_isolated_env.jj_config_path
    assert jj_isolated_env.jj_config_path.read_text() == ""


def test_isolated_env_gives_jj_and_git_the_test_identity(
    jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv, tmp_path: Path
) -> None:
    assert run_jj(jj_binary, ("config", "get", "user.name"), cwd=tmp_path).strip() == jj_isolated_env.user_name
    assert run_jj(jj_binary, ("config", "get", "user.email"), cwd=tmp_path).strip() == jj_isolated_env.user_email
    assert _run_git(("config", "--global", "user.name"), cwd=tmp_path) == jj_isolated_env.user_name
    assert _run_git(("config", "--global", "user.email"), cwd=tmp_path) == jj_isolated_env.user_email
    assert _run_git(("config", "--global", "init.defaultBranch"), cwd=tmp_path) == "main"


def test_colocated_repo_has_git_and_jj(jj_colocated_repo: JjColocatedRepo) -> None:
    assert (jj_colocated_repo.path / ".git").is_dir()
    assert (jj_colocated_repo.path / ".jj").is_dir()


def test_colocated_repo_tracks_the_default_bookmark_at_origin(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    bookmarks = run_jj(
        jj_binary,
        ("bookmark", "list", "--all-remotes", "-T", 'name ++ "@" ++ remote ++ " tracked=" ++ tracked ++ "\n"'),
        cwd=jj_colocated_repo.path,
    )

    assert f"{jj_colocated_repo.default_bookmark}@origin tracked=true" in bookmarks.splitlines()


def test_colocated_repo_keeps_its_jj_repo_config_inside_the_isolated_env(
    jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv, jj_colocated_repo: JjColocatedRepo
) -> None:
    repo_config_path = run_jj(jj_binary, ("config", "path", "--repo"), cwd=jj_colocated_repo.path).strip()

    assert Path(repo_config_path).is_relative_to(jj_isolated_env.config_home_path)


def test_workspace_has_jj_and_no_git(jj_workspace: JjWorkspace) -> None:
    assert (jj_workspace.path / ".jj").is_dir()
    assert not (jj_workspace.path / ".git").exists()


def test_workspace_is_registered_under_its_name_on_top_of_the_default_bookmark(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    workspace_names = run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\n"'), cwd=jj_colocated_repo.path)
    parent_bookmarks = run_jj(
        jj_binary,
        ("log", "--no-graph", "-r", "@-", "-T", 'local_bookmarks.map(|b| b.name()).join(" ")'),
        cwd=jj_workspace.path,
    )

    assert jj_workspace.name in workspace_names.splitlines()
    assert parent_bookmarks.split() == [jj_colocated_repo.default_bookmark]


def test_github_looking_origin_shows_a_github_url_and_pushes_to_the_bare_repo(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    github_url = make_github_looking_origin(jj_colocated_repo.path, jj_colocated_repo.remote_path)
    run_jj(
        jj_binary,
        ("bookmark", "create", "pushed-bookmark", "-r", jj_colocated_repo.default_bookmark),
        cwd=jj_colocated_repo.path,
    )
    run_jj(jj_binary, ("git", "push", "--bookmark", "pushed-bookmark"), cwd=jj_colocated_repo.path)

    assert github_url.startswith("https://github.com/")
    assert _run_git(("remote", "get-url", "origin"), cwd=jj_colocated_repo.path) == github_url
    remote_branches = _run_git(
        ("for-each-ref", "--format=%(refname:short)", "refs/heads"), cwd=jj_colocated_repo.remote_path
    )
    assert "pushed-bookmark" in remote_branches.splitlines()


def test_make_workspace_stale_leaves_the_workspace_reporting_a_stale_working_copy(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, jj_workspace.path)
    status = subprocess.run((str(jj_binary.path), "status"), cwd=jj_workspace.path, capture_output=True, text=True)

    assert status.returncode != 0
    assert "The working copy is stale" in status.stderr
