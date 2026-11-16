"""Unit tests for :mod:`sculptor.services.workspace_service.jj_workspace_poller`, against real jj.

Tests drive a single ``_scan_once()`` and assert on what is fanned out to observer queues.
"""

import shlex
import shutil
from pathlib import Path
from queue import Queue

import pytest

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.foundation.async_monkey_patches_test import record_logged_error_levels
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.jj_workspace_poller import JjWorkspacePoller
from sculptor.services.workspace_service.stale_working_copy_registry import StaleWorkingCopyRegistry
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import JjWorkspaceVcs
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import run_jj
from sculptor.testing.workspace_vcs import make_test_git_cli
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceJjStateInfo
from sculptor.web.data_types import WorkspaceTargetBranchesInfo

_TARGET = "main@origin"


def _make_workspace(
    target_branch: str | None = _TARGET,
    initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.JJ_WORKSPACE,
) -> Workspace:
    return Workspace(
        object_id=WorkspaceID(),
        project_id=ProjectID(),
        organization_reference=OrganizationReference("test-org"),
        description="test workspace",
        initialization_strategy=initialization_strategy,
        target_branch=target_branch,
    )


class _Harness:
    """A poller over fake workspace rows whose checkouts are real jj workspaces, counting every jj it runs."""

    def __init__(
        self,
        concurrency_group: ConcurrencyGroup,
        jj_binary: JjBinary,
        repo: JjColocatedRepo,
        tmp_path: Path,
    ) -> None:
        self.jj_binary = jj_binary
        self.repo = repo
        self.workspaces: list[Workspace] = []
        self.checkout_by_workspace: dict[WorkspaceID, Path] = {}
        self.refreshed_diffs: list[WorkspaceID] = []
        self.stale_working_copies = StaleWorkingCopyRegistry()
        self._invocation_log = tmp_path / "jj-invocations.log"
        self._invocation_log.touch()
        wrapper = tmp_path / "counting-jj"
        wrapper.write_text(
            "#!/bin/bash\n"
            + f'echo "$*" >> {shlex.quote(str(self._invocation_log))}\n'
            + f'exec {shlex.quote(str(jj_binary.path))} "$@"\n'
        )
        wrapper.chmod(0o755)
        self.poller = JjWorkspacePoller(
            concurrency_group=concurrency_group,
            read_workspaces=lambda: list(self.workspaces),
            jj=JjCli(concurrency_group, lambda tool: str(wrapper) if tool is Dependency.JJ else None),
            resolve_working_dir=self._resolve_working_dir,
            refresh_diff_on_working_copy_change=self.refreshed_diffs.append,
            stale_working_copies=self.stale_working_copies,
        )
        self.queue: Queue[StreamingUpdateSourceTypes] = Queue()
        self.poller.add_observer(self.queue)

    def _resolve_working_dir(self, workspace: Workspace) -> Path | None:
        return self.checkout_by_workspace.get(workspace.object_id)

    def add_workspace(self, workspace: Workspace | None = None, base: str = "main") -> tuple[Workspace, Path]:
        workspace = workspace or _make_workspace()
        checkout = self.repo.path.parent / "environments" / str(workspace.object_id) / "code"
        checkout.parent.mkdir(parents=True)
        run_jj(
            self.jj_binary,
            ("workspace", "add", "--no-colocate", "--name", str(workspace.object_id), "-r", base, str(checkout)),
            cwd=self.repo.path,
        )
        self.workspaces.append(workspace)
        self.checkout_by_workspace[workspace.object_id] = checkout
        return workspace, checkout

    def jj(self, checkout: Path, *arguments: str) -> str:
        return run_jj(self.jj_binary, arguments, cwd=checkout)

    def count_jj_invocations(self) -> int:
        return len(self._invocation_log.read_text().splitlines())

    def scan(self) -> list[StreamingUpdateSourceTypes]:
        self.poller._scan_once()
        items: list[StreamingUpdateSourceTypes] = []
        while not self.queue.empty():
            items.append(self.queue.get_nowait())
        return items


