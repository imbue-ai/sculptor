import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.interfaces.environments.errors import EnvironmentNotFoundError
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import DEFAULT_JJ_WORKSPACE_SETUP_COMMAND
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import JjWorkspaceVcs
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.jj_repos import run_jj

_SNAPSHOT_LIMIT_MIB = 10
_MEBIBYTE = 1024 * 1024
_BASE = "main@origin"


class _SnapshotLimit:
    """A settable stand-in for the user's configured snapshot size limit."""

    def __init__(self, mib: int) -> None:
        self.mib = mib

    def read(self) -> int:
        return self.mib


def _jj(jj_binary: JjBinary, cwd: Path, *arguments: str) -> str:
    return run_jj(jj_binary, arguments, cwd=cwd)


def _commit_id(jj_binary: JjBinary, repo_dir: Path, revset: str) -> str:
    return _jj(jj_binary, repo_dir, "--ignore-working-copy", "log", "--no-graph", "-r", revset, "-T", "commit_id")


def _count_operations(jj_binary: JjBinary, repo_dir: Path) -> int:
    output = _jj(jj_binary, repo_dir, "--ignore-working-copy", "op", "log", "--no-graph", "-T", 'id ++ "\\n"')
    return len(output.splitlines())


def _workspace_roots_by_name(jj_binary: JjBinary, repo_dir: Path) -> dict[str, Path]:
    output = _jj(
        jj_binary, repo_dir, "--ignore-working-copy", "workspace", "list", "-T", 'name ++ "\\t" ++ root ++ "\\n"'
    )
    return {name: Path(root) for name, root in (line.split("\t") for line in output.splitlines())}


def _workspace_config_value(jj_binary: JjBinary, checkout: Path, key: str) -> str:
    return _jj(jj_binary, checkout, "--ignore-working-copy", "config", "get", key).strip()


def _spec(repo: JjColocatedRepo, checkout_path: Path, base_ref: str | None = _BASE) -> CheckoutSpec:
    return CheckoutSpec(
        repo_path=repo.path,
        checkout_path=checkout_path,
        base_ref=base_ref,
        new_ref_name="feat",
        checkout_name=f"ws_{uuid4().hex}",
    )


def _untrack_main(jj_binary: JjBinary, repo: JjColocatedRepo) -> None:
    """Leave `main@origin` untracked, as Sculptor's own colocation does; the fixture repository tracks it."""
    _jj(jj_binary, repo.path, "bookmark", "untrack", "main@origin")


def _push_bookmark_from(jj_binary: JjBinary, repo_dir: Path, name: str, revision: str) -> None:
    _jj(jj_binary, repo_dir, "--ignore-working-copy", "bookmark", "create", name, "-r", revision)
    _jj(jj_binary, repo_dir, "--ignore-working-copy", "git", "push", "--bookmark", name)


@pytest.fixture
def snapshot_limit() -> _SnapshotLimit:
    return _SnapshotLimit(_SNAPSHOT_LIMIT_MIB)


@pytest.fixture
def jj_vcs(jj_cli: JjCli, git_cli: GitCli, snapshot_limit: _SnapshotLimit) -> JjWorkspaceVcs:
    return JjWorkspaceVcs(jj_cli, git_cli, snapshot_limit.read)


@pytest.fixture
def checkout(jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo) -> CheckoutLocation:
    """A jj workspace of `jj_colocated_repo` created through the seam, based on `main@origin`."""
    return jj_vcs.create_checkout(_spec(jj_colocated_repo, jj_colocated_repo.path.parent / "env" / "code"))


@pytest.mark.parametrize("is_main_tracked", [True, False])
def test_resolve_default_target_is_the_remote_trunk_bookmark(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, is_main_tracked: bool
) -> None:
    if not is_main_tracked:
        _untrack_main(jj_binary, jj_colocated_repo)

    assert jj_vcs.resolve_default_target(jj_colocated_repo.path) == "main@origin"


def test_resolve_default_target_falls_back_to_a_local_main_without_a_remote(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, git_repo: Path
) -> None:
    colocate_with_jj(jj_binary, git_repo)

    assert jj_vcs.resolve_default_target(git_repo) == "main"


def test_resolve_default_target_is_none_outside_a_jj_repository(jj_vcs: JjWorkspaceVcs, git_repo: Path) -> None:
    assert jj_vcs.resolve_default_target(git_repo) is None


