"""Unit tests for CIBabysitterCoordinator covering the 8 spec scenarios.

Tests drive ``_handle_status`` directly, bypassing the queue and
consumer thread. Service dependencies are stubbed with concrete
NotImplementedError-stubbed subclasses of the abstract Service base
classes; only the methods the coordinator actually uses are
implemented.
"""

import datetime
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Any
from typing import Generator
from typing import Literal
from typing import cast

import pytest
from pydantic import PrivateAttr

from sculptor.config.user_config import BabysitterAgentClaude
from sculptor.config.user_config import BabysitterAgentMRU
from sculptor.config.user_config import BabysitterAgentPi
from sculptor.config.user_config import BabysitterAgentRegistered
from sculptor.config.user_config import CIBabysitterConfig
from sculptor.config.user_config import UserConfig
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.async_monkey_patches_test import expect_at_least_logged_errors
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentSignalRunnerMessage
from sculptor.interfaces.agents.agent import TerminalStatusSignal
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TransactionID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.ci_babysitter_service import coordinator as coordinator_module
from sculptor.services.ci_babysitter_service.coordinator import CIBabysitterCoordinator
from sculptor.services.ci_babysitter_service.coordinator import ChatAgent
from sculptor.services.ci_babysitter_service.coordinator import Disabled
from sculptor.services.ci_babysitter_service.coordinator import DriveableTerminal
from sculptor.services.ci_babysitter_service.transitions import Transition
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.git_repos import ReadOnlyGitRepo
from sculptor.services.task_service.api import TaskService
from sculptor.services.terminal_agent_registry.registry import TerminalAgentRegistration
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.state.messages import Message
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

    def get_live_messages_for_task(self, task_id: TaskID) -> Any:
        return _stub(task_id)

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
        # Most-recent-first agent tasks the resolver sees through the coordinator's
        # own transactions (used by get_state_snapshot's proactive resolve).
        self.tasks: list[Task] = []


class _FakeTransaction(_StubTransaction):
    _env: _FakeEnv = PrivateAttr()

    def __init__(self, env: _FakeEnv) -> None:
        super().__init__(request_id=None, transaction_id=TransactionID())
        self._env = env

    def get_workspace(self, workspace_id: WorkspaceID) -> Workspace | None:
        return self._env.workspace if workspace_id == self._env.workspace.object_id else None

    def get_tasks_for_project(self, project_id: ProjectID, input_data_classes: Any = None) -> list[Task]:
        del project_id, input_data_classes
        return list(self._env.tasks)

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


def _ready_terminal_messages() -> list[Message]:
    """Seed messages for which scan_terminal_signal_state reports run-started + IDLE."""
    return [
        EnvironmentAcquiredRunnerMessage.model_construct(message_id=AgentMessageID(), environment=None),
        TerminalAgentSignalRunnerMessage(signal=TerminalStatusSignal.IDLE),
    ]


class _FakeTaskService(_StubTaskService):
    _env: _FakeEnv = PrivateAttr()
    _create_task_calls: list[Task] = PrivateAttr(default_factory=list)
    _create_message_calls: list[tuple[ChatInputUserMessage, TaskID]] = PrivateAttr(default_factory=list)
    _delete_task_calls: list[TaskID] = PrivateAttr(default_factory=list)
    # Messages the terminal-readiness subscription is seeded with. Defaults to an
    # already-at-prompt program so terminal-drive tests deliver; the never-ready
    # test sets this to []. The live queue is exposed so a test can push more
    # messages after the worker subscribes.
    _seeded_terminal_messages: list[Message] = PrivateAttr(default_factory=list)
    _live_terminal_queue: "Queue[Message] | None" = PrivateAttr(default=None)

    def __init__(self, env: _FakeEnv, concurrency_group: ConcurrencyGroup) -> None:
        super().__init__(concurrency_group=concurrency_group, task_sync_dir=Path("/tmp"))
        self._env = env
        self._seeded_terminal_messages = _ready_terminal_messages()

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

    @property
    def live_terminal_queue(self) -> "Queue[Message] | None":
        return self._live_terminal_queue

    @contextmanager
    def subscribe_to_task(self, task_id: TaskID) -> Generator["Queue[Message]", None, None]:
        del task_id
        queue: "Queue[Message]" = Queue()
        for message in self._seeded_terminal_messages:
            queue.put(message)
        self._live_terminal_queue = queue
        try:
            yield queue
        finally:
            self._live_terminal_queue = None


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