def _states(items: list[StreamingUpdateSourceTypes]) -> list[WorkspaceJjStateInfo]:
    return [item for item in items if isinstance(item, WorkspaceJjStateInfo)]


def _targets(items: list[StreamingUpdateSourceTypes]) -> list[WorkspaceTargetBranchesInfo]:
    return [item for item in items if isinstance(item, WorkspaceTargetBranchesInfo)]


@pytest.fixture
def harness(
    test_root_concurrency_group: ConcurrencyGroup,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_colocated_repo: JjColocatedRepo,
    tmp_path: Path,
) -> _Harness:
    return _Harness(test_root_concurrency_group, jj_binary, jj_colocated_repo, tmp_path)


def test_a_jj_workspace_publishes_its_working_copy_and_the_bookmarks_it_can_target(harness: _Harness) -> None:
    workspace, checkout = harness.add_workspace()

    items = harness.scan()

    change_id = harness.jj(checkout, "--ignore-working-copy", "log", "--no-graph", "-r", "@", "-T", "change_id")
    prefix = harness.jj(
        checkout, "--ignore-working-copy", "log", "--no-graph", "-r", "@", "-T", "change_id.shortest().prefix()"
    )
    assert _states(items) == [
        WorkspaceJjStateInfo(
            workspace_id=workspace.object_id,
            working_copy_change_id=change_id,
            working_copy_change_id_prefix_length=len(prefix),
            working_copy_description="",
            is_working_copy_empty=True,
            bookmarks=(),
            primary_bookmark=None,
            unbookmarked_revision_count=0,
            has_conflict=False,
            is_divergent=False,
            is_working_copy_stale=False,
        )
    ]
    (targets,) = _targets(items)
    assert set(targets.target_branches) == {"main", "main@origin"}
    assert targets.pr_base_names == {"main": "main", "main@origin": "main"}
    assert harness.poller.get_jj_state(workspace.object_id) == _states(items)[0]


def test_the_state_changes_exactly_when_the_agent_describes_commits_or_bookmarks(harness: _Harness) -> None:
    _, checkout = harness.add_workspace()
    harness.scan()

    (checkout / "draft.txt").write_text("an edit jj snapshots without a description\n")
    harness.jj(checkout, "util", "snapshot")
    after_edit = _states(harness.scan())
    harness.jj(checkout, "describe", "-m", "add the draft")
    after_describe = _states(harness.scan())
    harness.jj(checkout, "new")
    after_commit = _states(harness.scan())
    harness.jj(checkout, "bookmark", "create", "-r", "@-", "draft")
    after_bookmark = _states(harness.scan())

    assert [state.is_working_copy_empty for state in after_edit] == [False]
    assert [state.working_copy_description for state in after_describe] == ["add the draft"]
    assert [(state.working_copy_description, state.unbookmarked_revision_count) for state in after_commit] == [("", 1)]
    assert after_commit[0].working_copy_change_id != after_describe[0].working_copy_change_id
    assert [(state.bookmarks, state.primary_bookmark) for state in after_bookmark] == [(("draft",), "draft")]


def test_a_snapshot_that_changes_nothing_the_state_shows_publishes_nothing(harness: _Harness) -> None:
    _, checkout = harness.add_workspace()
    (checkout / "first.txt").write_text("first\n")
    harness.jj(checkout, "util", "snapshot")
    harness.scan()

    (checkout / "second.txt").write_text("second\n")
    harness.jj(checkout, "util", "snapshot")

    assert harness.scan() == []


def test_an_idle_cycle_runs_no_process(harness: _Harness) -> None:
    harness.add_workspace()
    harness.add_workspace()
    harness.scan()
    invocations_after_first_scan = harness.count_jj_invocations()

    harness.scan()

    assert invocations_after_first_scan == 2
    assert harness.count_jj_invocations() == invocations_after_first_scan


