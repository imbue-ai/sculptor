"""Unit tests for :mod:`sculptor.services.workspace_service.branch_poller`.

The poller is a background loop with no UI trigger, so per the repo's test
strategy its mechanics are exercised here rather than via Playwright. Tests drive
a single ``_scan_once()`` and assert on what is fanned out to observer queues.
"""

import shlex
import shutil
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Callable
from typing import Generator

import pytest
from loguru import logger

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.foundation.async_monkey_patches_test import record_logged_error_levels
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.api import WorkspaceNotFoundError
from sculptor.services.workspace_service.branch_poller import WorkspaceBranchPoller
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.vcs_runners import VcsRunners
from sculptor.testing.local_git_repo import LocalGitRepo
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceBranchInfo
from sculptor.web.data_types import WorkspaceTargetBranchesInfo


class _FakeWorkspace:
    def __init__(
        self,
        object_id: WorkspaceID,
        project_id: ProjectID,
        target_branch: str | None = None,
        initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.WORKTREE,
    ) -> None:
        self.object_id = object_id
        self.project_id = project_id
        self.target_branch = target_branch
        self.is_deleted = False
        self.initialization_strategy = initialization_strategy


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
    refresh_diff_on_branch_change: Callable[[WorkspaceID], None] = lambda _workspace_id: None,
    resolve_working_dir: Callable[[Workspace], Path | None] | None = None,
) -> WorkspaceBranchPoller:
    return WorkspaceBranchPoller(
        concurrency_group=cg,
        data_model_service=_FakeDataModelService(workspaces),  # type: ignore[arg-type]
        vcs_runners=VcsRunners(git=git_cli, jj=JjCli(cg, lambda tool: None)),
        resolve_working_dir=resolve_working_dir or (lambda workspace: working_dirs.get(workspace.object_id)),
        refresh_diff_on_branch_change=refresh_diff_on_branch_change,
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


def test_target_branches_name_the_pull_request_base_of_each_remote_candidate(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    LocalGitRepo(base_repo).run_git(["remote", "add", "origin", str(tmp_path / "origin.git")])
    _add_remote_ref(base_repo, "origin/main")
    _add_remote_ref(base_repo, "origin/feature/foo")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID(), target_branch="origin/main")
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    target_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert target_infos[0].pr_base_names == {"origin/main": "main", "origin/feature/foo": "feature/foo"}


def test_target_branches_keep_a_local_candidate_whose_first_segment_is_no_remote(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    LocalGitRepo(base_repo).run_git(["branch", "release/1.0"])
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    target_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert target_infos[0].pr_base_names["release/1.0"] == "release/1.0"


def test_a_new_target_outside_the_candidates_is_published_with_its_pull_request_base(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    LocalGitRepo(base_repo).run_git(["remote", "add", "upstream", str(tmp_path / "upstream.git")])
    _add_remote_ref(base_repo, "upstream/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID(), target_branch="upstream/main")
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)
    poller._scan_once()
    _drain(queue)

    workspace.target_branch = "upstream/release/2.0"
    poller._scan_once()

    target_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceTargetBranchesInfo)]
    assert [info.target_branches for info in target_infos] == [("upstream/main",)]
    assert target_infos[0].pr_base_names == {"upstream/main": "main", "upstream/release/2.0": "release/2.0"}


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
        [workspace],
        {workspace.object_id: worktree},
        test_root_concurrency_group,
        git_cli,
        refresh_diff_on_branch_change=refresh_calls.append,
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
    """A second scan of an unchanged repo forks git zero times."""
    _add_remote_ref(base_repo, "origin/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)

    # The first scan must fork git, or the empty log after the second would prove nothing.
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


def test_a_repository_left_without_workspaces_is_scanned_afresh_when_one_returns(
    base_repo: Path,
    tmp_path: Path,
    test_root_concurrency_group: ConcurrencyGroup,
    git_cli: GitCli,
    git_invocation_log: Path,
) -> None:
    _add_remote_ref(base_repo, "origin/main")
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    workspaces = [workspace]
    poller = _build_poller(workspaces, {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    poller._scan_once()
    workspaces.clear()
    poller._scan_once()
    workspaces.append(workspace)
    git_invocation_log.write_text("")

    poller._scan_once()

    remote_listings = [
        arguments for _, arguments in _read_git_invocations(git_invocation_log) if arguments.startswith("branch -r")
    ]
    assert len(remote_listings) == 1


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


def test_a_workspace_that_cannot_be_scanned_does_not_stop_the_others(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    worktree = tmp_path / "ws"
    _add_worktree(base_repo, worktree, "wsbranch")
    orphaned = _FakeWorkspace(WorkspaceID(), ProjectID())
    healthy = _FakeWorkspace(WorkspaceID(), ProjectID())

    def resolve_working_dir(workspace: Workspace) -> Path | None:
        if workspace.object_id == orphaned.object_id:
            raise WorkspaceNotFoundError(workspace.object_id)
        return worktree

    poller = _build_poller(
        [orphaned, healthy], {}, test_root_concurrency_group, git_cli, resolve_working_dir=resolve_working_dir
    )
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    poller._scan_once()

    branch_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceBranchInfo)]
    assert [(info.workspace_id, info.current_branch) for info in branch_infos] == [(healthy.object_id, "wsbranch")]


# What the branch scan logs when it runs git in a jj workspace.
_JJ_WORKSPACE_LOG = "Branch scan ran git in a jj workspace"


def test_git_run_in_a_jj_workspace_while_scanning_one_workspace_is_logged_at_error_and_skips_only_it(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    jj_workspace = tmp_path / "jj-workspace"
    (jj_workspace / ".jj").mkdir(parents=True)
    misdispatched_checkout = tmp_path / "misdispatched"
    healthy_checkout = tmp_path / "healthy"
    _add_worktree(base_repo, misdispatched_checkout, "misdispatched-branch")
    _add_worktree(base_repo, healthy_checkout, "healthy-branch")
    misdispatched = _FakeWorkspace(WorkspaceID(), ProjectID())
    healthy = _FakeWorkspace(WorkspaceID(), ProjectID())

    def refresh_diff(workspace_id: WorkspaceID) -> None:
        if workspace_id == misdispatched.object_id:
            git_cli.run_git(["status"], jj_workspace, is_read_only=True)

    poller = _build_poller(
        [misdispatched, healthy],
        {misdispatched.object_id: misdispatched_checkout, healthy.object_id: healthy_checkout},
        test_root_concurrency_group,
        git_cli,
        refresh_diff_on_branch_change=refresh_diff,
    )
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)
    poller._scan_once()
    _drain(queue)
    LocalGitRepo(misdispatched_checkout).run_git(["checkout", "-b", "misdispatched-renamed"])
    LocalGitRepo(healthy_checkout).run_git(["checkout", "-b", "healthy-renamed"])

    with expect_exact_logged_errors([_JJ_WORKSPACE_LOG]):
        with record_logged_error_levels() as levels:
            poller._scan_once()

    assert levels == ["ERROR"]
    branch_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceBranchInfo)]
    assert [(info.workspace_id, info.current_branch) for info in branch_infos] == [
        (healthy.object_id, "healthy-renamed")
    ]


def test_git_run_in_a_jj_workspace_by_the_target_scan_is_logged_once_at_error(
    base_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    # A worktree of the git store a jj repository keeps inside its workspace: the
    # target scan reads candidates in the store's parent, which is in the jj workspace.
    git_store = tmp_path / "jj-workspace" / ".jj" / "repo" / "store" / "git"
    LocalGitRepo(tmp_path).run_git(["clone", "--bare", str(base_repo), str(git_store)])
    worktree = tmp_path / "ws"
    LocalGitRepo(tmp_path).run_git(["--git-dir", str(git_store), "worktree", "add", "-b", "wsbranch", str(worktree)])
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    poller = _build_poller([workspace], {workspace.object_id: worktree}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    with expect_exact_logged_errors([_JJ_WORKSPACE_LOG]):
        with record_logged_error_levels() as levels:
            poller._scan_once()
            poller._scan_once()

    assert levels == ["ERROR"]
    branch_infos = [item for item in _drain(queue) if isinstance(item, WorkspaceBranchInfo)]
    assert [info.current_branch for info in branch_infos] == ["wsbranch"]


def test_git_run_in_a_jj_workspace_right_after_an_ordinary_scan_failure_is_still_logged_at_error(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli
) -> None:
    jj_workspace = tmp_path / "jj-workspace"
    (jj_workspace / ".jj").mkdir(parents=True)
    workspace = _FakeWorkspace(WorkspaceID(), ProjectID())
    scan_count = [0]

    def resolve_working_dir(_workspace: Workspace) -> Path | None:
        scan_count[0] += 1
        if scan_count[0] == 1:
            raise WorkspaceNotFoundError(workspace.object_id)
        git_cli.run_git(["status"], jj_workspace, is_read_only=True)
        return jj_workspace

    poller = _build_poller(
        [workspace], {}, test_root_concurrency_group, git_cli, resolve_working_dir=resolve_working_dir
    )

    with expect_exact_logged_errors(["Branch scan is skipping", _JJ_WORKSPACE_LOG]):
        with record_logged_error_levels() as levels:
            poller._scan_once()
            poller._scan_once()

    assert levels == ["LOW_PRIORITY", "ERROR"]


def test_a_jj_workspace_gets_neither_a_branch_nor_target_branches(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup, git_cli: GitCli, git_invocation_log: Path
) -> None:
    checkout = tmp_path / "ws"
    (checkout / ".jj").mkdir(parents=True)
    workspace = _FakeWorkspace(
        WorkspaceID(), ProjectID(), initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE
    )
    poller = _build_poller([workspace], {workspace.object_id: checkout}, test_root_concurrency_group, git_cli)
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    poller.add_observer(queue)

    with record_logged_error_levels() as levels:
        poller._scan_once()

    assert levels == []
    assert _drain(queue) == []
    assert _read_git_invocations(git_invocation_log) == []
