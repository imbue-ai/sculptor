import shlex
from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmark
from sculptor.services.workspace_service.vcs.jj_data_types import JjHeadIdentity
from sculptor.services.workspace_service.vcs.jj_repo_queries import select_target_candidates
from sculptor.services.workspace_service.vcs.jj_workspace_scan import name_pull_request_base
from sculptor.services.workspace_service.vcs.jj_workspace_scan import project_jj_workspace_identity
from sculptor.services.workspace_service.vcs.jj_workspace_scan import resolve_target_commit_id
from sculptor.services.workspace_service.vcs.jj_workspace_scan import scan_jj_workspaces
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj

_TARGET = "main@origin"


class _CountingJj:
    """A jj runner whose every invocation is appended, one line each, to a log."""

    def __init__(self, cli: JjCli, invocation_log: Path) -> None:
        self.cli = cli
        self._invocation_log = invocation_log

    def count_invocations(self) -> int:
        return len(self._invocation_log.read_text().splitlines())


@pytest.fixture
def counting_jj(
    test_root_concurrency_group: ConcurrencyGroup, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv, tmp_path: Path
) -> _CountingJj:
    invocation_log = tmp_path / "jj-invocations.log"
    invocation_log.touch()
    wrapper = tmp_path / "counting-jj"
    wrapper.write_text(
        f'#!/bin/bash\necho "$*" >> {shlex.quote(str(invocation_log))}\nexec {shlex.quote(str(jj_binary.path))} "$@"\n'
    )
    wrapper.chmod(0o755)
    cli = JjCli(test_root_concurrency_group, lambda tool: str(wrapper) if tool is Dependency.JJ else None)
    return _CountingJj(cli, invocation_log)


def _add_workspace(jj_binary: JjBinary, repo: JjColocatedRepo, name: str, base: str = "main") -> Path:
    path = repo.path.parent / "workspaces" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    run_jj(jj_binary, ("workspace", "add", "--no-colocate", "--name", name, "-r", base, str(path)), cwd=repo.path)
    return path


def _commit(jj_binary: JjBinary, checkout: Path, file_name: str, message: str) -> None:
    (checkout / file_name).write_text(f"{message}\n")
    run_jj(jj_binary, ("commit", "-m", message), cwd=checkout)


def _create_bookmarks(jj_binary: JjBinary, checkout: Path, revision: str, *names: str) -> None:
    run_jj(jj_binary, ("bookmark", "create", "-r", revision, *names), cwd=checkout)


def _read(jj_binary: JjBinary, checkout: Path, template: str, revision: str = "@") -> str:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "log", "--no-graph", "-r", revision, "-T", template), cwd=checkout
    ).strip()


def _count_operations(jj_binary: JjBinary, repo: Path) -> int:
    return len(
        run_jj(jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "-T", 'id ++ "\\n"'), cwd=repo).split()
    )


def _identity(scan_target: tuple[JjCli, Path], name: str, target_ref: str | None = _TARGET) -> JjHeadIdentity:
    jj, repo_dir = scan_target
    scan = scan_jj_workspaces(jj, repo_dir, {name: target_ref})
    identity = project_jj_workspace_identity(scan, name, target_ref, requested_bookmark=None)
    assert identity is not None
    return identity


