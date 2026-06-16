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
import time
from dataclasses import dataclass
from queue import Empty
from queue import Queue

from loguru import logger
from pydantic import PrivateAttr

from sculptor.config.user_config import BabysitterAgentClaude
from sculptor.config.user_config import BabysitterAgentPi
from sculptor.config.user_config import BabysitterAgentRegistered
from sculptor.config.user_config import UserConfig
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalStatusSignal
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
from sculptor.services.terminal_agent_registry.registry import get_registration
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import EffortLevel
from sculptor.state.messages import LLMModel
from sculptor.state.messages import Message
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.derived import PrStatusInfo
from sculptor.web.derived import scan_terminal_signal_state
from sculptor.web.pr_polling_service import PrPollingService
from sculptor.web.terminal_input import TerminalDeliveryResult
from sculptor.web.terminal_input import deliver_prompt_to_terminal_agent

_BABYSITTER_TITLE = "CI Babysitter"
_CONSUMER_QUEUE_TIMEOUT_SECONDS = 1.0

# Persistent disabled reasons surfaced when the MRU is a terminal that can't
# receive automated prompts, or when a pinned harness is no longer available.
# Defined here so Phase 4's proactive surfacing and the tests use identical copy.
_DISABLED_REASON_MRU_NON_DRIVEABLE = "Your most-recent agent is a terminal that can't receive automated prompts, so the CI Babysitter can't act here. Pick a specific agent in CI Babysitter settings, or use a chat or prompt-enabled terminal agent."
_DISABLED_REASON_PINNED_UNAVAILABLE = (
    "The CI Babysitter's selected agent is no longer available. Choose another in CI Babysitter settings."
)
# Transient (runtime) reason: the most recent terminal drive couldn't reach the
# program's prompt. Cleared by the next successful drive or when the CI cycle
# resolves; the attempt still counts against retry_cap.
_TRANSIENT_REASON_UNREACHABLE = "Couldn't reach the terminal agent's prompt; will retry on the next failure."

# A freshly-spawned terminal program needs a moment to reach its prompt. The
# worker subscribes to the real readiness signal rather than guessing with
# sleeps; this backstop only bounds the never-ready pathology. Overridable so
# unit tests run fast.
_TERMINAL_READINESS_BACKSTOP_SECONDS = 30.0
_TERMINAL_READINESS_POLL_SECONDS = 0.5


@dataclass(frozen=True)
class ChatAgent:
    """Resolution result: drive a chat agent via the message queue."""

    config: ClaudeCodeSDKAgentConfig | PiAgentConfig


@dataclass(frozen=True)
class DriveableTerminal:
    """Resolution result: drive a registered, opt-in terminal agent's PTY."""

    config: RegisteredTerminalAgentConfig


@dataclass(frozen=True)
class Disabled:
    """Resolution result: the babysitter cannot act; surface ``reason``.

    ``transient`` distinguishes a persistent reason (MRU non-driveable /
    pinned-unavailable) from a runtime one (set in Phase 3). Only persistent
    reasons arise from the resolver.
    """

    reason: str
    transient: bool = False


ResolvedBabysitterAgent = ChatAgent | DriveableTerminal | Disabled


