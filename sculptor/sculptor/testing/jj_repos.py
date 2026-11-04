"""Pytest fixtures and helpers for tests that run the real jj (Jujutsu) binary.

The fixtures build repositories with the raw git and jj CLIs rather than with Sculptor's
own jj code, so they stay an independent oracle for the code under test. They are
registered in ``sculptor/conftest.py``.

Tests assert on the structure of what jj produces (bookmarks, files, workspaces), never on
change or commit ids, so ``JJ_RANDOMNESS_SEED`` is left unset.
"""

import re
import shlex
import shutil
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import GitCommitSnapshot
from sculptor.testing.git_snapshot import create_repo_from_snapshot

JJ_TEST_USER_NAME = "Sculptor Test"
JJ_TEST_USER_EMAIL = "sculptor-test@example.com"
JJ_TEST_DEFAULT_BOOKMARK = "main"
JJ_TEST_GITHUB_URL = "https://github.com/sculptor-tests/jj-fixture.git"

# `jj --version` prints `jj 0.46.0-<40-hex commit hash>`.
_JJ_VERSION_PATTERN = re.compile(r"^jj (\d+\.\d+\.\d+)(?:-\S+)?$")
_JJ_INSTALL_HINT = f"jj >= {JJ_PINNED_VERSION} not found; run `just install-jj`"
_STALE_EDIT_FILE_NAME = "stale-edit.txt"


class JjBinary(FrozenModel):
    path: Path
    version: str


class JjIsolatedEnv(FrozenModel):
    jj_config_path: Path
    git_config_path: Path
    config_home_path: Path
    user_name: str
    user_email: str


class JjColocatedRepo(FrozenModel):
    path: Path
    remote_path: Path
    default_bookmark: str


class JjWorkspace(FrozenModel):
    path: Path
    name: str


class JjFixtureCommandError(Exception):
    """Raised when a jj or git command run by a jj fixture or helper exits non-zero."""


def default_jj_binary_candidates() -> tuple[Path, ...]:
    """The venv's jj (where `just install-jj` puts it), then the first jj on PATH.

    A developer machine may have an older jj earlier on PATH, so PATH alone is not enough.
    """
    venv_jj = Path(sys.prefix) / "bin" / "jj"
    jj_on_path = shutil.which("jj")
    if jj_on_path is None:
        return (venv_jj,)
    return (venv_jj, Path(jj_on_path))


def resolve_jj_binary(candidates: Sequence[Path]) -> JjBinary | None:
    """Return the first candidate whose `jj --version` is at or above the pinned version."""
    minimum_version = _parse_version_numbers(JJ_PINNED_VERSION)
    for candidate in candidates:
        version = _read_jj_version(candidate)
        if version is not None and _parse_version_numbers(version) >= minimum_version:
            return JjBinary(path=candidate, version=version)
    return None


def require_jj_binary(candidates: Sequence[Path]) -> JjBinary:
    """Resolve jj or fail the test: a skip would let a machine without jj pass silently."""
    jj_binary = resolve_jj_binary(candidates)
    if jj_binary is None:
        checked = ", ".join(str(candidate) for candidate in candidates)
        pytest.fail(f"{_JJ_INSTALL_HINT} (checked {checked})")
    return jj_binary


def describe_jj_for_report_header(candidates: Sequence[Path]) -> str:
    jj_binary = resolve_jj_binary(candidates)
    if jj_binary is None:
        return f"jj: none at or above {JJ_PINNED_VERSION}; run `just install-jj`"
    return f"jj: {jj_binary.path} ({jj_binary.version})"


def run_jj(jj_binary: JjBinary, args: Sequence[str], cwd: Path) -> str:
    """Run jj in `cwd` and return its stdout, raising `JjFixtureCommandError` with stderr on failure."""
    return _run_command((str(jj_binary.path), *args), cwd)


def colocate_with_jj(jj_binary: JjBinary, repo_path: Path) -> None:
    """Turn an existing git repository into a colocated jj repository."""
    run_jj(jj_binary, ("git", "init", "--colocate"), cwd=repo_path)


def add_bare_origin(repo_path: Path, remote_path: Path) -> None:
    """Create a bare repository at `remote_path`, add it as `origin`, and push the current branch to it."""
    _run_git(("init", "--bare", str(remote_path)), cwd=repo_path)
    _run_git(("remote", "add", "origin", str(remote_path)), cwd=repo_path)
    _run_git(("push", "--set-upstream", "origin", "HEAD"), cwd=repo_path)


def make_github_looking_origin(repo_path: Path, bare_remote_path: Path) -> str:
    """Point `origin` at a GitHub URL while pushes still land in `bare_remote_path`.

    `pushInsteadOf` rewrites only the push URL, so `git remote get-url origin` keeps
    reporting the GitHub URL; a plain `insteadOf` would rewrite what it reports too.
    Fetches go to the GitHub URL. Returns that URL.
    """
    _run_git(("remote", "set-url", "origin", JJ_TEST_GITHUB_URL), cwd=repo_path)
    _run_git(("config", f"url.{bare_remote_path}.pushInsteadOf", JJ_TEST_GITHUB_URL), cwd=repo_path)
    return JJ_TEST_GITHUB_URL


