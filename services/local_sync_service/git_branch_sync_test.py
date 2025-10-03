import os
import re
import tempfile
import time
from pathlib import Path
from typing import Generator

import pytest
from loguru import logger
from pydantic import AnyUrl
from pydantic import ValidationError

from imbue_core.agents.data_types.ids import ProjectID
from sculptor.interfaces.agents.v1.agent import LocalEnvironment
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeOfPause
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.local_sync_service.data_types import NewNoticesInSyncHandlingError
from sculptor.services.local_sync_service.git_branch_sync import FileContentDivergenceReconciler
from sculptor.services.local_sync_service.git_branch_sync import RemoteReadOnlyGitRepo
from sculptor.services.local_sync_service.git_branch_sync import RepoBranchSyncReconciler
from sculptor.services.local_sync_service.git_branch_sync import _BranchSyncRepo
from sculptor.testing.local_git_repo import LocalGitRepo


def wrap_path_in_url(path: Path) -> AnyUrl:
    return AnyUrl(f"file://{path}")


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def make_test_repo(
    repo_path: Path,
    user_name: str = "Test User",
    user_email: str = "test@example.com",
    initial_file: str = "test.txt",
    initial_content: str = "content",
    initial_commit_msg: str = "Initial commit",
) -> LocalGitRepo:
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = LocalGitRepo(repo_path)
    repo.write_file(initial_file, initial_content)
    repo.configure_git(git_user_name=user_name, git_user_email=user_email)
    return repo


def make_test_repos_with_branch(temp_dir: Path, branch_name: str = "test/sync-branch") -> tuple[Path, Path, str]:
    """Helper to create three test repositories with a shared branch."""
    user_path = temp_dir / "user"
    agent_path = temp_dir / "agent/code"

    # Create user repo
    user_repo = make_test_repo(user_path)

    # Create test branch
    user_repo.run_git(["checkout", "-b", branch_name])
    user_repo.write_file("branch_file.txt", "branch content")
    user_repo.run_git(["add", "branch_file.txt"])
    user_repo.run_git(["commit", "-m", "Branch commit"])

    user_repo.clone_repo(agent_path)
    assert agent_path.exists()
    return user_path, agent_path, branch_name


def add_commit_to_repo(repo_path: Path | _BranchSyncRepo, filename: str, content: str, commit_msg: str) -> None:
    """Helper to add a commit to an existing repository."""
    if isinstance(repo_path, _BranchSyncRepo):
        if isinstance(repo_path.repo, LocalReadOnlyGitRepo):
            repo_path = repo_path.repo.get_repo_path()
        else:
            assert isinstance(repo_path.repo, RemoteReadOnlyGitRepo)
            env = repo_path.repo.environment
            assert isinstance(env, LocalEnvironment)
            repo_path = _extract_env_repo_path(repo_path.repo)
    repo = LocalGitRepo(repo_path)
    repo.write_file(filename, content)
    repo.run_git(["add", filename])
    repo.run_git(["commit", "-m", commit_msg])


def create_local_environment(repo_path: Path) -> LocalEnvironment:
    return LocalEnvironment(
        environment_id=LocalEnvironmentID(str(repo_path.parent)),
        config=LocalEnvironmentConfig(),
        project_id=ProjectID(),
    )


# TODO should be fixture
def create_syncer(user_path: Path, agent_path: Path, branch_name: str) -> RepoBranchSyncReconciler:
    return RepoBranchSyncReconciler.build(branch_name, user_path, create_local_environment(agent_path))


def assert_repos_in_sync(syncer: RepoBranchSyncReconciler) -> None:
    user_commit = syncer.user_repo.get_current_commit_hash()
    agent_commit = syncer.agent_repo.get_current_commit_hash()
    assert user_commit == agent_commit, f"commits not equal: {user_commit=}, {agent_commit=}"


def get_repo_commit(repo_path: Path, rev: str = "HEAD") -> str:
    """Helper to get the current commit hash of a repository."""
    repo = LocalGitRepo(repo_path)
    return repo.run_git(["rev-parse", rev])


