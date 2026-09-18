"""Tests for worktree_strategy module — verifying create and remove behavior."""

import subprocess
from pathlib import Path

import pytest

from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.environment_manager.environments.worktree_strategy import WorktreeError
from sculptor.services.workspace_service.environment_manager.environments.worktree_strategy import create_worktree
from sculptor.services.workspace_service.environment_manager.environments.worktree_strategy import remove_worktree


def _make_repo(path: Path, branch: str = "main") -> None:
    """Create a minimal git repo with one commit on the given branch."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    (path / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()
    if current != branch:
        subprocess.run(["git", "branch", "-m", current, branch], cwd=path, check=True, capture_output=True)


def _branch_exists(repo: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", branch], capture_output=True, text=True, check=True
    )
    return bool(result.stdout.strip())


def _current_branch(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit_unmerged_change(worktree: Path) -> None:
    (worktree / "new.txt").write_text("new")
    subprocess.run(["git", "add", "."], cwd=worktree, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@t.com", "commit", "-m", "unmerged"],
        cwd=worktree,
        check=True,
        capture_output=True,
    )


def test_create_worktree_happy_path(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"

    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="feat/x",
    )

    assert (destination / ".git").exists()
    assert _current_branch(destination) == "feat/x"
    basename = destination.name
    assert (user_repo / ".git" / "worktrees" / basename).exists()


def test_create_worktree_missing_base_ref_raises(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"

    with expect_exact_logged_errors(["{}: {}"]):
        with pytest.raises(WorktreeError):
            create_worktree(
                user_repo_path=user_repo,
                destination=destination,
                concurrency_group=test_root_concurrency_group,
                base_ref="does-not-exist",
                new_branch="feat/x",
            )


def test_create_worktree_branch_already_exists_raises(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    subprocess.run(["git", "-C", str(user_repo), "branch", "foo"], check=True, capture_output=True)
    destination = tmp_path / "worktree"

    with expect_exact_logged_errors(["{}: {}"]):
        with pytest.raises(WorktreeError):
            create_worktree(
                user_repo_path=user_repo,
                destination=destination,
                concurrency_group=test_root_concurrency_group,
                base_ref="main",
                new_branch="foo",
            )


def test_create_worktree_destination_exists_raises(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    destination.mkdir()
    (destination / "existing.txt").write_text("hi")

    with expect_exact_logged_errors(["{}: {}"]):
        with pytest.raises(WorktreeError):
            create_worktree(
                user_repo_path=user_repo,
                destination=destination,
                concurrency_group=test_root_concurrency_group,
                base_ref="main",
                new_branch="feat/x",
            )


def test_remove_worktree_never_preserves_branch(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="feat/x",
    )

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="feat/x",
        deletion_policy="never",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert not (user_repo / ".git" / "worktrees" / destination.name).exists()
    assert _branch_exists(user_repo, "feat/x")


def test_remove_worktree_delete_if_safe_merged_branch(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="feat/x",
    )

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="feat/x",
        deletion_policy="delete_if_safe",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert not _branch_exists(user_repo, "feat/x")


def test_remove_worktree_delete_if_safe_unmerged_branch_preserves(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="feat/x",
    )
    _commit_unmerged_change(destination)

    with expect_exact_logged_errors(["{}: {}"]):
        remove_worktree(
            user_repo_path=user_repo,
            destination=destination,
            branch_name="feat/x",
            deletion_policy="delete_if_safe",
            concurrency_group=test_root_concurrency_group,
        )

    assert not destination.exists()
    assert _branch_exists(user_repo, "feat/x")


def test_remove_worktree_always_force_deletes_unmerged_branch(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="feat/x",
    )
    _commit_unmerged_change(destination)

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="feat/x",
        deletion_policy="always",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert not _branch_exists(user_repo, "feat/x")


def test_remove_worktree_is_idempotent(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="feat/x",
    )

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="feat/x",
        deletion_policy="never",
        concurrency_group=test_root_concurrency_group,
    )
    with expect_exact_logged_errors(["{}: {}"]):
        remove_worktree(
            user_repo_path=user_repo,
            destination=destination,
            branch_name="feat/x",
            deletion_policy="never",
            concurrency_group=test_root_concurrency_group,
        )


def test_remove_worktree_deletes_branch_renamed_inside_worktree(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """A branch renamed after creation (e.g. by the agent's auto-rename) is still cleaned up."""
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="user/random-slug",
    )
    subprocess.run(["git", "branch", "-m", "user/descriptive-name"], cwd=destination, check=True, capture_output=True)
    assert _current_branch(destination) == "user/descriptive-name"

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="user/random-slug",
        deletion_policy="delete_if_safe",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert not _branch_exists(user_repo, "user/descriptive-name")
    assert not _branch_exists(user_repo, "user/random-slug")


def test_remove_worktree_force_deletes_renamed_unmerged_branch_under_always(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="user/random-slug",
    )
    subprocess.run(["git", "branch", "-m", "user/descriptive-name"], cwd=destination, check=True, capture_output=True)
    _commit_unmerged_change(destination)

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="user/random-slug",
        deletion_policy="always",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert not _branch_exists(user_repo, "user/descriptive-name")


def test_remove_worktree_leaves_foreign_checked_out_branch_alone(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Checking out a pre-existing branch in the worktree must not get that branch deleted.

    The worktree's own (still existing) branch is the one the policy applies to.
    """
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    subprocess.run(["git", "-C", str(user_repo), "branch", "someone-elses-work"], check=True, capture_output=True)
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="user/random-slug",
    )
    subprocess.run(["git", "checkout", "someone-elses-work"], cwd=destination, check=True, capture_output=True)
    _commit_unmerged_change(destination)

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="user/random-slug",
        deletion_policy="always",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert _branch_exists(user_repo, "someone-elses-work")
    assert not _branch_exists(user_repo, "user/random-slug")


def test_remove_worktree_leaves_a_foreign_branch_alone_when_the_created_branch_was_deleted(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """A branch checked out in the worktree is only deleted when git records it as the rename.

    Deleting the created branch by hand and checking out an unrelated one leaves the
    worktree on a branch that was never this workspace's.
    """
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    subprocess.run(["git", "-C", str(user_repo), "branch", "someone-elses-work"], check=True, capture_output=True)
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="user/random-slug",
    )
    subprocess.run(["git", "checkout", "someone-elses-work"], cwd=destination, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(user_repo), "branch", "-D", "user/random-slug"], check=True, capture_output=True)

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="user/random-slug",
        deletion_policy="always",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert _branch_exists(user_repo, "someone-elses-work")


def test_remove_worktree_leaves_branches_alone_when_rename_cannot_be_identified(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """With the created branch gone and HEAD detached, no branch can be attributed to the workspace."""
    user_repo = tmp_path / "user"
    _make_repo(user_repo, "main")
    destination = tmp_path / "worktree"
    create_worktree(
        user_repo_path=user_repo,
        destination=destination,
        concurrency_group=test_root_concurrency_group,
        base_ref="main",
        new_branch="user/random-slug",
    )
    subprocess.run(["git", "branch", "-m", "user/descriptive-name"], cwd=destination, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "--detach"], cwd=destination, check=True, capture_output=True)

    remove_worktree(
        user_repo_path=user_repo,
        destination=destination,
        branch_name="user/random-slug",
        deletion_policy="always",
        concurrency_group=test_root_concurrency_group,
    )

    assert not destination.exists()
    assert _branch_exists(user_repo, "user/descriptive-name")
