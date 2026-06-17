"""In-process coordinator that turns PrPollingService observations into
babysitter agent prompts.

The coordinator subscribes to the existing PrPollingService observer
queue, runs a pure transition classifier on each PrStatusInfo update,
and (for actionable transitions) ensures a per-workspace "CI Babysitter"
task exists and delivers the user-configured prompt via
``task_service.create_message``.

In-memory state; the babysitter task itself
is a regular Task row and is fully persistent.
"""

import threading
from queue import Empty
from queue import Queue

from loguru import logger
from pydantic import PrivateAttr

from sculptor.config.user_config import UserConfig
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import is_terminal_agent_config
from sculptor.primitives.constants import ANONYMOUS_USER_REFERENCE
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.service import Service
from sculptor.services.ci_babysitter_service.state import CIBabysitterState
from sculptor.services.ci_babysitter_service.transitions import Transition
from sculptor.services.ci_babysitter_service.transitions import classify_transitions
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.task_service.api import TaskService
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import EffortLevel
from sculptor.state.messages import LLMModel
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.derived import PrStatusInfo
from sculptor.web.pr_polling_service import PrPollingService

_BABYSITTER_TITLE = "CI Babysitter"
_CONSUMER_QUEUE_TIMEOUT_SECONDS = 1.0


def _model_from_config_or_fallback(config: UserConfig) -> LLMModel:
    if config.default_llm:
        try:
            return LLMModel(config.default_llm)
        except ValueError:
            logger.debug("Invalid default_llm {!r} in user config; using fallback", config.default_llm)
    return LLMModel.CLAUDE_4_OPUS_200K


class CIBabysitterWorkspaceStateView(SerializableModel):
    """Read-only view of per-workspace coordinator state for the pause API."""

    paused: bool
    retry_count: int
    retired: bool
    at_cap: bool


