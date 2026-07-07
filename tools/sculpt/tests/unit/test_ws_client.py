"""Unit tests for the WebSocket client module."""

import asyncio
import json
import threading
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
import websockets
import websockets.server

from sculpt.ws_client import AgentNotFoundError
from sculpt.ws_client import AgentSnapshot
from sculpt.ws_client import ExitReason
from sculpt.ws_client import _build_ws_url
from sculpt.ws_client import _options_from_pending_question
from sculpt.ws_client import _snapshot_from_view
from sculpt.ws_client import fetch_agent_state
from sculpt.ws_client import fetch_all_agents
from sculpt.ws_client import follow_agent


def _pending_question_update(
    *labels: str, chat_messages: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """A task update dict carrying a pendingUserQuestion with the given option labels."""
    return {
        "chatMessages": chat_messages or [],
        "pendingUserQuestion": {
            "questions": [{"options": [{"label": label} for label in labels]}],
        },
    }


class TestOptionsFromPendingQuestion:
    def test_extracts_option_labels(self) -> None:
        update = _pending_question_update("Red", "Blue")
        assert _options_from_pending_question(update) == ["Red", "Blue"]

    def test_none_update_yields_none(self) -> None:
        assert _options_from_pending_question(None) is None

    def test_empty_update_yields_none(self) -> None:
        assert _options_from_pending_question({}) is None

    def test_missing_pending_question_yields_none(self) -> None:
        assert _options_from_pending_question({"chatMessages": []}) is None

    def test_null_pending_question_yields_none(self) -> None:
        assert _options_from_pending_question({"pendingUserQuestion": None}) is None

    def test_non_dict_pending_question_yields_none(self) -> None:
        assert _options_from_pending_question({"pendingUserQuestion": "bogus"}) is None

    def test_empty_questions_yields_none(self) -> None:
        assert _options_from_pending_question({"pendingUserQuestion": {"questions": []}}) is None

    def test_empty_options_yields_none(self) -> None:
        update = {"pendingUserQuestion": {"questions": [{"options": []}]}}
        assert _options_from_pending_question(update) is None

    def test_options_without_labels_yields_none(self) -> None:
        update = {"pendingUserQuestion": {"questions": [{"options": [{"label": ""}, {}]}]}}
        assert _options_from_pending_question(update) is None

    def test_only_first_question_is_read(self) -> None:
        update = {
            "pendingUserQuestion": {
                "questions": [
                    {"options": [{"label": "First"}]},
                    {"options": [{"label": "Second"}]},
                ],
            },
        }
        assert _options_from_pending_question(update) == ["First"]


class TestSnapshotFromView:
    def test_update_populates_waiting_options_and_messages(self) -> None:
        messages = [{"id": "msg_1", "role": "user", "content": "hi"}]
        update = _pending_question_update("Red", "Blue", chat_messages=messages)

        snapshot = _snapshot_from_view("tsk_abc", _make_task_view(task_id="tsk_abc"), update)

        assert snapshot.waiting_options == ["Red", "Blue"]
        assert snapshot.messages == messages

    def test_no_update_yields_no_waiting_options(self) -> None:
        snapshot = _snapshot_from_view("tsk_abc", _make_task_view(task_id="tsk_abc"))

        assert snapshot.waiting_options is None
        assert snapshot.messages == []


def test_build_ws_url_no_scope() -> None:
    assert _build_ws_url("http://x", "tok") == "ws://x/api/v1/stream/ws?x-session-token=tok"


def test_build_ws_url_with_all_scope() -> None:
    assert _build_ws_url("http://x", "tok", scope="all") == "ws://x/api/v1/stream/ws?x-session-token=tok&scope=all"


def test_build_ws_url_with_agent_scope() -> None:
    assert (
        _build_ws_url("http://x", "tok", scope="agent:tsk_abc")
        == "ws://x/api/v1/stream/ws?x-session-token=tok&scope=agent:tsk_abc"
    )


def test_build_ws_url_https_to_wss() -> None:
    assert (
        _build_ws_url("https://x", "tok", scope="workspace:ws_1")
        == "wss://x/api/v1/stream/ws?x-session-token=tok&scope=workspace:ws_1"
    )


def _make_task_view(
    task_id: str = "tsk_abc123",
    status: str = "RUNNING",
    task_status: str = "RUNNING",
    current_activity: str | None = None,
    last_activity: str | None = None,
    task_completed: int = 0,
    task_total: int = 0,
    current_task_subject: str | None = None,
    waiting_detail: str | None = None,
    error_detail: str | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "projectId": "prj_test",
        "workspaceId": "ws_test",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:01:00Z",
        "taskStatus": task_status,
        "status": status,
        "title": "Test task",
        "model": "CLAUDE-4-SONNET",
        "interface": "TERMINAL",
        "isDeleted": False,
        "artifactNames": ["artifact1"],
        "workspacePeekStatus": "WORKING",
        "currentActivity": current_activity,
        "lastActivity": last_activity,
        "taskCompleted": task_completed,
        "taskTotal": task_total,
        "currentTaskSubject": current_task_subject,
        "waitingDetail": waiting_detail,
        "errorDetail": error_detail,
    }


def _make_dump(
    task_views: dict[str, dict[str, Any]],
    task_updates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "taskViewsByTaskId": task_views,
        "taskUpdateByTaskId": task_updates or {},
    }


def _start_ws_server(
    payload: str | None, delay: float = 0.0
) -> tuple[str, threading.Event, dict[str, Any]]:
    """Start a WebSocket server in a background thread that sends the given payload.

    Returns (url, shutdown_event, server_info). server_info["last_path"] is
    populated with the request path of each accepted connection so tests can
    assert on the query string.
    """
    shutdown_event = threading.Event()
    ready_event = threading.Event()
    server_info: dict[str, Any] = {}

    async def handler(ws: websockets.server.ServerConnection) -> None:
        server_info["last_path"] = ws.request.path
        if delay > 0:
            await asyncio.sleep(delay)
        if payload is not None:
            await ws.send(payload)
        await ws.wait_closed()

    async def run_server() -> None:
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            server_info["port"] = port
            ready_event.set()
            while not shutdown_event.is_set():
                await asyncio.sleep(0.05)

    def thread_target() -> None:
        asyncio.run(run_server())

    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()
    ready_event.wait(timeout=5.0)

    url = f"ws://127.0.0.1:{server_info['port']}"
    return url, shutdown_event, server_info


def test_fetch_agent_state_happy_path() -> None:
    task_id = f"tsk_{uuid4().hex}"
    view = _make_task_view(task_id=task_id, current_activity="Editing file.py")
    messages = [{"role": "user", "content": "hello"}]
    dump = _make_dump(
        task_views={task_id: view},
        task_updates={task_id: {"chatMessages": messages}},
    )
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "fake-token", task_id)
        assert isinstance(snapshot, AgentSnapshot)
        assert snapshot.task_id == task_id
        assert snapshot.status == "RUNNING"
        assert snapshot.current_activity == "Editing file.py"
        assert snapshot.messages == messages
        assert snapshot.artifact_names == ["artifact1"]
    finally:
        shutdown.set()


