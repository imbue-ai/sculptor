import tempfile
from pathlib import Path
from typing import Generator

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.testing.local_git_repo import LocalGitRepo


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


def add_commit_to_repo(repo_path: Path, filename: str, content: str, commit_msg: str) -> None:
    """Helper to add a commit to an existing repository."""
    repo = LocalGitRepo(repo_path)
    repo.write_file(filename, content)
    # NOTE: Using LocalGitRepo helper for file write and commit as these operations
    # are testing helpers that aren't part of the public API we're testing
    repo.run_git(["add", filename])
    repo.run_git(["commit", "-m", commit_msg])


class TestHasAnyCommits:
    """Tests for the has_any_commits method."""

    def test_returns_false_for_non_git_directory(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that has_any_commits returns False when .git doesn't exist."""
        repo_path = temp_dir / "not_a_repo"
        repo_path.mkdir()

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)

        assert repo.has_any_commits() is False

    def test_returns_false_for_empty_git_repo(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that has_any_commits returns False for initialized repo with no commits."""
        repo_path = temp_dir / "empty_repo"
        repo_path.mkdir()
        LocalGitRepo(repo_path).run_git(["init"])

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)

        assert repo.has_any_commits() is False

    def test_returns_true_for_repo_with_commits(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that has_any_commits returns True when commits exist."""
        repo_path = temp_dir / "repo_with_commits"
        make_test_repo(repo_path)

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)

        assert repo.has_any_commits() is True