def test_a_changed_working_copy_change_id_refreshes_the_diff_and_a_description_does_not(harness: _Harness) -> None:
    workspace, checkout = harness.add_workspace()
    harness.scan()

    harness.jj(checkout, "describe", "-m", "described")
    harness.scan()
    refreshed_after_describe = list(harness.refreshed_diffs)
    harness.jj(checkout, "new")
    harness.scan()

    assert refreshed_after_describe == []
    assert harness.refreshed_diffs == [workspace.object_id]


def test_a_conflicted_bookmark_is_not_offered_as_a_target(harness: _Harness) -> None:
    _, checkout = harness.add_workspace()
    harness.jj(checkout, "commit", "-m", "side a")
    harness.jj(checkout, "new", "-m", "side b", "main")
    harness.jj(checkout, "commit", "-m", "side b")
    operation_before_bookmark = harness.jj(
        checkout, "--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"
    )
    harness.jj(checkout, "bookmark", "create", "-r", "@-", "forked")
    harness.jj(
        checkout,
        "--at-op",
        operation_before_bookmark,
        "--ignore-working-copy",
        "bookmark",
        "create",
        "forked",
        "-r",
        'description(exact:"side a\\n")',
    )

    (targets,) = _targets(harness.scan())

    assert "forked" not in targets.target_branches
    assert {"main", "main@origin"} <= set(targets.target_branches)


def test_a_workspaces_own_bookmarks_are_not_offered_as_its_targets(harness: _Harness) -> None:
    _, checkout = harness.add_workspace()
    harness.jj(checkout, "commit", "-m", "work")
    harness.jj(checkout, "bookmark", "create", "-r", "@-", "own")
    other, _ = harness.add_workspace()

    targets_by_workspace = {targets.workspace_id: targets for targets in _targets(harness.scan())}

    assert "own" in targets_by_workspace[other.object_id].target_branches
    own_targets = next(
        targets for workspace_id, targets in targets_by_workspace.items() if workspace_id != other.object_id
    )
    assert "own" not in own_targets.target_branches


def test_every_offered_target_is_one_the_workspaces_vcs_accepts_as_a_target(
    harness: _Harness, test_root_concurrency_group: ConcurrencyGroup, jj_binary: JjBinary
) -> None:
    workspace, checkout = harness.add_workspace()
    harness.jj(checkout, "commit", "-m", "side a")
    harness.jj(checkout, "bookmark", "create", "-r", "@-", "own")
    harness.jj(checkout, "new", "-m", "side b", "main")
    harness.jj(checkout, "commit", "-m", "side b")
    operation_before_bookmark = harness.jj(
        checkout, "--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"
    )
    harness.jj(checkout, "bookmark", "create", "-r", "@-", "forked")
    harness.jj(
        checkout,
        "--at-op",
        operation_before_bookmark,
        "--ignore-working-copy",
        "bookmark",
        "create",
        "forked",
        "-r",
        "own",
    )
    vcs = JjWorkspaceVcs(
        JjCli(test_root_concurrency_group, lambda tool: str(jj_binary.path) if tool is Dependency.JJ else None),
        make_test_git_cli(test_root_concurrency_group),
        lambda: 10,
    )

    (targets,) = _targets(harness.scan())

    state = harness.poller.get_jj_state(workspace.object_id)
    assert state is not None
    accepted_targets = vcs.list_target_candidates(harness.repo.path)
    assert set(targets.target_branches) | set(state.bookmarks) == set(accepted_targets)
    assert "forked" not in accepted_targets


def test_a_stale_mark_is_published_and_cleared_without_running_jj(harness: _Harness) -> None:
    workspace, _ = harness.add_workspace()
    harness.scan()
    invocations_after_first_scan = harness.count_jj_invocations()

    harness.stale_working_copies.mark_stale(workspace.object_id)
    marked = _states(harness.scan())
    harness.stale_working_copies.mark_fresh(workspace.object_id)
    cleared = _states(harness.scan())

    assert [state.is_working_copy_stale for state in marked] == [True]
    assert [state.is_working_copy_stale for state in cleared] == [False]
    assert harness.count_jj_invocations() == invocations_after_first_scan


