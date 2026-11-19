import base64
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.interfaces.environments.errors import EnvironmentNotFoundError
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.vcs.data_types import AgentVcsEnvironment
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import CommitFileChange
from sculptor.services.workspace_service.vcs.data_types import FileAtRefResult
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.errors import CheckoutFilesUnavailableError
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import JjWorkingCopyStaleError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_data_types import JjHeadIdentity
from sculptor.services.workspace_service.vcs.jj_data_types import JjInitialBookmarkOutcome
from sculptor.services.workspace_service.vcs.jj_data_types import JjRevisionHistory
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import DEFAULT_JJ_WORKSPACE_SETUP_COMMAND
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import JjWorkspaceVcs
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.jj_repos import make_github_looking_origin
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj
from sculptor.testing.sculptor_folder import isolated_sculptor_folder  # noqa: F401
from sculptor.utils.build import get_jj_bin_dir
from sculptor.utils.build import link_jj_bin

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


def _commit_change(jj_binary: JjBinary, checkout: Path, file_name: str, content: str, message: str) -> None:
    """Write `file_name` and commit it as `message`, leaving a new empty working copy on top."""
    (checkout / file_name).write_text(content)
    _jj(jj_binary, checkout, "commit", "-m", message)


def _set_bookmarks(jj_binary: JjBinary, checkout: Path, revision: str, *names: str) -> None:
    _jj(jj_binary, checkout, "--ignore-working-copy", "bookmark", "set", "--allow-backwards", *names, "-r", revision)


def _latest_operation(jj_binary: JjBinary, repo_dir: Path) -> str:
    return _jj(jj_binary, repo_dir, "--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id")


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


def test_jj_workspace_vcs_implements_the_vcs_seam(jj_vcs: JjWorkspaceVcs) -> None:
    assert isinstance(jj_vcs, WorkspaceVcs)


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


def test_read_identity_of_a_fresh_workspace_reports_an_empty_undescribed_working_copy_without_bookmarks(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    change_id = _jj(
        jj_binary, checkout.checkout_path, "--ignore-working-copy", "log", "--no-graph", "-r", "@", "-T", "change_id"
    )

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert identity == JjHeadIdentity(
        working_copy_change_id=change_id,
        working_copy_change_id_prefix=identity.working_copy_change_id_prefix,
        description_first_line="",
        is_working_copy_empty=True,
        bookmarks=(),
        primary_bookmark=None,
        unbookmarked_revision_count=0,
        has_conflict=False,
        is_divergent=False,
    )
    assert identity.working_copy_change_id_prefix
    assert change_id.startswith(identity.working_copy_change_id_prefix)


def test_read_identity_reports_the_working_copy_description_first_line_and_its_snapshotted_edits(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    (checkout.checkout_path / "notes.txt").write_text("notes\n")
    _jj(jj_binary, checkout.checkout_path, "describe", "-m", "Add notes\n\nWith a longer body.")

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name=None)

    assert identity.description_first_line == "Add notes"
    assert not identity.is_working_copy_empty
    assert identity.unbookmarked_revision_count == 1


def test_read_identity_with_one_bookmark_counts_the_described_revisions_above_it(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "feat")
    _commit_change(jj_binary, checkout.checkout_path, "b.txt", "b\n", "second")

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert identity.bookmarks == ("feat",)
    assert identity.primary_bookmark == "feat"
    assert identity.unbookmarked_revision_count == 1


def test_read_identity_with_many_bookmarks_orders_them_nearest_first_and_prefers_the_requested_name_on_a_tie(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "lower")
    _commit_change(jj_binary, checkout.checkout_path, "b.txt", "b\n", "second")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "aa-other", "zz-requested")

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name="zz-requested")

    assert identity.bookmarks == ("zz-requested", "aa-other", "lower")
    assert identity.primary_bookmark == "zz-requested"
    assert identity.unbookmarked_revision_count == 0


def test_read_identity_prefers_a_bookmark_that_tracks_a_remote_on_a_tie(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "aa-local", "zz-pushed")
    _jj(jj_binary, checkout.checkout_path, "--ignore-working-copy", "git", "push", "--bookmark", "zz-pushed")

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name=None)

    assert identity.bookmarks == ("zz-pushed", "aa-local")


def test_read_identity_never_makes_the_targets_own_name_primary(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "main")

    identity = jj_vcs.read_identity(checkout, target_ref="main@origin", requested_ref_name=None)

    assert identity.bookmarks == ("main",)
    assert identity.primary_bookmark is None
    assert identity.unbookmarked_revision_count == 1


def test_read_identity_leaves_out_a_conflicted_bookmark(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    workspace = checkout.checkout_path
    _commit_change(jj_binary, workspace, "a.txt", "a\n", "first")
    _commit_change(jj_binary, workspace, "b.txt", "b\n", "second")
    _jj(jj_binary, workspace, "--ignore-working-copy", "new", "--no-edit", "-m", "off the stack", "@--")
    _set_bookmarks(jj_binary, workspace, "@--", "kept", "split")
    operation = _latest_operation(jj_binary, workspace)
    # jj resolves concurrent moves itself when one target descends from the other, so the moves go to siblings.
    _set_bookmarks(jj_binary, workspace, "@-", "split")
    _jj(
        jj_binary,
        workspace,
        "--ignore-working-copy",
        "--at-op",
        operation,
        "bookmark",
        "set",
        "split",
        "-r",
        'description(exact:"off the stack\\n")',
    )

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name="split")

    assert identity.bookmarks == ("kept",)
    assert identity.primary_bookmark == "kept"


