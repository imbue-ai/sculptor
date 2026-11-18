import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.workspace_service.vcs.errors import JjWorkingCopyStaleError
from sculptor.services.workspace_service.vcs.errors import VcsCommandExitError
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmark
from sculptor.services.workspace_service.vcs.jj_repo_queries import add_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import does_bookmark_exist
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_bookmarks
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import init_colocated
from sculptor.services.workspace_service.vcs.jj_repo_queries import is_jj_colocated
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_bookmarks
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_tracked_bookmark_names
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_workspaces
from sculptor.services.workspace_service.vcs.jj_repo_queries import read_remotes
from sculptor.services.workspace_service.vcs.jj_repo_queries import read_workspace_config_path
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_commit_id
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_trunk_symbol
from sculptor.services.workspace_service.vcs.jj_repo_queries import set_workspace_config
from sculptor.services.workspace_service.vcs.jj_repo_queries import update_stale
from sculptor.services.workspace_service.vcs.jj_revsets import JjRevset
from sculptor.services.workspace_service.vcs.jj_revsets import local_bookmark_revset
from sculptor.services.workspace_service.vcs.jj_revsets import revset_for_base
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import add_bare_origin
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj


def _read_commit_id(jj_binary: JjBinary, repo_dir: Path, revset: str) -> str:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "log", "--no-graph", "-r", revset, "-T", "commit_id"), cwd=repo_dir
    )


def _create_commit_on_main(jj_binary: JjBinary, repo_dir: Path, description: str) -> str:
    run_jj(jj_binary, ("--ignore-working-copy", "new", "--no-edit", "-m", description, "main"), cwd=repo_dir)
    return _read_commit_id(jj_binary, repo_dir, f'children(main) & description(exact:"{description}\\n")')


def _make_conflicted_bookmark(jj_binary: JjBinary, repo_dir: Path, name: str) -> None:
    """Move `name` to two different commits in concurrent operations, which jj merges into a conflict."""
    side_a = _create_commit_on_main(jj_binary, repo_dir, "side a")
    side_b = _create_commit_on_main(jj_binary, repo_dir, "side b")
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "create", name, "-r", "main"), cwd=repo_dir)
    operation = run_jj(
        jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"), cwd=repo_dir
    )
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "set", name, "-r", side_a), cwd=repo_dir)
    run_jj(
        jj_binary, ("--ignore-working-copy", "--at-op", operation, "bookmark", "set", name, "-r", side_b), cwd=repo_dir
    )


def _push_new_bookmark(jj_binary: JjBinary, repo: JjColocatedRepo, name: str) -> None:
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "create", name, "-r", "main"), cwd=repo.path)
    run_jj(jj_binary, ("--ignore-working-copy", "git", "push", "--bookmark", name), cwd=repo.path)


def _make_colocated_repo_without_remote(jj_binary: JjBinary, repo_path: Path, branch: str) -> Path:
    repo_path.mkdir()
    run_blocking(["git", "init", "-q", "-b", branch], cwd=repo_path)
    (repo_path / "file.txt").write_text("content\n")
    run_blocking(["git", "add", "file.txt"], cwd=repo_path)
    run_blocking(["git", "commit", "-q", "-m", "init"], cwd=repo_path)
    colocate_with_jj(jj_binary, repo_path)
    return repo_path


def _bookmarks_named(bookmarks: list[JjBookmark], name: str) -> list[JjBookmark]:
    return [bookmark for bookmark in bookmarks if bookmark.name == name]


def _workspaces_by_name(jj_cli: JjCli, repo_dir: Path) -> dict[str, Path]:
    return {entry.name: entry.root for entry in list_workspaces(jj_cli, repo_dir)}


def _new_workspace_destination(repo: JjColocatedRepo) -> Path:
    destination = repo.path.parent / "workspaces" / f"ws-{uuid4().hex[:8]}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _count_operations(jj_binary: JjBinary, repo_dir: Path) -> int:
    output = run_jj(jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "-T", 'id ++ "\\n"'), cwd=repo_dir)
    return len(output.splitlines())