def test_fetch_agent_state_not_found() -> None:
    dump = _make_dump(task_views={"tsk_xyz": _make_task_view(task_id="tsk_xyz")})
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        with pytest.raises(AgentNotFoundError):
            fetch_agent_state(url.replace("ws://", "http://"), "fake-token", "tsk_nope")
    finally:
        shutdown.set()


def test_fetch_agent_state_timeout() -> None:
    url, shutdown, _info = _start_ws_server(None, delay=10.0)
    try:
        with pytest.raises(TimeoutError):
            fetch_agent_state(url.replace("ws://", "http://"), "fake-token", "tsk_any", timeout=0.1)
    finally:
        shutdown.set()


def test_fetch_agent_state_messages_extraction() -> None:
    task_id = f"tsk_{uuid4().hex}"
    messages = [
        {"role": "user", "content": "what is going on"},
        {"role": "assistant", "content": "I am working on the task"},
    ]
    dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id)},
        task_updates={task_id: {"chatMessages": messages}},
    )
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "fake-token", task_id)
        assert snapshot.messages == messages
    finally:
        shutdown.set()


def test_fetch_agent_state_no_messages() -> None:
    task_id = f"tsk_{uuid4().hex}"
    dump = _make_dump(task_views={task_id: _make_task_view(task_id=task_id)})
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "fake-token", task_id)
        assert snapshot.messages == []
    finally:
        shutdown.set()