# Agent resolution for babysitter tasks: _resolve_babysitter_agent maps the
# user's setting (MRU or a pinned harness) + the workspace's most-recent agent
# to a ChatAgent / DriveableTerminal / Disabled result.


class _TasksTransaction(_FakeTransaction):
    _tasks: list[Task] = PrivateAttr(default_factory=list)

    def __init__(self, env: _FakeEnv, tasks: list[Task]) -> None:
        super().__init__(env)
        self._tasks = tasks

    def get_tasks_for_project(self, project_id: ProjectID, input_data_classes: Any = None) -> list[Task]:
        del project_id, input_data_classes
        return list(self._tasks)


def _make_agent_task(
    env: _FakeEnv,
    agent_config: Any,
    created_at: str,
    default_model: LLMModel | None = None,
    title: str = "Agent",
) -> Task:
    return Task(
        object_id=TaskID(),
        created_at=datetime.datetime.fromisoformat(created_at),
        user_reference=UserReference("usr_123"),
        organization_reference=OrganizationReference("org-123"),
        project_id=env.project_id,
        input_data=AgentTaskInputsV2(
            agent_config=agent_config,
            git_hash="abc123",
            default_model=default_model,
        ),
        current_state=AgentTaskStateV2(workspace_id=env.workspace_id, title=title),
    )


def _make_config_with_agent(agent: Any, enable_pi_agent: bool = False) -> UserConfig:
    return UserConfig(
        user_email="test@example.com",
        user_id="u",
        organization_id="o",
        instance_id="i",
        enable_pi_agent=enable_pi_agent,
        ci_babysitter=CIBabysitterConfig(enabled=True, agent=agent),
    )


def _opt_in_registration(registration_id: str = "claude-code") -> TerminalAgentRegistration:
    return TerminalAgentRegistration(
        registration_id=registration_id,
        display_name="Claude Code",
        launch_command="claude",
        accepts_automated_prompts=True,
    )


def _revoked_registration(registration_id: str = "claude-code") -> TerminalAgentRegistration:
    return TerminalAgentRegistration(
        registration_id=registration_id,
        display_name="Claude Code",
        launch_command="claude",
        accepts_automated_prompts=False,
    )


def _resolve(coordinator: CIBabysitterCoordinator, env: _FakeEnv, config: UserConfig, tasks: list[Task]) -> Any:
    return coordinator._resolve_babysitter_agent(
        env.workspace_id, env.project_id, config, _TasksTransaction(env, tasks)
    )