def _read_config_value(jj_cli: JjCli, repo_dir: Path, key: str) -> str:
    result = jj_cli.run(["config", "get", key], repo_dir, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)
    return result.stdout.strip()


def test_is_jj_colocated_is_true_for_a_colocated_repository(jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo) -> None:
    assert is_jj_colocated(jj_cli, jj_colocated_repo.path)


def test_is_jj_colocated_compares_resolved_paths(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, tmp_path: Path
) -> None:
    symlinked_repo = tmp_path / "symlinked_repo"
    symlinked_repo.symlink_to(jj_colocated_repo.path)

    assert is_jj_colocated(jj_cli, symlinked_repo)


def test_is_jj_colocated_is_false_for_a_plain_git_repository(jj_cli: JjCli, git_repo: Path) -> None:
    assert not is_jj_colocated(jj_cli, git_repo)


def test_is_jj_colocated_is_false_for_a_workspace_with_no_git_directory(
    jj_cli: JjCli, jj_workspace: JjWorkspace
) -> None:
    assert not is_jj_colocated(jj_cli, jj_workspace.path)


def test_is_jj_colocated_is_false_when_the_jj_repository_uses_a_different_git_directory(
    jj_cli: JjCli, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repo_path = tmp_path / "split"
    repo_path.mkdir()
    run_jj(jj_binary, ("git", "init", "--no-colocate"), cwd=repo_path)
    run_blocking(["git", "init", "-q"], cwd=repo_path)

    assert not is_jj_colocated(jj_cli, repo_path)


def test_init_colocated_keeps_the_git_branch_checked_out_and_tracks_no_bookmark(
    jj_cli: JjCli, git_repo: Path, tmp_path: Path
) -> None:
    add_bare_origin(git_repo, tmp_path / "origin.git")

    init_colocated(jj_cli, git_repo)

    head = run_blocking(["git", "symbolic-ref", "--short", "HEAD"], cwd=git_repo).stdout.strip()
    (remote_main,) = [bookmark for bookmark in list_bookmarks(jj_cli, git_repo) if bookmark.remote == "origin"]
    assert is_jj_colocated(jj_cli, git_repo)
    assert head == "main"
    assert not remote_main.is_tracked


def test_list_bookmarks_reports_local_and_remote_bookmarks_without_the_git_remote(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    main_commit_id = _read_commit_id(jj_binary, jj_colocated_repo.path, "main")

    bookmarks = list_bookmarks(jj_cli, jj_colocated_repo.path)

    assert bookmarks == [
        JjBookmark(name="main", remote=None, target_commit_ids=(main_commit_id,), is_tracked=False),
        JjBookmark(name="main", remote="origin", target_commit_ids=(main_commit_id,), is_tracked=True),
    ]
    assert all(bookmark.commit_id == main_commit_id and not bookmark.is_conflicted for bookmark in bookmarks)


def test_list_bookmarks_reports_a_conflicted_bookmark_as_conflicted(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _make_conflicted_bookmark(jj_binary, jj_colocated_repo.path, "contested")

    (contested,) = _bookmarks_named(list_bookmarks(jj_cli, jj_colocated_repo.path), "contested")

    assert contested.is_conflicted
    assert contested.commit_id is None


def test_list_bookmarks_reports_a_locally_deleted_bookmark_as_absent_not_conflicted(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_new_bookmark(jj_binary, jj_colocated_repo, "doomed")
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "delete", "doomed"), cwd=jj_colocated_repo.path)

    local, remote = _bookmarks_named(list_bookmarks(jj_cli, jj_colocated_repo.path), "doomed")

    assert local.remote is None
    assert local.target_commit_ids == (None,)
    assert local.commit_id is None
    assert not local.is_conflicted
    assert remote.remote == "origin"
    assert remote.commit_id is not None


def test_list_tracked_bookmark_names_lists_the_bookmarks_on_a_revset_that_track_a_real_remote(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_new_bookmark(jj_binary, jj_colocated_repo, "pushed")
    run_jj(
        jj_binary,
        ("--ignore-working-copy", "bookmark", "create", "local-only", "-r", "main"),
        cwd=jj_colocated_repo.path,
    )
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "untrack", "main@origin"), cwd=jj_colocated_repo.path)

    names = list_tracked_bookmark_names(jj_cli, jj_colocated_repo.path, JjRevset("main"))

    assert names == {"pushed"}


def test_resolve_trunk_symbol_names_the_remote_bookmark_on_trunk(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo
) -> None:
    assert resolve_trunk_symbol(jj_cli, jj_colocated_repo.path) == "main@origin"


@pytest.mark.parametrize(("branch", "expected_symbol"), [("main", "main"), ("master", "master"), ("dev", None)])
def test_resolve_trunk_symbol_without_a_remote_falls_back_to_local_main_then_master(
    jj_cli: JjCli, jj_binary: JjBinary, tmp_path: Path, branch: str, expected_symbol: str | None
) -> None:
    repo_path = _make_colocated_repo_without_remote(jj_binary, tmp_path / "local_only", branch)

    assert resolve_trunk_symbol(jj_cli, repo_path) == expected_symbol


def test_resolve_trunk_symbol_is_none_when_trunk_is_not_the_root_and_has_no_remote_bookmark(
    jj_cli: JjCli, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repo_path = _make_colocated_repo_without_remote(jj_binary, tmp_path / "local_only", "main")
    run_jj(
        jj_binary,
        ("--ignore-working-copy", "config", "set", "--repo", 'revset-aliases."trunk()"', "main"),
        cwd=repo_path,
    )

    assert resolve_trunk_symbol(jj_cli, repo_path) is None


def test_resolve_trunk_symbol_is_none_when_a_user_trunk_alias_names_no_commit(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    run_jj(
        jj_binary,
        ("--ignore-working-copy", "config", "set", "--repo", 'revset-aliases."trunk()"', "present(develop@origin)"),
        cwd=jj_colocated_repo.path,
    )

    assert resolve_trunk_symbol(jj_cli, jj_colocated_repo.path) is None


def test_resolve_commit_id_returns_the_single_commit_a_revset_names(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    main_commit_id = _read_commit_id(jj_binary, jj_colocated_repo.path, "main")

    assert resolve_commit_id(jj_cli, jj_colocated_repo.path, local_bookmark_revset("main")) == main_commit_id
    assert resolve_commit_id(jj_cli, jj_colocated_repo.path, JjRevset(main_commit_id)) == main_commit_id


@pytest.mark.parametrize(
    "revset",
    [
        JjRevset("0123456789abcdef0123456789abcdef01234567"),
        local_bookmark_revset("no-such-bookmark"),
        JjRevset("main | root()"),
    ],
)
def test_resolve_commit_id_is_none_unless_exactly_one_commit_matches(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, revset: JjRevset
) -> None:
    assert resolve_commit_id(jj_cli, jj_colocated_repo.path, revset) is None


def test_does_bookmark_exist_finds_local_and_remote_only_bookmarks(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_new_bookmark(jj_binary, jj_colocated_repo, "remote-only")
    run_jj(jj_binary, ("--ignore-working-copy", "bookmark", "forget", "remote-only"), cwd=jj_colocated_repo.path)

    assert does_bookmark_exist(jj_cli, jj_colocated_repo.path, "main")
    assert does_bookmark_exist(jj_cli, jj_colocated_repo.path, "remote-only")
    assert not does_bookmark_exist(jj_cli, jj_colocated_repo.path, "missing")


def test_read_remotes_maps_each_remote_to_its_fetch_url(jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo) -> None:
    run_blocking(["git", "remote", "add", "upstream", "https://example.com/fetch.git"], cwd=jj_colocated_repo.path)
    run_blocking(
        ["git", "remote", "set-url", "--push", "upstream", "https://example.com/push.git"], cwd=jj_colocated_repo.path
    )

    assert read_remotes(jj_cli, jj_colocated_repo.path) == {
        "origin": str(jj_colocated_repo.remote_path),
        "upstream": "https://example.com/fetch.git",
    }


def test_forget_bookmarks_drops_local_and_remote_tracking_bookmarks_but_leaves_the_remote_branch(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_new_bookmark(jj_binary, jj_colocated_repo, "finished")

    forget_bookmarks(jj_cli, jj_colocated_repo.path, ["finished"])

    remote_branch = run_blocking(
        ["git", "--git-dir", str(jj_colocated_repo.remote_path), "branch", "--list", "finished"],
        cwd=jj_colocated_repo.path,
    ).stdout
    assert _bookmarks_named(list_bookmarks(jj_cli, jj_colocated_repo.path), "finished") == []
    assert remote_branch.strip() == "finished"


def test_forget_bookmarks_matches_names_exactly_rather_than_as_globs(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo
) -> None:
    forget_bookmarks(jj_cli, jj_colocated_repo.path, ["ma*"])

    assert _bookmarks_named(list_bookmarks(jj_cli, jj_colocated_repo.path), "main") != []


def test_forget_bookmarks_with_no_names_changes_nothing(jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo) -> None:
    before = list_bookmarks(jj_cli, jj_colocated_repo.path)

    forget_bookmarks(jj_cli, jj_colocated_repo.path, [])

    assert list_bookmarks(jj_cli, jj_colocated_repo.path) == before


def test_list_workspaces_reports_each_workspace_name_and_absolute_root(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    workspaces = _workspaces_by_name(jj_cli, jj_colocated_repo.path)

    assert workspaces.keys() == {"default", jj_workspace.name}
    assert workspaces["default"] == jj_colocated_repo.path.resolve()
    assert workspaces[jj_workspace.name] == jj_workspace.path.resolve()


def test_list_workspaces_still_lists_a_workspace_whose_root_was_deleted(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    shutil.rmtree(jj_workspace.path)

    assert jj_workspace.name in _workspaces_by_name(jj_cli, jj_colocated_repo.path)


def test_list_workspaces_reports_a_name_jj_would_quote_as_the_raw_name(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    awkward_name = 'ws "q" 1'
    destination = _new_workspace_destination(jj_colocated_repo)
    run_jj(
        jj_binary,
        ("workspace", "add", "--no-colocate", "--name", awkward_name, "-r", "main", str(destination)),
        cwd=jj_colocated_repo.path,
    )

    assert _workspaces_by_name(jj_cli, jj_colocated_repo.path)[awkward_name] == destination.resolve()


def test_add_workspace_creates_a_jj_only_checkout_whose_parent_commit_is_the_base(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo
) -> None:
    destination = _new_workspace_destination(jj_colocated_repo)
    base_revset = revset_for_base("main@origin")

    add_workspace(jj_cli, jj_colocated_repo.path, name="sculptor-ws", base_revset=base_revset, destination=destination)

    base_commit_id = resolve_commit_id(jj_cli, jj_colocated_repo.path, base_revset)
    assert (destination / ".jj").is_dir()
    assert not (destination / ".git").exists()
    assert (destination / "README.md").is_file()
    assert resolve_commit_id(jj_cli, destination, JjRevset("@-")) == base_commit_id
    assert _workspaces_by_name(jj_cli, jj_colocated_repo.path)["sculptor-ws"] == destination.resolve()


def test_add_workspace_refuses_a_name_that_is_already_taken(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    with pytest.raises(VcsCommandExitError):
        add_workspace(
            jj_cli,
            jj_colocated_repo.path,
            name=jj_workspace.name,
            base_revset=local_bookmark_revset("main"),
            destination=_new_workspace_destination(jj_colocated_repo),
        )


def test_add_workspace_refuses_a_destination_that_is_not_empty(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo
) -> None:
    destination = _new_workspace_destination(jj_colocated_repo)
    destination.mkdir()
    (destination / "existing.txt").write_text("already here\n")

    with pytest.raises(VcsCommandExitError):
        add_workspace(
            jj_cli,
            jj_colocated_repo.path,
            name="sculptor-ws",
            base_revset=local_bookmark_revset("main"),
            destination=destination,
        )


def test_add_workspace_refuses_a_destination_whose_parent_is_missing(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo
) -> None:
    with pytest.raises(VcsCommandExitError):
        add_workspace(
            jj_cli,
            jj_colocated_repo.path,
            name="sculptor-ws",
            base_revset=local_bookmark_revset("main"),
            destination=jj_colocated_repo.path.parent / "missing_parent" / "ws",
        )


def test_forget_workspace_removes_the_workspace_from_the_repository(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    forget_workspace(jj_cli, jj_colocated_repo.path, jj_workspace.name)

    assert jj_workspace.name not in _workspaces_by_name(jj_cli, jj_colocated_repo.path)


def test_forget_workspace_succeeds_when_the_directory_is_already_gone(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    shutil.rmtree(jj_workspace.path)

    forget_workspace(jj_cli, jj_colocated_repo.path, jj_workspace.name)

    assert jj_workspace.name not in _workspaces_by_name(jj_cli, jj_colocated_repo.path)


def test_forget_workspace_succeeds_for_an_unknown_name(jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo) -> None:
    forget_workspace(jj_cli, jj_colocated_repo.path, "never-existed")

    assert _workspaces_by_name(jj_cli, jj_colocated_repo.path).keys() == {"default"}


def test_read_workspace_config_path_is_none_for_a_workspace_without_config_and_creates_nothing(
    jj_cli: JjCli, jj_isolated_env: JjIsolatedEnv, jj_workspace: JjWorkspace
) -> None:
    assert read_workspace_config_path(jj_cli, jj_workspace.path) is None
    assert not (jj_isolated_env.config_home_path / "jj" / "workspaces").exists()


def test_set_workspace_config_applies_to_that_workspace_only_and_creates_no_operation(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    operations_before = _count_operations(jj_binary, jj_workspace.path)

    set_workspace_config(jj_cli, jj_workspace.path, "snapshot.max-new-file-size", "12345")

    config_path = read_workspace_config_path(jj_cli, jj_workspace.path)
    assert config_path is not None
    assert "max-new-file-size = 12345" in config_path.read_text()
    assert _read_config_value(jj_cli, jj_workspace.path, "snapshot.max-new-file-size") == "12345"
    assert _read_config_value(jj_cli, jj_colocated_repo.path, "snapshot.max-new-file-size") != "12345"
    assert _count_operations(jj_binary, jj_workspace.path) == operations_before


def test_forget_workspace_leaves_the_workspace_config_file_behind(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    set_workspace_config(jj_cli, jj_workspace.path, "snapshot.max-new-file-size", "12345")
    config_path = read_workspace_config_path(jj_cli, jj_workspace.path)
    assert config_path is not None

    forget_workspace(jj_cli, jj_colocated_repo.path, jj_workspace.name)

    assert config_path.is_file()


def test_update_stale_brings_a_stale_workspace_back_into_use(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, jj_workspace.path)
    with pytest.raises(JjWorkingCopyStaleError):
        jj_cli.run(["status"], jj_workspace.path, snapshot=JjSnapshotPolicy.SNAPSHOT)

    update_stale(jj_cli, jj_workspace.path)

    assert jj_cli.run(["status"], jj_workspace.path, snapshot=JjSnapshotPolicy.SNAPSHOT).returncode == 0