def test_list_target_candidates_lists_local_and_remote_bookmarks_as_jj_symbols(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_bookmark_from(jj_binary, jj_colocated_repo.path, "pushed", "main")
    _jj(jj_binary, jj_colocated_repo.path, "--ignore-working-copy", "bookmark", "create", "local-only", "-r", "main")

    candidates = jj_vcs.list_target_candidates(jj_colocated_repo.path)

    assert sorted(candidates) == ["local-only", "main", "main@origin", "pushed", "pushed@origin"]


def test_list_target_candidates_skips_a_conflicted_bookmark(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    repo = jj_colocated_repo.path
    _jj(jj_binary, repo, "--ignore-working-copy", "new", "--no-edit", "-m", "side a", "main")
    _jj(jj_binary, repo, "--ignore-working-copy", "new", "--no-edit", "-m", "side b", "main")
    _jj(jj_binary, repo, "--ignore-working-copy", "bookmark", "create", "split", "-r", "main")
    operation = _jj(jj_binary, repo, "--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id")
    _jj(jj_binary, repo, "--ignore-working-copy", "bookmark", "set", "split", "-r", 'description(exact:"side a\\n")')
    _jj(
        jj_binary,
        repo,
        "--ignore-working-copy",
        "--at-op",
        operation,
        "bookmark",
        "set",
        "split",
        "-r",
        'description(exact:"side b\\n")',
    )

    assert "split" not in jj_vcs.list_target_candidates(repo)


def test_validate_new_ref_name_accepts_an_unused_well_formed_name(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo
) -> None:
    assert jj_vcs.validate_new_ref_name(jj_colocated_repo.path, "feature/new").status == RefNameStatus.AVAILABLE


@pytest.mark.parametrize("ref_name", ["", "has@sign", "@", "double..dot", "trailing/", "-leading-dash"])
def test_validate_new_ref_name_rejects_a_malformed_name(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo, ref_name: str
) -> None:
    assert jj_vcs.validate_new_ref_name(jj_colocated_repo.path, ref_name).status == RefNameStatus.MALFORMED


def test_validate_new_ref_name_rejects_an_existing_local_bookmark(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo
) -> None:
    assert jj_vcs.validate_new_ref_name(jj_colocated_repo.path, "main").status == RefNameStatus.ALREADY_EXISTS


def test_validate_new_ref_name_rejects_a_bookmark_that_exists_only_on_a_remote(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_bookmark_from(jj_binary, jj_colocated_repo.path, "remote-only", "main")
    _jj(jj_binary, jj_colocated_repo.path, "--ignore-working-copy", "bookmark", "forget", "remote-only")
    _jj(jj_binary, jj_colocated_repo.path, "--ignore-working-copy", "git", "fetch")

    validation = jj_vcs.validate_new_ref_name(jj_colocated_repo.path, "remote-only")

    assert validation.status == RefNameStatus.ALREADY_EXISTS


def test_validate_new_ref_name_rejects_a_git_branch_jj_has_not_imported_yet(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo
) -> None:
    run_blocking(["git", "branch", "made-in-git"], cwd=jj_colocated_repo.path)

    validation = jj_vcs.validate_new_ref_name(jj_colocated_repo.path, "made-in-git")

    assert validation.status == RefNameStatus.ALREADY_EXISTS


def test_resolve_base_commit_id_resolves_a_remote_bookmark_and_a_commit_id(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    main_commit_id = _commit_id(jj_binary, jj_colocated_repo.path, "main@origin")

    assert jj_vcs.resolve_base_commit_id(jj_colocated_repo.path, "main@origin") == main_commit_id
    assert jj_vcs.resolve_base_commit_id(jj_colocated_repo.path, main_commit_id) == main_commit_id


@pytest.mark.parametrize("base_ref", ["origin/main", "missing", "missing@origin", "a" * 40])
def test_resolve_base_commit_id_is_none_for_what_names_no_commit(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo, base_ref: str
) -> None:
    assert jj_vcs.resolve_base_commit_id(jj_colocated_repo.path, base_ref) is None


def test_default_setup_command_fetches_origin_with_jj_and_never_fails(jj_vcs: JjWorkspaceVcs) -> None:
    assert jj_vcs.default_setup_command() == DEFAULT_JJ_WORKSPACE_SETUP_COMMAND
    assert DEFAULT_JJ_WORKSPACE_SETUP_COMMAND == "jj git fetch --remote origin 2>/dev/null || true"


def test_repository_reads_add_no_operation(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    repo = jj_colocated_repo.path
    operations_before = _count_operations(jj_binary, repo)

    jj_vcs.resolve_default_target(repo)
    jj_vcs.list_target_candidates(repo)
    jj_vcs.validate_new_ref_name(repo, "unused")
    jj_vcs.resolve_base_commit_id(repo, _BASE)

    assert _count_operations(jj_binary, repo) == operations_before


@pytest.mark.parametrize("is_main_tracked", [True, False])
def test_create_checkout_adds_a_jj_only_workspace_whose_working_copy_is_a_child_of_the_base(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, is_main_tracked: bool
) -> None:
    if not is_main_tracked:
        _untrack_main(jj_binary, jj_colocated_repo)
    spec = _spec(jj_colocated_repo, jj_colocated_repo.path.parent / "env" / "code")

    location = jj_vcs.create_checkout(spec)

    assert location == CheckoutLocation(
        repo_path=spec.repo_path, checkout_path=spec.checkout_path, checkout_name=spec.checkout_name
    )
    assert (location.checkout_path / ".jj" / "repo").is_file()
    assert not (location.checkout_path / ".git").exists()
    assert (location.checkout_path / "README.md").read_text() == "# jj fixture repo\n"
    assert _workspace_roots_by_name(jj_binary, jj_colocated_repo.path)[spec.checkout_name] == spec.checkout_path
    assert _commit_id(jj_binary, location.checkout_path, "@-") == _commit_id(
        jj_binary, jj_colocated_repo.path, "main@origin"
    )


def test_create_checkout_writes_the_snapshot_size_limit_into_the_workspace_config(
    checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    configured = _workspace_config_value(jj_binary, checkout.checkout_path, "snapshot.max-new-file-size")

    assert configured == str(_SNAPSHOT_LIMIT_MIB * _MEBIBYTE)
    assert _workspace_config_value(jj_binary, jj_colocated_repo.path, "snapshot.max-new-file-size") != configured


def test_create_checkout_creates_a_missing_parent_directory(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo
) -> None:
    spec = _spec(jj_colocated_repo, jj_colocated_repo.path.parent / "not" / "yet" / "there" / "code")

    location = jj_vcs.create_checkout(spec)

    assert (location.checkout_path / ".jj").is_dir()


def test_create_checkout_replaces_a_lost_workspace_of_the_same_name(
    jj_vcs: JjWorkspaceVcs, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    first_spec = _spec(jj_colocated_repo, jj_colocated_repo.path.parent / "lost" / "code")
    jj_vcs.create_checkout(first_spec)
    shutil.rmtree(first_spec.checkout_path.parent)
    second_spec = first_spec.model_copy(update={"checkout_path": jj_colocated_repo.path.parent / "new" / "code"})

    jj_vcs.create_checkout(second_spec)

    assert _workspace_roots_by_name(jj_binary, jj_colocated_repo.path)[second_spec.checkout_name] == (
        second_spec.checkout_path
    )


def test_create_checkout_requires_a_base(jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo) -> None:
    with pytest.raises(InvalidCheckoutSpecError):
        jj_vcs.create_checkout(_spec(jj_colocated_repo, jj_colocated_repo.path.parent / "code", base_ref=None))


def test_verify_checkout_re_applies_the_current_snapshot_size_limit(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, snapshot_limit: _SnapshotLimit
) -> None:
    snapshot_limit.mib = 3

    jj_vcs.verify_checkout(checkout)

    configured = _workspace_config_value(jj_binary, checkout.checkout_path, "snapshot.max-new-file-size")
    assert configured == str(3 * _MEBIBYTE)


def test_verify_checkout_adds_no_operation(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    operations_before = _count_operations(jj_binary, checkout.checkout_path)

    jj_vcs.verify_checkout(checkout)

    assert _count_operations(jj_binary, checkout.checkout_path) == operations_before


def test_verify_checkout_reports_a_checkout_whose_jj_store_link_is_gone(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    (checkout.checkout_path / ".jj" / "repo").unlink()

    with pytest.raises(EnvironmentNotFoundError):
        jj_vcs.verify_checkout(checkout)


def test_verify_checkout_reports_a_checkout_directory_that_is_gone(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    shutil.rmtree(checkout.checkout_path)

    with pytest.raises(EnvironmentNotFoundError):
        jj_vcs.verify_checkout(checkout)