def test_fetch_agent_state_missing_optional_fields() -> None:
    task_id = f"tsk_{uuid4().hex}"
    minimal_view = {
        "id": task_id,
        "status": "RUNNING",
        "taskStatus": "RUNNING",
        "updatedAt": "2026-01-01T00:00:00Z",
        "model": "CLAUDE-4-SONNET",
        "interface": "TERMINAL",
        "projectId": "prj_test",
        "workspaceId": "ws_test",
        "createdAt": "2026-01-01T00:00:00Z",
        "isDeleted": False,
    }
    dump = _make_dump(task_views={task_id: minimal_view})
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "fake-token", task_id)
        assert snapshot.current_activity is None
        assert snapshot.last_activity is None
        assert snapshot.task_completed == 0
        assert snapshot.task_total == 0
        assert snapshot.current_task_subject is None
        assert snapshot.waiting_detail is None
        assert snapshot.error_detail is None
        assert snapshot.title is None
        assert snapshot.artifact_names == []
    finally:
        shutdown.set()


def test_fetch_agent_state_skips_null_message() -> None:
    task_id = f"tsk_{uuid4().hex}"
    dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id)},
        task_updates={task_id: {"chatMessages": [{"role": "user", "content": "hi"}]}},
    )
    shutdown_event = threading.Event()
    ready_event = threading.Event()
    server_info: dict[str, Any] = {}

    async def handler(ws: websockets.server.ServerConnection) -> None:
        await ws.send("null")
        await ws.send(json.dumps(dump))
        await ws.wait_closed()

    async def run_server() -> None:
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            server_info["port"] = port
            ready_event.set()
            while not shutdown_event.is_set():
                await asyncio.sleep(0.05)

    thread = threading.Thread(target=lambda: asyncio.run(run_server()), daemon=True)
    thread.start()
    ready_event.wait(timeout=5.0)

    url = f"http://127.0.0.1:{server_info['port']}"
    try:
        snapshot = fetch_agent_state(url, "fake-token", task_id)
        assert snapshot.task_id == task_id
        assert snapshot.messages == [{"role": "user", "content": "hi"}]
    finally:
        shutdown_event.set()


def _start_ws_server_with_messages(
    messages_to_send: Sequence[str], delay_between: float = 0.05
) -> tuple[str, threading.Event]:
    """Start a WebSocket server that sends a sequence of messages."""
    shutdown_event = threading.Event()
    ready_event = threading.Event()
    server_info: dict[str, Any] = {}

    async def handler(ws: websockets.server.ServerConnection) -> None:
        for msg in messages_to_send:
            await ws.send(msg)
            await asyncio.sleep(delay_between)
        await ws.wait_closed()

    async def run_server() -> None:
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            server_info["port"] = port
            ready_event.set()
            while not shutdown_event.is_set():
                await asyncio.sleep(0.05)

    thread = threading.Thread(target=lambda: asyncio.run(run_server()), daemon=True)
    thread.start()
    ready_event.wait(timeout=5.0)

    url = f"ws://127.0.0.1:{server_info['port']}"
    return url, shutdown_event


def test_follow_auto_exit_terminal_state() -> None:
    task_id = f"tsk_{uuid4().hex}"
    initial_view = _make_task_view(task_id=task_id, status="RUNNING")
    initial_dump = _make_dump(
        task_views={task_id: initial_view},
        task_updates={task_id: {"chatMessages": [{"id": "msg_1", "role": "user", "content": [{"type": "text", "text": "hi"}]}]}},
    )
    update_view = _make_task_view(task_id=task_id, status="READY")
    update_dump = {"taskViewsByTaskId": {task_id: update_view}, "taskUpdateByTaskId": {}}

    url, shutdown = _start_ws_server_with_messages([
        json.dumps(initial_dump),
        json.dumps(update_dump),
    ])
    try:
        statuses: list[AgentSnapshot] = []
        all_messages: list[list[dict[str, Any]]] = []

        result = follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            task_id,
            on_status=statuses.append,
            on_messages=all_messages.append,
        )

        assert result == ExitReason.TERMINAL_STATE
        assert len(statuses) >= 2
        assert statuses[0].status == "RUNNING"
        assert statuses[-1].status == "READY"
        assert len(all_messages) >= 1
    finally:
        shutdown.set()


