"""Unit tests for :mod:`sculptor.services.workspace_service.branch_poller`.

The poller is a background loop with no UI trigger, so per the repo's test
strategy its mechanics are exercised here rather than via Playwright. Tests drive
a single ``_scan_once()`` and assert on what is fanned out to observer queues:

- current branch is detected (and the diff refreshed only on a transition),
- target branches are projected from the repo's own remote-tracking refs (keyed
  by common git dir) — including the no-remote fallback that excludes the
  workspace's own branch,
- a checkout with no ``.git`` is flagged in the published state and logged, and
- an idle re-scan of an unchanged repo forks no git (``HEAD`` and remote-ref stat
  signatures unchanged).
"""

import shlex
import shutil
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Generator

import pytest
from loguru import logger

from sculptor.config.user_config import DependencyPaths
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.branch_poller import WorkspaceBranchPoller
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.testing.local_git_repo import LocalGitRepo
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceBranchInfo
from sculptor.web.data_types import WorkspaceTargetBranchesInfo


class _FakeWorkspace:
    def __init__(self, object_id: WorkspaceID, project_id: ProjectID) -> None:
        self.object_id = object_id
        self.project_id = project_id
        self.is_deleted = False
        self.initialization_strategy = WorkspaceInitializationStrategy.WORKTREE


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
    git_cli: GitCli,
    refresh_calls: list[WorkspaceID] | None = None,
) -> WorkspaceBranchPoller:
    return WorkspaceBranchPoller(
        concurrency_group=cg,
        data_model_service=_FakeDataModelService(workspaces),  # type: ignore[arg-type]
        git_cli=git_cli,
        resolve_working_dir=lambda workspace: working_dirs.get(workspace.object_id),
        refresh_diff_on_branch_change=(refresh_calls.append if refresh_calls is not None else (lambda _id: None)),
    )


def _drain(queue: Queue[StreamingUpdateSourceTypes]) -> list[StreamingUpdateSourceTypes]:
    items: list[StreamingUpdateSourceTypes] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _read_git_invocations(invocation_log: Path) -> list[tuple[Path, str]]:
    """The ``(cwd, arguments)`` of every git call the logging wrapper saw, in order."""
    invocations: list[tuple[Path, str]] = []
    for line in invocation_log.read_text().splitlines():
        cwd, arguments = line.split("\t", 1)
        invocations.append((Path(cwd), arguments))
    return invocations


@pytest.fixture
def base_repo(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> Path:
    base = tmp_path / "base"
    _make_base_repo(base, test_root_concurrency_group)
    return base


@pytest.fixture
def git_cli(test_root_concurrency_group: ConcurrencyGroup) -> GitCli:
    dependency_management_service = DependencyManagementService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("dependency_management_service"),
    )
    return GitCli(test_root_concurrency_group, dependency_management_service.resolve_binary_path)


@pytest.fixture
def git_invocation_log(tmp_path: Path) -> Generator[Path, None, None]:
    """Route the poller's git through a wrapper that records each call's directory and arguments."""
    real_git = shutil.which("git")
    assert real_git is not None
    invocation_log = tmp_path / "git-invocations.log"
    invocation_log.touch()
    wrapper = tmp_path / "logging-git"
    wrapper_lines = (
        "#!/bin/bash",
        f'echo "$(pwd -P)\t$*" >> {shlex.quote(str(invocation_log))}',
        f'exec {shlex.quote(real_git)} "$@"',
    )
    wrapper.write_text("\n".join(wrapper_lines) + "\n")
    wrapper.chmod(0o755)
    config = get_default_user_config_instance().model_copy(
        update={"dependency_paths": DependencyPaths(git=str(wrapper))}
    )
    set_user_config_instance(config)
    yield invocation_log
    set_user_config_instance(None)


@pytest.fixture
def poller_warning_count() -> Generator[list[int], None, None]:
    """How many warnings the poller module has logged, as a one-element list.

    Counts records rather than matching text: the session's JSON log sink blanks
    ``record["message"]`` before sinks added later see it.
    """
    count = [0]

    def _count(_message: object) -> None:
        count[0] += 1

    handler_id = logger.add(_count, level="WARNING", filter=WorkspaceBranchPoller.__module__)
    yield count
    logger.remove(handler_id)


