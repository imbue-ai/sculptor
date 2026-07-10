"""Unit tests for PiLoginService and broadcast_pi_models_refresh.

The interactive /login round-trip (pi actually writing auth.json) is covered by the
real_pi conformance tests; here we cover the service lifecycle (spawn registers a
PTY, teardown stops it and broadcasts), the keystroke driver's logout selector
sequence, the auth.json completion judgement, and the broadcast's pi-only targeting —
all with a stand-in terminal manager.
"""

from typing import Callable
from typing import cast
from unittest.mock import MagicMock

import pytest

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RefreshModelsUserMessage
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.services import pi_login_service as pi_login_service_module
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction
from sculptor.services.pi_login_service import PiLoginMode
from sculptor.services.pi_login_service import PiLoginService
from sculptor.services.pi_login_service import _OutputAccumulator
from sculptor.services.pi_login_service import _drive_pi_session
from sculptor.services.pi_login_service import _login_change_observed
from sculptor.services.pi_login_service import broadcast_pi_models_refresh
from sculptor.services.pi_login_service import pi_login_terminal_id
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


def _make_agent_task(agent_config: PiAgentConfig | ClaudeCodeSDKAgentConfig) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=UserReference("anonymous"),
        organization_reference=OrganizationReference("anonymous"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(agent_config=agent_config, git_hash="x", system_prompt=None),
        current_state=AgentTaskStateV2(workspace_id=WorkspaceID()),
    )


def test_broadcast_pi_models_refresh_targets_only_pi_agents() -> None:
    pi_task = _make_agent_task(PiAgentConfig())
    claude_task = _make_agent_task(ClaudeCodeSDKAgentConfig())

    transaction = MagicMock(spec=TaskAndDataModelTransaction)
    transaction.get_active_tasks.return_value = (pi_task, claude_task)
    task_service = MagicMock()

    messaged_count = broadcast_pi_models_refresh(task_service, transaction)

    assert messaged_count == 1
    task_service.create_message.assert_called_once()
    call = task_service.create_message.call_args
    assert isinstance(call.kwargs["message"], RefreshModelsUserMessage)
    assert call.kwargs["task_id"] == pi_task.object_id


def test_broadcast_pi_models_refresh_no_pi_agents_messages_none() -> None:
    transaction = MagicMock(spec=TaskAndDataModelTransaction)
    transaction.get_active_tasks.return_value = (_make_agent_task(ClaudeCodeSDKAgentConfig()),)
    task_service = MagicMock()

    messaged_count = broadcast_pi_models_refresh(task_service, transaction)

    assert messaged_count == 0
    task_service.create_message.assert_not_called()