class CIBabysitterCoordinator(Service):
    """In-process observer that turns CI/MR transitions into agent prompts."""

    _data_model_service: DataModelService = PrivateAttr()
    _task_service: TaskService = PrivateAttr()
    _git_repo_service: GitRepoService = PrivateAttr()
    _pr_polling_service: PrPollingService = PrivateAttr()
    _queue: Queue[StreamingUpdateSourceTypes] = PrivateAttr(default_factory=Queue)
    _state: dict[WorkspaceID, CIBabysitterState] = PrivateAttr(default_factory=dict)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _shutdown_event: threading.Event = PrivateAttr(default_factory=threading.Event)

    def __init__(
        self,
        *,
        concurrency_group: ConcurrencyGroup,
        data_model_service: DataModelService,
        task_service: TaskService,
        git_repo_service: GitRepoService,
        pr_polling_service: PrPollingService,
    ) -> None:
        super().__init__(concurrency_group=concurrency_group)
        self._data_model_service = data_model_service
        self._task_service = task_service
        self._git_repo_service = git_repo_service
        self._pr_polling_service = pr_polling_service

    def start(self) -> None:
        # Note: in-memory state is rebuilt lazily on first poll per
        # workspace.
        self._pr_polling_service.add_observer(self._queue)
        self.concurrency_group.start_new_thread(
            target=self._consumer_loop,
            name="ci-babysitter-coordinator",
        )

    def stop(self) -> None:
        self._shutdown_event.set()
        self._pr_polling_service.remove_observer(self._queue)

    def set_paused(self, workspace_id: WorkspaceID, paused: bool) -> None:
        with self._lock:
            state = self._state.get(workspace_id)
            if state is None:
                project_id = self._lookup_workspace_project_id(workspace_id)
                if project_id is None:
                    logger.debug("set_paused: workspace {} not found", workspace_id)
                    return
                state = CIBabysitterState(workspace_id=workspace_id, project_id=project_id)
                self._state[workspace_id] = state
            state.paused = paused

    def get_state_snapshot(self, workspace_id: WorkspaceID) -> CIBabysitterWorkspaceStateView | None:
        with self._lock:
            state = self._state.get(workspace_id)
            if state is None:
                return None
            config = get_user_config_instance()
            return CIBabysitterWorkspaceStateView(
                paused=state.paused,
                retry_count=state.retry_count,
                retired=state.retired,
                at_cap=state.retry_count >= config.ci_babysitter.retry_cap,
            )

    def _consumer_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                item = self._queue.get(timeout=_CONSUMER_QUEUE_TIMEOUT_SECONDS)
            except Empty:
                continue
            if not isinstance(item, PrStatusInfo):
                continue
            try:
                self._handle_status(item)
            except Exception:
                logger.exception("CIBabysitterCoordinator: error handling PrStatusInfo for {}", item.workspace_id)

    def _handle_status(self, new: PrStatusInfo) -> None:
        with self._lock:
            state = self._state.get(new.workspace_id)
            if state is None:
                project_id = self._lookup_workspace_project_id(new.workspace_id)
                if project_id is None:
                    return
                state = CIBabysitterState(workspace_id=new.workspace_id, project_id=project_id)
                self._state[new.workspace_id] = state
            prev = state.prev_status
            # Transient "lost MR" gap: when the workspace's branch flips
            # (e.g. detached HEAD during a babysitter-driven rebase), the
            # polling service can't match the workspace to an MR and emits
            # pr_state="none". Treating this as a real transition would
            # clobber the coordinator's prev_status with an "unknown"
            # value, and the next poll that re-finds the MR would look
            # like a fresh False→True / running→failed transition.
            #
            # Suppress: don't update prev_status and don't dispatch.
            if new.pr_state == "none" and prev is not None and prev.pr_state != "none":
                return
            state.prev_status = new
            # Re-arm the merge-conflict dispatch dedup the moment we
            # observe an explicit "no conflict" state. This lets a
            # later re-conflict re-prompt as expected.
            if new.has_conflicts is False:
                state.last_dispatched_merge_conflict = False

        transitions = classify_transitions(prev, new)
        # Apply lifecycle transitions first so a same-cycle merge/close
        # retires the babysitter before any pipeline_failed / merge_conflict
        # in the same diff has a chance to dispatch a spurious prompt.
        for transition in transitions:
            if transition is Transition.PIPELINE_PASSED:
                with self._lock:
                    state.retry_count = 0
            elif transition in (Transition.MR_MERGED, Transition.MR_CLOSED):
                with self._lock:
                    state.retired = True
        for transition in transitions:
            if transition in (Transition.PIPELINE_FAILED, Transition.MERGE_CONFLICT):
                self._dispatch_prompt(state, transition, new)

    def _dispatch_prompt(self, state: CIBabysitterState, transition: Transition, new: PrStatusInfo) -> None:
        config = get_user_config_instance()
        with self._lock:
            if not config.ci_babysitter.enabled:
                return
            if state.retired:
                return
            if state.paused:
                return
            if state.retry_count >= config.ci_babysitter.retry_cap:
                return
            # Per-commit-id dedup: never resend the same prompt for the
            # same underlying state. The classifier already de-dupes
            # most cases, but the polling service can clear and refresh
            # state (e.g. branch flip during rebase) and emit what looks
            # like a fresh transition. This is the hard guarantee.
            if transition is Transition.PIPELINE_FAILED:
                if new.pipeline_id is not None and new.pipeline_id == state.last_dispatched_pipeline_failed_id:
                    logger.info(
                        "CIBabysitterCoordinator: suppressing duplicate PIPELINE_FAILED prompt for workspace={} pipeline_id={}",
                        state.workspace_id,
                        new.pipeline_id,
                    )
                    return
            elif transition is Transition.MERGE_CONFLICT:
                if state.last_dispatched_merge_conflict:
                    logger.info(
                        "CIBabysitterCoordinator: suppressing duplicate MERGE_CONFLICT prompt for workspace={}",
                        state.workspace_id,
                    )
                    return

        if transition is Transition.PIPELINE_FAILED:
            prompt_text = config.ci_babysitter.pipeline_failed_prompt
        elif transition is Transition.MERGE_CONFLICT:
            prompt_text = config.ci_babysitter.merge_conflict_prompt
        else:
            logger.error("CIBabysitterCoordinator: _dispatch_prompt called with non-actionable {}", transition)
            return

        task_id = self._ensure_babysitter_task(state)
        if task_id is None:
            return

        with self._data_model_service.open_transaction(RequestID()) as transaction:
            model = self._select_model_for_task(task_id, config, transaction)
            message = ChatInputUserMessage(
                text=prompt_text,
                message_id=AgentMessageID(),
                model_name=model,
                fast_mode=config.default_fast_mode,
                effort=EffortLevel(config.default_effort_level),
            )
            self._task_service.create_message(message, task_id, transaction)

        with self._lock:
            state.retry_count += 1
            if transition is Transition.PIPELINE_FAILED:
                state.last_dispatched_pipeline_failed_id = new.pipeline_id
            elif transition is Transition.MERGE_CONFLICT:
                state.last_dispatched_merge_conflict = True

    def _ensure_babysitter_task(self, state: CIBabysitterState) -> TaskID | None:
        with self._lock:
            existing_task_id = state.babysitter_task_id
        if existing_task_id is not None:
            with self._data_model_service.open_transaction(RequestID()) as transaction:
                task = self._task_service.get_task(existing_task_id, transaction)
            if task is not None and not task.is_deleted:
                return existing_task_id
            with self._lock:
                state.babysitter_task_id = None

        task_id = self._create_babysitter_task(state)
        if task_id is not None:
            with self._lock:
                state.babysitter_task_id = task_id
        return task_id

    def _create_babysitter_task(self, state: CIBabysitterState) -> TaskID | None:
        # v1 limitation: babysitter tasks are created under
        # ANONYMOUS_USER_REFERENCE. Sculptor is currently single-user
        # desktop where this matches the auth fallback; multi-user
        # support would need to inject the active user reference here.
        config = get_user_config_instance()
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            workspace = transaction.get_workspace(state.workspace_id)
            if workspace is None or workspace.is_deleted:
                logger.debug("Cannot create babysitter task: workspace {} missing", state.workspace_id)
                return None
            project = transaction.get_project(workspace.project_id)
            if project is None or project.is_deleted:
                logger.debug("Cannot create babysitter task: project {} missing", workspace.project_id)
                return None
            # Inherit the model from the workspace's most recent existing agent so the
            # babysitter matches the user's last-chosen model (and uses FakeClaude in
            # tests where the parent agent does). Falls back to default_llm only when
            # the workspace has no prior agent.
            model = self._select_model_for_workspace(state.workspace_id, workspace.project_id, config, transaction)
            with self._git_repo_service.open_local_user_git_repo_for_read(project) as repo:
                initial_commit_hash = repo.get_current_commit_hash()
            agent_config = self._select_chat_agent_config_for_workspace(
                state.workspace_id, workspace.project_id, transaction
            )
            task = Task(
                object_id=TaskID(),
                max_seconds=None,
                organization_reference=workspace.organization_reference,
                user_reference=ANONYMOUS_USER_REFERENCE,
                project_id=project.object_id,
                input_data=AgentTaskInputsV2(
                    agent_config=agent_config,
                    git_hash=initial_commit_hash,
                    system_prompt=project.default_system_prompt,
                    default_model=model,
                ),
                current_state=AgentTaskStateV2(
                    title=_BABYSITTER_TITLE,
                    workspace_id=state.workspace_id,
                ),
            )
            inserted = self._task_service.create_task(task, transaction)
        return inserted.object_id

    def _select_model_for_task(
        self, task_id: TaskID, config: UserConfig, transaction: DataModelTransaction
    ) -> LLMModel:
        task = self._task_service.get_task(task_id, transaction)
        if task is not None and isinstance(task.input_data, AgentTaskInputsV2) and task.input_data.default_model:
            return task.input_data.default_model
        return _model_from_config_or_fallback(config)

    def _workspace_agent_tasks_most_recent_first(
        self,
        workspace_id: WorkspaceID,
        project_id: ProjectID,
        transaction: DataModelTransaction,
    ) -> list[Task]:
        """The workspace's agent tasks, most-recent-first, excluding
        deleted/deleting tasks and the babysitter's own."""
        try:
            # pyrefly: ignore [missing-attribute]
            project_tasks = transaction.get_tasks_for_project(
                project_id=project_id,
                input_data_classes=(AgentTaskInputsV2,),
            )
        except Exception as exc:
            logger.debug("Could not list workspace tasks for inheritance: {}", exc)
            project_tasks = ()
        workspace_agent_tasks = [
            task
            for task in project_tasks
            if isinstance(task.current_state, AgentTaskStateV2)
            and task.current_state.workspace_id == workspace_id
            and isinstance(task.input_data, AgentTaskInputsV2)
            and not task.is_deleted
            and not task.is_deleting
            and task.current_state.title != _BABYSITTER_TITLE
        ]
        return sorted(workspace_agent_tasks, key=lambda t: t.created_at, reverse=True)

    def _select_chat_agent_config_for_workspace(
        self,
        workspace_id: WorkspaceID,
        project_id: ProjectID,
        transaction: DataModelTransaction,
    ) -> ClaudeCodeSDKAgentConfig | PiAgentConfig:
        """Inherit the chat-agent config type from the workspace's most recent
        chat agent, falling back to Claude.

        Terminal agents are skipped — the babysitter is always a chat agent
        (it is driven by prompts) and a terminal config carries nothing to
        inherit.
        """
        for task in self._workspace_agent_tasks_most_recent_first(workspace_id, project_id, transaction):
            input_data = task.input_data
            assert isinstance(input_data, AgentTaskInputsV2)
            if is_terminal_agent_config(input_data.agent_config):
                continue
            if isinstance(input_data.agent_config, PiAgentConfig):
                return PiAgentConfig()
            return ClaudeCodeSDKAgentConfig()
        return ClaudeCodeSDKAgentConfig()

    def _select_model_for_workspace(
        self,
        workspace_id: WorkspaceID,
        project_id: ProjectID,
        config: UserConfig,
        transaction: DataModelTransaction,
    ) -> LLMModel:
        # Most-recent-first; pick the first task that yields a usable model.
        # Task input_data.default_model is None when the agent was created in
        # waiting state and the model was first selected via a chat message;
        # in that case fall back to the model_name of the most recent
        # ChatInputUserMessage on that task.
        for task in self._workspace_agent_tasks_most_recent_first(workspace_id, project_id, transaction):
            input_data = task.input_data
            assert isinstance(input_data, AgentTaskInputsV2)
            # Terminal agents have no model concept — skip them explicitly so
            # an older chat agent's model wins.
            if is_terminal_agent_config(input_data.agent_config):
                continue
            if input_data.default_model is not None:
                return input_data.default_model
            inherited = self._latest_chat_model_for_task(task.object_id, transaction)
            if inherited is not None:
                return inherited
        return _model_from_config_or_fallback(config)

    def _latest_chat_model_for_task(self, task_id: TaskID, transaction: DataModelTransaction) -> LLMModel | None:
        try:
            messages = self._task_service.get_saved_messages_for_task(task_id, transaction)
        except Exception as exc:
            logger.debug("Could not load messages for task {} for model inheritance: {}", task_id, exc)
            return None
        for message in reversed(messages):
            if isinstance(message, ChatInputUserMessage) and message.model_name is not None:
                return message.model_name
        return None

    def _lookup_workspace_project_id(self, workspace_id: WorkspaceID) -> ProjectID | None:
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            workspace = transaction.get_workspace(workspace_id)
            if workspace is None:
                return None
            return workspace.project_id