def test_follow_auto_exit_waiting() -> None:
    task_id = f"tsk_{uuid4().hex}"
    initial_view = _make_task_view(task_id=task_id, status="RUNNING")
    initial_dump = _make_dump(task_views={task_id: initial_view})
    update_view = _make_task_view(task_id=task_id, status="WAITING", waiting_detail="Need input")
    update_dump = {"taskViewsByTaskId": {task_id: update_view}, "taskUpdateByTaskId": {}}

    url, shutdown = _start_ws_server_with_messages([
        json.dumps(initial_dump),
        json.dumps(update_dump),
    ])
    try:
        statuses: list[AgentSnapshot] = []

        result = follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            task_id,
            on_status=statuses.append,
            on_messages=lambda _: None,
        )

        assert result == ExitReason.WAITING
        assert any(s.status == "WAITING" for s in statuses)
    finally:
        shutdown.set()


def test_follow_new_messages() -> None:
    task_id = f"tsk_{uuid4().hex}"
    initial_msg = {"id": "msg_1", "role": "user", "content": [{"type": "text", "text": "hello"}]}
    initial_dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id)},
        task_updates={task_id: {"chatMessages": [initial_msg]}},
    )
    new_msg = {"id": "msg_2", "role": "assistant", "content": [{"type": "text", "text": "hi back"}]}
    update = {
        "taskViewsByTaskId": {task_id: _make_task_view(task_id=task_id, status="READY")},
        "taskUpdateByTaskId": {task_id: {"chatMessages": [new_msg]}},
    }

    url, shutdown = _start_ws_server_with_messages([
        json.dumps(initial_dump),
        json.dumps(update),
    ])
    try:
        all_messages: list[list[dict[str, Any]]] = []

        result = follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            task_id,
            on_status=lambda _: None,
            on_messages=all_messages.append,
        )

        assert result == ExitReason.TERMINAL_STATE
        assert len(all_messages) == 2
        assert all_messages[0][0]["id"] == "msg_1"
        assert all_messages[1][0]["id"] == "msg_2"
    finally:
        shutdown.set()


def test_follow_message_deduplication() -> None:
    task_id = f"tsk_{uuid4().hex}"
    msg_a = {"id": "msg_a", "role": "user", "content": [{"type": "text", "text": "a"}]}
    msg_b = {"id": "msg_b", "role": "assistant", "content": [{"type": "text", "text": "b"}]}
    msg_c = {"id": "msg_c", "role": "user", "content": [{"type": "text", "text": "c"}]}

    initial_dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id)},
        task_updates={task_id: {"chatMessages": [msg_a, msg_b]}},
    )
    update = {
        "taskViewsByTaskId": {task_id: _make_task_view(task_id=task_id, status="READY")},
        "taskUpdateByTaskId": {task_id: {"chatMessages": [msg_a, msg_b, msg_c]}},
    }

    url, shutdown = _start_ws_server_with_messages([
        json.dumps(initial_dump),
        json.dumps(update),
    ])
    try:
        all_messages: list[list[dict[str, Any]]] = []

        follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            task_id,
            on_status=lambda _: None,
            on_messages=all_messages.append,
        )

        assert len(all_messages) == 2
        assert [m["id"] for m in all_messages[0]] == ["msg_a", "msg_b"]
        assert [m["id"] for m in all_messages[1]] == ["msg_c"]
    finally:
        shutdown.set()


def test_follow_ignores_other_agents() -> None:
    target_id = f"tsk_target_{uuid4().hex}"
    other_id = f"tsk_other_{uuid4().hex}"
    initial_dump = _make_dump(
        task_views={
            target_id: _make_task_view(task_id=target_id),
            other_id: _make_task_view(task_id=other_id),
        },
    )
    update_other = {
        "taskViewsByTaskId": {other_id: _make_task_view(task_id=other_id, status="ERROR")},
        "taskUpdateByTaskId": {},
    }
    update_target = {
        "taskViewsByTaskId": {target_id: _make_task_view(task_id=target_id, status="READY")},
        "taskUpdateByTaskId": {},
    }

    url, shutdown = _start_ws_server_with_messages([
        json.dumps(initial_dump),
        json.dumps(update_other),
        json.dumps(update_target),
    ])
    try:
        statuses: list[AgentSnapshot] = []

        result = follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            target_id,
            on_status=statuses.append,
            on_messages=lambda _: None,
        )

        assert result == ExitReason.TERMINAL_STATE
        for s in statuses:
            assert s.task_id == target_id


    finally:
        shutdown.set()