def test_scan_emits_branch_and_remote_targets(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    _add_remote_ref(base_repo, "origin/main")
    _add_remote_ref(base_repo, "origin/dev")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    emitted = _drain(queue)
    branch_infos = [item for item in emitted if isinstance(item, WorkspaceBranchInfo)]
    target_infos = [item for item in emitted if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert [info.current_branch for info in branch_infos] == ["wsbranch"]
    assert [info.checkout_problem for info in branch_infos] == [None]
    # When the repo has remotes, the target list is its remote-tracking refs.
    assert set(target_infos[0].target_branches) == {"origin/main", "origin/dev"}


def test_target_falls_back_to_local_excluding_own_branch(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    # No remotes: the repo's local branches are the fallback; the poller drops the
    # workspace's own branch (diffing a branch against itself is a no-op).
    LocalGitRepo(base_repo).run_git(["branch", "feature-x"])
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    target_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert "feature-x" in target_infos[0].target_branches
    assert "wsbranch" not in target_infos[0].target_branches


def test_get_current_branch_returns_cached_value_and_none_for_unknown(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)

    assert poller.get_current_branch(workspace.object_id) is None  # Nothing scanned yet.

    poller._scan_once()

    assert poller.get_current_branch(workspace.object_id) == "wsbranch"
    assert poller.get_current_branch(WorkspaceID()) is None


def test_branch_change_emits_and_refreshes_diff(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    refresh_calls: list[WorkspaceID] = []
    poller = _build_poller(
        [workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli, refresh_calls=refresh_calls
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


def test_detached_head_is_published_as_head(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    LocalGitRepo(worktree).run_git(["checkout", "--detach"])
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)

    poller._scan_once()

    assert poller.get_current_branch(workspace.object_id) == "HEAD"


def test_idle_rescan_forks_no_git(
    base_repo: Path,
    tmp_path: Path,
    test_root_concurrency_group: ConcurrencyGroup,
    git_cli: GitCli,
    git_invocation_log: Path,
) -> None:
    """A second scan of an unchanged repo forks git zero times.

    The ``HEAD`` and remote-ref stat signatures are unchanged since the first
    scan, so neither the branch nor the target-candidate read runs on an idle cycle.
    """
    _add_remote_ref(base_repo, "origin/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)

    # The first scan forks git to read the branch and list the target candidates.
    poller._scan_once()
    assert _read_git_invocations(git_invocation_log) != []
    git_invocation_log.write_text("")

    poller._scan_once()

    assert _read_git_invocations(git_invocation_log) == []


def test_new_observer_is_backfilled(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    _add_remote_ref(base_repo, "origin/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)

    poller._scan_once()

    late_observer: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(late_observer)
    backfilled = _drain(late_observer)
    assert any(isinstance(item, WorkspaceBranchInfo) and item.current_branch == "wsbranch" for item in backfilled)
    assert any(isinstance(item, WorkspaceTargetBranchesInfo) for item in backfilled)


def test_remote_scan_runs_once_per_repo_in_the_main_repo(
    base_repo: Path,
    tmp_path: Path,
    test_root_concurrency_group: ConcurrencyGroup,
    git_cli: GitCli,
    git_invocation_log: Path,
) -> None:
    """Two worktrees of the same base share one common git dir, so the remote-ref
    listing (`git branch -r`) runs once for the repo, in the main repository
    rather than in either worktree."""
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
        git_cli,
    )

    poller._scan_once()

    remote_listing_directories = [
        cwd for cwd, arguments in _read_git_invocations(git_invocation_log) if arguments.startswith("branch -r")
    ]
    assert remote_listing_directories == [base_repo.resolve()]


@pytest.mark.parametrize("checkout_shape", ["plain_directory", "jj_workspace", "missing_directory"])
def test_checkout_without_git_is_flagged_in_published_state(
    checkout_shape: str, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    checkout = tmp_path / "ws"
    if checkout_shape == "plain_directory":
        checkout.mkdir()
    elif checkout_shape == "jj_workspace":
        (checkout / ".jj").mkdir(parents=True)
    elif checkout_shape == "missing_directory":
        pass
    else:
        raise AssertionError(f"Unknown checkout shape {checkout_shape}")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: checkout}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    emitted = _drain(queue)
    assert len(emitted) == 1
    flagged = emitted[0]
    assert isinstance(flagged, WorkspaceBranchInfo)
    assert flagged.workspace_id == workspace.object_id
    assert flagged.current_branch is None
    assert flagged.checkout_problem is not None


def test_checkout_without_git_is_logged_once_across_scans(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli, poller_warning_count: list[int]
) -> None:
    checkout = tmp_path / "ws"
    checkout.mkdir()
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: checkout}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()
    poller._scan_once()

    assert poller_warning_count == [1]
    assert len(_drain(queue)) == 1


def test_flagged_checkout_publishes_its_branch_once_it_has_git(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    worktree = tmp_path / "ws"
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)
    poller._scan_once()
    _drain(queue)

    _add_worktree(base_repo, worktree, "wsbranch")
    poller._scan_once()

    branch_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceBranchInfo)]
    assert [(info.current_branch, info.checkout_problem) for info in branch_infos] == [("wsbranch", None)]