def _stub_session_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the keystroke driver and auth.json poll for lifecycle-only tests.

    spawn() starts both on background threads; here we only assert PTY registration
    and teardown, so the driver is a no-op and the poll reads a fixed empty set
    (never the developer's real ~/.pi/agent/auth.json).
    """
    monkeypatch.setattr(pi_login_service_module, "_drive_pi_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(pi_login_service_module, "read_auth_json_provider_ids", set)


def test_spawn_registers_pty_and_teardown_stops_and_broadcasts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = MagicMock()
    fake_manager.subscribe.return_value = b""
    monkeypatch.setattr(pi_login_service_module, "LocalTerminalManager", MagicMock(return_value=fake_manager))
    _stub_session_threads(monkeypatch)
    broadcast_mock = MagicMock()
    monkeypatch.setattr(pi_login_service_module, "broadcast_pi_models_refresh", broadcast_mock)

    service = PiLoginService(
        concurrency_group=MagicMock(spec=ConcurrencyGroup),
        data_model_service=MagicMock(spec=DataModelService),
        task_service=MagicMock(spec=TaskService),
    )

    login_id = service.spawn(PiLoginMode.LOGIN, "/fake/pi")
    terminal_id = pi_login_terminal_id(login_id)
    try:
        assert get_terminal_manager(terminal_id) is fake_manager
        assert service.is_active(login_id)
        fake_manager.start.assert_called_once()
    finally:
        service.teardown(login_id)

    assert get_terminal_manager(terminal_id) is None
    assert not service.is_active(login_id)
    fake_manager.stop.assert_called_once()
    broadcast_mock.assert_called_once()


def test_teardown_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = MagicMock()
    fake_manager.subscribe.return_value = b""
    monkeypatch.setattr(pi_login_service_module, "LocalTerminalManager", MagicMock(return_value=fake_manager))
    _stub_session_threads(monkeypatch)
    broadcast_mock = MagicMock()
    monkeypatch.setattr(pi_login_service_module, "broadcast_pi_models_refresh", broadcast_mock)

    service = PiLoginService(
        concurrency_group=MagicMock(spec=ConcurrencyGroup),
        data_model_service=MagicMock(spec=DataModelService),
        task_service=MagicMock(spec=TaskService),
    )
    login_id = service.spawn(PiLoginMode.LOGOUT, "/fake/pi")

    service.teardown(login_id)
    service.teardown(login_id)  # second call must not raise or re-stop

    fake_manager.stop.assert_called_once()
    # Done and WebSocket-close both tear the same session down; only the call that
    # actually unregisters the PTY broadcasts, so the credential change fans out once.
    broadcast_mock.assert_called_once()


def test_login_change_observed_logout_completes_when_key_removed() -> None:
    # Logout completes only once the target key is gone — and not for a provider that
    # was never in auth.json (e.g. an env-detected one), so it can't false-complete.
    assert _login_change_observed(PiLoginMode.LOGOUT, "openai", {"anthropic", "openai"}, {"anthropic"})
    assert not _login_change_observed(PiLoginMode.LOGOUT, "openai", {"anthropic", "openai"}, {"anthropic", "openai"})
    assert not _login_change_observed(PiLoginMode.LOGOUT, "openai", {"anthropic"}, {"anthropic"})


def test_login_change_observed_login_completes_when_key_appears() -> None:
    assert _login_change_observed(PiLoginMode.LOGIN, "openai", {"anthropic"}, {"anthropic", "openai"})
    assert not _login_change_observed(PiLoginMode.LOGIN, "openai", {"anthropic"}, {"anthropic"})
    # Provider-agnostic (empty-state CTA): any newly added key completes the session.
    assert _login_change_observed(PiLoginMode.LOGIN, None, set(), {"anthropic"})
    assert not _login_change_observed(PiLoginMode.LOGIN, None, {"anthropic"}, {"anthropic"})


class _FakeTerminal:
    """A stand-in LocalTerminalManager that records writes and scripts pi's output.

    Each write can emit bytes back through the subscribed callback (as pi's TUI would
    render), so the marker-driven driver advances deterministically with no real PTY.
    """

    def __init__(self, on_write) -> None:
        self._callbacks: list = []
        self._on_write = on_write
        self.writes: list[bytes] = []

    def subscribe(self, callback) -> bytes:
        self._callbacks.append(callback)
        return b""

    def remove_output_callback(self, callback) -> None:
        self._callbacks.remove(callback)

    def emit(self, data: bytes) -> None:
        for callback in list(self._callbacks):
            callback(data)

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        self._on_write(self, data)


def _drive_with_fake_pi(
    monkeypatch: pytest.MonkeyPatch,
    mode: PiLoginMode,
    provider_id: str | None,
    on_write: Callable[[_FakeTerminal, bytes], None] = lambda manager, data: None,
) -> _FakeTerminal:
    """Run _drive_pi_session against a scripted _FakeTerminal and return it.

    Launch readiness is scripted (write_launch_command emits a readiness marker) and
    the fuzzy-filter settle is zeroed, so the driver advances without real waits.
    """
    monkeypatch.setattr(pi_login_service_module, "_PI_FILTER_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(
        pi_login_service_module,
        "write_launch_command",
        lambda manager, command, **kwargs: manager.emit(b"escape interrupt"),
    )
    terminal = _FakeTerminal(on_write)
    manager = cast(LocalTerminalManager, terminal)
    _drive_pi_session(_OutputAccumulator(manager), manager, "/fake/pi", mode, provider_id)
    return terminal


def test_drive_pi_session_logout_filters_and_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    def on_write(manager: _FakeTerminal, data: bytes) -> None:
        if data == b"/logout\r":
            manager.emit(b"Select provider to logout:")

    terminal = _drive_with_fake_pi(monkeypatch, PiLoginMode.LOGOUT, "openai", on_write)

    # Submit the slash, fuzzy-filter to the chosen provider, then confirm with Return.
    assert terminal.writes == [b"/logout\r", b"openai", b"\r"]


def test_drive_pi_session_agnostic_login_only_opens_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = _drive_with_fake_pi(monkeypatch, PiLoginMode.LOGIN, None)

    # The empty-state CTA names no provider — pi's own selectors take over, so only
    # the slash is driven.
    assert terminal.writes == [b"/login\r"]


def test_drive_pi_session_login_api_key_provider_lands_on_key_input(monkeypatch: pytest.MonkeyPatch) -> None:
    def on_write(manager: _FakeTerminal, data: bytes) -> None:
        if data == b"/login\r":
            manager.emit(b"Select authentication method:")
        elif data == b"\r":
            manager.emit(b"Select provider to configure:")

    terminal = _drive_with_fake_pi(monkeypatch, PiLoginMode.LOGIN, "openai", on_write)

    # openai is API-key-only, so its single valid method is chosen automatically
    # (Down + Return on pi's method selector), then the provider list is
    # fuzzy-filtered to the provider and confirmed — landing on the key input.
    assert terminal.writes == [b"/login\r", b"\x1b[B", b"\r", b"openai", b"\r"]


def test_drive_pi_session_login_subscription_provider_lets_user_pick_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def on_write(manager: _FakeTerminal, data: bytes) -> None:
        if data == b"/login\r":
            manager.emit(b"Select authentication method:")
            # As if the user picked a method in pi's TUI: the provider list renders.
            manager.emit(b"Select provider to configure:")

    terminal = _drive_with_fake_pi(monkeypatch, PiLoginMode.LOGIN, "anthropic", on_write)

    # anthropic also supports subscription login, so the method choice stays with the
    # user; once their choice renders the provider list, the provider is auto-selected.
    assert terminal.writes == [b"/login\r", b"anthropic", b"\r"]


def test_drive_pi_session_login_gives_up_when_method_selector_never_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pi_login_service_module, "_PI_SELECTOR_TIMEOUT_SECONDS", 0.05)

    terminal = _drive_with_fake_pi(monkeypatch, PiLoginMode.LOGIN, "openai")

    # The slash is retried once (an early keystroke can be dropped); with no selector
    # ever rendering, the session is left for manual completion — nothing else typed.
    assert terminal.writes == [b"/login\r", b"/login\r"]


def test_poll_marks_completed_on_auth_json_change(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PiLoginService(
        concurrency_group=MagicMock(spec=ConcurrencyGroup),
        data_model_service=MagicMock(spec=DataModelService),
        task_service=MagicMock(spec=TaskService),
    )
    login_id = "test-login"
    terminal_id = pi_login_terminal_id(login_id)
    register_terminal_manager(terminal_id, MagicMock())  # is_active() True
    try:
        # auth.json already reflects the logout, so the first poll iteration completes.
        monkeypatch.setattr(pi_login_service_module, "read_auth_json_provider_ids", lambda: {"anthropic"})
        assert not service.is_completed(login_id)
        service._poll_for_completion(login_id, PiLoginMode.LOGOUT, "openai", {"anthropic", "openai"})
        assert service.is_completed(login_id)
    finally:
        unregister_terminal_manager(terminal_id)