def test_follow_handles_null_keepalive() -> None:
    task_id = f"tsk_{uuid4().hex}"
    initial_dump = _make_dump(task_views={task_id: _make_task_view(task_id=task_id)})
    terminal_update = {
        "taskViewsByTaskId": {task_id: _make_task_view(task_id=task_id, status="READY")},
        "taskUpdateByTaskId": {},
    }

    url, shutdown = _start_ws_server_with_messages([
        json.dumps(initial_dump),
        "null",
        "null",
        json.dumps(terminal_update),
    ])
    try:
        result = follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            task_id,
            on_status=lambda _: None,
            on_messages=lambda _: None,
        )

        assert result == ExitReason.TERMINAL_STATE
    finally:
        shutdown.set()


def test_follow_reconnect() -> None:
    task_id = f"tsk_{uuid4().hex}"
    msg_1 = {"id": "msg_1", "role": "user", "content": [{"type": "text", "text": "hello"}]}
    initial_dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id)},
        task_updates={task_id: {"chatMessages": [msg_1]}},
    )
    reconnect_dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id, status="READY")},
        task_updates={task_id: {"chatMessages": [msg_1]}},
    )

    connection_count = 0
    shutdown_event = threading.Event()
    ready_event = threading.Event()
    server_info: dict[str, Any] = {}

    async def handler(ws: websockets.server.ServerConnection) -> None:
        nonlocal connection_count
        connection_count += 1
        if connection_count == 1:
            await ws.send(json.dumps(initial_dump))
            await asyncio.sleep(0.05)
            await ws.close()
        else:
            await ws.send(json.dumps(reconnect_dump))
            await ws.wait_closed()

    async def run_server() -> None:
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            server_info["port"] = port
            ready_event.set()
            while not shutdown_event.is_set():
                await asyncio.sleep(0.05)

    thread = threading.Thread(target=lambda: asyncio.run(run_server()), daemon=True)
    thread.start()
    ready_event.wait(timeout=5.0)

    url = f"http://127.0.0.1:{server_info['port']}"
    reconnect_called = []
    all_messages: list[list[dict[str, Any]]] = []

    try:
        result = follow_agent(
            url,
            "fake-token",
            task_id,
            on_status=lambda _: None,
            on_messages=all_messages.append,
            on_reconnect=lambda: reconnect_called.append(True),
            max_retries=3,
        )

        assert result == ExitReason.TERMINAL_STATE
        assert len(reconnect_called) >= 1
        all_msg_ids = [m["id"] for batch in all_messages for m in batch]
        assert all_msg_ids.count("msg_1") == 1
    finally:
        shutdown_event.set()


def test_follow_retry_exhausted() -> None:
    task_id = f"tsk_{uuid4().hex}"
    initial_dump = _make_dump(task_views={task_id: _make_task_view(task_id=task_id)})

    connection_count = 0
    shutdown_event = threading.Event()
    ready_event = threading.Event()
    server_info: dict[str, Any] = {}

    async def handler(ws: websockets.server.ServerConnection) -> None:
        nonlocal connection_count
        connection_count += 1
        if connection_count == 1:
            await ws.send(json.dumps(initial_dump))
            await asyncio.sleep(0.05)
        await ws.close()

    async def run_server() -> None:
        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            server_info["port"] = port
            ready_event.set()
            while not shutdown_event.is_set():
                await asyncio.sleep(0.05)

    thread = threading.Thread(target=lambda: asyncio.run(run_server()), daemon=True)
    thread.start()
    ready_event.wait(timeout=5.0)

    url = f"http://127.0.0.1:{server_info['port']}"

    try:
        result = follow_agent(
            url,
            "fake-token",
            task_id,
            on_status=lambda _: None,
            on_messages=lambda _: None,
            max_retries=1,
        )

        assert result == ExitReason.RETRY_EXHAUSTED
    finally:
        shutdown_event.set()


def test_fetch_agent_state_url_includes_agent_scope() -> None:
    task_id = "tsk_full_id_capture"
    dump = _make_dump(task_views={task_id: _make_task_view(task_id=task_id)})
    url, shutdown, info = _start_ws_server(json.dumps(dump))
    try:
        fetch_agent_state(url.replace("ws://", "http://"), "tok", task_id)
        assert "scope=agent:tsk_full_id_capture" in info["last_path"]
        assert "x-session-token=tok" in info["last_path"]
    finally:
        shutdown.set()


