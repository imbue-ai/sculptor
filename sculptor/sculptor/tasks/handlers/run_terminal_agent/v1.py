"""The terminal-agent task handler.

Terminal agents have no chat: the handler acquires the workspace
environment, spawns an agent-scoped PTY running a login shell in the
workspace code directory, and then simply keeps the task RUNNING for the
agent's lifetime while periodically refreshing the workspace diff. There is
no message-queue subscription, no title generation, no artifact sync, no
snapshotting — Sculptor never parses the shell's output.

The task ends only via shutdown/archive/delete (`UserPausedTaskError`, which
the task-service runner maps to QUEUED — or DELETED when archiving). A shell
self-exit does NOT end the task: the WebSocket route respawns the PTY on the
next connection (architecture §3).
"""

from __future__ import annotations

import datetime
from typing import Any
from typing import Callable
from typing import cast

from loguru import logger

from imbue_core.concurrency_group import ConcurrencyExceptionGroup
from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.event_utils import ReadOnlyEvent
from imbue_core.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentReleasedRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentTypes
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.tasks.handlers.run_agent.setup import load_initial_task_state
from sculptor.tasks.handlers.run_agent.v1 import _on_exception
from sculptor.tasks.handlers.run_terminal_agent.diff_refresh import PeriodicDiffRefresher
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import AgentTerminalConfig
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import create_agent_terminal
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import register_agent_terminal_config
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import stop_agent_terminal
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import unregister_agent_terminal_config
from sculptor.utils.build import get_sculpt_bin_dir

# it will take at most this much time to notice a shutdown request
_POLL_SECONDS: float = 1.0
_DIFF_REFRESH_INTERVAL_SECONDS: float = 3.0


def run_terminal_agent_task_v1(
    task_data: AgentTaskInputsV2,
    task: Task,
    services: ServiceCollectionForTask,
    task_deadline: datetime.datetime | None,
    settings: SculptorSettings,
    concurrency_group: ConcurrencyGroup,
    shutdown_event: ReadOnlyEvent,
    on_started: Callable[[], None] | None = None,
) -> Callable[[DataModelTransaction], Any] | None:
    """Run a terminal agent: acquire the environment, own a PTY, stay RUNNING.

    Mirrors `run_agent_task_v1`'s setup and error contract (environment
    acquisition, Acquired/Released runner messages, shutdown → re-queue) but
    has none of the chat machinery.
    """
    user_reference = task.user_reference
    task_id = task.object_id

    root_progress_handle = RootProgressHandle()

    try:
        with logger.contextualize(task_id=task_id):
            logger.debug("running terminal agent task {} for user {}", task_id, user_reference)
            task_state, project = load_initial_task_state(services, task)

            with (
                concurrency_group.make_concurrency_group(
                    name=f"run_terminal_agent_v1_{task_id}"
                ) as environment_concurrency_group,
                services.workspace_service.agent_environment_context(
                    project=project,
                    workspace_id=task_state.workspace_id,
                    task_id=task.object_id,
                    concurrency_group=environment_concurrency_group,
                    root_progress_handle=root_progress_handle,
                    shutdown_event=shutdown_event,
                ) as environment,
            ):
                # Emit EnvironmentAcquiredRunnerMessage — the run-start anchor
                # the terminal status driver keys on (architecture §5).
                assert isinstance(environment, LocalAgentExecutionEnvironment)
                underlying_env = cast(EnvironmentTypes, environment.underlying_environment)
                with services.data_model_service.open_task_transaction() as transaction:
                    services.task_service.create_message(
                        EnvironmentAcquiredRunnerMessage(environment=underlying_env),
                        task_id=task.object_id,
                        transaction=transaction,
                    )
                try:
                    # Signal the frontend that a diff is available without
                    # generating it now (matches the chat handler).
                    services.workspace_service.mark_workspace_diff_stale(
                        task_state.workspace_id,
                    )
                    _run_terminal_agent_in_environment(
                        task=task,
                        task_state=task_state,
                        project=project,
                        underlying_env=underlying_env,
                        environment_concurrency_group=environment_concurrency_group,
                        services=services,
                        settings=settings,
                        shutdown_event=shutdown_event,
                        on_started=on_started,
                    )
                finally:
                    with services.data_model_service.open_task_transaction() as transaction:
                        services.task_service.create_message(
                            EnvironmentReleasedRunnerMessage(),
                            task_id=task.object_id,
                            transaction=transaction,
                        )
    # handle ConcurrencyExceptionGroup as a general exception
    except ConcurrencyExceptionGroup as e:
        _on_exception(e, task_id, user_reference, services, shutdown_event)
    # all other exceptions should be handled and turned into task failures
    except Exception as e:
        _on_exception(e, task_id, user_reference, services, shutdown_event)
    return None