def make_workspace_stale(jj_binary: JjBinary, repo_path: Path, workspace_path: Path) -> None:
    """Leave the workspace's working copy stale relative to the repository.

    Snapshots an edit in the workspace, then restores the main repository to the operation
    before that snapshot. jj only reports a working copy as stale when its tree differs from
    the one the repository records, so the edit is needed.
    """
    operation_before_snapshot = run_jj(
        jj_binary,
        ("--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"),
        cwd=repo_path,
    )
    (workspace_path / _STALE_EDIT_FILE_NAME).write_text("edit made before the operation restore\n")
    run_jj(jj_binary, ("util", "snapshot"), cwd=workspace_path)
    run_jj(jj_binary, ("op", "restore", operation_before_snapshot), cwd=repo_path)


@pytest.fixture(scope="session")
def jj_binary() -> JjBinary:
    return require_jj_binary(default_jj_binary_candidates())


@pytest.fixture
def jj_isolated_env(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> JjIsolatedEnv:
    """Give jj and git an empty user config and a test identity for the duration of a test."""
    root = tmp_path_factory.mktemp("jj_env")
    jj_config_path = root / "jj" / "config.toml"
    jj_config_path.parent.mkdir()
    jj_config_path.touch()
    git_config_path = root / "gitconfig"
    git_config_path.write_text(
        f"[user]\n\tname = {JJ_TEST_USER_NAME}\n\temail = {JJ_TEST_USER_EMAIL}\n"
        + f"[init]\n\tdefaultBranch = {JJ_TEST_DEFAULT_BOOKMARK}\n"
    )
    config_home_path = root / "config_home"
    config_home_path.mkdir()
    monkeypatch.setenv("JJ_CONFIG", str(jj_config_path))
    monkeypatch.setenv("JJ_USER", JJ_TEST_USER_NAME)
    monkeypatch.setenv("JJ_EMAIL", JJ_TEST_USER_EMAIL)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # jj keeps per-repo and per-workspace config under $XDG_CONFIG_HOME/jj/repos even when
    # JJ_CONFIG is set, so without this, tests would write into the developer's config dir.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home_path))
    return JjIsolatedEnv(
        jj_config_path=jj_config_path,
        git_config_path=git_config_path,
        config_home_path=config_home_path,
        user_name=JJ_TEST_USER_NAME,
        user_email=JJ_TEST_USER_EMAIL,
    )


@pytest.fixture
def jj_colocated_repo(
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path_factory: pytest.TempPathFactory,
    test_root_concurrency_group: ConcurrencyGroup,
) -> JjColocatedRepo:
    """A colocated git + jj repository with one commit, whose `main` tracks `main@origin` in a bare remote."""
    root = tmp_path_factory.mktemp("jj_colocated_repo")
    repo_path = root / "repo"
    remote_path = root / "origin.git"
    create_repo_from_snapshot(
        FullLocalGitRepo(
            git_user_name=jj_isolated_env.user_name,
            git_user_email=jj_isolated_env.user_email,
            git_branch=JJ_TEST_DEFAULT_BOOKMARK,
            main_history=(
                GitCommitSnapshot(
                    contents_by_path={"README.md": "# jj fixture repo\n"},
                    commit_message="initial commit",
                    commit_time="2025-01-01T00:00:00",
                ),
            ),
        ),
        destination_path=repo_path,
        concurrency_group=test_root_concurrency_group,
    )
    add_bare_origin(repo_path, remote_path)
    colocate_with_jj(jj_binary, repo_path)
    # `jj git init --colocate` leaves the remote bookmark untracked.
    run_jj(jj_binary, ("bookmark", "track", f"{JJ_TEST_DEFAULT_BOOKMARK}@origin"), cwd=repo_path)
    return JjColocatedRepo(path=repo_path, remote_path=remote_path, default_bookmark=JJ_TEST_DEFAULT_BOOKMARK)


@pytest.fixture
def jj_workspace(jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo) -> JjWorkspace:
    """A non-colocated jj workspace of `jj_colocated_repo` whose working copy sits on the default bookmark."""
    name = f"ws-{uuid.uuid4().hex[:8]}"
    path = jj_colocated_repo.path.parent / "workspaces" / name
    # jj refuses to create a workspace whose parent directory does not exist.
    path.parent.mkdir(parents=True, exist_ok=True)
    run_jj(
        jj_binary,
        ("workspace", "add", "--no-colocate", "--name", name, "-r", jj_colocated_repo.default_bookmark, str(path)),
        cwd=jj_colocated_repo.path,
    )
    return JjWorkspace(path=path, name=name)


def _read_jj_version(binary: Path) -> str | None:
    try:
        result = subprocess.run((str(binary), "--version"), capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    match = _JJ_VERSION_PATTERN.match(result.stdout.strip())
    if match is None:
        return None
    return match.group(1)


def _parse_version_numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _run_git(args: Sequence[str], cwd: Path) -> str:
    return _run_command(("git", *args), cwd)


def _run_command(command: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise JjFixtureCommandError(
            f"`{shlex.join(command)}` failed in {cwd} with exit code {result.returncode}:\n{result.stderr}"
        )
    return result.stdout