def test_read_identity_reports_a_conflicted_working_copy(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    workspace = checkout.checkout_path
    _commit_change(jj_binary, workspace, "README.md", "one\n", "side one")
    _jj(jj_binary, workspace, "new", "-m", "side two", "main@origin")
    _commit_change(jj_binary, workspace, "README.md", "two\n", "side two")
    _jj(jj_binary, workspace, "new", 'description(exact:"side one\\n")', 'description(exact:"side two\\n")')

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name=None)

    assert identity.has_conflict


def test_read_identity_reports_a_divergent_working_copy(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    workspace = checkout.checkout_path
    change_id = _jj(jj_binary, workspace, "--ignore-working-copy", "log", "--no-graph", "-r", "@", "-T", "change_id")
    operation = _latest_operation(jj_binary, workspace)
    _jj(jj_binary, workspace, "--ignore-working-copy", "describe", "-m", "version a", "@")
    _jj(
        jj_binary,
        workspace,
        "--ignore-working-copy",
        "--at-op",
        operation,
        "describe",
        "-m",
        "version b",
        f"change_id({change_id})",
    )

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name=None)

    assert identity.is_divergent


@pytest.mark.parametrize("target_ref", [None, "missing@origin", "not a symbol"])
def test_read_identity_without_a_usable_target_uses_the_workspaces_mutable_stack(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, target_ref: str | None
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "feat")

    identity = jj_vcs.read_identity(checkout, target_ref=target_ref, requested_ref_name=None)

    assert identity.bookmarks == ("feat",)


def test_read_identity_neither_snapshots_nor_adds_an_operation(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    (checkout.checkout_path / "unsnapshotted.txt").write_text("not yet seen by jj\n")
    operations_before = _count_operations(jj_binary, checkout.checkout_path)

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name=None)

    assert identity.is_working_copy_empty
    assert _count_operations(jj_binary, checkout.checkout_path) == operations_before


def test_read_identity_keeps_working_in_a_stale_workspace(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout.checkout_path)

    identity = jj_vcs.read_identity(checkout, target_ref=_BASE, requested_ref_name=None)

    assert identity.bookmarks == ()


def test_get_pull_request_refs_has_no_head_without_a_bookmark(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    assert jj_vcs.get_pull_request_refs(checkout, target_ref=_BASE, requested_ref_name="feat").head_ref_names == ()


def test_get_pull_request_refs_lists_the_stack_bookmarks_most_likely_first_without_the_targets_name(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "lower", "main")
    _commit_change(jj_binary, checkout.checkout_path, "b.txt", "b\n", "second")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "upper")

    refs = jj_vcs.get_pull_request_refs(checkout, target_ref="main@origin", requested_ref_name=None)

    assert refs.head_ref_names == ("upper", "lower")


