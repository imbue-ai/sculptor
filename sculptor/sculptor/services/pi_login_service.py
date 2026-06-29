"""Drive pi's interactive /login and /logout inline, decoupled from the Task
machinery.

Settings is a global route; terminal-agent Tasks are workspace-scoped. So a small
PiLoginService owns ephemeral PTYs (LocalTerminalManager on a server-lifetime
concurrency group) running interactive pi, keyed by a login-session id.

pi has no headless auth: /login and /logout are interactive TUI slash commands. The
PTY hosts a real login shell, types the resolved pi binary path, then drives pi's own
flow with keystrokes (a carriage return submits — pi's raw-mode TUI ignores a bare
newline). For /logout the chosen provider is known up front (the user clicked its
Disconnect), so the service fuzzy-filters pi's "select provider" list to that provider
and confirms, fully automatically. For /login the service only opens the prompt; the
user picks the provider and enters credentials in the terminal.

Completion is observed against auth.json itself (the credential store pi writes): a
background poll watches for the chosen provider's key to disappear (/logout) or appear
(/login). The modal polls is_completed to auto-close, and teardown broadcasts a live
model-catalog refresh, so the change is perceived by running pi agents without a
restart. The PTY MUST inherit the user's real environment and MUST NOT set
PI_CODING_AGENT_DIR, so pi reads/writes the user's real ~/.pi/agent/auth.json.
"""

import threading
import time
from enum import StrEnum
from pathlib import Path
from typing import Callable

from loguru import logger
from pydantic import PrivateAttr

from sculptor.agents.pi_agent.authenticated_providers import read_auth_json_provider_ids
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
    # web-layer DataModelTransaction.
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


# pi's interactive TUI has rendered once one of these appears in the PTY stream, so a
# slash command is not typed into a half-initialized shell.
_PI_READY_MARKERS: tuple[bytes, ...] = (b"ctrl+", b"\xe2\x80\xa2", b"interrupt")

# pi's /logout provider list prints this header; matched before fuzzy-filtering.
_PI_LOGOUT_SELECTOR_MARKER = b"Select provider to logout"

# A carriage return — the Return key — submits in pi's raw-mode TUI (a bare newline is
# a literal newline in the input box).
_PI_SUBMIT = b"\r"

# How long to wait for pi's TUI to come up before typing a slash command. The real
# login pi runs against the user's providers and may fetch a catalog at startup.
_PI_READY_TIMEOUT_SECONDS = 20.0

# How long to wait for the /logout selector to render after submitting the slash.
_PI_SELECTOR_TIMEOUT_SECONDS = 8.0

# Let pi's fuzzy filter settle on the typed provider id before confirming the choice.
_PI_FILTER_SETTLE_SECONDS = 0.5

# Cadence / cap of the auth.json completion poll. The cap bounds an idle login the
# user never completes; the poll also exits early once the PTY is torn down.
_COMPLETION_POLL_INTERVAL_SECONDS = 0.7
_COMPLETION_POLL_TIMEOUT_SECONDS = 600.0