def test_fetch_all_agents_workspace_scope_url() -> None:
    dump = _make_dump(task_views={})
    url, shutdown, info = _start_ws_server(json.dumps(dump))
    try:
        fetch_all_agents(url.replace("ws://", "http://"), "tok", scope="workspace:ws_abc")
        assert "scope=workspace:ws_abc" in info["last_path"]
    finally:
        shutdown.set()


def test_fetch_all_agents_project_scope_url() -> None:
    dump = _make_dump(task_views={})
    url, shutdown, info = _start_ws_server(json.dumps(dump))
    try:
        fetch_all_agents(url.replace("ws://", "http://"), "tok", scope="project:prj_abc")
        assert "scope=project:prj_abc" in info["last_path"]
    finally:
        shutdown.set()


def test_fetch_all_agents_default_all_scope_url() -> None:
    dump = _make_dump(task_views={})
    url, shutdown, info = _start_ws_server(json.dumps(dump))
    try:
        fetch_all_agents(url.replace("ws://", "http://"), "tok")
        assert "scope=all" in info["last_path"]
    finally:
        shutdown.set()


def test_fetch_agent_state_reads_exactly_one_frame() -> None:
    task_id = "tsk_one_frame"
    dump = _make_dump(task_views={task_id: _make_task_view(task_id=task_id)})
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "tok", task_id, timeout=2.0)
        assert snapshot.task_id == task_id
    finally:
        shutdown.set()


def test_follow_dedupes_status_when_view_unchanged() -> None:
    """The server re-emits the task view on every internal task update — many
    of those don't change anything user-visible (e.g. streaming partials bump
    the view's mtime but not its rendered fields). Verify the client emits
    on_status only when meaningful fields actually change.
    """
    task_id = f"tsk_{uuid4().hex}"
    view = _make_task_view(task_id=task_id, status="RUNNING")
    initial_dump = _make_dump(task_views={task_id: view})
    # Same view re-emitted three times — should produce zero extra on_status calls.
    same_view_dump = {"taskViewsByTaskId": {task_id: view}, "taskUpdateByTaskId": {}}
    # Now a different status — should produce one on_status call.
    changed_dump = {
        "taskViewsByTaskId": {task_id: _make_task_view(task_id=task_id, status="READY")},
        "taskUpdateByTaskId": {},
    }

    url, shutdown = _start_ws_server_with_messages(
        [
            json.dumps(initial_dump),
            json.dumps(same_view_dump),
            json.dumps(same_view_dump),
            json.dumps(same_view_dump),
            json.dumps(changed_dump),
        ]
    )
    try:
        statuses: list[str] = []
        follow_agent(
            url.replace("ws://", "http://"),
            "tok",
            task_id,
            on_status=lambda s: statuses.append(s.status),
            on_messages=lambda _ms: None,
        )
        # Initial status + the one real change. The three identical re-emits do not fire.
        assert statuses == ["RUNNING", "READY"]
    finally:
        shutdown.set()


def test_follow_emits_streaming_partial_messages() -> None:
    """Streaming-in-flight content arrives in task_update.inProgressChatMessage.
    Verify the client emits on_partial as the message grows, then once with
    None at stream end. The completed chatMessages entry that arrives on a
    subsequent frame still flows through on_messages so consumers that don't
    process partials (text mode, anything that ignores on_partial) still get
    the full assistant turn.
    """
    task_id = f"tsk_{uuid4().hex}"
    view = _make_task_view(task_id=task_id, status="RUNNING")
    final_view = _make_task_view(task_id=task_id, status="READY")

    partial_1 = {"id": "msg_1", "role": "assistant", "content": [{"type": "text", "text": "Hel"}]}
    partial_2 = {"id": "msg_1", "role": "assistant", "content": [{"type": "text", "text": "Hello"}]}

    dump_partial_1 = {
        "taskViewsByTaskId": {task_id: view},
        "taskUpdateByTaskId": {task_id: {"chatMessages": [], "inProgressChatMessage": partial_1}},
    }
    # Same content again — should not re-emit.
    dump_partial_1_repeat = dump_partial_1
    dump_partial_2 = {
        "taskViewsByTaskId": {task_id: view},
        "taskUpdateByTaskId": {task_id: {"chatMessages": [], "inProgressChatMessage": partial_2}},
    }
    # Streaming completes: content moves to chatMessages, inProgressChatMessage becomes None.
    dump_complete = {
        "taskViewsByTaskId": {task_id: final_view},
        "taskUpdateByTaskId": {task_id: {"chatMessages": [partial_2], "inProgressChatMessage": None}},
    }

    initial_dump = _make_dump(task_views={task_id: view})

    url, shutdown = _start_ws_server_with_messages(
        [
            json.dumps(initial_dump),
            json.dumps(dump_partial_1),
            json.dumps(dump_partial_1_repeat),
            json.dumps(dump_partial_2),
            json.dumps(dump_complete),
        ]
    )
    try:
        partials: list[dict[str, Any] | None] = []
        completed: list[list[dict[str, Any]]] = []
        follow_agent(
            url.replace("ws://", "http://"),
            "tok",
            task_id,
            on_status=lambda _s: None,
            on_messages=completed.append,
            on_partial=partials.append,
        )
        # Two distinct partial states + a final None when streaming ends.
        assert [p["content"][0]["text"] if p else None for p in partials] == ["Hel", "Hello", None]
        # The completed chatMessages entry still flows through on_messages so
        # consumers that don't subscribe to partials still see the assistant
        # message. Partial-aware consumers can dedupe by message id.
        assert len(completed) == 1
        assert completed[0][0]["id"] == "msg_1"
    finally:
        shutdown.set()


