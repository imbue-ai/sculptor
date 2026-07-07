"""Tests for local diff generation (SCU-1627).

Cover the de-shelled diff path — the bare-``git`` + Python untracked-file
orchestration that replaced the former ``bash -c "git diff …; <pipeline>"`` — and
the content-aware fingerprint that lets ``maybe_refresh_workspace_diff`` skip
redundant regenerations without going stale.
"""

import os
import subprocess
from pathlib import Path

from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService

# The exact shell pipeline this code path replaced. Kept here only as the
# reference oracle for the byte-identical regression test below.
_FORMER_UNTRACKED_PIPELINE = (
    "git ls-files --others --exclude-standard -z"
    + " | xargs -0 -I {} find {} -maxdepth 0 -type f -print0"
    + " | xargs -0 -I {} git --no-pager diff --no-index /dev/null {}"
)


def _service(services: CompleteServiceCollection) -> DefaultWorkspaceService:
    workspace_service = services.workspace_service
    assert isinstance(workspace_service, DefaultWorkspaceService)
    return workspace_service


def _former_shell_diff(repo: Path, base: str, context_flag: str) -> str:
    """Reproduce the former ``bash -c "git diff …; <untracked>"`` output, stripped."""
    result = subprocess.run(
        ["bash", "-c", f"git --no-pager diff -M {context_flag} {base}; {_FORMER_UNTRACKED_PIPELINE}"],
        cwd=repo,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


def test_uncommitted_diff_is_byte_identical_to_former_shell_pipeline(
    initial_commit_repo: tuple[Path, str], test_service_collection: CompleteServiceCollection
) -> None:
    repo, _ = initial_commit_repo
    # A mix that exercises tracked + untracked, plus a path with a space.
    (repo / "file1.txt").write_text("Content 1 modified\nsecond line\n")  # tracked, unstaged
    (repo / "brand new.txt").write_text("hello\nworld\n")  # untracked, space in name
    (repo / "sub").mkdir()
    (repo / "sub" / "nested.txt").write_text("nested\n")  # untracked, nested

    new_output = _service(test_service_collection)._compute_diff_with_untracked(repo, "HEAD", "-U3", "uncommitted")

    assert new_output == _former_shell_diff(repo, "HEAD", "-U3")
    # Sanity: the untracked files really are present (not a vacuously-equal empty diff).
    assert "brand new.txt" in new_output
    assert "sub/nested.txt" in new_output


def test_untracked_diff_excludes_symlinks_and_directories(
    initial_commit_repo: tuple[Path, str], test_service_collection: CompleteServiceCollection
) -> None:
    repo, _ = initial_commit_repo
    (repo / "real.txt").write_text("real\n")
    os.symlink(repo / "real.txt", repo / "link.txt")  # symlink: `find -type f` excludes it

    untracked_diff = _service(test_service_collection)._untracked_files_diff(repo)

    assert "real.txt" in untracked_diff
    # The symlink must not appear as an added file (matches the former `find -type f`).
    assert "link.txt" not in untracked_diff


def test_untracked_diff_empty_when_nothing_untracked(
    initial_commit_repo: tuple[Path, str], test_service_collection: CompleteServiceCollection
) -> None:
    repo, _ = initial_commit_repo
    assert _service(test_service_collection)._untracked_files_diff(repo) == ""


def test_fingerprint_changes_when_modified_file_edited_again(
    initial_commit_repo: tuple[Path, str], test_service_collection: CompleteServiceCollection
) -> None:
    # The key staleness guarantee: a second edit of an already-modified file keeps
    # `git status` output identical (" M file1.txt"), so a status-only fingerprint
    # would miss it. Ours includes size+mtime, so it must change.
    repo, _ = initial_commit_repo
    service = _service(test_service_collection)
    tracked = repo / "file1.txt"

    tracked.write_text("AAAA")
    first = service._compute_diff_fingerprint(repo, None, 3, include_target_branch_diff=False)

    tracked.write_text("BBBB")  # same length, still " M" in git status
    os.utime(tracked, ns=(2_000_000_000, 2_000_000_000))  # deterministic, distinct mtime
    second = service._compute_diff_fingerprint(repo, None, 3, include_target_branch_diff=False)

    assert first is not None and second is not None
    assert first != second


def test_fingerprint_changes_on_head_move_and_context_lines(
    initial_commit_repo: tuple[Path, str], test_service_collection: CompleteServiceCollection
) -> None:
    repo, _ = initial_commit_repo
    service = _service(test_service_collection)

    base = service._compute_diff_fingerprint(repo, None, 3, include_target_branch_diff=False)
    wider_context = service._compute_diff_fingerprint(repo, None, 10, include_target_branch_diff=False)
    assert base is not None and wider_context is not None
    assert base != wider_context, "context width is part of the diff and must change the fingerprint"

    subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-m", "advance HEAD"], check=True)
    after_commit = service._compute_diff_fingerprint(repo, None, 3, include_target_branch_diff=False)
    assert after_commit is not None and after_commit != base, "HEAD movement must change the fingerprint"


def test_fingerprint_stable_when_nothing_changes(
    initial_commit_repo: tuple[Path, str], test_service_collection: CompleteServiceCollection
) -> None:
    repo, _ = initial_commit_repo
    service = _service(test_service_collection)
    (repo / "untracked.txt").write_text("u\n")

    first = service._compute_diff_fingerprint(repo, None, 3, include_target_branch_diff=False)
    second = service._compute_diff_fingerprint(repo, None, 3, include_target_branch_diff=False)

    assert first is not None and first == second
