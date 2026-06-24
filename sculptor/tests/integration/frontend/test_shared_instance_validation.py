"""Validation tests for the shared Sculptor instance infrastructure.

These tests verify that the session-scoped shared instance, between-test
cleanup, git repo isolation, and fail-fast mechanism all work correctly.
They are a smoke-test for Phase 1 infrastructure; comprehensive coverage
comes during Phase 2 test migration.

NOTE: Tests within a file run in definition order by default.  The "first /
second" test pairs below rely on this ordering.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

# ------------------------------------------------------------------
# Cleanup correctness
# ------------------------------------------------------------------


def test_cleanup_between_tests_first(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace and verify it exists as a sidebar row."""
    start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="Cleanup test task",
    )

    # Verify the workspace row was created
    page = sculptor_instance_.page
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(1)


def test_cleanup_between_tests_second(sculptor_instance_: SculptorInstance) -> None:
    """Verify that the first test's workspace row was cleaned up."""
    page = sculptor_instance_.page
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(0)


# ------------------------------------------------------------------
# Git repo isolation
# ------------------------------------------------------------------


def test_git_repo_reset_first(sculptor_instance_: SculptorInstance) -> None:
    """Modify the git repo by adding a file and committing."""
    repo = sculptor_instance_.repo
    repo.write_file("first_test_marker.txt", "created by first test")
    repo.commit("First test commit", commit_time="2025-06-01T00:00:00")

    assert (repo.base_path / "first_test_marker.txt").exists()


def test_git_repo_reset_second(sculptor_instance_: SculptorInstance) -> None:
    """Verify the repo was reset — the prior test's changes should be gone."""
    repo = sculptor_instance_.repo
    assert not (repo.base_path / "first_test_marker.txt").exists(), (
        "Cleanup should have created a fresh repo without the prior test's files"
    )

    # Standard initial-repo files should still be present
    assert (repo.base_path / "src" / "app.py").exists(), "Initial repo file src/app.py missing"
    assert (repo.base_path / "stuff.txt").exists(), "Initial repo file stuff.txt missing"


# ------------------------------------------------------------------
# Mutual exclusivity: sculptor_instance_ vs sculptor_instance_factory_
# ------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="Should fail due to fixture mutual exclusivity")
def test_mutual_exclusivity(
    sculptor_instance_: SculptorInstance,
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Requesting both fixtures in the same test must fail.

    The body is intentionally empty — the mutual exclusivity check in
    sculptor_instance_factory_ should prevent this test from ever reaching
    here.  If it does reach here, ``xfail(strict=True)`` will report XPASS
    (unexpected pass), correctly flagging that the guard is broken.
    """
