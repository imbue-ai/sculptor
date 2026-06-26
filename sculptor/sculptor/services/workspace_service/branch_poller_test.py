"""Unit tests for :mod:`sculptor.services.workspace_service.branch_poller`.

The poller is a background loop with no UI trigger, so per the repo's test
strategy its mechanics are exercised here rather than via Playwright. Tests drive
a single ``_scan_once()`` and assert on what is fanned out to observer queues:

- current branch is detected (and the diff refreshed only on a transition),
- target branches are projected from the repo's own remote-tracking refs (keyed
  by common git dir) — including the no-remote fallback that excludes the
  workspace's own branch, and
- an idle re-scan of an unchanged repo forks no git (symbolic ``HEAD`` read from
  the file; remote-ref stat signature unchanged).
"""

from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Generator
from unittest.mock import patch

import pytest

import sculptor.services.git_repo_service.default_implementation as git_repo_default
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.workspace_service.branch_poller import WorkspaceBranchPoller
from sculptor.testing.local_git_repo import LocalGitRepo
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceBranchInfo
from sculptor.web.data_types import WorkspaceTargetBranchesInfo


class _FakeWorkspace:
    def __init__(self, object_id: WorkspaceID, project_id: ProjectID) -> None:
        self.object_id = object_id
        self.project_id = project_id
        self.is_deleted = False


class _FakeTransaction:
    def __init__(self, workspaces: list[_FakeWorkspace]) -> None:
        self._workspaces = workspaces

    def get_workspaces(self) -> list[_FakeWorkspace]:
        return list(self._workspaces)


class _FakeDataModelService:
    def __init__(self, workspaces: list[_FakeWorkspace]) -> None:
        self.workspaces = workspaces

    @contextmanager
    def open_transaction(self, _request_id: object) -> Generator[_FakeTransaction, None, None]:
        yield _FakeTransaction(self.workspaces)


def _make_base_repo(base: Path, cg: ConcurrencyGroup) -> None:
    base.mkdir(parents=True, exist_ok=True)
    repo = LocalWritableGitRepo.from_new_repository(
        repo_path=base, concurrency_group=cg, user_email="t@example.com", user_name="Tester"
    )
    (base / "f.txt").write_text("hi")
    repo.stage_all_files()
    repo.create_commit("init")


def _add_worktree(base: Path, worktree: Path, branch: str) -> None:
    LocalGitRepo(base).run_git(["worktree", "add", str(worktree), "-b", branch])


def _add_remote_ref(base: Path, remote_branch: str) -> None:
    """Create a remote-tracking ref the way a fetch would, with no network."""
    LocalGitRepo(base).run_git(["update-ref", f"refs/remotes/{remote_branch}", "HEAD"])


def _build_poller(
    workspaces: list[_FakeWorkspace],
    working_dirs: dict[WorkspaceID, Path],
    cg: ConcurrencyGroup,
    refresh_calls: list[WorkspaceID] | None = None,
) -> WorkspaceBranchPoller:
    return WorkspaceBranchPoller(
        concurrency_group=cg,
        data_model_service=_FakeDataModelService(workspaces),  # type: ignore[arg-type]
        resolve_working_dir=lambda workspace: working_dirs.get(workspace.object_id),
        refresh_diff_on_branch_change=(refresh_calls.append if refresh_calls is not None else (lambda _id: None)),
    )


def _drain(queue: Queue[StreamingUpdateSourceTypes]) -> list[StreamingUpdateSourceTypes]:
    items: list[StreamingUpdateSourceTypes] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


@pytest.fixture
def base_repo(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> Path:
    base = tmp_path / "base"
    _make_base_repo(base, test_root_concurrency_group)
    return base


def test_scan_emits_branch_and_remote_targets(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    _add_remote_ref(base_repo, "origin/main")
    _add_remote_ref(base_repo, "origin/dev")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    emitted = _drain(queue)
    branch_infos = [item for item in emitted if isinstance(item, WorkspaceBranchInfo)]
    target_infos = [item for item in emitted if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert [info.current_branch for info in branch_infos] == ["wsbranch"]
    # When the repo has remotes, the target list is its remote-tracking refs.
    assert set(target_infos[0].target_branches) == {"origin/main", "origin/dev"}


def test_target_falls_back_to_local_excluding_own_branch(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    # No remotes: the repo's local branches are the fallback; the poller drops the
    # workspace's own branch (diffing a branch against itself is a no-op).
    LocalGitRepo(base_repo).run_git(["branch", "feature-x"])
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    target_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert "feature-x" in target_infos[0].target_branches
    assert "wsbranch" not in target_infos[0].target_branches


def test_branch_change_emits_and_refreshes_diff(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    refresh_calls: list[WorkspaceID] = []
    poller = _build_poller(
        [workspace], {workspace.object_id: worktree}, test_root_concurrency_group, refresh_calls=refresh_calls
    )
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()
    assert refresh_calls == []  # No refresh on first detection.
    _drain(queue)

    LocalGitRepo(worktree).run_git(["checkout", "-b", "switched"])
    poller._scan_once()

    branch_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceBranchInfo)]
    assert [info.current_branch for info in branch_infos] == ["switched"]
    assert refresh_calls == [workspace.object_id]


def test_idle_rescan_forks_no_git(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """A second scan of an unchanged repo forks git zero times.

    Branch detection reads the symbolic ``HEAD`` straight from the file, and the
    remote scan's stat signature is unchanged since the first scan, so neither
    path forks git on an idle cycle.
    """
    _add_remote_ref(base_repo, "origin/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group)

    # First scan warms the remote-ref cache (this one does fork git to list refs).
    poller._scan_once()

    with patch.object(git_repo_default, "run_git_command_local", wraps=git_repo_default.run_git_command_local) as spy:
        poller._scan_once()

    assert spy.call_count == 0


def test_new_observer_is_backfilled(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    _add_remote_ref(base_repo, "origin/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group)

    poller._scan_once()

    late_observer: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(late_observer)
    backfilled = _drain(late_observer)
    assert any(isinstance(item, WorkspaceBranchInfo) and item.current_branch == "wsbranch" for item in backfilled)
    assert any(isinstance(item, WorkspaceTargetBranchesInfo) for item in backfilled)


def test_remote_scan_runs_once_per_repo_across_worktrees(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Two worktrees of the same base share one common git dir, so the remote-ref
    listing (`git branch -r`) runs once for the repo, not once per workspace."""
    _add_remote_ref(base_repo, "origin/main")
    worktree_a = tmp_path / "ws_a"
    worktree_b = tmp_path / "ws_b"
    _add_worktree(base_repo, worktree_a, "branch-a")
    _add_worktree(base_repo, worktree_b, "branch-b")
    workspace_a = _FakeWorkspace(WorkspaceID(), ProjectID())
    workspace_b = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller(
        [workspace_a, workspace_b],
        {workspace_a.object_id: worktree_a, workspace_b.object_id: worktree_b},
        test_root_concurrency_group,
    )

    with patch.object(git_repo_default, "run_git_command_local", wraps=git_repo_default.run_git_command_local) as spy:
        poller._scan_once()

    remote_listing_calls = [call for call in spy.call_args_list if {"branch", "-r"} <= set(call.args[1])]
    assert len(remote_listing_calls) == 1
