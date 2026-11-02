import base64
from collections.abc import Sequence
from pathlib import Path

import pytest

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.vcs.data_types import AgentVcsEnvironment
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import GitHeadIdentity
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.errors import CheckoutFilesUnavailableError
from sculptor.services.workspace_service.vcs.errors import GitCommandInJjWorkspaceError
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_workspace_vcs import DEFAULT_GIT_WORKSPACE_SETUP_COMMAND
from sculptor.services.workspace_service.vcs.git_workspace_vcs import GitWorkspaceVcs


def _git(cwd: Path, arguments: Sequence[str]) -> str:
    return run_blocking(["git", *arguments], cwd=cwd).stdout.strip()


def _commit_file(repo: Path, name: str, content: str | bytes, message: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    _git(repo, ["add", "--", name])
    _git(repo, ["commit", "-q", "-m", message])
    return _git(repo, ["rev-parse", "HEAD"])


def _branch_exists(repo: Path, branch: str) -> bool:
    return _git(repo, ["branch", "--list", branch]) != ""


def _in_place(repo: Path) -> CheckoutLocation:
    return CheckoutLocation(repo_path=repo, checkout_path=repo)


@pytest.fixture
def worktree_vcs(git_cli: GitCli) -> GitWorkspaceVcs:
    return GitWorkspaceVcs(WorkspaceInitializationStrategy.WORKTREE, git_cli)


@pytest.fixture
def clone_vcs(git_cli: GitCli) -> GitWorkspaceVcs:
    return GitWorkspaceVcs(WorkspaceInitializationStrategy.CLONE, git_cli)


@pytest.fixture
def in_place_vcs(git_cli: GitCli) -> GitWorkspaceVcs:
    return GitWorkspaceVcs(WorkspaceInitializationStrategy.IN_PLACE, git_cli)


@pytest.fixture
def worktree(worktree_vcs: GitWorkspaceVcs, git_repo: Path, tmp_path: Path) -> CheckoutLocation:
    """A worktree of `git_repo` on branch `feature`, created through the seam."""
    spec = CheckoutSpec(
        repo_path=git_repo, checkout_path=tmp_path / "env" / "code", base_ref="main", new_ref_name="feature"
    )
    return worktree_vcs.create_checkout(spec)


# create_checkout


def test_create_checkout_adds_a_worktree_on_a_new_branch_off_the_base(
    worktree: CheckoutLocation, git_repo: Path
) -> None:
    assert (worktree.checkout_path / ".git").is_file()
    assert _git(worktree.checkout_path, ["symbolic-ref", "--short", "HEAD"]) == "feature"
    assert _git(worktree.checkout_path, ["rev-parse", "HEAD"]) == _git(git_repo, ["rev-parse", "main"])
    assert worktree.repo_path == git_repo


def test_create_checkout_fails_for_a_worktree_with_a_missing_base(
    worktree_vcs: GitWorkspaceVcs, git_repo: Path, tmp_path: Path
) -> None:
    spec = CheckoutSpec(repo_path=git_repo, checkout_path=tmp_path / "code", base_ref="nope", new_ref_name="feature")

    with pytest.raises(VcsCommandError):
        worktree_vcs.create_checkout(spec)

    assert not _branch_exists(git_repo, "feature")


def test_create_checkout_requires_a_base_and_a_branch_for_a_worktree(
    worktree_vcs: GitWorkspaceVcs, git_repo: Path, tmp_path: Path
) -> None:
    with pytest.raises(InvalidCheckoutSpecError):
        worktree_vcs.create_checkout(
            CheckoutSpec(repo_path=git_repo, checkout_path=tmp_path / "code", base_ref=None, new_ref_name="feature")
        )
    with pytest.raises(InvalidCheckoutSpecError):
        worktree_vcs.create_checkout(
            CheckoutSpec(repo_path=git_repo, checkout_path=tmp_path / "code", base_ref="main", new_ref_name=None)
        )


def test_create_checkout_in_place_uses_the_repository_and_creates_nothing(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path, tmp_path: Path
) -> None:
    spec = CheckoutSpec(repo_path=git_repo, checkout_path=git_repo, base_ref=None, new_ref_name=None)

    assert in_place_vcs.create_checkout(spec) == _in_place(git_repo)
    assert _git(git_repo, ["worktree", "list", "--porcelain"]).count("worktree ") == 1


def test_create_checkout_clones_and_creates_the_requested_branch(
    clone_vcs: GitWorkspaceVcs, git_repo: Path, tmp_path: Path
) -> None:
    _git(git_repo, ["branch", "base"])
    destination = tmp_path / "env" / "code"
    destination.parent.mkdir()
    spec = CheckoutSpec(repo_path=git_repo, checkout_path=destination, base_ref="base", new_ref_name="feature")

    location = clone_vcs.create_checkout(spec)

    assert location == CheckoutLocation(repo_path=git_repo, checkout_path=destination)
    assert (destination / ".git").is_dir()
    assert _git(destination, ["symbolic-ref", "--short", "HEAD"]) == "feature"
    assert not _branch_exists(git_repo, "feature")


# verify_checkout and remove_checkout


def test_verify_checkout_accepts_a_git_checkout(worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation) -> None:
    worktree_vcs.verify_checkout(worktree)


def test_remove_checkout_deletes_a_merged_branch_when_safe(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    worktree_vcs.remove_checkout(worktree, "feature", "delete_if_safe")

    assert not worktree.checkout_path.exists()
    assert not _branch_exists(git_repo, "feature")


def test_remove_checkout_keeps_an_unmerged_branch_when_deleting_only_if_safe(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    _commit_file(worktree.checkout_path, "new.txt", "new\n", "unmerged")

    worktree_vcs.remove_checkout(worktree, "feature", "delete_if_safe")

    assert not worktree.checkout_path.exists()
    assert _branch_exists(git_repo, "feature")


def test_remove_checkout_always_deletes_an_unmerged_branch(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    _commit_file(worktree.checkout_path, "new.txt", "new\n", "unmerged")

    worktree_vcs.remove_checkout(worktree, "feature", "always")

    assert not _branch_exists(git_repo, "feature")


def test_remove_checkout_never_deletes_the_branch_under_the_never_policy(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    worktree_vcs.remove_checkout(worktree, "feature", "never")

    assert not worktree.checkout_path.exists()
    assert _branch_exists(git_repo, "feature")


def test_remove_checkout_deletes_the_branch_the_created_one_was_renamed_to(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    _git(worktree.checkout_path, ["branch", "-m", "feature", "renamed"])

    worktree_vcs.remove_checkout(worktree, "feature", "always")

    assert not _branch_exists(git_repo, "renamed")


def test_remove_checkout_leaves_an_unrelated_branch_alone_after_the_created_one_is_gone(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    _git(worktree.checkout_path, ["checkout", "-q", "-b", "unrelated"])
    _git(git_repo, ["branch", "-D", "feature"])

    worktree_vcs.remove_checkout(worktree, "feature", "always")

    assert _branch_exists(git_repo, "unrelated")


def test_remove_checkout_survives_a_worktree_directory_that_is_already_gone(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    run_blocking(["rm", "-rf", str(worktree.checkout_path)])

    worktree_vcs.remove_checkout(worktree, "feature", "always")

    assert not _branch_exists(git_repo, "feature")


def test_remove_checkout_survives_a_repository_that_is_gone(worktree_vcs: GitWorkspaceVcs, tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    worktree_vcs.remove_checkout(
        CheckoutLocation(repo_path=missing, checkout_path=missing / "code"), "feature", "always"
    )


def test_remove_checkout_skips_a_worktree_with_no_recorded_branch(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation
) -> None:
    worktree_vcs.remove_checkout(worktree, None, "always")

    assert worktree.checkout_path.exists()


def test_remove_checkout_leaves_an_in_place_repository_alone(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    in_place_vcs.remove_checkout(_in_place(git_repo), "main", "always")

    assert _branch_exists(git_repo, "main")


# resolve_default_target and list_target_candidates


def test_resolve_default_target_prefers_the_remote_head(worktree_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    _git(git_repo, ["update-ref", "refs/remotes/origin/trunk", "HEAD"])
    _git(git_repo, ["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk"])

    assert worktree_vcs.resolve_default_target(git_repo) == "origin/trunk"


def test_resolve_default_target_falls_back_to_origin_main_then_master(
    worktree_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    _git(git_repo, ["update-ref", "refs/remotes/origin/master", "HEAD"])
    assert worktree_vcs.resolve_default_target(git_repo) == "origin/master"

    _git(git_repo, ["update-ref", "refs/remotes/origin/main", "HEAD"])
    assert worktree_vcs.resolve_default_target(git_repo) == "origin/main"


def test_resolve_default_target_uses_the_local_branch_without_a_remote(
    worktree_vcs: GitWorkspaceVcs, in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    assert worktree_vcs.resolve_default_target(git_repo) == "main"
    assert in_place_vcs.resolve_default_target(git_repo) == "main"


def test_resolve_default_target_names_the_clone_origin_without_a_remote(
    clone_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    assert clone_vcs.resolve_default_target(git_repo) == "origin/main"


def test_resolve_default_target_is_none_without_main_or_master(worktree_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    _git(git_repo, ["branch", "-m", "main", "trunk"])

    assert worktree_vcs.resolve_default_target(git_repo) is None


def test_list_target_candidates_lists_remote_branches_of_every_remote(
    worktree_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    _git(git_repo, ["branch", "local-only"])
    _git(git_repo, ["update-ref", "refs/remotes/origin/main", "HEAD"])
    _git(git_repo, ["update-ref", "refs/remotes/upstream/dev", "HEAD"])

    assert worktree_vcs.list_target_candidates(git_repo) == ["origin/main", "upstream/dev"]


def test_list_target_candidates_falls_back_to_local_branches_without_remotes(
    worktree_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    _git(git_repo, ["branch", "dev"])

    assert worktree_vcs.list_target_candidates(git_repo) == ["dev", "main"]


# validate_new_ref_name, resolve_base_commit_id, default_setup_command, read_identity


def test_validate_new_ref_name_accepts_an_unused_well_formed_name(
    worktree_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    assert worktree_vcs.validate_new_ref_name(git_repo, "feat/new").status == RefNameStatus.AVAILABLE


def test_validate_new_ref_name_rejects_malformed_names(worktree_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    for name in ("", "bad..name", "-leading-dash", "has space", "trailing.lock"):
        assert worktree_vcs.validate_new_ref_name(git_repo, name).status == RefNameStatus.MALFORMED, name


def test_validate_new_ref_name_reports_an_existing_branch(worktree_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    validation = worktree_vcs.validate_new_ref_name(git_repo, "main")

    assert validation.status == RefNameStatus.ALREADY_EXISTS
    assert validation.ref_name == "main"


def test_resolve_base_commit_id_resolves_a_ref_to_its_commit(worktree_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    assert worktree_vcs.resolve_base_commit_id(git_repo, "HEAD") == _git(git_repo, ["rev-parse", "HEAD"])


def test_resolve_base_commit_id_is_none_for_an_unknown_ref(worktree_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    assert worktree_vcs.resolve_base_commit_id(git_repo, "no-such-ref") is None


def test_default_setup_command_fetches_origin_without_failing(worktree_vcs: GitWorkspaceVcs) -> None:
    assert worktree_vcs.default_setup_command() == DEFAULT_GIT_WORKSPACE_SETUP_COMMAND
    assert DEFAULT_GIT_WORKSPACE_SETUP_COMMAND == "git fetch origin 2>/dev/null || true"


def test_read_identity_reports_the_worktree_branch(worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation) -> None:
    assert worktree_vcs.read_identity(worktree) == GitHeadIdentity(branch_name="feature")


# compute_diff_artifact


def test_compute_diff_artifact_includes_modified_and_untracked_files(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    (git_repo / "file.txt").write_text("changed\n")
    (git_repo / "untracked.txt").write_text("brand new\n")

    artifact = in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref=None, context_lines=3)

    assert "diff --git a/file.txt b/file.txt" in artifact.uncommitted_diff
    assert "+changed" in artifact.uncommitted_diff
    assert "diff --git a/untracked.txt b/untracked.txt" in artifact.uncommitted_diff
    assert "+brand new" in artifact.uncommitted_diff
    assert artifact.target_branch_diff == ""
    assert artifact.target_branch_merge_base == ""
    assert artifact.file_errors == {}


def test_compute_diff_artifact_skips_untracked_symlinks_and_directories(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    (git_repo / "link.txt").symlink_to(git_repo / "file.txt")
    nested = git_repo / "nested"
    nested.mkdir()
    _git(nested, ["init", "-q"])

    artifact = in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref=None, context_lines=3)

    assert artifact.uncommitted_diff == ""


def test_compute_diff_artifact_handles_untracked_files_named_like_options(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    (git_repo / "--stat").write_text("tricky\n")

    artifact = in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref=None, context_lines=3)

    assert "+tricky" in artifact.uncommitted_diff


def test_compute_diff_artifact_diffs_everything_since_the_merge_base_with_the_target(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    merge_base = _git(git_repo, ["rev-parse", "main"])
    _commit_file(git_repo, "main_only.txt", "on main\n", "main moves on")
    _commit_file(worktree.checkout_path, "committed.txt", "committed\n", "work")
    (worktree.checkout_path / "file.txt").write_text("uncommitted\n")
    (worktree.checkout_path / "untracked.txt").write_text("untracked\n")

    artifact = worktree_vcs.compute_diff_artifact(worktree, target_ref="main", context_lines=3)

    assert artifact.target_branch_merge_base == merge_base
    assert "+committed" in artifact.target_branch_diff
    assert "+uncommitted" in artifact.target_branch_diff
    assert "+untracked" in artifact.target_branch_diff
    assert "main_only.txt" not in artifact.target_branch_diff
    assert "committed.txt" not in artifact.uncommitted_diff


def test_compute_diff_artifact_leaves_the_target_diff_empty_for_an_unknown_target(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    artifact = in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref="origin/nope", context_lines=3)

    assert artifact.target_branch_diff == ""
    assert artifact.target_branch_merge_base == ""


def test_compute_diff_artifact_honours_the_context_line_count(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    _commit_file(git_repo, "long.txt", "".join(f"line {i}\n" for i in range(20)), "long")
    (git_repo / "long.txt").write_text("".join(f"line {i}\n" if i != 10 else "changed\n" for i in range(20)))

    zero = in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref=None, context_lines=0)
    three = in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref=None, context_lines=3)

    assert "\n line 9\n" not in zero.uncommitted_diff
    assert "\n line 9\n" in three.uncommitted_diff


def test_compute_diff_artifact_rejects_negative_context(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    with pytest.raises(ValueError):
        in_place_vcs.compute_diff_artifact(_in_place(git_repo), target_ref=None, context_lines=-1)


# get_revision_history


def test_get_revision_history_lists_commits_since_the_fork_point_with_file_changes(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    fork_point = _git(git_repo, ["rev-parse", "main"])
    _commit_file(git_repo, "main_only.txt", "on main\n", "main moves on")
    checkout = worktree.checkout_path
    first = _commit_file(checkout, "added.txt", "one\ntwo\n", "add a file")
    (checkout / "file.txt").write_text("content\nmore\n")
    _git(checkout, ["mv", "added.txt", "renamed.txt"])
    _git(checkout, ["commit", "-q", "-a", "-m", "edit and rename"])

    history = worktree_vcs.get_revision_history(worktree, target_ref="main", base_commit_id=None)

    assert history.fork_point == fork_point
    assert [commit.message for commit in history.commits] == ["edit and rename", "add a file"]
    newest, oldest = history.commits
    assert oldest.hash == first
    assert oldest.parent_hashes == [fork_point]
    assert oldest.author_name == "Test"
    assert oldest.author_email == "test@example.com"
    assert [(change.path, change.status, change.additions) for change in oldest.files] == [("added.txt", "A", 2)]
    changes_by_path = {change.path: change for change in newest.files}
    assert changes_by_path["file.txt"].status == "M"
    assert changes_by_path["file.txt"].additions == 1
    assert changes_by_path["renamed.txt"].status == "R"
    assert changes_by_path["renamed.txt"].old_path == "added.txt"


def test_get_revision_history_uses_the_base_commit_without_a_target(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    base = _git(git_repo, ["rev-parse", "main"])
    _commit_file(worktree.checkout_path, "a.txt", "a\n", "work")

    history = worktree_vcs.get_revision_history(worktree, target_ref=None, base_commit_id=base)

    assert history.fork_point == base
    assert [commit.message for commit in history.commits] == ["work"]


def test_get_revision_history_falls_back_to_the_base_commit_for_an_unknown_target(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    base = _git(git_repo, ["rev-parse", "main"])

    history = worktree_vcs.get_revision_history(worktree, target_ref="origin/nope", base_commit_id=base)

    assert history.fork_point == base
    assert history.commits == []


def test_get_revision_history_is_empty_without_any_fork_point(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation
) -> None:
    history = worktree_vcs.get_revision_history(worktree, target_ref=None, base_commit_id=None)

    assert history.commits == []
    assert history.fork_point is None


# get_revision_diff


def test_get_revision_diff_diffs_a_commit_against_its_parent(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    parent = _git(git_repo, ["rev-parse", "HEAD"])
    commit = _commit_file(git_repo, "second.txt", "second\n", "second")

    revision_diff = in_place_vcs.get_revision_diff(_in_place(git_repo), commit[:7])

    assert revision_diff.commit_id == commit
    assert revision_diff.parent_commit_id == parent
    assert "+second" in revision_diff.diff
    assert "file.txt" not in revision_diff.diff


def test_get_revision_diff_diffs_a_root_commit(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    root = _git(git_repo, ["rev-parse", "HEAD"])

    revision_diff = in_place_vcs.get_revision_diff(_in_place(git_repo), root)

    assert revision_diff.parent_commit_id is None
    assert "+content" in revision_diff.diff


def test_get_revision_diff_rejects_malformed_ids_and_non_commits(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    tree = _git(git_repo, ["rev-parse", "HEAD^{tree}"])
    for bad_id in ("HEAD", "--stat", "abc", "f" * 40, tree):
        with pytest.raises(InvalidRevisionError):
            in_place_vcs.get_revision_diff(_in_place(git_repo), bad_id)


# list_files and read_file_at_revision


def test_list_files_lists_tracked_and_untracked_files_but_not_ignored_ones(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    _commit_file(git_repo, ".gitignore", "*.log\n", "ignore logs")
    (git_repo / "debug.log").write_text("noise\n")
    (git_repo / "src").mkdir()
    (git_repo / "src" / "new.py").write_text("print()\n")

    assert in_place_vcs.list_files(_in_place(git_repo)) == [".gitignore", "file.txt", "src/new.py"]


def test_list_files_raises_when_the_checkout_is_not_a_repository(
    in_place_vcs: GitWorkspaceVcs, tmp_path: Path
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    with pytest.raises(CheckoutFilesUnavailableError):
        in_place_vcs.list_files(_in_place(plain))


def test_read_file_at_revision_returns_text_content(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    (git_repo / "file.txt").write_text("not yet committed\n")

    result = in_place_vcs.read_file_at_revision(_in_place(git_repo), "file.txt", "HEAD")

    assert result.encoding == "utf-8"
    assert result.content == "content\n"


def test_read_file_at_revision_base64_encodes_binary_content(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    _commit_file(git_repo, "blob.bin", b"ab\x00cd", "binary")

    result = in_place_vcs.read_file_at_revision(_in_place(git_repo), "blob.bin", "HEAD")

    assert result.encoding == "base64"
    assert base64.b64decode(result.content) == b"ab\x00cd"


def test_read_file_at_revision_raises_for_a_missing_file(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    with pytest.raises(FileNotFoundAtRefError):
        in_place_vcs.read_file_at_revision(_in_place(git_repo), "missing.txt", "HEAD")


# discard_file_changes


def test_discard_file_changes_restores_a_tracked_file(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    (git_repo / "file.txt").write_text("changed\n")

    result = in_place_vcs.discard_file_changes(_in_place(git_repo), "file.txt")

    assert result.success
    assert (git_repo / "file.txt").read_text() == "content\n"


def test_discard_file_changes_deletes_an_untracked_file(in_place_vcs: GitWorkspaceVcs, git_repo: Path) -> None:
    (git_repo / "-untracked.txt").write_text("new\n")

    result = in_place_vcs.discard_file_changes(_in_place(git_repo), "-untracked.txt")

    assert result.success
    assert not (git_repo / "-untracked.txt").exists()


def test_discard_file_changes_rejects_paths_outside_the_checkout(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    absolute = in_place_vcs.discard_file_changes(_in_place(git_repo), "/etc/passwd")
    traversal = in_place_vcs.discard_file_changes(_in_place(git_repo), "../outside.txt")

    assert not absolute.success
    assert absolute.error_message == "Absolute paths are not allowed"
    assert not traversal.success
    assert traversal.error_message == "Path traversal is not allowed"


# get_pull_request_refs, agent_environment, compute_change_fingerprint


def test_get_pull_request_refs_reports_the_branch_and_origin(
    worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation, git_repo: Path
) -> None:
    _git(git_repo, ["remote", "add", "origin", "git@github.com:owner/repo.git"])

    refs = worktree_vcs.get_pull_request_refs(worktree)

    assert refs.head_ref_names == ("feature",)
    assert refs.origin_url == "git@github.com:owner/repo.git"


def test_get_pull_request_refs_has_no_head_for_a_detached_checkout(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    _git(git_repo, ["checkout", "-q", "--detach"])

    refs = in_place_vcs.get_pull_request_refs(_in_place(git_repo))

    assert refs.head_ref_names == ()
    assert refs.origin_url is None


def test_agent_environment_adds_nothing_for_git(worktree_vcs: GitWorkspaceVcs, worktree: CheckoutLocation) -> None:
    assert worktree_vcs.agent_environment(worktree) == AgentVcsEnvironment()


def test_compute_change_fingerprint_changes_with_edits_and_commits(
    in_place_vcs: GitWorkspaceVcs, git_repo: Path
) -> None:
    location = _in_place(git_repo)
    initial = in_place_vcs.compute_change_fingerprint(location)
    assert initial is not None
    assert in_place_vcs.compute_change_fingerprint(location) == initial

    (git_repo / "file.txt").write_text("edited\n")
    edited = in_place_vcs.compute_change_fingerprint(location)
    _git(git_repo, ["commit", "-q", "-a", "-m", "edit"])
    committed = in_place_vcs.compute_change_fingerprint(location)

    assert len({initial, edited, committed}) == 3


def test_compute_change_fingerprint_is_none_outside_a_repository(
    in_place_vcs: GitWorkspaceVcs, tmp_path: Path
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    assert in_place_vcs.compute_change_fingerprint(_in_place(plain)) is None


# The tripwire escapes even the operations that degrade gracefully on git failures.


def test_tripwire_escapes_operations_that_swallow_git_failures(in_place_vcs: GitWorkspaceVcs, tmp_path: Path) -> None:
    jj_workspace = tmp_path / "jj_workspace"
    (jj_workspace / ".jj").mkdir(parents=True)
    location = CheckoutLocation(repo_path=jj_workspace, checkout_path=jj_workspace)

    with pytest.raises(GitCommandInJjWorkspaceError):
        in_place_vcs.compute_diff_artifact(location, target_ref="main", context_lines=3)
    with pytest.raises(GitCommandInJjWorkspaceError):
        in_place_vcs.compute_change_fingerprint(location)
    with pytest.raises(GitCommandInJjWorkspaceError):
        in_place_vcs.get_pull_request_refs(location)
    with pytest.raises(GitCommandInJjWorkspaceError):
        in_place_vcs.get_revision_history(location, target_ref="main", base_commit_id=None)