class _ContentDivergencePathReconciler(FileContentDivergenceReconciler):
    temp_dir: Path
    paths: tuple[Path, Path]

    @property
    def exact_paths_to_react_to(self) -> tuple[Path, ...]:
        return self.paths

    @property
    def dirs_to_watch(self) -> tuple[Path, ...]:
        return (self.temp_dir,)

    @property
    def local_dirs_to_watch(self) -> tuple[Path, ...]:
        return (self.temp_dir,)

    @property
    def environment_dirs_to_watch(self) -> tuple[Path, ...]:
        return ()

    def handle_path_changes(self, relevant_paths: tuple[Path, ...]) -> None:
        return None

    def is_relevant_subpath(self, path: Path) -> bool:
        if path not in self.exact_paths_to_react_to:
            return False
        unique_contents = {self._fallback_to_cache(p, p.read_text()) for p in self.exact_paths_to_react_to}
        is_any_path_divergent = len(unique_contents) > 1
        if not is_any_path_divergent:
            logger.debug("Ignoring path change: No divergence detected for paths {}", self.exact_paths_to_react_to)
            return False
        return is_any_path_divergent


@pytest.fixture
def single_test_repo(temp_dir: Path) -> Path:
    """Create a single test repository."""
    repo_path = temp_dir / "test_repo"
    make_test_repo(repo_path)
    return repo_path


@pytest.fixture
def test_repos_and_branch(temp_dir: Path) -> tuple[Path, Path, str]:
    """Set up three test repositories for testing."""
    return make_test_repos_with_branch(temp_dir)


@pytest.fixture
def branch_syncer(test_repos_and_branch: tuple[Path, Path, str]) -> RepoBranchSyncReconciler:
    return create_syncer(*test_repos_and_branch)


def test_content_divergence_path_reconciler(temp_dir: Path) -> None:
    test_file1 = temp_dir / "test1.txt"
    test_file2 = temp_dir / "test2.txt"
    other_file = temp_dir / "other.txt"

    test_file1.write_text("test")
    test_file2.write_text("test")
    other_file.write_text("test_ignored")

    reconciler = _ContentDivergencePathReconciler(
        tag="test_divergence", temp_dir=temp_dir, paths=(test_file1, test_file2)
    )

    # Test that exact paths are considered relevant
    assert not reconciler.is_relevant_subpath(test_file1) and not reconciler.is_relevant_subpath(test_file2), (
        "should be irrelevant if contents are the same"
    )

    test_file1.write_text("modified content")
    assert reconciler.is_relevant_subpath(test_file1), "should be relevant if contents diverge"
    assert reconciler.is_relevant_subpath(test_file2), (
        "previously unchanged path should become relevant if one diverges"
    )

    assert not reconciler.is_relevant_subpath(other_file), "should not be relevant if not in exact paths"


def test_sync_repo_fetch_and_reset_mixed(temp_dir: Path) -> None:
    source_path = temp_dir / "source"
    target_path = temp_dir / "target"

    make_test_repo(source_path).clone_repo(target_path)

    add_commit_to_repo(source_path, "test.txt", "updated content", "Update content")

    sync_target = _BranchSyncRepo(repo=LocalWritableGitRepo(repo_path=target_path), branch_name="main")
    sync_target.fetch_and_reset_mixed_on_branch(from_remote=wrap_path_in_url(source_path))

    # Target should now have the same commit as source
    target_commit = get_repo_commit(target_path)
    source_commit = get_repo_commit(source_path)
    assert target_commit == source_commit


def test_repo_sync_init_with_invalid_branch(test_repos_and_branch: tuple[Path, Path, str]) -> None:
    user_path, agent_path, _ = test_repos_and_branch
    with pytest.raises(ValidationError, match="invalid branch"):
        reconciler = RepoBranchSyncReconciler.build(
            "non-existent",
            user_path,
            create_local_environment(agent_path),
        )
        reconciler.user_repo.fetch_and_reset_mixed_on_branch(from_remote=reconciler.agent_repo.url)


