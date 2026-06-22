"""Drive pi's interactive /login and /logout inline, decoupled from the Task
machinery.

Settings is a global route; terminal-agent Tasks are workspace-scoped. So a small
PiLoginService owns ephemeral PTYs (LocalTerminalManager on a server-lifetime
concurrency group) running interactive pi, keyed by a login-session id. On teardown
it fires the live model-catalog refresh broadcast, since credentials may have
changed.

pi has no headless auth: /login and /logout are interactive TUI slash commands that
open pi's own provider selector (they take no provider argument). The PTY hosts a
real login shell, types the resolved pi binary path, then types the slash command.
The PTY MUST inherit the user's real environment and MUST NOT set
PI_CODING_AGENT_DIR, so pi writes the user's real ~/.pi/agent/auth.json.
"""

import threading
from enum import StrEnum
from pathlib import Path

from loguru import logger
from pydantic import PrivateAttr

from sculptor.database.models import AgentTaskInputsV2
from sculptor.foundation.common import generate_id
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RefreshModelsUserMessage
from sculptor.primitives.ids import RequestID
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction
from sculptor.services.task_service.api import TaskService
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    LocalTerminalManager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import write_launch_command


def broadcast_pi_models_refresh(task_service: TaskService, transaction: DataModelTransaction) -> int:
    """Fan a RefreshModelsUserMessage out to every active pi agent (fire-and-forget).

    A credential change (login/logout terminal close, paste-key write) is global —
    Settings has no current-agent concept — so every running pi agent re-reads
    auth.json and re-emits its catalog between turns. Returns the number of pi
    agents messaged. Non-pi agents are skipped: a Claude agent has no refresh
    handler and would just drop the message.
    """
    messaged_count = 0
    # get_active_tasks lives on the concrete task transaction; narrow from the
    # web-layer DataModelTransaction (mirrors the upsert_task call sites in app.py).
    assert isinstance(transaction, TaskAndDataModelTransaction)
    for task in transaction.get_active_tasks((AgentTaskInputsV2,)):
        if not isinstance(task.input_data, AgentTaskInputsV2):
            continue
        if not isinstance(task.input_data.agent_config, PiAgentConfig):
            continue
        task_service.create_message(
            message=RefreshModelsUserMessage(),
            task_id=task.object_id,
            transaction=transaction,
        )
        messaged_count += 1
    logger.info("Broadcast pi models refresh to {} agent(s)", messaged_count)
    return messaged_count


class PiLoginMode(StrEnum):
    """Which interactive pi flow the login PTY drives."""

    LOGIN = "login"
    LOGOUT = "logout"


def pi_login_terminal_id(login_id: str) -> str:
    """The terminal-manager registry key (== synthetic environment id) for a login session.

    Kept out of the agent:<task_id> namespace so it never collides with an agent
    terminal, and so stop_terminals_for_environment can act as a backstop.
    """
    return f"pi-login:{login_id}"


# How long to wait for pi's TUI to come up before typing the slash command. pi's
# own startup is slower than the shell prompt; the slash command is lost if typed
# too early. The frontend also shows on-screen guidance as a fallback.
_PI_TUI_READINESS_SECONDS = 2.0


class PiLoginService(Service):
    """Spawn / attach / tear down ephemeral pi login PTYs, decoupled from Tasks."""

    data_model_service: DataModelService
    task_service: TaskService

    _login_ids: set[str] = PrivateAttr(default_factory=set)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def spawn(self, mode: PiLoginMode, pi_binary_path: str, provider_id: str | None = None) -> str:
        """Spawn a login PTY, type the pi binary then the /login|/logout slash command.

        ``provider_id`` is on-screen guidance / refresh context only — pi's /login and
        /logout take no provider argument (the user picks in pi's own selector). The
        PTY inherits the user's environment (extra_env empty, no PI_CODING_AGENT_DIR,
        no api-key secrets) so pi writes the user's real ~/.pi/agent/auth.json.
        """
        del provider_id
        login_id = generate_id()
        terminal_id = pi_login_terminal_id(login_id)
        home = Path.home()
        manager = LocalTerminalManager(
            environment_id=terminal_id,
            workspace_path=home,
            working_directory=home,
            concurrency_group=self.concurrency_group,
            extra_env={},
            env_var_override=False,
            terminal_id=terminal_id,
        )
        manager.start()
        registered = register_terminal_manager(terminal_id, manager)
        if registered is not manager:
            # Lost a race (same login_id is nonce-unique, so this is vanishingly
            # unlikely) — drop our duplicate and reuse the winner.
            manager.stop()
        with self._lock:
            self._login_ids.add(login_id)

        write_launch_command(registered, pi_binary_path)
        slash_command = "/login" if mode == PiLoginMode.LOGIN else "/logout"
        write_launch_command(registered, slash_command, timeout_seconds=_PI_TUI_READINESS_SECONDS)
        logger.info("Spawned pi {} PTY (login_id={})", mode.value, login_id)
        return login_id

    def is_active(self, login_id: str) -> bool:
        """True while a login session's PTY is registered."""
        return get_terminal_manager(pi_login_terminal_id(login_id)) is not None

    def teardown(self, login_id: str) -> None:
        """Stop the login PTY and broadcast a model refresh (credentials may have changed).

        Idempotent: safe to call on Done, on WebSocket close, and again afterwards.
        """
        with self._lock:
            self._login_ids.discard(login_id)
        manager = unregister_terminal_manager(pi_login_terminal_id(login_id))
        if manager is not None:
            manager.stop()
        with self.data_model_service.open_transaction(RequestID()) as transaction:
            broadcast_pi_models_refresh(self.task_service, transaction)

    def stop(self) -> None:
        """Reap any login PTYs still registered at server shutdown."""
        with self._lock:
            login_ids = list(self._login_ids)
            self._login_ids.clear()
        for login_id in login_ids:
            manager = unregister_terminal_manager(pi_login_terminal_id(login_id))
            if manager is not None:
                manager.stop()