def test_mru_most_recent_claude_resolves_chat_claude(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    tasks = [_make_agent_task(env, ClaudeCodeSDKAgentConfig(), "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU()), tasks)
    assert isinstance(result, ChatAgent)
    assert isinstance(result.config, ClaudeCodeSDKAgentConfig)


def test_mru_most_recent_pi_resolves_pi_when_enabled(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    tasks = [_make_agent_task(env, PiAgentConfig(), "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU(), enable_pi_agent=True), tasks)
    assert isinstance(result, ChatAgent)
    assert isinstance(result.config, PiAgentConfig)


def test_mru_most_recent_pi_falls_back_to_claude_when_pi_disabled(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    # MRU is best-effort: an MRU Pi while Pi is disabled must not brick the
    # babysitter — fall back to Claude (unlike a *pinned* Pi, which goes Disabled).
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    tasks = [_make_agent_task(env, PiAgentConfig(), "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU(), enable_pi_agent=False), tasks)
    assert isinstance(result, ChatAgent)
    assert isinstance(result.config, ClaudeCodeSDKAgentConfig)


def test_mru_most_recent_driveable_terminal_resolves_driveable(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    terminal_config = RegisteredTerminalAgentConfig(
        registration_id="claude-code",
        display_name="Claude Code",
        launch_command="claude",
        accepts_automated_prompts=True,
    )
    tasks = [_make_agent_task(env, terminal_config, "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU()), tasks)
    assert isinstance(result, DriveableTerminal)
    assert result.config.registration_id == "claude-code"
    assert result.config.accepts_automated_prompts is True


def test_mru_most_recent_plain_terminal_is_disabled(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    tasks = [_make_agent_task(env, TerminalAgentConfig(), "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU()), tasks)
    assert isinstance(result, Disabled)
    assert result.reason == coordinator_module._DISABLED_REASON_MRU_NON_DRIVEABLE
    assert result.transient is False


def test_mru_most_recent_registered_with_revoked_opt_in_is_disabled(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The task's stamped opt-in may be stale; the live registration revoked it.
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _revoked_registration(_id))
    terminal_config = RegisteredTerminalAgentConfig(
        registration_id="claude-code",
        display_name="Claude Code",
        launch_command="claude",
        accepts_automated_prompts=True,
    )
    tasks = [_make_agent_task(env, terminal_config, "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU()), tasks)
    assert isinstance(result, Disabled)
    assert result.reason == coordinator_module._DISABLED_REASON_MRU_NON_DRIVEABLE


def test_mru_no_prior_task_resolves_chat_claude(env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU()), [])
    assert isinstance(result, ChatAgent)
    assert isinstance(result.config, ClaudeCodeSDKAgentConfig)


def test_mru_does_not_skip_terminal_to_reach_older_chat(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    # REQ-AGENT-2: most-recent is a plain terminal, older is Claude. The resolver
    # must NOT skip the terminal to reach the older chat agent — it goes Disabled.
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    tasks = [
        _make_agent_task(env, ClaudeCodeSDKAgentConfig(), "2026-01-01T00:00:00"),
        _make_agent_task(env, TerminalAgentConfig(), "2026-01-02T00:00:00"),
    ]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentMRU()), tasks)
    assert isinstance(result, Disabled)
    assert result.reason == coordinator_module._DISABLED_REASON_MRU_NON_DRIVEABLE


def test_pinned_claude_resolves_chat_claude(env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    # A most-recent Pi must be ignored when Claude is pinned.
    tasks = [_make_agent_task(env, PiAgentConfig(), "2026-01-01T00:00:00")]
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentClaude()), tasks)
    assert isinstance(result, ChatAgent)
    assert isinstance(result.config, ClaudeCodeSDKAgentConfig)


def test_pinned_pi_resolves_pi_when_enabled(env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentPi(), enable_pi_agent=True), [])
    assert isinstance(result, ChatAgent)
    assert isinstance(result.config, PiAgentConfig)


def test_pinned_pi_is_disabled_when_pi_disabled(env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup) -> None:
    # A *pinned* Pi while Pi is disabled goes Disabled — no silent fallback.
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentPi(), enable_pi_agent=False), [])
    assert isinstance(result, Disabled)
    assert result.reason == coordinator_module._DISABLED_REASON_PINNED_UNAVAILABLE


def test_pinned_registered_available_resolves_driveable(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    result = _resolve(
        coordinator, env, _make_config_with_agent(BabysitterAgentRegistered(registration_id="claude-code")), []
    )
    assert isinstance(result, DriveableTerminal)
    assert result.config.registration_id == "claude-code"


def test_pinned_registered_unavailable_is_disabled(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: None)
    result = _resolve(coordinator, env, _make_config_with_agent(BabysitterAgentRegistered(registration_id="gone")), [])
    assert isinstance(result, Disabled)
    assert result.reason == coordinator_module._DISABLED_REASON_PINNED_UNAVAILABLE


def test_deliver_prompt_to_agent_writes_to_terminal_via_helper(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The seam dispatches a registered-terminal task through the Task 1.1 helper.
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    terminal_config = RegisteredTerminalAgentConfig(
        registration_id="claude-code",
        display_name="Claude Code",
        launch_command="claude",
        accepts_automated_prompts=True,
    )
    task = _make_agent_task(env, terminal_config, "2026-01-01T00:00:00")
    calls: list[tuple[TaskID, str, bool]] = []

    def _fake_deliver(received_task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task_service
        calls.append((received_task.object_id, text, submit))
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake_deliver)
    result = coordinator.deliver_prompt_to_agent(task, "fix the pipeline", _make_user_config())

    assert result is coordinator_module.TerminalDeliveryResult.DELIVERED
    assert calls == [(task.object_id, "fix the pipeline", True)]
    # No chat message was queued for the terminal path.
    assert task_service.create_message_calls == []


# Terminal-drive worker: the babysitter offloads a registered-terminal drive to
# a worker thread, tracks a transient disabled-reason, and coalesces overlapping
# drives. Tests pin a registered agent so resolution returns DriveableTerminal.


def _make_terminal_config(failed_prompt: str = "FAILED_PROMPT", retry_cap: int = 3) -> UserConfig:
    return UserConfig(
        user_email="test@example.com",
        user_id="u",
        organization_id="o",
        instance_id="i",
        ci_babysitter=CIBabysitterConfig(
            enabled=True,
            retry_cap=retry_cap,
            pipeline_failed_prompt=failed_prompt,
            agent=BabysitterAgentRegistered(registration_id="claude-code"),
        ),
    )


def _wait_until(predicate: Any, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "condition not met within timeout"


def test_terminal_drive_worker_delivers_and_clears_transient_reason(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    calls: list[tuple[str, bool]] = []

    def _fake(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, task_service
        calls.append((text, submit))
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake)
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    state = coordinator._state[env.workspace_id]
    _wait_until(lambda: not state.terminal_drive_in_progress)

    assert calls == [("FAILED_PROMPT", True)]
    assert state.transient_disabled_reason is None
    assert state.retry_count == 1
    # A terminal task was created and driven via the PTY, not a chat message.
    assert len(task_service.create_task_calls) == 1
    assert task_service.create_message_calls == []


def test_terminal_drive_failure_sets_transient_reason_and_counts_retry(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))

    def _fake(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, text, submit, task_service
        return coordinator_module.TerminalDeliveryResult.NOT_AT_PROMPT

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake)
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    state = coordinator._state[env.workspace_id]
    _wait_until(lambda: not state.terminal_drive_in_progress)

    assert state.transient_disabled_reason == coordinator_module._TRANSIENT_REASON_UNREACHABLE
    # A failed drive still counts against retry_cap (REQ-DRIVE-4).
    assert state.retry_count == 1


def test_overlapping_terminal_drive_coalesces(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    calls: list[str] = []

    def _fake(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, submit, task_service
        calls.append(text)
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake)
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)
    state = coordinator._state[env.workspace_id]

    # Simulate a drive already in flight: a second failure (new pipeline_id) must
    # not start a racing worker.
    state.terminal_drive_in_progress = True
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))

    assert calls == []
    # Coalesced dispatch does not bump retry/dedup bookkeeping for this cycle.
    assert state.retry_count == 0


def test_terminal_drive_in_progress_clears_on_worker_exception(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))

    def _boom(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, text, submit, task_service
        raise RuntimeError("pty exploded")

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _boom)
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    with expect_at_least_logged_errors({"CIBabysitterCoordinator: terminal drive failed for workspace="}):
        coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
        state = coordinator._state[env.workspace_id]
        # A worker exception must never park the workspace with the guard stuck on.
        _wait_until(lambda: not state.terminal_drive_in_progress)
    assert state.terminal_drive_in_progress is False


def test_terminal_drive_does_not_block_consumer_loop(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # _dispatch_prompt must return promptly even when the write blocks; the
    # write happens on the worker, not the consumer thread.
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    release = threading.Event()
    started = threading.Event()

    def _blocking(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, text, submit, task_service
        started.set()
        release.wait(timeout=5.0)
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _blocking)
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    # The dispatch returned while the worker is still blocked inside the write.
    assert started.wait(timeout=2.0)
    state = coordinator._state[env.workspace_id]
    assert state.terminal_drive_in_progress is True
    release.set()
    _wait_until(lambda: not state.terminal_drive_in_progress)


def test_terminal_drive_waits_for_idle_then_delivers(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A freshly-spawned program is not at its prompt yet: the subscription is
    # seeded empty, and the IDLE signal is pushed after the worker subscribes.
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    calls: list[str] = []

    def _fake(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, submit, task_service
        calls.append(text)
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake)
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    task_service._seeded_terminal_messages = []  # program has not reached its prompt yet
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    state = coordinator._state[env.workspace_id]

    # The worker is now blocked in the readiness wait. Push the readiness signal.
    _wait_until(lambda: task_service.live_terminal_queue is not None)
    queue = task_service.live_terminal_queue
    assert queue is not None
    for message in _ready_terminal_messages():
        queue.put(message)

    _wait_until(lambda: not state.terminal_drive_in_progress)
    assert calls == ["FAILED_PROMPT"]
    assert state.transient_disabled_reason is None


def test_terminal_drive_never_ready_times_out(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    monkeypatch.setattr(coordinator_module, "_TERMINAL_READINESS_BACKSTOP_SECONDS", 0.3)
    monkeypatch.setattr(coordinator_module, "_TERMINAL_READINESS_POLL_SECONDS", 0.05)
    calls: list[str] = []

    def _fake(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, submit, task_service
        calls.append(text)
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake)
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    task_service._seeded_terminal_messages = []  # never reaches its prompt
    _seed_baseline(coordinator, env.workspace_id)

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    state = coordinator._state[env.workspace_id]
    _wait_until(lambda: not state.terminal_drive_in_progress)

    # No write happened, but the attempt counted and the transient reason is set.
    assert calls == []
    assert state.transient_disabled_reason == coordinator_module._TRANSIENT_REASON_UNREACHABLE
    assert state.retry_count == 1


def test_terminal_drive_retries_reuse_same_task(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two failures (new pipeline_id each) within retry_cap reuse one terminal task.
    patch_user_config.config = _make_terminal_config()
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    calls: list[str] = []

    def _fake(task: Task, text: str, *, submit: bool, task_service: Any) -> Any:
        del task, submit, task_service
        calls.append(text)
        return coordinator_module.TerminalDeliveryResult.DELIVERED

    monkeypatch.setattr(coordinator_module, "deliver_prompt_to_terminal_agent", _fake)
    coordinator, task_service = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)
    state = coordinator._state[env.workspace_id]

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=1))
    _wait_until(lambda: not state.terminal_drive_in_progress)
    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="failed", pipeline_id=2))
    _wait_until(lambda: not state.terminal_drive_in_progress)

    assert len(task_service.create_task_calls) == 1  # one task reused across retries
    assert len(calls) == 2
    assert state.retry_count == 2


def test_transient_reason_clears_on_pipeline_passed(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    _seed_baseline(coordinator, env.workspace_id)
    state = coordinator._state[env.workspace_id]
    state.transient_disabled_reason = "stale hiccup"

    coordinator._handle_status(_make_status(env.workspace_id, pipeline_status="passed", pipeline_id=1))
    assert state.transient_disabled_reason is None


def test_select_model_for_workspace_skips_terminal_agents(
    env: _FakeEnv, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    # The terminal task is most recent and even carries a default_model (it
    # never does in production — this proves the skip is explicit); the older
    # chat task's model must win.
    tasks = [
        _make_agent_task(env, ClaudeCodeSDKAgentConfig(), "2026-01-01T00:00:00", default_model=LLMModel.CLAUDE_4_OPUS),
        _make_agent_task(env, TerminalAgentConfig(), "2026-01-02T00:00:00", default_model=LLMModel.CLAUDE_4_SONNET),
    ]
    model = coordinator._select_model_for_workspace(
        env.workspace_id, env.project_id, _make_user_config(), _TasksTransaction(env, tasks)
    )
    assert model == LLMModel.CLAUDE_4_OPUS


# get_state_snapshot proactively recomputes the persistent disabled-reason on
# every read and surfaces the stored transient reason.


def test_snapshot_surfaces_persistent_reason_for_plain_terminal_mru(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    coordinator.set_paused(env.workspace_id, False)  # create per-workspace state
    # Most-recent agent is a plain terminal — never driveable. No failure yet.
    env.tasks = [_make_agent_task(env, TerminalAgentConfig(), "2026-01-01T00:00:00")]

    snapshot = coordinator.get_state_snapshot(env.workspace_id)
    assert snapshot is not None
    assert snapshot.disabled_reason == coordinator_module._DISABLED_REASON_MRU_NON_DRIVEABLE


def test_snapshot_reason_self_heals_when_mru_becomes_driveable(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    coordinator.set_paused(env.workspace_id, False)
    env.tasks = [_make_agent_task(env, TerminalAgentConfig(), "2026-01-01T00:00:00")]
    before = coordinator.get_state_snapshot(env.workspace_id)
    assert before is not None
    assert before.disabled_reason is not None

    # The user opens a Claude chat agent — the reason is recomputed, not stored.
    env.tasks = [_make_agent_task(env, ClaudeCodeSDKAgentConfig(), "2026-01-02T00:00:00")]
    after = coordinator.get_state_snapshot(env.workspace_id)
    assert after is not None
    assert after.disabled_reason is None


def test_snapshot_surfaces_pinned_unavailable_reason(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    patch_user_config.config = _make_config_with_agent(BabysitterAgentPi(), enable_pi_agent=False)
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    coordinator.set_paused(env.workspace_id, False)

    snapshot = coordinator.get_state_snapshot(env.workspace_id)
    assert snapshot is not None
    assert snapshot.disabled_reason == coordinator_module._DISABLED_REASON_PINNED_UNAVAILABLE


def test_snapshot_surfaces_transient_reason_for_driveable_terminal(
    env: _FakeEnv,
    patch_user_config: _ConfigSlot,
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coordinator_module, "get_registration", lambda _id: _opt_in_registration(_id))
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    coordinator.set_paused(env.workspace_id, False)
    terminal_config = RegisteredTerminalAgentConfig(
        registration_id="claude-code",
        display_name="Claude Code",
        launch_command="claude",
        accepts_automated_prompts=True,
    )
    env.tasks = [_make_agent_task(env, terminal_config, "2026-01-01T00:00:00")]
    coordinator._state[env.workspace_id].transient_disabled_reason = coordinator_module._TRANSIENT_REASON_UNREACHABLE

    snapshot = coordinator.get_state_snapshot(env.workspace_id)
    assert snapshot is not None
    # The MRU resolves driveable (no persistent reason), so the stored transient
    # reason is surfaced.
    assert snapshot.disabled_reason == coordinator_module._TRANSIENT_REASON_UNREACHABLE


def test_snapshot_has_no_reason_for_healthy_chat_mru(
    env: _FakeEnv, patch_user_config: _ConfigSlot, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    coordinator, _ = _build_coordinator(env, test_root_concurrency_group)
    coordinator.set_paused(env.workspace_id, False)
    env.tasks = [_make_agent_task(env, ClaudeCodeSDKAgentConfig(), "2026-01-01T00:00:00")]

    snapshot = coordinator.get_state_snapshot(env.workspace_id)
    assert snapshot is not None
    assert snapshot.disabled_reason is None