def test_missing_workspaces_targets_and_checkouts_are_tolerated(harness: _Harness, tmp_path: Path) -> None:
    forgotten, _ = harness.add_workspace()
    harness.jj(harness.repo.path, "workspace", "forget", str(forgotten.object_id))
    without_target, _ = harness.add_workspace(_make_workspace(target_branch="gone@origin"))
    without_checkout = _make_workspace()
    harness.workspaces.append(without_checkout)
    harness.checkout_by_workspace[without_checkout.object_id] = tmp_path / "never-created"
    deleted_checkout, deleted_checkout_path = harness.add_workspace()
    shutil.rmtree(deleted_checkout_path)

    with record_logged_error_levels() as levels:
        items = harness.scan()

    assert levels == []
    assert [state.workspace_id for state in _states(items)] == [without_target.object_id]
    assert deleted_checkout.object_id not in {targets.workspace_id for targets in _targets(items)}


def test_a_workspace_whose_update_fails_is_logged_once_and_does_not_stop_the_others(
    harness: _Harness,
) -> None:
    failing, failing_checkout = harness.add_workspace()
    healthy, healthy_checkout = harness.add_workspace()
    harness.scan()

    def refresh_diff(workspace_id: WorkspaceID) -> None:
        if workspace_id == failing.object_id:
            raise _UnexpectedRefreshError(workspace_id)

    harness.poller._refresh_diff_on_working_copy_change = refresh_diff
    harness.jj(failing_checkout, "new")
    harness.jj(healthy_checkout, "new")

    with expect_exact_logged_errors(["jj workspace scan is skipping"]):
        with record_logged_error_levels() as levels:
            first_states = _states(harness.scan())
            harness.jj(failing_checkout, "describe", "-m", "still failing")
            second_states = _states(harness.scan())

    assert levels == ["LOW_PRIORITY"]
    assert [state.workspace_id for state in first_states] == [healthy.object_id]
    assert second_states == []
    assert harness.poller.get_jj_state(failing.object_id) is not None


class _UnexpectedRefreshError(Exception):
    """Raised by a diff refresh standing in for a failure no handler anticipates."""


def test_a_git_workspace_is_not_scanned(harness: _Harness, tmp_path: Path) -> None:
    git_workspace = _make_workspace(initialization_strategy=WorkspaceInitializationStrategy.WORKTREE)
    harness.workspaces.append(git_workspace)
    harness.checkout_by_workspace[git_workspace.object_id] = tmp_path

    assert harness.scan() == []
    assert harness.count_jj_invocations() == 0


def test_a_removed_workspace_is_dropped_from_the_backfill(harness: _Harness) -> None:
    workspace, _ = harness.add_workspace()
    harness.scan()

    harness.workspaces.remove(workspace)
    harness.scan()
    late_observer: Queue[StreamingUpdateSourceTypes] = Queue()
    harness.poller.add_observer(late_observer)

    assert late_observer.empty()
    assert harness.poller.get_jj_state(workspace.object_id) is None


def test_a_new_observer_is_backfilled_with_the_current_state(harness: _Harness) -> None:
    workspace, _ = harness.add_workspace()
    harness.scan()
    late_observer: Queue[StreamingUpdateSourceTypes] = Queue()

    harness.poller.add_observer(late_observer)

    backfilled: list[StreamingUpdateSourceTypes] = []
    while not late_observer.empty():
        backfilled.append(late_observer.get_nowait())
    assert [state.workspace_id for state in _states(backfilled)] == [workspace.object_id]
    assert [targets.workspace_id for targets in _targets(backfilled)] == [workspace.object_id]