class _OutputAccumulator:
    """Subscribe to a terminal's output and wait for content markers to appear.

    Drives the keystroke sequence off the rendered screen rather than fixed sleeps:
    the slash command waits for pi to be interactive, and the provider filter waits
    for pi's selector to render.
    """

    def __init__(self, manager: LocalTerminalManager) -> None:
        self._manager = manager
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._changed = threading.Event()
        snapshot = manager.subscribe(self._on_output)
        with self._lock:
            self._buffer.extend(snapshot)

    def _on_output(self, data: bytes) -> None:
        with self._lock:
            self._buffer.extend(data)
        self._changed.set()

    def wait_for(self, predicate: Callable[[bytes], bool], timeout_seconds: float) -> bool:
        """Block until ``predicate`` holds over all output so far, or until timeout."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            with self._lock:
                snapshot = bytes(self._buffer)
            if predicate(snapshot):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._changed.clear()
            self._changed.wait(min(remaining, 0.2))

    def close(self) -> None:
        self._manager.remove_output_callback(self._on_output)


def _login_change_observed(mode: PiLoginMode, provider_id: str | None, baseline: set[str], current: set[str]) -> bool:
    """True once auth.json reflects the session's intended credential change.

    /logout (always provider-scoped — Disconnect targets an auth.json-backed provider):
    that provider's key has disappeared. /login: the chosen provider's key has appeared,
    or, for the provider-agnostic empty-state CTA, any new provider key has appeared.
    """
    if mode == PiLoginMode.LOGOUT:
        return provider_id is not None and provider_id in baseline and provider_id not in current
    if provider_id is not None:
        return provider_id in current and provider_id not in baseline
    return bool(current - baseline)


def _drive_pi_session(
    accumulator: _OutputAccumulator,
    manager: LocalTerminalManager,
    pi_binary_path: str,
    mode: PiLoginMode,
    provider_id: str | None,
) -> None:
    """Launch pi in the PTY and drive its /login or /logout flow.

    Logout is fully automatic: submit /logout, wait for pi's provider list, fuzzy-filter
    to the chosen provider id, and confirm. Login only opens the prompt — the user picks
    the provider and supplies credentials in the terminal. The slash is retried once for
    logout, since a keystroke typed before pi is interactive can be dropped.
    """
    # Launch pi as a shell job (the shell is cooked-mode, so a newline submits).
    write_launch_command(manager, pi_binary_path)

    # Best-effort: wait for pi's TUI before typing. The logout retry below is the real
    # safety net for a too-early slash; login has no auto-steps to lose.
    if not accumulator.wait_for(lambda b: any(m in b for m in _PI_READY_MARKERS), _PI_READY_TIMEOUT_SECONDS):
        logger.debug("pi TUI readiness marker not seen; driving the slash command anyway")

    slash = b"/login" if mode == PiLoginMode.LOGIN else b"/logout"
    manager.write(slash + _PI_SUBMIT)

    if mode != PiLoginMode.LOGOUT or provider_id is None:
        return

    if not accumulator.wait_for(lambda b: _PI_LOGOUT_SELECTOR_MARKER in b, _PI_SELECTOR_TIMEOUT_SECONDS):
        # The first slash was likely dropped (typed before pi was ready) — submit once
        # more. Guarded on the marker's absence, so a rendered selector is never typed into.
        manager.write(slash + _PI_SUBMIT)
        if not accumulator.wait_for(lambda b: _PI_LOGOUT_SELECTOR_MARKER in b, _PI_SELECTOR_TIMEOUT_SECONDS):
            logger.warning("pi /logout selector never rendered; leaving the session for manual completion")
            return

    # Fuzzy-filter pi's list to the chosen provider, then confirm: typing the provider id
    # narrows to its row, and Return removes its stored key.
    manager.write(provider_id.encode())
    time.sleep(_PI_FILTER_SETTLE_SECONDS)
    manager.write(_PI_SUBMIT)


class PiLoginService(Service):
    """Spawn / attach / tear down ephemeral pi login PTYs, decoupled from Tasks."""

    data_model_service: DataModelService
    task_service: TaskService

    _login_ids: set[str] = PrivateAttr(default_factory=set)
    # Login sessions whose intended credential change has been observed in auth.json.
    # Read by the modal's status poll to auto-close; never pruned (bounded by total
    # logins in a server's lifetime).
    _completed_ids: set[str] = PrivateAttr(default_factory=set)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def spawn(self, mode: PiLoginMode, pi_binary_path: str, provider_id: str | None = None) -> str:
        """Spawn a login PTY and drive pi's /login|/logout, polling auth.json for completion.

        ``provider_id`` is the row to filter to in pi's /logout selector and the key to
        watch for in auth.json; it is None only for the empty-state "authenticate a
        provider" CTA, where pi's own selector picks. The PTY inherits the user's
        environment (extra_env empty, no PI_CODING_AGENT_DIR, no api-key secrets) so pi
        reads/writes the user's real ~/.pi/agent/auth.json.
        """
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
            # Lost a registration race — drop our duplicate and reuse the winner.
            manager.stop()
        with self._lock:
            self._login_ids.add(login_id)

        # Snapshot auth.json before driving, so completion is judged against the change
        # this session makes rather than whatever was already present.
        baseline = read_auth_json_provider_ids()
        threading.Thread(
            target=self._drive_and_close,
            args=(registered, pi_binary_path, mode, provider_id),
            name=f"pi-login-drive:{login_id}",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._poll_for_completion,
            args=(login_id, mode, provider_id, baseline),
            name=f"pi-login-poll:{login_id}",
            daemon=True,
        ).start()
        logger.info("Spawned pi {} PTY (login_id={}, provider={})", mode.value, login_id, provider_id)
        return login_id

    def _drive_and_close(
        self, manager: LocalTerminalManager, pi_binary_path: str, mode: PiLoginMode, provider_id: str | None
    ) -> None:
        """Run the keystroke driver on a background thread, always releasing the subscription."""
        accumulator = _OutputAccumulator(manager)
        try:
            _drive_pi_session(accumulator, manager, pi_binary_path, mode, provider_id)
        except Exception as exc:  # noqa: BLE001 - best-effort; the session may be torn down mid-sequence
            logger.debug("pi login keystroke driver stopped early: {}", exc)
        finally:
            accumulator.close()

    def _poll_for_completion(
        self, login_id: str, mode: PiLoginMode, provider_id: str | None, baseline: set[str]
    ) -> None:
        """Watch auth.json until the session's credential change lands, then mark it completed."""
        deadline = time.monotonic() + _COMPLETION_POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if not self.is_active(login_id):
                return  # torn down (Done / closed / cancelled) before completing
            if _login_change_observed(mode, provider_id, baseline, read_auth_json_provider_ids()):
                with self._lock:
                    self._completed_ids.add(login_id)
                logger.info("pi {} completed for login_id={} (provider={})", mode.value, login_id, provider_id)
                return
            time.sleep(_COMPLETION_POLL_INTERVAL_SECONDS)

    def is_active(self, login_id: str) -> bool:
        """True while a login session's PTY is registered."""
        return get_terminal_manager(pi_login_terminal_id(login_id)) is not None

    def is_completed(self, login_id: str) -> bool:
        """True once the session's intended credential change was observed in auth.json."""
        with self._lock:
            return login_id in self._completed_ids

    def teardown(self, login_id: str) -> None:
        """Stop the login PTY and broadcast a model refresh (credentials may have changed).

        Idempotent: safe to call on Done, on WebSocket close, and again afterwards.
        Done and WebSocket-close both fire for a single session, so only the call
        that actually unregisters the PTY broadcasts — later no-op teardowns skip it,
        keeping the credential change to one refresh fan-out.
        """
        with self._lock:
            self._login_ids.discard(login_id)
        manager = unregister_terminal_manager(pi_login_terminal_id(login_id))
        if manager is None:
            return
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