def test_fetch_agent_state_extracts_waiting_options() -> None:
    task_id = f"tsk_{uuid4().hex}"
    dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id, status="WAITING")},
        task_updates={
            task_id: {
                "chatMessages": [],
                "pendingUserQuestion": {
                    "questions": [{"options": [{"label": "Red"}, {"label": "Blue"}]}],
                },
            }
        },
    )
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "fake-token", task_id)
        assert snapshot.waiting_options == ["Red", "Blue"]
    finally:
        shutdown.set()


def test_fetch_agent_state_no_pending_question_yields_no_options() -> None:
    task_id = f"tsk_{uuid4().hex}"
    dump = _make_dump(
        task_views={task_id: _make_task_view(task_id=task_id)},
        task_updates={task_id: {"chatMessages": []}},
    )
    url, shutdown, _info = _start_ws_server(json.dumps(dump))
    try:
        snapshot = fetch_agent_state(url.replace("ws://", "http://"), "fake-token", task_id)
        assert snapshot.waiting_options is None
    finally:
        shutdown.set()


def test_follow_carries_waiting_options_across_view_only_frames() -> None:
    """A frame may carry the task view without its update; the follow loop must
    keep rendering the last-known pending-question options on such frames
    instead of blanking them."""
    task_id = f"tsk_{uuid4().hex}"
    pending_update = {
        "chatMessages": [],
        "pendingUserQuestion": {
            "questions": [{"options": [{"label": "Red"}, {"label": "Blue"}]}],
        },
    }

    initial_dump = _make_dump(task_views={task_id: _make_task_view(task_id=task_id)})
    # Frame with both view and update: options become known.
    frame_with_question = {
        "taskViewsByTaskId": {task_id: _make_task_view(task_id=task_id, waiting_detail="Pick one")},
        "taskUpdateByTaskId": {task_id: pending_update},
    }
    # View-only frame (changed activity, no update): options must persist.
    frame_view_only = {
        "taskViewsByTaskId": {
            task_id: _make_task_view(
                task_id=task_id, waiting_detail="Pick one", current_activity="thinking"
            )
        },
        "taskUpdateByTaskId": {},
    }
    terminal_frame = {
        "taskViewsByTaskId": {task_id: _make_task_view(task_id=task_id, status="READY")},
        "taskUpdateByTaskId": {},
    }

    url, shutdown = _start_ws_server_with_messages(
        [
            json.dumps(initial_dump),
            json.dumps(frame_with_question),
            json.dumps(frame_view_only),
            json.dumps(terminal_frame),
        ]
    )
    try:
        statuses: list[AgentSnapshot] = []
        result = follow_agent(
            url.replace("ws://", "http://"),
            "fake-token",
            task_id,
            on_status=statuses.append,
            on_messages=lambda _: None,
        )

        assert result == ExitReason.TERMINAL_STATE
        thinking_snapshot = next(s for s in statuses if s.current_activity == "thinking")
        assert thinking_snapshot.waiting_options == ["Red", "Blue"]
    finally:
        shutdown.set()