def _driveable_terminal_from_registration(registration_id: str) -> DriveableTerminal | None:
    """A DriveableTerminal stamped from the *live* registration, or None when the
    registration is gone or has revoked automated-prompt opt-in.

    Re-reads the registration from disk so a since-revoked opt-in (or a stale
    stamped config) is never trusted. Fields are copied the same way
    ``_agent_config_for_request`` stamps a creation request (app.py).
    """
    registration = get_registration(registration_id)
    if registration is None or not registration.accepts_automated_prompts:
        return None
    return DriveableTerminal(
        RegisteredTerminalAgentConfig(
            registration_id=registration.registration_id,
            display_name=registration.display_name,
            launch_command=registration.launch_command,
            resume_command_template=registration.resume_command_template,
            accepts_automated_prompts=registration.accepts_automated_prompts,
        )
    )


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
    # Why the babysitter is inert for this workspace, if it is. Persistent
    # reasons (MRU non-driveable / pinned harness unavailable) are recomputed on
    # every read so they appear before any failure and self-heal; the transient
    # terminal-unreachable reason is surfaced from stored state.
    disabled_reason: str | None = None
    # True when disabled_reason is the transient terminal-unreachable reason (the
    # babysitter will retry on the next failure), False for a persistent reason
    # (the babysitter is inert until the user changes the MRU/config). Lets the
    # UI keep the pause toggle usable for transient reasons but inert otherwise.
    disabled_reason_is_transient: bool = False


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
        config = get_user_config_instance()
        with self._lock:
            state = self._state.get(workspace_id)
            if state is None:
                return None
            paused = state.paused
            retry_count = state.retry_count
            retired = state.retired
            project_id = state.project_id
            transient_reason = state.transient_disabled_reason

        # Recompute the persistent reason on every read (outside the lock — it
        # does DB I/O) so it appears before any failure and self-heals when the
        # user changes the MRU or fixes the registration.
        disabled_reason: str | None = None
        disabled_reason_is_transient = False
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            resolved = self._resolve_babysitter_agent(workspace_id, project_id, config, transaction)
        if isinstance(resolved, Disabled) and not resolved.transient:
            disabled_reason = resolved.reason
        elif transient_reason is not None:
            # Only a driveable terminal accrues a transient reason, so persistent
            # and transient are mutually exclusive in practice; persistent wins.
            disabled_reason = transient_reason
            disabled_reason_is_transient = True

        return CIBabysitterWorkspaceStateView(
            paused=paused,
            retry_count=retry_count,
            retired=retired,
            at_cap=retry_count >= config.ci_babysitter.retry_cap,
            disabled_reason=disabled_reason,
            disabled_reason_is_transient=disabled_reason_is_transient,
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
                    # The transient reason reflects a one-off hiccup; once the
                    # cycle resolves it no longer applies.
                    state.transient_disabled_reason = None
            elif transition in (Transition.MR_MERGED, Transition.MR_CLOSED):
                with self._lock:
                    state.retired = True
                    state.transient_disabled_reason = None
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

        # Resolve which agent to drive (MRU or a pinned harness). All policy
        # gates above stay here; only delivery differs per agent kind, via the
        # single deliver_prompt_to_agent seam below.
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            resolved = self._resolve_babysitter_agent(state.workspace_id, state.project_id, config, transaction)
        if isinstance(resolved, Disabled):
            # No spawn, no task. Surfacing the reason to the UI is Phase 4,
            # which recomputes persistent reasons on every status read.
            logger.info(
                "CIBabysitterCoordinator: not dispatching for workspace={} — {}",
                state.workspace_id,
                resolved.reason,
            )
            return

        task_id = self._ensure_babysitter_task(state, resolved)
        if task_id is None:
            return

        if isinstance(resolved, DriveableTerminal):
            # Offload the PTY drive to a worker so the single-threaded consumer
            # loop stays responsive to every other workspace's PR updates (the
            # readiness wait added in Task 3.2 can block for seconds).
            with self._lock:
                if state.terminal_drive_in_progress:
                    # Coalesce: the in-flight worker will write the prompt. Don't
                    # start a racing worker or bump bookkeeping for this cycle.
                    logger.info(
                        "CIBabysitterCoordinator: terminal drive already in progress for workspace={}, coalescing",
                        state.workspace_id,
                    )
                    return
                state.terminal_drive_in_progress = True
            self.concurrency_group.start_new_thread(
                target=self._run_terminal_drive,
                args=(state, task_id, prompt_text, config),
                name="ci-babysitter-terminal-drive",
            )
        else:
            with self._data_model_service.open_transaction(RequestID()) as transaction:
                task = self._task_service.get_task(task_id, transaction)
            if task is None:
                return
            self.deliver_prompt_to_agent(task, prompt_text, config)

        with self._lock:
            # The attempt counts against retry_cap whether or not the terminal
            # worker ultimately delivers (REQ-DRIVE-4).
            state.retry_count += 1
            if transition is Transition.PIPELINE_FAILED:
                state.last_dispatched_pipeline_failed_id = new.pipeline_id
            elif transition is Transition.MERGE_CONFLICT:
                state.last_dispatched_merge_conflict = True

    def _run_terminal_drive(
        self, state: CIBabysitterState, task_id: TaskID, prompt_text: str, config: UserConfig
    ) -> None:
        """Worker: drive a registered terminal agent's PTY off the consumer loop.

        Sets the transient disabled-reason on a failed write and clears it on
        success; always clears the in-progress flag so a crash can't park the
        workspace with the guard stuck on.
        """
        try:
            with self._data_model_service.open_transaction(RequestID()) as transaction:
                task = self._task_service.get_task(task_id, transaction)
            if task is None:
                return
            if not self._wait_for_terminal_ready(task_id):
                # Never-ready within the backstop (REQ-DRIVE-4): give up for this
                # cycle only — no write — and retry on the next CI failure. The
                # retry was already counted at dispatch.
                with self._lock:
                    state.transient_disabled_reason = _TRANSIENT_REASON_UNREACHABLE
                return
            result = self.deliver_prompt_to_agent(task, prompt_text, config)
            with self._lock:
                if result is TerminalDeliveryResult.DELIVERED:
                    state.transient_disabled_reason = None
                else:
                    state.transient_disabled_reason = _TRANSIENT_REASON_UNREACHABLE
        except Exception as exc:
            logger.error(
                "CIBabysitterCoordinator: terminal drive failed for workspace={}: {}", state.workspace_id, exc
            )
        finally:
            with self._lock:
                state.terminal_drive_in_progress = False

    def _wait_for_terminal_ready(self, task_id: TaskID) -> bool:
        """Block until the terminal program is at its prompt, or the backstop fires.

        Subscribes to the task's message stream (seeded with current messages, so
        an already-idle program is detected immediately) and returns True the
        instant ``scan_terminal_signal_state`` reports the run started and the
        latest signal is IDLE/WAITING. Returns False if the never-ready backstop
        elapses or the coordinator is shutting down. Guard 2 re-checks readiness
        at write time, so a stale signal still can't slip a write through.
        """
        deadline = time.monotonic() + _TERMINAL_READINESS_BACKSTOP_SECONDS
        messages: list[Message] = []
        with self._task_service.subscribe_to_task(task_id) as queue:
            while True:
                run_started, latest_signal = scan_terminal_signal_state(messages)
                if run_started and latest_signal in (TerminalStatusSignal.IDLE, TerminalStatusSignal.WAITING):
                    return True
                if self._shutdown_event.is_set() or time.monotonic() >= deadline:
                    return False
                try:
                    messages.append(queue.get(timeout=_TERMINAL_READINESS_POLL_SECONDS))
                except Empty:
                    continue
        return False  # unreachable: the loop only exits via return

    def _resolve_babysitter_agent(
        self,
        workspace_id: WorkspaceID,
        project_id: ProjectID,
        config: UserConfig,
        transaction: DataModelTransaction,
    ) -> ResolvedBabysitterAgent:
        """Decide which agent the babysitter drives for this workspace.

        Either a pinned harness (Claude / Pi / a specific registered terminal)
        or the workspace's single most-recently-used agent type. MRU never skips
        the most-recent agent to reach an older one (REQ-AGENT-2).
        """
        choice = config.ci_babysitter.agent
        if isinstance(choice, BabysitterAgentClaude):
            return ChatAgent(ClaudeCodeSDKAgentConfig())
        if isinstance(choice, BabysitterAgentPi):
            # A pinned Pi while Pi is disabled goes Disabled — no silent fallback
            # (REQ-SET-5). This differs from an MRU Pi, which falls back to Claude.
            if config.enable_pi_agent:
                return ChatAgent(PiAgentConfig())
            return Disabled(_DISABLED_REASON_PINNED_UNAVAILABLE)
        if isinstance(choice, BabysitterAgentRegistered):
            driveable = _driveable_terminal_from_registration(choice.registration_id)
            if driveable is not None:
                return driveable
            return Disabled(_DISABLED_REASON_PINNED_UNAVAILABLE)

        # MRU: take the single most-recent non-babysitter task; do NOT iterate
        # past it (REQ-AGENT-2 forbids skipping a terminal MRU to reach an older
        # chat agent).
        tasks = self._workspace_agent_tasks_most_recent_first(workspace_id, project_id, transaction)
        if not tasks:
            return ChatAgent(ClaudeCodeSDKAgentConfig())  # REQ-AGENT-6: no prior agent → Claude
        input_data = tasks[0].input_data
        assert isinstance(input_data, AgentTaskInputsV2)
        agent_config = input_data.agent_config
        if isinstance(agent_config, ClaudeCodeSDKAgentConfig):
            return ChatAgent(ClaudeCodeSDKAgentConfig())
        if isinstance(agent_config, PiAgentConfig):
            # MRU is a best-effort inherit: an MRU Pi while Pi is disabled should
            # not brick the babysitter — fall back to Claude.
            if config.enable_pi_agent:
                return ChatAgent(PiAgentConfig())
            return ChatAgent(ClaudeCodeSDKAgentConfig())
        if isinstance(agent_config, RegisteredTerminalAgentConfig):
            # Re-resolve against the live registration: the task's stamped
            # accepts_automated_prompts may be stale.
            driveable = _driveable_terminal_from_registration(agent_config.registration_id)
            if driveable is not None:
                return driveable
            return Disabled(_DISABLED_REASON_MRU_NON_DRIVEABLE)
        # plain TerminalAgentConfig (a bare shell) — never driveable.
        return Disabled(_DISABLED_REASON_MRU_NON_DRIVEABLE)

    def deliver_prompt_to_agent(self, task: Task, prompt_text: str, config: UserConfig) -> TerminalDeliveryResult:
        """The single delivery seam: how a prompt physically reaches the agent.

        Dispatches on the task's own agent config. Chat agents receive a queued
        ChatInputUserMessage (today's flow, verbatim); registered terminal agents
        get a guarded PTY write via the shared Task 1.1 helper.
        """
        input_data = task.input_data
        assert isinstance(input_data, AgentTaskInputsV2)
        if isinstance(input_data.agent_config, RegisteredTerminalAgentConfig):
            # Single guarded write. Called from the terminal-drive worker
            # (Task 3.1) so it never blocks the consumer loop. For a freshly
            # created task the program usually hasn't reached its prompt yet, so
            # this returns NOT_AT_PROMPT until Task 3.2 adds the readiness wait.
            return deliver_prompt_to_terminal_agent(task, prompt_text, submit=True, task_service=self._task_service)
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            model = self._select_model_for_task(task.object_id, config, transaction)
            message = ChatInputUserMessage(
                text=prompt_text,
                message_id=AgentMessageID(),
                model_name=model,
                fast_mode=config.default_fast_mode,
                effort=EffortLevel(config.default_effort_level),
            )
            self._task_service.create_message(message, task.object_id, transaction)
        return TerminalDeliveryResult.DELIVERED

    def _ensure_babysitter_task(
        self, state: CIBabysitterState, resolved: ChatAgent | DriveableTerminal
    ) -> TaskID | None:
        with self._lock:
            existing_task_id = state.babysitter_task_id
        if existing_task_id is not None:
            with self._data_model_service.open_transaction(RequestID()) as transaction:
                task = self._task_service.get_task(existing_task_id, transaction)
            if task is not None and not task.is_deleted:
                return existing_task_id
            with self._lock:
                state.babysitter_task_id = None

        task_id = self._create_babysitter_task(state, resolved.config)
        if task_id is not None:
            with self._lock:
                state.babysitter_task_id = task_id
        return task_id

    def _create_babysitter_task(
        self,
        state: CIBabysitterState,
        agent_config: ClaudeCodeSDKAgentConfig | PiAgentConfig | RegisteredTerminalAgentConfig,
    ) -> TaskID | None:
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