def test_get_pull_request_refs_names_the_targets_bookmark_as_the_base(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    def read_base(target_ref: str | None) -> str | None:
        return jj_vcs.get_pull_request_refs(checkout, target_ref=target_ref, requested_ref_name=None).base_ref_name

    assert read_base("release/1.0@origin") == "release/1.0"
    assert read_base("main") == "main"
    assert read_base(None) is None


def test_get_pull_request_refs_raises_when_the_checkout_is_gone(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    shutil.rmtree(checkout.checkout_path)

    with pytest.raises(VcsCommandError):
        jj_vcs.get_pull_request_refs(checkout, target_ref=_BASE, requested_ref_name=None)


def _bookmarked_commit_id(jj_binary: JjBinary, repo_dir: Path, name: str) -> str | None:
    """The commit the local bookmark `name` points at; None when there is no such bookmark."""
    revset = f'present(bookmarks(exact:"{name}"))'
    return _commit_id(jj_binary, repo_dir, revset) or None


def test_create_initial_bookmark_puts_the_requested_bookmark_on_the_newest_described_change(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _commit_change(jj_binary, checkout.checkout_path, "b.txt", "b\n", "second")

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.CREATED
    assert _bookmarked_commit_id(jj_binary, checkout.checkout_path, "feat") == _commit_id(
        jj_binary, checkout.checkout_path, "@-"
    )


def test_create_initial_bookmark_snapshots_the_agents_last_edits_first(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _jj(jj_binary, checkout.checkout_path, "describe", "-m", "work in the working copy")
    (checkout.checkout_path / "late.txt").write_text("written after the last jj command\n")

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.CREATED
    files = _jj(jj_binary, checkout.checkout_path, "--ignore-working-copy", "file", "list", "-r", "feat")
    assert "late.txt" in files.split()


@pytest.mark.parametrize("bookmark_names", [("mine",), ("mine", "also-mine")])
def test_create_initial_bookmark_leaves_a_stack_that_already_has_bookmarks_alone(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, bookmark_names: tuple[str, ...]
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", *bookmark_names)
    _commit_change(jj_binary, checkout.checkout_path, "b.txt", "b\n", "second")

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.STACK_HAS_A_BOOKMARK
    assert _bookmarked_commit_id(jj_binary, checkout.checkout_path, "feat") is None


def test_create_initial_bookmark_waits_while_the_work_is_undescribed(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    (checkout.checkout_path / "a.txt").write_text("a\n")

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.NO_SINGLE_NEWEST_DESCRIBED_REVISION
    assert _bookmarked_commit_id(jj_binary, checkout.checkout_path, "feat") is None


def test_create_initial_bookmark_waits_while_two_described_changes_are_both_newest(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _make_merge_working_copy(jj_binary, checkout.checkout_path)

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.NO_SINGLE_NEWEST_DESCRIBED_REVISION
    assert _bookmarked_commit_id(jj_binary, checkout.checkout_path, "feat") is None


def test_create_initial_bookmark_leaves_a_requested_name_another_stack_has_taken(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _jj(jj_binary, jj_colocated_repo.path, "--ignore-working-copy", "new", "--no-edit", "-m", "elsewhere", _BASE)
    _set_bookmarks(jj_binary, jj_colocated_repo.path, 'description(exact:"elsewhere\n")', "feat")
    taken_commit_id = _bookmarked_commit_id(jj_binary, jj_colocated_repo.path, "feat")
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.NAME_UNAVAILABLE
    assert _bookmarked_commit_id(jj_binary, checkout.checkout_path, "feat") == taken_commit_id


def test_create_initial_bookmark_leaves_a_requested_name_that_exists_only_on_a_remote(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _push_bookmark_from(jj_binary, jj_colocated_repo.path, "feat", _BASE)
    _jj(jj_binary, jj_colocated_repo.path, "--ignore-working-copy", "bookmark", "forget", "feat")
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")

    outcome = jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")

    assert outcome is JjInitialBookmarkOutcome.NAME_UNAVAILABLE
    assert _bookmarked_commit_id(jj_binary, checkout.checkout_path, "feat") is None


def test_create_initial_bookmark_raises_in_a_stale_workspace(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout.checkout_path)

    with pytest.raises(JjWorkingCopyStaleError):
        jj_vcs.create_initial_bookmark(checkout, target_ref=_BASE, requested_ref_name="feat")


def _advance_origin_main(jj_binary: JjBinary, repo: JjColocatedRepo, file_name: str) -> None:
    """Commit `file_name` on `main` in the user's checkout, push it, and fetch, so `main@origin` moves on."""
    (repo.path / file_name).write_text("on main\n")
    run_blocking(["git", "add", file_name], cwd=repo.path)
    run_blocking(["git", "commit", "-q", "-m", "main moves on"], cwd=repo.path)
    run_blocking(["git", "push", "-q", "origin", "main"], cwd=repo.path)
    _jj(jj_binary, repo.path, "git", "fetch")


def _make_merge_working_copy(jj_binary: JjBinary, checkout: Path) -> None:
    """Leave the working copy a new change on top of two siblings that touch different files."""
    _commit_change(jj_binary, checkout, "one.txt", "one\n", "side one")
    _jj(jj_binary, checkout, "new", "-m", "side two", "main@origin")
    _commit_change(jj_binary, checkout, "two.txt", "two\n", "side two")
    _jj(jj_binary, checkout, "new", 'description(exact:"side one\\n")', 'description(exact:"side two\\n")')


def _refuse_large_files(jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, snapshot_limit: _SnapshotLimit) -> None:
    """Lower the limit to 1 MiB and write a 2 MiB file, which jj then refuses to snapshot."""
    snapshot_limit.mib = 1
    jj_vcs.verify_checkout(checkout)
    (checkout.checkout_path / "big.bin").write_bytes(b"x" * (2 * _MEBIBYTE))


def test_compute_diff_artifact_diffs_the_working_copy_against_its_parent_including_new_files(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    (checkout.checkout_path / "README.md").write_text("changed\n")
    (checkout.checkout_path / "new.txt").write_text("brand new\n")

    artifact = jj_vcs.compute_diff_artifact(checkout, target_ref=None, context_lines=3)

    assert "diff --git a/README.md b/README.md" in artifact.uncommitted_diff
    assert "+changed" in artifact.uncommitted_diff
    assert "diff --git a/new.txt b/new.txt" in artifact.uncommitted_diff
    assert "+brand new" in artifact.uncommitted_diff
    assert artifact.uncommitted_diff_base == _commit_id(jj_binary, checkout.checkout_path, "@-")
    assert artifact.target_branch_diff == ""
    assert artifact.target_branch_merge_base == ""
    assert artifact.file_errors == {}


@pytest.mark.parametrize("is_main_tracked", [True, False])
def test_compute_diff_artifact_diffs_everything_since_the_fork_point_with_the_target(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    is_main_tracked: bool,
) -> None:
    if not is_main_tracked:
        _untrack_main(jj_binary, jj_colocated_repo)
    fork_point = _commit_id(jj_binary, jj_colocated_repo.path, "main@origin")
    _advance_origin_main(jj_binary, jj_colocated_repo, "main_only.txt")
    _commit_change(jj_binary, checkout.checkout_path, "committed.txt", "committed\n", "work")
    (checkout.checkout_path / "README.md").write_text("uncommitted\n")

    artifact = jj_vcs.compute_diff_artifact(checkout, target_ref=_BASE, context_lines=3)

    assert artifact.target_branch_merge_base == fork_point
    assert "+committed" in artifact.target_branch_diff
    assert "+uncommitted" in artifact.target_branch_diff
    assert "main_only.txt" not in artifact.target_branch_diff
    assert "committed.txt" not in artifact.uncommitted_diff
    assert "+uncommitted" in artifact.uncommitted_diff


def test_compute_diff_artifact_shows_the_requested_lines_of_context(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    lines = [f"line {number}\n" for number in range(1, 11)]
    _commit_change(jj_binary, checkout.checkout_path, "lines.txt", "".join(lines), "add lines")
    lines[4] = "changed\n"
    (checkout.checkout_path / "lines.txt").write_text("".join(lines))

    narrow = jj_vcs.compute_diff_artifact(checkout, target_ref=None, context_lines=0)
    wide = jj_vcs.compute_diff_artifact(checkout, target_ref=None, context_lines=2)

    assert "\n line 4\n" not in narrow.uncommitted_diff
    assert "\n line 3\n line 4\n-line 5\n+changed\n line 6\n line 7" in wide.uncommitted_diff
    assert "\n line 2\n" not in wide.uncommitted_diff


def test_compute_diff_artifact_reports_a_file_too_large_to_snapshot(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, snapshot_limit: _SnapshotLimit
) -> None:
    _refuse_large_files(jj_vcs, checkout, snapshot_limit)

    artifact = jj_vcs.compute_diff_artifact(checkout, target_ref=_BASE, context_lines=3)

    assert "big.bin" not in artifact.uncommitted_diff
    assert "big.bin" not in artifact.target_branch_diff
    assert list(artifact.file_errors) == ["big.bin"]
    assert "(2097152 bytes)" in artifact.file_errors["big.bin"]


@pytest.mark.parametrize("target_ref", ["missing@origin", "origin/main", "a" * 40])
def test_compute_diff_artifact_leaves_the_target_diff_empty_for_a_target_that_names_no_commit(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, target_ref: str
) -> None:
    (checkout.checkout_path / "README.md").write_text("changed\n")

    artifact = jj_vcs.compute_diff_artifact(checkout, target_ref=target_ref, context_lines=3)

    assert "+changed" in artifact.uncommitted_diff
    assert artifact.target_branch_diff == ""
    assert artifact.target_branch_merge_base == ""


def test_compute_diff_artifact_names_no_single_old_side_for_a_merge_working_copy(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _make_merge_working_copy(jj_binary, checkout.checkout_path)
    (checkout.checkout_path / "README.md").write_text("changed on the merge\n")

    artifact = jj_vcs.compute_diff_artifact(checkout, target_ref=None, context_lines=3)

    assert artifact.uncommitted_diff_base == ""
    assert "+changed on the merge" in artifact.uncommitted_diff
    assert "one.txt" not in artifact.uncommitted_diff


def test_compute_diff_artifact_raises_for_a_stale_workspace(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout.checkout_path)

    with pytest.raises(JjWorkingCopyStaleError):
        jj_vcs.compute_diff_artifact(checkout, target_ref=_BASE, context_lines=3)


def test_get_revision_history_lists_the_revisions_since_the_fork_point_newest_first(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    fork_point = _commit_id(jj_binary, jj_colocated_repo.path, "main@origin")
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first\n\nwith a body")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "feat")
    (checkout.checkout_path / "README.md").write_text("edited\n")

    history = jj_vcs.get_revision_history(checkout, target_ref=_BASE, base_commit_id=None)

    assert history.fork_point == fork_point
    working_copy, first = history.revisions
    assert working_copy.is_working_copy
    assert working_copy.description == ""
    assert working_copy.parent_commit_ids == (first.commit_id,)
    assert working_copy.files == (
        CommitFileChange(path="README.md", status="M", old_path=None, additions=1, deletions=1),
    )
    assert not first.is_working_copy
    assert first.description == "first\n\nwith a body"
    assert first.bookmarks == ("feat",)
    assert first.author_name == JJ_TEST_USER_NAME
    assert first.author_email == JJ_TEST_USER_EMAIL
    assert first.parent_commit_ids == (fork_point,)
    assert first.files == (CommitFileChange(path="a.txt", status="A", old_path=None, additions=1, deletions=0),)
    assert first.change_id == _jj(
        jj_binary, checkout.checkout_path, "--ignore-working-copy", "log", "--no-graph", "-r", "@-", "-T", "change_id"
    )
    assert (first.is_empty, first.has_conflict, first.is_divergent) == (False, False, False)


def test_get_revision_history_gives_each_change_id_its_shortest_unique_prefix(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")

    history = jj_vcs.get_revision_history(checkout, target_ref=_BASE, base_commit_id=None)

    assert len(history.revisions) == 2
    for revision in history.revisions:
        expected_prefix = _jj(
            jj_binary,
            checkout.checkout_path,
            "--ignore-working-copy",
            "log",
            "--no-graph",
            "-r",
            revision.commit_id,
            "-T",
            "change_id.shortest().prefix()",
        )
        assert revision.change_id_prefix == expected_prefix
        assert revision.change_id.startswith(revision.change_id_prefix)


def test_get_revision_history_reports_a_rename_with_its_old_path(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    workspace = checkout.checkout_path
    _commit_change(jj_binary, workspace, "orig.txt", "l1\nl2\nl3\n", "add orig")
    (workspace / "orig.txt").rename(workspace / "renamed.txt")
    _commit_change(jj_binary, workspace, "renamed.txt", "l1\nl2\nl3\nl4\n", "rename")

    history = jj_vcs.get_revision_history(checkout, target_ref=_BASE, base_commit_id=None)

    rename = history.revisions[1]
    assert rename.files == (
        CommitFileChange(path="renamed.txt", status="R", old_path="orig.txt", additions=1, deletions=0),
    )


@pytest.mark.parametrize("target_ref", [None, "missing@origin"])
def test_get_revision_history_falls_back_to_the_base_commit_without_a_usable_target(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    target_ref: str | None,
) -> None:
    base = _commit_id(jj_binary, jj_colocated_repo.path, "main@origin")

    history = jj_vcs.get_revision_history(checkout, target_ref=target_ref, base_commit_id=base)

    assert history.fork_point == base
    assert [revision.is_working_copy for revision in history.revisions] == [True]


def test_get_revision_history_is_empty_without_any_fork_point(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    history = jj_vcs.get_revision_history(checkout, target_ref=None, base_commit_id=None)

    assert history == JjRevisionHistory(revisions=(), fork_point=None)


def test_get_revision_diff_diffs_a_revision_against_its_parent(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    commit_id = _commit_id(jj_binary, checkout.checkout_path, "@-")

    revision_diff = jj_vcs.get_revision_diff(checkout, commit_id)

    assert revision_diff.commit_id == commit_id
    assert revision_diff.parent_commit_id == _commit_id(jj_binary, checkout.checkout_path, "@--")
    assert "diff --git a/a.txt b/a.txt" in revision_diff.diff
    assert "+a" in revision_diff.diff


def test_get_revision_diff_names_no_single_parent_for_a_merge(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _make_merge_working_copy(jj_binary, checkout.checkout_path)

    revision_diff = jj_vcs.get_revision_diff(checkout, _commit_id(jj_binary, checkout.checkout_path, "@"))

    assert revision_diff.parent_commit_id is None
    assert revision_diff.diff == ""


@pytest.mark.parametrize("commit_id", ["@", "main", "abc123", "A" * 40, "a" * 40])
def test_get_revision_diff_rejects_anything_but_the_full_id_of_an_existing_commit(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, commit_id: str
) -> None:
    with pytest.raises(InvalidRevisionError):
        jj_vcs.get_revision_diff(checkout, commit_id)


def test_list_files_lists_every_file_including_ones_not_yet_snapshotted(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    (checkout.checkout_path / "dir").mkdir()
    (checkout.checkout_path / "dir" / "b c (1).txt").write_text("new\n")

    assert jj_vcs.list_files(checkout) == ["README.md", "dir/b c (1).txt"]


def test_list_files_leaves_out_a_file_too_large_to_snapshot(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, snapshot_limit: _SnapshotLimit
) -> None:
    _refuse_large_files(jj_vcs, checkout, snapshot_limit)

    assert jj_vcs.list_files(checkout) == ["README.md"]


def test_list_files_reports_a_stale_workspace_as_unavailable(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout.checkout_path)

    with pytest.raises(CheckoutFilesUnavailableError):
        jj_vcs.list_files(checkout)


def test_read_file_at_revision_reads_a_file_as_a_commit_has_it(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    (checkout.checkout_path / "dir name").mkdir()
    _commit_change(jj_binary, checkout.checkout_path, "dir name/a (1).txt", "first\n", "add")
    commit_id = _commit_id(jj_binary, checkout.checkout_path, "@-")
    (checkout.checkout_path / "dir name" / "a (1).txt").write_text("later\n")

    result = jj_vcs.read_file_at_revision(checkout, "dir name/a (1).txt", commit_id)

    assert result == FileAtRefResult(content="first\n", encoding="utf-8")


def test_read_file_at_revision_base64_encodes_content_with_a_nul_byte(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    (checkout.checkout_path / "data.bin").write_bytes(b"a\x00b")
    _jj(jj_binary, checkout.checkout_path, "commit", "-m", "binary")

    result = jj_vcs.read_file_at_revision(checkout, "data.bin", _commit_id(jj_binary, checkout.checkout_path, "@-"))

    assert result == FileAtRefResult(content=base64.b64encode(b"a\x00b").decode("ascii"), encoding="base64")


def test_read_file_at_revision_reports_a_file_the_commit_does_not_have(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    with pytest.raises(FileNotFoundAtRefError):
        jj_vcs.read_file_at_revision(checkout, "missing.txt", _commit_id(jj_binary, checkout.checkout_path, "@"))


@pytest.mark.parametrize("revision", ["@", "HEAD", "main@origin", "all()", "abc123"])
def test_read_file_at_revision_accepts_only_a_full_commit_id(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, revision: str
) -> None:
    with pytest.raises(FileNotFoundAtRefError):
        jj_vcs.read_file_at_revision(checkout, "README.md", revision)


def test_discard_file_changes_restores_a_modified_file_and_deletes_an_added_one(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    (checkout.checkout_path / "README.md").write_text("changed\n")
    (checkout.checkout_path / "new file.txt").write_text("new\n")

    results = [jj_vcs.discard_file_changes(checkout, path) for path in ("README.md", "new file.txt")]

    assert [result.success for result in results] == [True, True]
    assert (checkout.checkout_path / "README.md").read_text() == "# jj fixture repo\n"
    assert not (checkout.checkout_path / "new file.txt").exists()
    assert jj_vcs.compute_diff_artifact(checkout, target_ref=None, context_lines=3).uncommitted_diff == ""


@pytest.mark.parametrize("file_path", ["/etc/passwd", "../outside.txt"])
def test_discard_file_changes_refuses_a_path_outside_the_checkout(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, file_path: str
) -> None:
    result = jj_vcs.discard_file_changes(checkout, file_path)

    assert not result.success
    assert result.error_message


def test_discard_file_changes_reports_a_stale_workspace_as_a_failure(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, checkout.checkout_path)

    result = jj_vcs.discard_file_changes(checkout, "README.md")

    assert not result.success
    assert "stale" in (result.error_message or "")


def test_compute_change_fingerprint_changes_with_an_edit_and_is_stable_otherwise(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation
) -> None:
    first = jj_vcs.compute_change_fingerprint(checkout)
    second = jj_vcs.compute_change_fingerprint(checkout)
    (checkout.checkout_path / "README.md").write_text("changed\n")
    after_edit = jj_vcs.compute_change_fingerprint(checkout)

    assert first is not None
    assert first == second
    assert after_edit not in (None, first)


def test_compute_change_fingerprint_is_none_when_jj_fails(jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation) -> None:
    shutil.rmtree(checkout.checkout_path)

    assert jj_vcs.compute_change_fingerprint(checkout) is None


def test_agent_environment_puts_jj_on_path_points_gh_at_a_github_origin_and_stops_git_above_the_checkout(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    jj_colocated_repo: JjColocatedRepo,
    isolated_sculptor_folder: Path,  # noqa: F811
) -> None:
    make_github_looking_origin(jj_colocated_repo.path, jj_colocated_repo.remote_path)

    environment = jj_vcs.agent_environment(checkout)

    assert environment == AgentVcsEnvironment(
        path_prefixes=(get_jj_bin_dir(),),
        environment_variables={
            "GH_REPO": "github.com/sculptor-tests/jj-fixture",
            "GIT_CEILING_DIRECTORIES": str(checkout.checkout_path.parent),
        },
        chat_agent_environment_variables={"JJ_EDITOR": "false"},
    )


def test_agent_environment_sets_no_gh_repo_for_an_origin_off_github(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    isolated_sculptor_folder: Path,  # noqa: F811
) -> None:
    assert "GH_REPO" not in jj_vcs.agent_environment(checkout).environment_variables


def test_a_process_on_the_agent_environment_path_finds_the_linked_jj_when_none_is_on_path(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    jj_binary: JjBinary,
    isolated_sculptor_folder: Path,  # noqa: F811
) -> None:
    path_without_jj = os.pathsep.join(["/usr/bin", "/bin"])
    assert shutil.which("jj", path=path_without_jj) is None
    link_jj_bin(jj_binary.path)
    environment = jj_vcs.agent_environment(checkout)
    agent_path = os.pathsep.join([*(str(prefix) for prefix in environment.path_prefixes), path_without_jj])

    found_jj = shutil.which("jj", path=agent_path)
    version = subprocess.run(
        ["jj", "--version"],
        cwd=checkout.checkout_path,
        env={**os.environ, "PATH": agent_path},
        capture_output=True,
        text=True,
    )

    assert found_jj is not None and Path(found_jj).resolve() == jj_binary.path.resolve()
    assert version.returncode == 0, version.stderr
    assert version.stdout.startswith(f"jj {jj_binary.version}")


def test_describing_the_agent_environment_creates_and_changes_no_file(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    isolated_sculptor_folder: Path,  # noqa: F811
) -> None:
    environment = jj_vcs.agent_environment(checkout)

    assert environment.path_prefixes == (get_jj_bin_dir(),)
    assert not environment.path_prefixes[0].exists()


def test_the_chat_agent_variables_make_a_jj_command_that_opens_an_editor_fail_at_once(
    jj_vcs: JjWorkspaceVcs,
    checkout: CheckoutLocation,
    jj_binary: JjBinary,
    isolated_sculptor_folder: Path,  # noqa: F811
) -> None:
    environment = jj_vcs.agent_environment(checkout)

    describe = subprocess.run(
        [str(jj_binary.path), "describe"],
        cwd=checkout.checkout_path,
        env={**os.environ, "EDITOR": "vi", **environment.chat_agent_environment_variables},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert describe.returncode != 0


def test_git_finds_no_enclosing_repository_from_a_checkout_under_the_agent_environment(
    jj_vcs: JjWorkspaceVcs, jj_colocated_repo: JjColocatedRepo, tmp_path: Path
) -> None:
    outer_repo = tmp_path / "outer"
    outer_repo.mkdir()
    run_blocking(["git", "init", "-q"], cwd=outer_repo)
    location = jj_vcs.create_checkout(_spec(jj_colocated_repo, outer_repo / "env" / "code"))
    show_toplevel = ["git", "rev-parse", "--show-toplevel"]
    agent_env = {**os.environ, **jj_vcs.agent_environment(location).environment_variables}

    without_ceiling = subprocess.run(show_toplevel, cwd=location.checkout_path, capture_output=True, text=True)
    with_ceiling = subprocess.run(show_toplevel, cwd=location.checkout_path, env=agent_env, capture_output=True)

    assert Path(without_ceiling.stdout.strip()).resolve() == outer_repo.resolve()
    assert with_ceiling.returncode != 0


def test_jj_still_fetches_under_the_agent_environment(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    agent_env = {**os.environ, **jj_vcs.agent_environment(checkout).environment_variables}

    fetch = subprocess.run(
        [str(jj_binary.path), "git", "fetch", "--remote", "origin"],
        cwd=checkout.checkout_path,
        env=agent_env,
        capture_output=True,
        text=True,
    )

    assert fetch.returncode == 0, fetch.stderr


def test_reads_of_an_unchanged_workspace_add_no_operation(
    jj_vcs: JjWorkspaceVcs, checkout: CheckoutLocation, jj_binary: JjBinary
) -> None:
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    commit_id = _commit_id(jj_binary, checkout.checkout_path, "@-")
    operations_before = _count_operations(jj_binary, checkout.checkout_path)

    jj_vcs.compute_diff_artifact(checkout, target_ref=_BASE, context_lines=3)
    jj_vcs.get_revision_history(checkout, target_ref=_BASE, base_commit_id=None)
    jj_vcs.get_revision_diff(checkout, commit_id)
    jj_vcs.list_files(checkout)
    jj_vcs.read_file_at_revision(checkout, "a.txt", commit_id)
    jj_vcs.compute_change_fingerprint(checkout)
    jj_vcs.agent_environment(checkout)

    assert _count_operations(jj_binary, checkout.checkout_path) == operations_before


def _local_bookmark_names(jj_binary: JjBinary, repo_dir: Path) -> set[str]:
    output = _jj(jj_binary, repo_dir, "--ignore-working-copy", "bookmark", "list", "-T", 'name ++ "\\n"')
    return set(output.split())


def _workspace_config_directory(jj_binary: JjBinary, checkout: Path) -> Path:
    return Path(_jj(jj_binary, checkout, "--ignore-working-copy", "config", "path", "--workspace").strip()).parent


def _is_visible(jj_binary: JjBinary, repo_dir: Path, commit_id: str) -> bool:
    revset = f"present({commit_id}) & ::visible_heads()"
    return _jj(jj_binary, repo_dir, "--ignore-working-copy", "log", "--no-graph", "-r", revset, "-T", '"x"') != ""


def _move_origin_main_to(jj_binary: JjBinary, repo: JjColocatedRepo, commit_id: str) -> None:
    """Make `main` on the remote point at `commit_id`, as merging a pull request does, then fetch it."""
    run_blocking(["git", "push", "-q", "origin", f"{commit_id}:refs/heads/main"], cwd=repo.path)
    _jj(jj_binary, repo.path, "--ignore-working-copy", "git", "fetch")


def _remote_branches(repo: JjColocatedRepo) -> set[str]:
    output = run_blocking(["git", "ls-remote", "--heads", str(repo.remote_path)], cwd=repo.path).stdout
    return {line.split("refs/heads/", 1)[1] for line in output.splitlines()}


@pytest.fixture
def stacked_checkout(checkout: CheckoutLocation, jj_binary: JjBinary) -> CheckoutLocation:
    """`checkout` with `lower` on its first revision, `upper` on its second, and an edit in the working copy."""
    _commit_change(jj_binary, checkout.checkout_path, "a.txt", "a\n", "first")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "lower")
    _commit_change(jj_binary, checkout.checkout_path, "b.txt", "b\n", "second")
    _set_bookmarks(jj_binary, checkout.checkout_path, "@-", "upper")
    (checkout.checkout_path / "c.txt").write_text("c\n")
    _jj(jj_binary, checkout.checkout_path, "describe", "-m", "third")
    return checkout


def test_remove_checkout_under_never_forgets_the_workspace_and_its_config_but_keeps_its_bookmarks(
    jj_vcs: JjWorkspaceVcs, stacked_checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    config_directory = _workspace_config_directory(jj_binary, stacked_checkout.checkout_path)
    assert config_directory.is_dir()

    jj_vcs.remove_checkout(stacked_checkout, target_ref=_BASE, created_ref_name="upper", deletion_policy="never")

    assert stacked_checkout.checkout_name not in _workspace_roots_by_name(jj_binary, jj_colocated_repo.path)
    assert not config_directory.exists()
    assert {"lower", "upper"} <= _local_bookmark_names(jj_binary, jj_colocated_repo.path)


def test_remove_checkout_under_always_forgets_every_bookmark_on_the_stack_and_keeps_the_commits(
    jj_vcs: JjWorkspaceVcs, stacked_checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    described_working_copy = _commit_id(jj_binary, stacked_checkout.checkout_path, "@")
    lower_commit = _commit_id(jj_binary, stacked_checkout.checkout_path, "lower")

    jj_vcs.remove_checkout(stacked_checkout, target_ref=_BASE, created_ref_name="upper", deletion_policy="always")

    assert _local_bookmark_names(jj_binary, jj_colocated_repo.path) == {"main"}
    assert _is_visible(jj_binary, jj_colocated_repo.path, described_working_copy)
    assert _is_visible(jj_binary, jj_colocated_repo.path, lower_commit)


def test_remove_checkout_never_forgets_the_targets_own_name(
    jj_vcs: JjWorkspaceVcs, stacked_checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _set_bookmarks(jj_binary, stacked_checkout.checkout_path, "lower", "main")

    jj_vcs.remove_checkout(stacked_checkout, target_ref="main@origin", created_ref_name=None, deletion_policy="always")

    assert _local_bookmark_names(jj_binary, jj_colocated_repo.path) == {"main"}


def test_remove_checkout_keeps_a_bookmark_on_another_live_workspaces_stack(
    jj_vcs: JjWorkspaceVcs, stacked_checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    other_workspace = jj_colocated_repo.path.parent / "other"
    _jj(
        jj_binary,
        jj_colocated_repo.path,
        "workspace",
        "add",
        "--no-colocate",
        "--name",
        "other",
        "-r",
        "lower",
        str(other_workspace),
    )

    jj_vcs.remove_checkout(stacked_checkout, target_ref=_BASE, created_ref_name="upper", deletion_policy="always")

    assert _local_bookmark_names(jj_binary, jj_colocated_repo.path) == {"main", "lower"}


@pytest.mark.parametrize("is_main_tracked", [True, False])
def test_remove_checkout_when_safe_forgets_a_fully_pushed_bookmark_and_leaves_the_remote_branch(
    jj_vcs: JjWorkspaceVcs,
    stacked_checkout: CheckoutLocation,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    is_main_tracked: bool,
) -> None:
    if not is_main_tracked:
        _untrack_main(jj_binary, jj_colocated_repo)
    _jj(jj_binary, stacked_checkout.checkout_path, "--ignore-working-copy", "git", "push", "--bookmark", "upper")

    jj_vcs.remove_checkout(
        stacked_checkout, target_ref=_BASE, created_ref_name="upper", deletion_policy="delete_if_safe"
    )

    assert _local_bookmark_names(jj_binary, jj_colocated_repo.path) == {"main", "lower"}
    assert "upper" in _remote_branches(jj_colocated_repo)


def test_remove_checkout_when_safe_keeps_a_bookmark_pushed_before_its_latest_change(
    jj_vcs: JjWorkspaceVcs, stacked_checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    _jj(jj_binary, stacked_checkout.checkout_path, "--ignore-working-copy", "git", "push", "--bookmark", "lower")
    _set_bookmarks(jj_binary, stacked_checkout.checkout_path, "upper", "lower")

    jj_vcs.remove_checkout(stacked_checkout, target_ref=_BASE, created_ref_name=None, deletion_policy="delete_if_safe")

    assert {"lower", "upper"} <= _local_bookmark_names(jj_binary, jj_colocated_repo.path)


@pytest.mark.parametrize("is_main_tracked", [True, False])
def test_remove_checkout_when_safe_forgets_the_created_bookmark_once_the_target_contains_it(
    jj_vcs: JjWorkspaceVcs,
    stacked_checkout: CheckoutLocation,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    is_main_tracked: bool,
) -> None:
    if not is_main_tracked:
        _untrack_main(jj_binary, jj_colocated_repo)
    _move_origin_main_to(jj_binary, jj_colocated_repo, _commit_id(jj_binary, stacked_checkout.checkout_path, "lower"))

    jj_vcs.remove_checkout(
        stacked_checkout, target_ref=_BASE, created_ref_name="lower", deletion_policy="delete_if_safe"
    )

    assert "lower" not in _local_bookmark_names(jj_binary, jj_colocated_repo.path)
    assert "upper" in _local_bookmark_names(jj_binary, jj_colocated_repo.path)


def test_remove_checkout_still_forgets_the_workspace_and_bookmarks_when_its_directory_is_gone(
    jj_vcs: JjWorkspaceVcs, stacked_checkout: CheckoutLocation, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    shutil.rmtree(stacked_checkout.checkout_path)

    jj_vcs.remove_checkout(stacked_checkout, target_ref=_BASE, created_ref_name="upper", deletion_policy="always")

    assert stacked_checkout.checkout_name not in _workspace_roots_by_name(jj_binary, jj_colocated_repo.path)
    assert _local_bookmark_names(jj_binary, jj_colocated_repo.path) == {"main"}


def test_remove_checkout_survives_a_repository_that_is_gone(jj_vcs: JjWorkspaceVcs, tmp_path: Path) -> None:
    location = CheckoutLocation(
        repo_path=tmp_path / "no-repo", checkout_path=tmp_path / "no-checkout", checkout_name=f"ws_{uuid4().hex}"
    )

    jj_vcs.remove_checkout(location, target_ref=_BASE, created_ref_name="feat", deletion_policy="always")