class TestFromNewRepository:
    """Tests for the from_new_repository class method."""

    def test_initializes_new_repo_successfully(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test successful initialization of a new repository."""
        repo_path = temp_dir / "new_repo"
        repo_path.mkdir()

        repo = LocalWritableGitRepo.from_new_repository(
            repo_path=repo_path,
            concurrency_group=test_root_concurrency_group,
            user_email="test@example.com",
            user_name="Test User",
        )

        assert (repo_path / ".git").exists()
        assert repo.repo_path == repo_path

        # Verify git config was set
        git_repo = LocalGitRepo(repo_path)
        user_email = git_repo.run_git(["config", "user.email"])
        user_name = git_repo.run_git(["config", "user.name"])
        assert user_email == "test@example.com"
        assert user_name == "Test User"

    def test_raises_when_directory_already_git_repo(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that initialization fails if directory is already a git repo."""
        repo_path = temp_dir / "existing_repo"
        make_test_repo(repo_path)

        with pytest.raises(GitRepoError) as exc_info:
            LocalWritableGitRepo.from_new_repository(
                repo_path=repo_path,
                user_email="test@example.com",
                user_name="Test User",
                concurrency_group=test_root_concurrency_group,
            )

        assert "already a git repository" in str(exc_info.value)

    def test_raises_when_directory_does_not_exist(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that initialization fails if directory doesn't exist."""
        repo_path = temp_dir / "nonexistent"

        with pytest.raises(GitRepoError) as exc_info:
            LocalWritableGitRepo.from_new_repository(
                repo_path=repo_path,
                user_email="test@example.com",
                user_name="Test User",
                concurrency_group=test_root_concurrency_group,
            )

        assert "does not exist" in str(exc_info.value)


class TestStageAllFiles:
    """Tests for the stage_all_files method."""

    def test_stages_new_files(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test staging new files with git add -A."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        # Add a new file
        (repo_path / "new_file.txt").write_text("new content")

        repo = LocalWritableGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        repo.stage_all_files()

        # Verify file is staged
        git_repo = LocalGitRepo(repo_path)
        staged_files = git_repo.run_git(["diff", "--cached", "--name-only"])
        assert "new_file.txt" in staged_files

    def test_stages_modified_files(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test staging modified files."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        # Modify existing file
        (repo_path / "test.txt").write_text("modified content")

        repo = LocalWritableGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        repo.stage_all_files()

        # Verify file is staged
        git_repo = LocalGitRepo(repo_path)
        staged_files = git_repo.run_git(["diff", "--cached", "--name-only"])
        assert "test.txt" in staged_files

    def test_stages_deleted_files(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test staging deleted files."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        # Delete existing file
        (repo_path / "test.txt").unlink()

        repo = LocalWritableGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        repo.stage_all_files()

        # Verify deletion is staged
        git_repo = LocalGitRepo(repo_path)
        staged_files = git_repo.run_git(["diff", "--cached", "--name-only"])
        assert "test.txt" in staged_files


class TestCreateCommit:
    """Tests for the create_commit method."""

    def test_creates_commit_with_staged_changes(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test creating a commit with staged changes."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        # Stage a change
        (repo_path / "new_file.txt").write_text("content")
        git_repo = LocalGitRepo(repo_path)
        git_repo.run_git(["add", "new_file.txt"])

        repo = LocalWritableGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        commit_hash = repo.create_commit("Add new file")

        assert commit_hash is not None
        assert len(commit_hash) == 40  # SHA-1 hash length

        # Verify commit message
        commit_msg = git_repo.run_git(["log", "-1", "--format=%s"])
        assert commit_msg == "Add new file"

    def test_creates_empty_commit_when_allowed(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test creating an empty commit with allow_empty=True."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        repo = LocalWritableGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        commit_hash = repo.create_commit("Empty commit", allow_empty=True)

        assert commit_hash is not None
        assert len(commit_hash) == 40

        # Verify commit message
        git_repo = LocalGitRepo(repo_path)
        commit_msg = git_repo.run_git(["log", "-1", "--format=%s"])
        assert commit_msg == "Empty commit"

    def test_returns_commit_hash(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test that create_commit returns the new commit hash."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        # Stage a change
        (repo_path / "new_file.txt").write_text("content")
        git_repo = LocalGitRepo(repo_path)
        git_repo.run_git(["add", "new_file.txt"])

        repo = LocalWritableGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        commit_hash = repo.create_commit("Test commit")

        # Verify returned hash matches HEAD
        head_hash = git_repo.run_git(["rev-parse", "HEAD"])
        assert commit_hash == head_hash


class TestGetCurrentCommitHash:
    """Tests for the get_current_commit_hash method."""

    def test_returns_current_commit_hash(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test getting current commit hash."""

        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        commit_hash = repo.get_current_commit_hash()

        # Verify it's a valid SHA-1 hash
        assert len(commit_hash) == 40
        assert all(c in "0123456789abcdef" for c in commit_hash)

        # Verify it matches git rev-parse HEAD
        git_repo = LocalGitRepo(repo_path)
        expected_hash = git_repo.run_git(["rev-parse", "HEAD"])
        assert commit_hash == expected_hash

    def test_raises_when_no_commits(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test that get_current_commit_hash raises error when repo has no commits."""

        repo_path = temp_dir / "empty_repo"
        repo_path.mkdir()
        LocalGitRepo(repo_path).run_git(["init"])

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        with pytest.raises(GitRepoError):
            repo.get_current_commit_hash()


class TestGetCurrentGitBranch:
    """Tests for the get_current_git_branch method."""

    def test_returns_current_branch(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test getting current branch name."""

        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        branch = repo.get_current_git_branch()

        assert branch == "main"

    def test_returns_different_branch(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        """Test getting current branch after checkout."""

        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        git_repo = LocalGitRepo(repo_path)
        git_repo.run_git(["checkout", "-b", "feature"])

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        branch = repo.get_current_git_branch()

        assert branch == "feature"


class TestGetAllBranches:
    """Tests for the get_all_branches method."""

    def test_returns_all_branches_in_alphabetical_order(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test getting all branches in alphabetical order."""

        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        git_repo = LocalGitRepo(repo_path)
        # Create branches
        git_repo.run_git(["checkout", "-b", "zebra-branch"])
        add_commit_to_repo(repo_path, "file1.txt", "content", "Commit on zebra-branch")

        git_repo.run_git(["checkout", "-b", "alpha-branch"])
        add_commit_to_repo(repo_path, "file2.txt", "content", "Commit on alpha-branch")

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        branches = repo.get_all_branches()

        # Should return all branches including main
        assert "alpha-branch" in branches
        assert "zebra-branch" in branches
        assert "main" in branches
        # Branches should be in alphabetical order
        assert branches.index("alpha-branch") < branches.index("main")
        assert branches.index("main") < branches.index("zebra-branch")


class TestIsBranchRef:
    """Tests for the is_branch_ref method."""

    def test_returns_true_for_existing_branch(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that existing branch returns True."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        git_repo = LocalGitRepo(repo_path)
        git_repo.run_git(["checkout", "-b", "feature"])

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        assert repo.is_branch_ref("feature") is True
        assert repo.is_branch_ref("main") is True

    def test_returns_false_for_nonexistent_branch(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that nonexistent branch returns False."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        assert repo.is_branch_ref("nonexistent") is False

    def test_returns_false_for_commit_hash(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Test that commit hash is not considered a branch ref."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        git_repo = LocalGitRepo(repo_path)
        commit_hash = git_repo.run_git(["rev-parse", "HEAD"])

        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        assert repo.is_branch_ref(commit_hash) is False


class TestIsValidBranchName:
    """Tests for the is_valid_branch_name method."""

    def test_accepts_normal_branch_names(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)
        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)

        assert repo.is_valid_branch_name("main") is True
        assert repo.is_valid_branch_name("feature") is True
        assert repo.is_valid_branch_name("imbue/board-demo-workspace") is True
        assert repo.is_valid_branch_name("maciek/scu-1636-linear-board") is True

    def test_rejects_illegal_branch_names(self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)
        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)

        assert repo.is_valid_branch_name("") is False
        assert repo.is_valid_branch_name("has space") is False
        assert repo.is_valid_branch_name("with:colon") is False
        assert repo.is_valid_branch_name("trailing.") is False
        assert repo.is_valid_branch_name("foo..bar") is False
        assert repo.is_valid_branch_name("foo~bar") is False
        assert repo.is_valid_branch_name("-leadingdash") is False

    def test_rejects_branch_name_with_embedded_command(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Regression: a workspace-name field accidentally filled with a prompt produced
        this branch name, and `git worktree add -b` failed deep in async environment setup."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)
        repo = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)

        bad_name = "imbue/board-demo-workspaceRun: git checkout -b dev/scu-1634-board-demo  (just create that branch, then stop)."
        assert repo.is_valid_branch_name(bad_name) is False


class TestGetRemoteBranches:
    """Tests for the get_remote_branches method."""

    def test_returns_remote_tracking_branches_excluding_head_pointer(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """Remote-tracking branches are listed, but the ``origin/HEAD`` pointer
        (e.g. ``origin/HEAD -> origin/main``) is excluded — it is an alias, not a
        branch a user can merge into.

        Remote-tracking refs are created directly with ``update-ref`` /
        ``symbolic-ref`` so the test needs no network or second repo.
        """
        repo_path = temp_dir / "repo"
        repo = make_test_repo(repo_path)
        repo.run_git(["update-ref", "refs/remotes/origin/main", "HEAD"])
        repo.run_git(["update-ref", "refs/remotes/origin/feature", "HEAD"])
        repo.run_git(["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"])

        read_only = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        remote_branches = read_only.get_remote_branches()

        assert "origin/main" in remote_branches
        assert "origin/feature" in remote_branches
        assert "origin/HEAD" not in remote_branches

    def test_returns_empty_for_repo_without_remotes(
        self, temp_dir: Path, test_root_concurrency_group: ConcurrencyGroup
    ) -> None:
        """A repo with no remote has no remote-tracking branches."""
        repo_path = temp_dir / "repo"
        make_test_repo(repo_path)

        read_only = LocalReadOnlyGitRepo(repo_path=repo_path, concurrency_group=test_root_concurrency_group)
        assert read_only.get_remote_branches() == []