def test_a_scan_projects_each_workspaces_working_copy_and_the_bookmarks_on_its_own_stack(
    counting_jj: _CountingJj, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    bookmarked = _add_workspace(jj_binary, jj_colocated_repo, "bookmarked")
    _commit(jj_binary, bookmarked, "a.txt", "add a")
    _create_bookmarks(jj_binary, bookmarked, "@-", "feat-a")
    unbookmarked = _add_workspace(jj_binary, jj_colocated_repo, "unbookmarked")
    _commit(jj_binary, unbookmarked, "b.txt", "add b")
    (unbookmarked / "c.txt").write_text("snapshotted by the describe\n")
    run_jj(jj_binary, ("describe", "-m", "wip on b\n\nmore detail"), cwd=unbookmarked)

    scan = scan_jj_workspaces(
        counting_jj.cli, jj_colocated_repo.path, {"bookmarked": _TARGET, "unbookmarked": _TARGET}
    )

    assert project_jj_workspace_identity(scan, "bookmarked", _TARGET, requested_bookmark=None) == JjHeadIdentity(
        working_copy_change_id=_read(jj_binary, bookmarked, "change_id"),
        working_copy_change_id_prefix=_read(jj_binary, bookmarked, "change_id.shortest().prefix()"),
        description_first_line="",
        is_working_copy_empty=True,
        bookmarks=("feat-a",),
        primary_bookmark="feat-a",
        unbookmarked_revision_count=0,
        has_conflict=False,
        is_divergent=False,
    )
    other = project_jj_workspace_identity(scan, "unbookmarked", _TARGET, requested_bookmark=None)
    assert other is not None
    assert (other.description_first_line, other.is_working_copy_empty) == ("wip on b", False)
    assert (other.bookmarks, other.primary_bookmark, other.unbookmarked_revision_count) == ((), None, 2)


def test_a_scan_runs_two_jj_commands_however_many_workspaces_it_reads_and_adds_no_operation(
    counting_jj: _CountingJj, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    names = [f"ws-{index}" for index in range(3)]
    for name in names:
        _add_workspace(jj_binary, jj_colocated_repo, name)
    operations_before = _count_operations(jj_binary, jj_colocated_repo.path)

    scan_jj_workspaces(counting_jj.cli, jj_colocated_repo.path, {name: _TARGET for name in names})

    assert counting_jj.count_invocations() == 2
    assert _count_operations(jj_binary, jj_colocated_repo.path) == operations_before


def test_a_workspace_the_repository_does_not_record_has_no_identity(
    counting_jj: _CountingJj, jj_colocated_repo: JjColocatedRepo
) -> None:
    scan = scan_jj_workspaces(counting_jj.cli, jj_colocated_repo.path, {"never-added": _TARGET})

    assert project_jj_workspace_identity(scan, "never-added", _TARGET, requested_bookmark=None) is None


def test_a_target_that_names_no_commit_measures_the_stack_from_the_working_copys_mutable_ancestors(
    counting_jj: _CountingJj, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    checkout = _add_workspace(jj_binary, jj_colocated_repo, "ws")
    _commit(jj_binary, checkout, "a.txt", "add a")
    _create_bookmarks(jj_binary, checkout, "@-", "feat-a")

    identity = _identity((counting_jj.cli, jj_colocated_repo.path), "ws", target_ref="gone@origin")

    assert identity.bookmarks == ("feat-a",)


def test_a_stack_stops_at_its_own_target_where_another_workspaces_stack_runs_past_it(
    counting_jj: _CountingJj, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    on_main = _add_workspace(jj_binary, jj_colocated_repo, "on-main")
    _commit(jj_binary, on_main, "release.txt", "release work")
    _create_bookmarks(jj_binary, on_main, "@-", "release", "shared")
    _add_workspace(jj_binary, jj_colocated_repo, "on-release", base="release")

    scan = scan_jj_workspaces(counting_jj.cli, jj_colocated_repo.path, {"on-main": _TARGET, "on-release": "release"})

    on_release_identity = project_jj_workspace_identity(scan, "on-release", "release", requested_bookmark=None)
    on_main_identity = project_jj_workspace_identity(scan, "on-main", _TARGET, requested_bookmark=None)
    assert on_release_identity is not None and on_main_identity is not None
    assert on_release_identity.bookmarks == ()
    assert set(on_main_identity.bookmarks) == {"release", "shared"}


def test_a_conflicted_bookmark_is_neither_on_a_stack_nor_a_target_candidate(
    counting_jj: _CountingJj, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    checkout = _add_workspace(jj_binary, jj_colocated_repo, "ws")
    _commit(jj_binary, checkout, "a.txt", "side a")
    run_jj(jj_binary, ("new", "-m", "side b", "main"), cwd=checkout)
    _commit(jj_binary, checkout, "b.txt", "side b")
    operation_before_bookmark = run_jj(
        jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"), cwd=checkout
    )
    _create_bookmarks(jj_binary, checkout, "@-", "forked")
    run_jj(
        jj_binary,
        (
            "--at-op",
            operation_before_bookmark,
            "--ignore-working-copy",
            "bookmark",
            "create",
            "forked",
            "-r",
            'description(exact:"side a\\n")',
        ),
        cwd=checkout,
    )

    scan = scan_jj_workspaces(counting_jj.cli, jj_colocated_repo.path, {"ws": _TARGET})

    identity = project_jj_workspace_identity(scan, "ws", _TARGET, requested_bookmark=None)
    assert identity is not None
    assert "forked" not in identity.bookmarks
    assert [bookmark.name for bookmark in scan.bookmarks if bookmark.is_conflicted] == ["forked"]
    assert "forked" not in select_target_candidates(scan.bookmarks)
    assert {"main", "main@origin"} <= set(select_target_candidates(scan.bookmarks))


def test_a_stale_workspace_is_scanned_like_any_other(
    counting_jj: _CountingJj, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    checkout = _add_workspace(jj_binary, jj_colocated_repo, "ws")
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout)

    identity = _identity((counting_jj.cli, checkout), "ws")

    assert identity.bookmarks == ()


def test_resolve_target_commit_id_names_a_bookmarks_commit_and_nothing_for_a_conflicted_or_unknown_one() -> None:
    commit_id = "a" * 40
    bookmarks = (
        JjBookmark(name="main", remote="origin", target_commit_ids=(commit_id,), is_tracked=True),
        JjBookmark(name="split", remote=None, target_commit_ids=(commit_id, None, "b" * 40), is_tracked=False),
    )

    assert resolve_target_commit_id("main@origin", bookmarks) == commit_id
    assert resolve_target_commit_id("main", bookmarks) is None
    assert resolve_target_commit_id("split", bookmarks) is None
    assert resolve_target_commit_id("c" * 40, bookmarks) == "c" * 40
    assert resolve_target_commit_id("a@b@c", bookmarks) is None
    assert resolve_target_commit_id(None, bookmarks) is None


def test_name_pull_request_base_drops_the_remote_of_a_bookmark_symbol() -> None:
    assert name_pull_request_base("release/1.0@origin") == "release/1.0"
    assert name_pull_request_base("main") == "main"
    assert name_pull_request_base("a@b@c") == "a@b@c"
