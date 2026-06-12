"""Unit tests for CIBabysitterCoordinator covering the 8 spec scenarios.

Tests drive ``_handle_status`` directly, bypassing the queue and
consumer thread. Service dependencies are stubbed with concrete
NotImplementedError-stubbed subclasses of the abstract Service base
classes; only the methods the coordinator actually uses are
implemented.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator
from typing import Literal
from typing import cast

import pytest
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.user_config import CIBabysitterConfig
from imbue_core.sculptor.user_config import UserConfig
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TransactionID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.ci_babysitter_service import coordinator as coordinator_module
from sculptor.services.ci_babysitter_service.coordinator import CIBabysitterCoordinator
from sculptor.services.ci_babysitter_service.transitions import Transition
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.git_repos import ReadOnlyGitRepo
from sculptor.services.task_service.api import TaskService
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.web.derived import PrStatusInfo
from sculptor.web.pr_polling_service import PrPollingService


def _stub(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("Stubbed by ci_babysitter_service.coordinator_test")


class _StubTransaction(DataModelTransaction):
    """Concrete DataModelTransaction with all abstract methods stubbed."""

    def add_callback(self, callback: Any) -> None:
        _stub(callback)

    def run_post_commit_hooks(self) -> None:
        _stub()

    def upsert_project(self, project: Any) -> Any:
        return _stub(project)

    def update_project_fields(self, project_id: Any, **fields: Any) -> Any:
        return _stub(project_id, **fields)

    def get_projects(self, organization_reference: Any = None) -> Any:
        return _stub(organization_reference)

    def get_user_settings(self, user_reference: Any) -> Any:
        return _stub(user_reference)

    def get_or_create_user_settings(self, user_reference: Any) -> Any:
        return _stub(user_reference)

    def get_project(self, project_id: ProjectID) -> Project | None:
        return _stub(project_id)

    def insert_notification(self, notification: Any) -> Any:
        return _stub(notification)

    def get_workspace(self, workspace_id: WorkspaceID) -> Workspace | None:
        return _stub(workspace_id)

    def get_workspaces(self, project_id: Any = None, organization_reference: Any = None) -> Any:
        return _stub(project_id, organization_reference)

    def get_workspace_include_deleted(self, workspace_id: WorkspaceID) -> Workspace | None:
        return _stub(workspace_id)

    def count_active_tasks_for_workspace(self, workspace_id: WorkspaceID) -> int:
        return _stub(workspace_id)

    def upsert_workspace(self, workspace: Any) -> Any:
        return _stub(workspace)

    def update_workspace_fields(self, workspace_id: Any, **fields: Any) -> Any:
        return _stub(workspace_id, **fields)

    def get_all_workspaces(self) -> Any:
        return _stub()


class _StubDataModelService(DataModelService):
    @contextmanager
    def open_transaction(
        self, request_id: RequestID, is_user_request: bool = True, *, immediate: bool = False
    ) -> Generator[DataModelTransaction, None, None]:
        del request_id, is_user_request, immediate
        yield _StubTransaction(request_id=None, transaction_id=TransactionID())

    @contextmanager
    def observe_user_changes(
        self, user_reference: Any, organization_reference: Any, queue: Any
    ) -> Generator[Any, None, None]:
        del user_reference, organization_reference
        yield queue


class _StubTaskService(TaskService):
    def create_task(self, task: Task, transaction: DataModelTransaction) -> Task:
        return _stub(task, transaction)

    def create_message(self, message: MessageTypes, task_id: TaskID, transaction: DataModelTransaction) -> None:
        _stub(message, task_id, transaction)

    def get_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task | None:
        return _stub(task_id, transaction)

    def get_task_environment(self, task_id: TaskID, transaction: DataModelTransaction) -> Any:
        return _stub(task_id, transaction)

    def mark_read(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        return _stub(task_id, transaction)

    def mark_unread(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        return _stub(task_id, transaction)

    def restore_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task:
        return _stub(task_id, transaction)

    def delete_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None:
        _stub(task_id, transaction)

    def get_artifact_file_url(self, task_id: TaskID, artifact_name: str) -> Any:
        return _stub(task_id, artifact_name)

    def set_artifact_file_data(self, task_id: TaskID, artifact_name: str, artifact_data: Any) -> None:
        _stub(task_id, artifact_name, artifact_data)

    def ensure_artifact_cache_populated(self, task_id: TaskID, artifact_name: str) -> bool:
        _stub(task_id, artifact_name)
        return False

    def get_saved_messages_for_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Any:
        return _stub(task_id, transaction)

    @contextmanager
    def subscribe_to_all_tasks_for_user(self, user_reference: Any) -> Generator[Any, None, None]:
        del user_reference
        yield _stub()

    @contextmanager
    def subscribe_to_project_task_containers(self, project_id: Any, user_reference: Any) -> Generator[Any, None, None]:
        del project_id, user_reference
        yield _stub()

    @contextmanager
    def subscribe_to_workspace_task_containers(
        self, workspace_id: WorkspaceID, user_reference: Any
    ) -> Generator[Any, None, None]:
        del workspace_id, user_reference
        yield _stub()

    @contextmanager
    def subscribe_to_single_task_container(self, task_id: TaskID, user_reference: Any) -> Generator[Any, None, None]:
        del task_id, user_reference
        yield _stub()

    @contextmanager
    def subscribe_to_task(self, task_id: TaskID) -> Generator[Any, None, None]:
        del task_id
        yield _stub()

    @contextmanager
    def subscribe_to_user_and_sculptor_system_messages(self, task_id: TaskID) -> Generator[Any, None, None]:
        del task_id
        yield _stub()


class _StubGitRepo(ReadOnlyGitRepo):
    def get_current_commit_hash(self) -> str:
        return _stub()

    def get_repo_path(self) -> Any:
        return _stub()

    def get_repo_url(self) -> Any:
        return _stub()

    def get_all_branches(self) -> list[str]:
        return _stub()

    def get_current_git_branch(self) -> str:
        return _stub()

    def is_branch_ref(self, branch: str) -> bool:
        return _stub(branch)

    def _run_git(self, args: list[str]) -> str:
        return _stub(args)


# Set abstract methods on stub classes that may have inherited abstracts we
# haven't enumerated. The explicit stubs above satisfy the type checker; this hides any
# parent-class abstracts at runtime that we don't actually need.
for _stub_cls in (_StubTransaction, _StubDataModelService, _StubTaskService, _StubGitRepo):
    _stub_cls.__abstractmethods__ = frozenset()


class _StubGitRepoService(GitRepoService):
    @contextmanager
    def open_local_user_git_repo_for_read(
        self, project: Project, log_command: bool = True
    ) -> Generator[ReadOnlyGitRepo, None, None]:
        del project, log_command
        yield _stub()


# WorkspaceService has many abstracts; tests don't call any. Build a stub
# class dynamically so the type checker sees ``_make_workspace_service`` as returning a
# real ``WorkspaceService`` without an abstract-instantiation error.
def _make_workspace_service(concurrency_group: ConcurrencyGroup) -> WorkspaceService:
    cls = type("_StubWorkspaceService", (WorkspaceService,), {})
    # pyrefly: ignore [missing-attribute]
    cls.__abstractmethods__ = frozenset()
    return cast(WorkspaceService, cls(concurrency_group=concurrency_group))


def _make_fake_git_repo_service(concurrency_group: ConcurrencyGroup) -> "_FakeGitRepoService":
    return _FakeGitRepoService(concurrency_group)


class _FakeEnv:
    def __init__(self) -> None:
        self.workspace_id = WorkspaceID()
        self.project_id = ProjectID()
        organization_reference = OrganizationReference("org-123")
        self.project = Project(
            object_id=self.project_id,
            organization_reference=organization_reference,
            name="test-project",
            user_git_repo_url="file:///tmp/repo",
            default_system_prompt="be helpful",
        )
        self.workspace = Workspace(
            object_id=self.workspace_id,
            project_id=self.project_id,
            organization_reference=organization_reference,
            description="test workspace",
            initialization_strategy=WorkspaceInitializationStrategy.CLONE,
        )
        self.tasks_by_id: dict[TaskID, Task] = {}


class _FakeTransaction(_StubTransaction):
    _env: _FakeEnv = PrivateAttr()

    def __init__(self, env: _FakeEnv) -> None:
        super().__init__(request_id=None, transaction_id=TransactionID())
        self._env = env

    def get_workspace(self, workspace_id: WorkspaceID) -> Workspace | None:
        return self._env.workspace if workspace_id == self._env.workspace.object_id else None

    def get_project(self, project_id: ProjectID) -> Project | None:
        return self._env.project if project_id == self._env.project.object_id else None


class _FakeDataModelService(_StubDataModelService):
    _env: _FakeEnv = PrivateAttr()

    def __init__(self, env: _FakeEnv, concurrency_group: ConcurrencyGroup) -> None:
        super().__init__(concurrency_group=concurrency_group)
        self._env = env

    @contextmanager
    def open_transaction(
        self, request_id: RequestID, is_user_request: bool = True, *, immediate: bool = False
    ) -> Generator[DataModelTransaction, None, None]:
        del request_id, is_user_request, immediate
        yield _FakeTransaction(self._env)


class _FakeTaskService(_StubTaskService):
    _env: _FakeEnv = PrivateAttr()
    _create_task_calls: list[Task] = PrivateAttr(default_factory=list)
    _create_message_calls: list[tuple[ChatInputUserMessage, TaskID]] = PrivateAttr(default_factory=list)
    _delete_task_calls: list[TaskID] = PrivateAttr(default_factory=list)

    def __init__(self, env: _FakeEnv, concurrency_group: ConcurrencyGroup) -> None:
        super().__init__(concurrency_group=concurrency_group, task_sync_dir=Path("/tmp"))
        self._env = env

    @property
    def create_task_calls(self) -> list[Task]:
        return self._create_task_calls

    @property
    def create_message_calls(self) -> list[tuple[ChatInputUserMessage, TaskID]]:
        return self._create_message_calls

    @property
    def delete_task_calls(self) -> list[TaskID]:
        return self._delete_task_calls

    def create_task(self, task: Task, transaction: DataModelTransaction) -> Task:
        del transaction
        self._create_task_calls.append(task)
        self._env.tasks_by_id[task.object_id] = task
        return task

    def create_message(self, message: MessageTypes, task_id: TaskID, transaction: DataModelTransaction) -> None:
        del transaction
        assert isinstance(message, ChatInputUserMessage)
        self._create_message_calls.append((message, task_id))

    def get_task(self, task_id: TaskID, transaction: DataModelTransaction) -> Task | None:
        del transaction
        return self._env.tasks_by_id.get(task_id)

    def delete_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None:
        del transaction
        self._delete_task_calls.append(task_id)


class _FakeGitRepo(_StubGitRepo):
    _commit_hash: str = PrivateAttr()

    def __init__(self, commit_hash: str) -> None:
        super().__init__()
        self._commit_hash = commit_hash

    def get_current_commit_hash(self) -> str:
        return self._commit_hash


class _FakeGitRepoService(_StubGitRepoService):
    _commit_hash: str = PrivateAttr()

    def __init__(self, concurrency_group: ConcurrencyGroup, commit_hash: str = "abc123") -> None:
        super().__init__(concurrency_group=concurrency_group)
        self._commit_hash = commit_hash

    @contextmanager
    def open_local_user_git_repo_for_read(
        self, project: Project, log_command: bool = True
    ) -> Generator[ReadOnlyGitRepo, None, None]:
        del project, log_command
        yield _FakeGitRepo(self._commit_hash)


def _make_user_config(
    enabled: bool = True,
    retry_cap: int = 3,
    failed_prompt: str = "FAILED_PROMPT",
    conflict_prompt: str = "CONFLICT_PROMPT",
) -> UserConfig:
    return UserConfig(
        user_email="test@example.com",
        user_id="u",
        organization_id="o",
        instance_id="i",
        ci_babysitter=CIBabysitterConfig(
            enabled=enabled,
            retry_cap=retry_cap,
            pipeline_failed_prompt=failed_prompt,
            merge_conflict_prompt=conflict_prompt,
        ),
    )


def _make_status(
    workspace_id: WorkspaceID,
    pr_state: Literal["none", "open", "merged", "closed"] = "open",
    pipeline_status: Literal["running", "passed", "failed"] | None = None,
    pipeline_id: int | None = None,
    has_conflicts: bool | None = None,
) -> PrStatusInfo:
    return PrStatusInfo(
        workspace_id=workspace_id,
        pr_state=pr_state,
        pipeline_status=pipeline_status,
        pipeline_id=pipeline_id,
        has_conflicts=has_conflicts,
    )


def _seed_baseline(coordinator: CIBabysitterCoordinator, workspace_id: WorkspaceID) -> None:
    """Prime the coordinator's first-poll baseline for a workspace.

    The classifier suppresses PIPELINE_FAILED and MERGE_CONFLICT on
    `prev is None` to avoid burning a retry on Sculptor restart against
    an already-red MR (architecture's first-poll baseline mitigation).
    Tests that want to exercise an actionable transition must seed a
    clean baseline poll first.
    """
    coordinator._handle_status(
        _make_status(workspace_id, pipeline_status="running", pipeline_id=0, has_conflicts=False)
    )


def _build_coordinator(
    env: _FakeEnv, concurrency_group: ConcurrencyGroup
) -> tuple[CIBabysitterCoordinator, _FakeTaskService]:
    task_service = _FakeTaskService(env, concurrency_group)
    data_model_service = _FakeDataModelService(env, concurrency_group)
    workspace_service = _make_workspace_service(concurrency_group)
    pr_polling_service = PrPollingService(
        concurrency_group=concurrency_group,
        data_model_service=data_model_service,
        workspace_service=workspace_service,
    )
    coordinator = CIBabysitterCoordinator(
        concurrency_group=concurrency_group,
        data_model_service=data_model_service,
        task_service=task_service,
        git_repo_service=_make_fake_git_repo_service(concurrency_group),
        pr_polling_service=pr_polling_service,
    )
    return coordinator, task_service


@pytest.fixture
def env() -> _FakeEnv:
    return _FakeEnv()


class _ConfigSlot:
    def __init__(self, config: UserConfig) -> None:
        self.config = config


@pytest.fixture
def patch_user_config(monkeypatch: pytest.MonkeyPatch) -> _ConfigSlot:
    slot = _ConfigSlot(_make_user_config())
    monkeypatch.setattr(coordinator_module, "get_user_config_instance", lambda: slot.config)
    return slot


def test_scenario_1_happy_path(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))

    assert len(task_service.create_task_calls) == 1
    first_task = task_service.create_task_calls[0]
    assert isinstance(first_task.current_state, AgentTaskStateV2)
    assert first_task.current_state.title == "CI Babysitter"
    assert len(task_service.create_message_calls) == 1
    sent_message, _ = task_service.create_message_calls[0]
    assert sent_message.text == "FAILED_PROMPT"
    state = coordinator._state[env.workspace_id]
    assert state.retry_count == 1

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="passed", pipeline_id=1))

    assert len(task_service.create_message_calls) == 1
    state = coordinator._state[env.workspace_id]
    assert state.retry_count == 0


def test_scenario_2_merge_conflict(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, has_conflicts=True))

    assert len(task_service.create_task_calls) == 1
    assert len(task_service.create_message_calls) == 1
    sent_message, _ = task_service.create_message_calls[0]
    assert sent_message.text == "CONFLICT_PROMPT"
    state = coordinator._state[env.workspace_id]
    assert state.retry_count == 1


def test_merge_conflict_present_at_first_observation_is_surfaced(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """SCU-1361: a conflict already present the first time the coordinator
    observes the MR (no clean baseline poll first) must still dispatch a
    MERGE_CONFLICT prompt.

    This is the common case: a branch cut from a stale main conflicts within
    seconds of MR creation, so the very first poll already shows
    has_conflicts=True. It also covers any backend restart against an
    already-conflicted MR, since the coordinator's prev_status is in-memory
    and resets to None on restart. The deliberate absence of a _seed_baseline
    call is the whole point of the regression.
    """
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)

    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=True))

    assert len(task_service.create_message_calls) == 1
    sent_message, _ = task_service.create_message_calls[0]
    assert sent_message.text == "CONFLICT_PROMPT"
    state = coordinator._state[env.workspace_id]
    assert state.retry_count == 1
    assert state.last_dispatched_merge_conflict is True

    # A subsequent poll with the conflict still present must NOT re-prompt:
    # the dispatch dedup holds for the rest of the process lifetime.
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=True))
    assert len(task_service.create_message_calls) == 1
    assert state.retry_count == 1


def test_scenario_3_retry_cap(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=2))
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=3))
    assert len(task_service.create_message_calls) == 3
    state = coordinator._state[env.workspace_id]
    assert state.retry_count == 3

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=4))
    assert len(task_service.create_message_calls) == 3
    assert state.retry_count == 3
    assert task_service.delete_task_calls == []

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="passed", pipeline_id=4))
    assert state.retry_count == 0

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=5))
    assert len(task_service.create_message_calls) == 4
    assert state.retry_count == 1


def test_scenario_4_pause_prevents_prompt(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator.set_paused(env.workspace_id, True)
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))

    assert task_service.create_message_calls == []
    assert task_service.create_task_calls == []
    state = coordinator._state[env.workspace_id]
    assert state.retry_count == 0


def test_scenario_5_mid_turn_queueing_reuses_task(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    assert len(task_service.create_task_calls) == 1
    first_task_id = task_service.create_message_calls[0][1]

    coordinator._handle_status(
        _make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1, has_conflicts=True)
    )

    assert len(task_service.create_task_calls) == 1
    assert len(task_service.create_message_calls) == 2
    assert task_service.create_message_calls[1][1] == first_task_id
    assert task_service.delete_task_calls == []


def test_scenario_6_human_push_non_interference(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    initial_messages = len(task_service.create_message_calls)
    initial_tasks = len(task_service.create_task_calls)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="running", pipeline_id=2))

    assert len(task_service.create_message_calls) == initial_messages
    assert len(task_service.create_task_calls) == initial_tasks


def test_scenario_7_mr_merged_retires(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    assert len(task_service.create_message_calls) == 1

    coordinator._handle_status(_make_status(env.workspace_id, pr_state="merged"))
    state = coordinator._state[env.workspace_id]
    assert state.retired is True

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=2))
    assert len(task_service.create_message_calls) == 1
    assert task_service.delete_task_calls == []


def test_same_cycle_merge_and_failed_suppresses_prompt(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """If MR_MERGED arrives in the same diff as PIPELINE_FAILED, retire wins.

    Reproduces a race where a user manually merges a still-red MR. The
    coordinator must process the retire transition before any pipeline-
    failed dispatch in the same diff, so no spurious prompt is sent.
    """
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(
        _make_status(env.workspace_id, pr_state="merged", pipeline_status="failed", pipeline_id=1)
    )

    assert task_service.create_task_calls == []
    assert task_service.create_message_calls == []
    state = coordinator._state[env.workspace_id]
    assert state.retired is True
    assert state.retry_count == 0


def test_scenario_8_feature_disabled(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    patch_user_config.config = _make_user_config(enabled=False)
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))

    assert task_service.create_task_calls == []
    assert task_service.create_message_calls == []


def test_transient_pr_state_none_does_not_clobber_prev_status(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """A transient pr_state="none" gap (e.g. detached HEAD mid-rebase)
    must not overwrite prev_status. If it did, the next poll that re-finds
    the MR would look like a fresh False→True merge_conflict transition
    and dispatch a duplicate prompt.
    """
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    # 1. Conflict appears → babysitter prompted.
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=True))
    assert len(task_service.create_message_calls) == 1

    # 2. Branch flips: MR can't be matched → polling emits pr_state="none".
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="none", has_conflicts=None))

    # 3. Branch back: MR re-found, conflict still present.
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=True))

    # The prompt MUST NOT have been resent.
    assert len(task_service.create_message_calls) == 1


def test_merge_conflict_dispatch_dedupes_until_resolved(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Even if the classifier emits a duplicate MERGE_CONFLICT
    (e.g. because the polling service stream was reset), the dispatch
    layer must suppress the duplicate until the conflict is observed
    as resolved (has_conflicts=False).
    """
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)
    state = coordinator._state[env.workspace_id]

    # 1. Conflict appears → first prompt.
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=True))
    assert len(task_service.create_message_calls) == 1
    assert state.last_dispatched_merge_conflict is True

    # 2. Force a re-dispatch by directly calling _dispatch_prompt with
    #    the same state — simulates a classifier emitting MERGE_CONFLICT
    #    again. The dispatch dedup must suppress.
    new = _make_status(env.workspace_id, pr_state="open", has_conflicts=True)
    coordinator._dispatch_prompt(state, Transition.MERGE_CONFLICT, new)
    assert len(task_service.create_message_calls) == 1

    # 3. Conflict resolved → re-arm the dedup.
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=False))
    assert state.last_dispatched_merge_conflict is False

    # 4. New conflict → fresh prompt is allowed.
    coordinator._handle_status(_make_status(env.workspace_id, pr_state="open", has_conflicts=True))
    assert len(task_service.create_message_calls) == 2


def test_pipeline_failed_dispatch_dedupes_per_pipeline_id(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """A second dispatch attempt for the same pipeline_id is suppressed.
    A new pipeline_id (next push) re-arms the dedup.
    """
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)
    state = coordinator._state[env.workspace_id]

    # 1. Pipeline 1 fails → first prompt.
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    assert len(task_service.create_message_calls) == 1
    assert state.last_dispatched_pipeline_failed_id == 1

    # 2. Force re-dispatch attempt for the same pipeline_id → suppressed.
    new = _make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1)
    coordinator._dispatch_prompt(state, Transition.PIPELINE_FAILED, new)
    assert len(task_service.create_message_calls) == 1

    # 3. New pipeline id (next push) → fresh prompt allowed.
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=2))
    assert len(task_service.create_message_calls) == 2
    assert state.last_dispatched_pipeline_failed_id == 2