def _run_terminal_agent_in_environment(
    task: Task,
    task_state: AgentTaskStateV2,
    project: Project,
    underlying_env: EnvironmentTypes,
    environment_concurrency_group: ConcurrencyGroup,
    services: ServiceCollectionForTask,
    settings: SculptorSettings,
    shutdown_event: ReadOnlyEvent,
    on_started: Callable[[], None] | None,
) -> None:
    """Spawn the agent PTY and idle until shutdown, ticking the diff refresher.

    Never returns normally (a normal return would mark the task SUCCEEDED and
    it would come back as a dead tab after restart): exits only by raising
    `UserPausedTaskError` on shutdown, or propagating an unexpected error.
    """
    # The PTY env: same SCULPT_* vars the workspace terminal gets, plus
    # SCULPT_AGENT_ID so `sculpt signal …` can identify this agent. The pty
    # scrubs inherited SCULPT_*/SCULPTOR_* vars and re-applies extra_env (PATH
    # is prepended), so everything must go through extra_env.
    extra_env: dict[str, str] = {
        "SCULPT_API_PORT": str(settings.BACKEND_PORT),
        "SCULPT_WORKSPACE_ID": str(task_state.workspace_id),
        "SCULPT_PROJECT_ID": str(project.object_id),
        "SCULPT_AGENT_ID": str(task.object_id),
        "PATH": str(get_sculpt_bin_dir()),
    }
    register_agent_terminal_config(
        task.object_id,
        AgentTerminalConfig(
            environment_id=str(underlying_env.environment_id),
            workspace_path=underlying_env.get_workspace_path(),
            working_directory=underlying_env.get_working_directory(),
            # The environment group, NOT the server-lifetime group workspace
            # terminals use: the agent PTY must not outlive this handler.
            concurrency_group=environment_concurrency_group,
            extra_env=extra_env,
            # Private LocalEnvironment attrs, matching what its own
            # start_terminal_manager reads for workspace terminals.
            env_var_override=underlying_env._env_var_override,
            sculptor_folder=underlying_env._sculptor_folder,
        ),
    )
    try:
        # Eager spawn. A failure is non-fatal: the WS route retries on demand.
        if create_agent_terminal(task.object_id) is None:
            logger.info("Failed to eagerly start terminal for agent {}; will retry on demand", task.object_id)

        if on_started is not None:
            on_started()

        refresher = PeriodicDiffRefresher(
            working_directory=underlying_env.get_working_directory(),
            on_change=lambda: services.workspace_service.maybe_refresh_workspace_diff(task_state.workspace_id),
            interval_seconds=_DIFF_REFRESH_INTERVAL_SECONDS,
        )
        # Idle until shutdown. A dead shell does NOT exit the loop — the
        # terminal is respawnable; the task ends only via shutdown/archive/delete.
        while True:
            if shutdown_event.wait(timeout=_POLL_SECONDS):
                raise UserPausedTaskError()
            if environment_concurrency_group.is_shutting_down():
                raise UserPausedTaskError()
            refresher.tick()
    finally:
        stop_agent_terminal(task.object_id)
        unregister_agent_terminal_config(task.object_id)