def test_repo_sync_base_case(test_repos_and_branch: tuple[Path, Path, str]) -> None:
    user_path, agent_path, branch_name = test_repos_and_branch
    syncer = create_syncer(user_path, agent_path, branch_name)
    assert syncer.is_currently_easily_syncable, "Syncer should be easily syncable at initialization"

    add_commit_to_repo(user_path, "user_file.txt", "user content", "User commit")
    assert syncer.is_currently_easily_syncable, "Syncer should be easily syncable after single commit"

    syncer.sync_heads(syncer.user_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert_repos_in_sync(syncer)


def test_repo_sync_heads_handles_multiple_commits(test_repos_and_branch: tuple[Path, Path, str]) -> None:
    """Test syncing when agent repo is more recent than user repo."""
    user_path, agent_path, branch_name = test_repos_and_branch
    syncer = create_syncer(user_path, agent_path, branch_name)

    add_commit_to_repo(agent_path, "agent_file.txt", "agent content", "Agent commit")
    add_commit_to_repo(agent_path, "agent_file_2.txt", "agent content 2", "Agent commit 2")

    syncer.sync_heads(syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath)
    assert_repos_in_sync(syncer)


def test_repo_sync_heads_no_changes_needed(branch_syncer: RepoBranchSyncReconciler) -> None:
    initial_commit = branch_syncer.user_repo.get_current_commit_hash()
    assert initial_commit == branch_syncer.agent_repo.get_current_commit_hash(), "init commit mismatch"

    branch_syncer.sync_heads(branch_syncer.user_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert branch_syncer.user_repo.get_current_commit_hash() == initial_commit
    assert_repos_in_sync(branch_syncer)


def test_fetch_with_retries_synces_in_reverse_direction(branch_syncer: RepoBranchSyncReconciler) -> None:
    add_commit_to_repo(branch_syncer.user_repo, "user_file.txt", "user content", "User commit")
    user_commit = branch_syncer.user_repo.get_current_commit_hash()
    branch_syncer.fetch_and_reset_mixed_with_reverse_retry(
        to_repo=branch_syncer.user_repo,
        from_repo=branch_syncer.agent_repo,
    )
    assert branch_syncer.user_repo.get_current_commit_hash() == user_commit
    assert branch_syncer.agent_repo.get_current_commit_hash() == user_commit


def test_repo_sync_heads_fails_on_confict(branch_syncer: RepoBranchSyncReconciler) -> None:
    add_commit_to_repo(branch_syncer.user_repo, "user_file.txt", "user content", "User commit")
    add_commit_to_repo(branch_syncer.agent_repo, "agent_file.txt", "agent content", "Agent commit")

    assert not branch_syncer.is_currently_easily_syncable, (
        "branch_syncer.is_currently_easily_syncable should be False after conflicting commits"
    )

    for ref in [
        branch_syncer.user_repo.head_ref_pointer_internal_untrustworthy_abspath,
        branch_syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath,
    ]:
        # pyre-ignore[16]
        with pytest.raises(GitRepoError, match=re.escape("[rejected]")):
            branch_syncer.sync_heads(ref)


def test_branch_divergence_shown_in_notices(branch_syncer: RepoBranchSyncReconciler) -> None:
    add_commit_to_repo(branch_syncer.user_repo, "user_file.txt", "user content", "User commit")
    add_commit_to_repo(branch_syncer.agent_repo, "agent_file.txt", "agent content", "Agent commit")

    assert not branch_syncer.is_currently_easily_syncable, (
        "branch_syncer.is_currently_easily_syncable should be False after conflicting commits"
    )

    notices = branch_syncer.get_notices()
    assert len(notices) == 1 and isinstance(notices[0], LocalSyncNoticeOfPause), (
        "Should have one pause notice for branch divergence"
    )
    assert "manual merging" in notices[0].reason, "notice message should indicate manual merging is needed"


def test_repo_sync_still_fetches_if_user_checks_out_different_branch(temp_dir: Path) -> None:
    """Test edge case: user checks out a different branch.

    The syncer should continue to work with the specified branch regardless.
    """
    # TODO obviously should be it's own fixture
    user_path, agent_path, branch_name = make_test_repos_with_branch(temp_dir)
    syncer = RepoBranchSyncReconciler.build(branch_name, user_path, create_local_environment(agent_path))

    add_commit_to_repo(user_path, "original_branch_file.txt", "original content", "Original branch commit")

    # User checks out a different branch, does some stuff
    user_repo = LocalGitRepo(user_path)
    user_repo.run_git(["checkout", "-b", "different-branch"])
    user_repo.write_file("different_file.txt", "different content")
    user_repo.run_git(["add", "different_file.txt"])
    user_repo.run_git(["commit", "-m", "Commit on different branch"])

    # Syncing should still work with the original branch
    syncer.sync_heads(syncer.user_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert syncer.user_repo.branch_name == branch_name
    assert syncer.agent_repo.branch_name == branch_name
    assert get_repo_commit(user_path, branch_name) == get_repo_commit(agent_path, branch_name)


def test_untracked_not_affected_by_sync(branch_syncer: RepoBranchSyncReconciler) -> None:
    user_repo = LocalGitRepo(branch_syncer.user_repo.repo.get_repo_path())
    file_path = "user_file.txt"
    file_content = "user content"
    user_repo.write_file(file_path, file_content)

    add_commit_to_repo(branch_syncer.agent_repo, "agent_file.txt", "agent content", "Agent commit")
    branch_syncer.sync_heads(branch_syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert file_path in branch_syncer.user_repo.repo.list_untracked_files(), (
        f"untracked files should be unaffected {user_repo.run_git(['status'])=}"
    )
    assert file_content == user_repo.read_file(file_path), "file content should really be unaffected"


def _extract_env_repo_path(repo: RemoteReadOnlyGitRepo) -> Path:
    assert isinstance(repo.environment, LocalEnvironment)
    return repo.environment.get_sandbox_path() / "code"


def test_added_file_gets_unstaged_as_modified_after_sync(branch_syncer: RepoBranchSyncReconciler) -> None:
    user_repo = LocalGitRepo(branch_syncer.user_repo.repo.get_repo_path())
    shared_file_path = "shared_file.txt"
    user_file_content = "user content"
    user_repo.write_file(shared_file_path, user_file_content)
    user_repo.run_git(["add", shared_file_path])
    assert shared_file_path in branch_syncer.user_repo.repo.list_staged(diff_filter="A")

    add_commit_to_repo(branch_syncer.agent_repo, shared_file_path, "agent content", "Agent commit")

    agent_repo = LocalGitRepo(_extract_env_repo_path(branch_syncer.agent_repo.repo))
    print(
        f"{branch_syncer.agent_repo.repo.get_current_git_branch()=} {branch_syncer.agent_repo.get_current_commit_hash()=} {agent_repo.run_git(['status'])=}"
    )
    branch_syncer.sync_heads(branch_syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert shared_file_path in branch_syncer.user_repo.repo.list_unstaged(diff_filter="M"), (
        "added files should be unstaged as modified if also added by agent due to reset --mixed behavior"
    )
    assert user_file_content == user_repo.read_file(shared_file_path), "file content should be unaffected"


def test_added_files_become_untracked_with_same_content_after_sync(branch_syncer: RepoBranchSyncReconciler) -> None:
    user_repo = LocalGitRepo(branch_syncer.user_repo.repo.repo_path)
    user_file_path = "shared_file.txt"
    user_file_content = "user content"
    user_repo.write_file(user_file_path, user_file_content)
    user_repo.run_git(["add", user_file_path])
    assert user_file_path in branch_syncer.user_repo.repo.list_staged(diff_filter="A")

    add_commit_to_repo(branch_syncer.agent_repo, "agent_file.txt", "agent content", "Agent commit")
    branch_syncer.sync_heads(branch_syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert user_file_path in branch_syncer.user_repo.repo.list_untracked_files(), (
        "added files should become untracked due to reset --mixed behavior"
    )
    assert user_file_content == user_repo.read_file(user_file_path), "file content should be unaffected"
    assert "agent_file.txt" in branch_syncer.user_repo.repo.list_unstaged(diff_filter="D"), (
        "a file added by the agent should become unstaged as deleted BECAUSE we're not touching the working tree at all (that's what mutagen is for)"
    )


def test_no_reset_on_different_branch(branch_syncer: RepoBranchSyncReconciler) -> None:
    """Test that no reset is done if the current branch is different from the branch to sync."""

    user_repo = LocalGitRepo(branch_syncer.user_repo.repo.repo_path)
    user_repo.run_git(["checkout", "-b", "different-branch"])
    user_repo.write_file("untracked_file.txt", "untracked content")
    user_repo.write_file("added_file.txt", "added content")
    user_repo.run_git(["add", "added_file.txt"])
    user_current_commit = branch_syncer.user_repo.get_current_commit_hash()

    add_commit_to_repo(branch_syncer.agent_repo, "agent_file.txt", "agent content", "Agent commit")
    branch_syncer.sync_heads(branch_syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath)

    assert "untracked_file.txt" in branch_syncer.user_repo.repo.list_untracked_files(), (
        "untracked files should be unaffected"
    )
    assert "added_file.txt" in branch_syncer.user_repo.repo.list_staged(diff_filter="A"), (
        "added files should be unaffected"
    )

    assert branch_syncer.user_repo.get_current_commit_hash() != branch_syncer.agent_repo.get_current_commit_hash(), (
        "user checkout should be unaffected"
    )
    assert branch_syncer.user_repo.repo.get_current_git_branch() == "different-branch"
    assert branch_syncer.user_repo.get_current_commit_hash() == user_current_commit


def test_repo_sync_multiple_branch_sync_operations(branch_syncer: RepoBranchSyncReconciler) -> None:
    """Test multiple sync operations in sequence."""
    add_commit_to_repo(branch_syncer.user_repo.repo.repo_path, "step1.txt", "step 1", "Step 1 commit")
    branch_syncer.sync_heads(branch_syncer.user_repo.head_ref_pointer_internal_untrustworthy_abspath)

    user_commit_1 = branch_syncer.user_repo.get_current_commit_hash()
    assert_repos_in_sync(branch_syncer)

    time.sleep(0.1)

    # Second sync: agent -> user
    add_commit_to_repo(branch_syncer.agent_repo, "step2.txt", "step 2", "Step 2 commit")
    branch_syncer.sync_heads(branch_syncer.agent_repo.head_ref_pointer_internal_untrustworthy_abspath)

    user_commit_2 = branch_syncer.user_repo.get_current_commit_hash()
    assert_repos_in_sync(branch_syncer)
    assert user_commit_2 != user_commit_1, "user_commit, sync, agent_commit, sync not working"


def test_ref_deletion_causes_notice(branch_syncer: RepoBranchSyncReconciler) -> None:
    repo_path = branch_syncer.user_repo.repo.get_repo_path()
    ref_path = branch_syncer.user_repo.head_ref_pointer_internal_untrustworthy_abspath
    os.remove(ref_path)

    assert not branch_syncer.is_relevant_subpath(ref_path), "Should not raise error (uses cached value)"
    assert not branch_syncer.is_relevant_subpath(Path("/")), "Should not raise error"

    notice: LocalSyncNoticeOfPause | None = None
    try:
        branch_syncer.handle_path_changes((ref_path,))
    except NewNoticesInSyncHandlingError as e:
        assert len(e.notices) == 1, f"expected singleton notice in {e.notices=}"
        assert isinstance(e.notices[0], LocalSyncNoticeOfPause)
        notice = e.notices[0]
    assert notice is not None, "syncer didn't raise a notice error due to ref deletion"
    assert str(repo_path) in notice.reason, f"{repo_path=} not in {notice.reason=}"
