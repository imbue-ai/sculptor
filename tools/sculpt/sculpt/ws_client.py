"""WebSocket client for fetching agent state from the Sculptor streaming endpoint."""

import asyncio
import enum
import json
import urllib.parse
from collections.abc import Callable
from typing import Any

import pydantic
import websockets
import websockets.exceptions


class AgentNotFoundError(Exception):
    """Raised when the target agent ID or prefix is not found in the WebSocket dump."""


class ExitReason(enum.Enum):
    TERMINAL_STATE = "terminal_state"
    WAITING = "waiting"
    CTRL_C = "ctrl_c"
    RETRY_EXHAUSTED = "retry_exhausted"


class AgentSnapshot(pydantic.BaseModel):
    """All data for a single agent extracted from the WebSocket dump."""

    model_config = pydantic.ConfigDict(frozen=True)

    task_id: str
    status: str
    task_status: str
    current_activity: str | None
    last_activity: str | None
    task_completed: int
    task_total: int
    current_task_subject: str | None
    waiting_detail: str | None
    # Answer options of the pending AskUserQuestion, from the task update's
    # server-maintained pendingUserQuestion (None when the agent isn't blocked
    # on one, or when the connection scope carries no task update).
    waiting_options: list[str] | None = None
    error_detail: str | None
    updated_at: str
    title: str | None
    # Terminal agents carry no model (Sculptor doesn't control it), so this is None for them.
    model: str | None
    interface: str
    project_id: str
    workspace_id: str
    created_at: str
    is_deleted: bool
    artifact_names: list[str]
    messages: list[dict[str, Any]]


def _build_ws_url(base_url: str, session_token: str, scope: str | None = None) -> str:
    """Convert an HTTP base URL to a WebSocket URL for the streaming endpoint.

    If `scope` is provided, append it as a `scope=` query parameter so the
    server narrows the connection. Pass None to leave the legacy unscoped
    behavior (server resolves missing scope to ScopeAll).
    """
    if base_url.startswith("https://"):
        ws_url = "wss://" + base_url[len("https://") :]
    elif base_url.startswith("http://"):
        ws_url = "ws://" + base_url[len("http://") :]
    else:
        ws_url = base_url
    url = f"{ws_url}/api/v1/stream/ws?x-session-token={urllib.parse.quote(session_token, safe='')}"
    if scope is not None:
        url = f"{url}&scope={urllib.parse.quote(scope, safe=':')}"
    return url


class ScopeMalformedError(Exception):
    """Server rejected the scope query string with HTTP 400."""


class ScopeForbiddenError(Exception):
    """Server rejected the scope upgrade with HTTP 403."""


class ScopeNotFoundError(Exception):
    """Server rejected the scope upgrade with HTTP 404."""


def _wrap_invalid_status(e: websockets.exceptions.InvalidStatus) -> Exception:
    """Map a WS upgrade rejection to a typed scope error, preserving the original for non-4xx."""
    status = e.response.status_code
    if status == 400:
        return ScopeMalformedError(str(e))
    if status == 403:
        return ScopeForbiddenError(str(e))
    if status == 404:
        return ScopeNotFoundError(str(e))
    return e


_TERMINAL_STATUSES = frozenset({"READY", "ERROR"})
_TERMINAL_TASK_STATUSES = frozenset({"FAILED", "CANCELLED", "DELETED", "SUCCEEDED"})

_MAX_RECONNECT_DELAY_SECONDS = 30


def _is_terminal_state(snapshot: AgentSnapshot) -> bool:
    return snapshot.status in _TERMINAL_STATUSES or snapshot.task_status in _TERMINAL_TASK_STATUSES


def _is_waiting_state(snapshot: AgentSnapshot) -> bool:
    return snapshot.status == "WAITING"


def _options_from_pending_question(update: dict[str, Any] | None) -> list[str] | None:
    """Option labels of the pending AskUserQuestion carried by a task update.

    The server maintains ``pendingUserQuestion`` (set when the agent asks,
    cleared when the user answers), so its presence is authoritative — no
    message-history scanning needed. Returns the first question's option
    labels, or None when nothing is pending.
    """
    if not update:
        return None
    pending = update.get("pendingUserQuestion")
    if not isinstance(pending, dict):
        return None
    questions = pending.get("questions") or []
    if not questions or not isinstance(questions[0], dict):
        return None
    options = questions[0].get("options") or []
    labels = [o.get("label") for o in options if isinstance(o, dict) and o.get("label")]
    return labels or None


def _snapshot_from_view(
    task_id: str, view: dict[str, Any], update: dict[str, Any] | None = None
) -> AgentSnapshot:
    """Build an AgentSnapshot from a task view dict plus its optional task update."""
    update = update or {}
    return AgentSnapshot(
        task_id=view.get("id", task_id),
        status=view.get("status", "UNKNOWN"),
        task_status=view.get("taskStatus", "UNKNOWN"),
        current_activity=view.get("currentActivity"),
        last_activity=view.get("lastActivity"),
        task_completed=view.get("taskCompleted", 0),
        task_total=view.get("taskTotal", 0),
        current_task_subject=view.get("currentTaskSubject"),
        waiting_detail=view.get("waitingDetail"),
        waiting_options=_options_from_pending_question(update),
        error_detail=view.get("errorDetail"),
        updated_at=view.get("updatedAt", ""),
        title=view.get("title"),
        model=view.get("model"),
        interface=view.get("interface", ""),
        project_id=view.get("projectId", ""),
        workspace_id=view.get("workspaceId", ""),
        created_at=view.get("createdAt", ""),
        is_deleted=view.get("isDeleted", False),
        artifact_names=view.get("artifactNames", []),
        messages=update.get("chatMessages", []),
    )


def _extract_snapshot(task_id: str, dump: dict[str, Any]) -> AgentSnapshot:
    """Extract an AgentSnapshot from the WebSocket state dump."""
    task_views = dump.get("taskViewsByTaskId", {})
    task_updates = dump.get("taskUpdateByTaskId", {})

    view = task_views[task_id]
    update = task_updates.get(task_id, {})

    return _snapshot_from_view(task_id, view, update)


async def _receive_initial_dump(ws: Any, timeout: float = 30.0) -> dict[str, Any]:
    """Receive and parse the initial state dump, skipping null keepalives."""
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        dump = json.loads(raw)
        if dump is not None:
            return dump


async def _fetch_agent_state_async(ws_url: str, agent_id: str, timeout: float) -> AgentSnapshot:
    """Connect to the scoped WebSocket, receive the initial dump, and extract the agent."""
    try:
        async with websockets.connect(ws_url, max_size=None) as ws:
            dump = await _receive_initial_dump(ws, timeout=timeout)
            task_views = dump.get("taskViewsByTaskId", {})
            if agent_id not in task_views:
                raise AgentNotFoundError(f"Agent {agent_id} not found in scoped frame")
            return _extract_snapshot(agent_id, dump)
    except websockets.exceptions.InvalidStatus as e:
        raise _wrap_invalid_status(e) from e


def fetch_agent_state(base_url: str, session_token: str, agent_id: str, timeout: float = 10.0) -> AgentSnapshot:
    """Fetch agent state via a one-shot WebSocket connection scoped to the agent.

    The connection uses ?scope=agent:<id> so the server only emits this
    agent's data. Reads exactly one frame and disconnects.
    """
    ws_url = _build_ws_url(base_url, session_token, scope=f"agent:{agent_id}")
    return asyncio.run(_fetch_agent_state_async(ws_url, agent_id, timeout))


async def _fetch_all_agents_async(ws_url: str, timeout: float) -> list[AgentSnapshot]:
    """Connect to the WebSocket, receive the initial dump, and extract all agents."""
    try:
        async with websockets.connect(ws_url, max_size=None) as ws:
            dump = await _receive_initial_dump(ws, timeout=timeout)
            task_views = dump.get("taskViewsByTaskId", {})
            task_updates = dump.get("taskUpdateByTaskId", {})
            return [
                _snapshot_from_view(task_id, view, task_updates.get(task_id))
                for task_id, view in task_views.items()
            ]
    except websockets.exceptions.InvalidStatus as e:
        raise _wrap_invalid_status(e) from e


def fetch_all_agents(
    base_url: str,
    session_token: str,
    scope: str = "all",
    timeout: float = 10.0,
) -> list[AgentSnapshot]:
    """Fetch all in-scope agent snapshots via a one-shot WebSocket connection.

    Defaults to scope='all'. Pass 'workspace:<id>' or 'project:<id>' to let
    the server narrow the dump.
    """
    ws_url = _build_ws_url(base_url, session_token, scope=scope)
    return asyncio.run(_fetch_all_agents_async(ws_url, timeout))


def _status_signature(snapshot: AgentSnapshot) -> tuple[Any, ...]:
    """Fields whose change should produce a fresh status emission.

    The server re-emits the task view on every internal task update — including
    ones that don't change anything user-visible (e.g. streaming partials, which
    bump the view's mtime but not its rendered fields). Comparing on the rendered
    fields lets the client emit one status per real change instead of one per
    server-side bump.
    """
    return (
        snapshot.status,
        snapshot.task_status,
        snapshot.current_activity,
        snapshot.last_activity,
        snapshot.task_completed,
        snapshot.task_total,
        snapshot.current_task_subject,
        snapshot.waiting_detail,
        tuple(snapshot.waiting_options) if snapshot.waiting_options is not None else None,
        snapshot.error_detail,
        snapshot.is_deleted,
    )


def _partial_signature(partial: dict[str, Any] | None) -> tuple[Any, ...]:
    """Identity fingerprint of an in-flight (streaming) chat message."""
    if partial is None:
        return ()
    return (partial.get("id"), json.dumps(partial.get("content", []), sort_keys=True, default=str))


async def _follow_loop(
    ws: Any,
    task_id: str,
    seen_message_ids: set[str],
    on_status: Callable[[AgentSnapshot], None],
    on_messages: Callable[[list[dict[str, Any]]], None],
    on_partial: Callable[[dict[str, Any] | None], None],
    last_status_sig: list[tuple[Any, ...]],
    last_partial_sig: list[tuple[Any, ...]],
    last_waiting_options: list[list[str] | None],
) -> ExitReason:
    """Process incremental WebSocket updates until a terminal/waiting state."""
    while True:
        raw = await ws.recv()
        dump = json.loads(raw)
        if dump is None:
            continue

        exit_reason: ExitReason | None = None

        # A frame may carry the view without the update; remember the latest
        # pending-question state so such view-only snapshots still render it.
        task_updates = dump.get("taskUpdateByTaskId", {})
        if task_id in task_updates:
            last_waiting_options[0] = _options_from_pending_question(task_updates[task_id])

        task_views = dump.get("taskViewsByTaskId", {})
        if task_id in task_views:
            snapshot = _snapshot_from_view(task_id, task_views[task_id]).model_copy(
                update={"waiting_options": last_waiting_options[0]}
            )
            sig = _status_signature(snapshot)
            if sig != last_status_sig[0]:
                last_status_sig[0] = sig
                on_status(snapshot)
            if _is_terminal_state(snapshot):
                exit_reason = ExitReason.TERMINAL_STATE
            elif _is_waiting_state(snapshot):
                exit_reason = ExitReason.WAITING

        if task_id in task_updates:
            update = task_updates[task_id]
            all_messages = update.get("chatMessages", [])
            new_messages = [m for m in all_messages if m.get("id") and m["id"] not in seen_message_ids]
            for m in new_messages:
                msg_id = m.get("id")
                if msg_id:
                    seen_message_ids.add(msg_id)
            if new_messages:
                on_messages(new_messages)

            partial = update.get("inProgressChatMessage")
            partial_sig = _partial_signature(partial)
            if partial_sig != last_partial_sig[0]:
                last_partial_sig[0] = partial_sig
                on_partial(partial)
                # The completed message will arrive as a chatMessages entry on a
                # subsequent frame; emit it via on_messages then so consumers
                # that don't process partials (text mode, anything that ignores
                # the new on_partial channel) still get the full assistant turn.

        if exit_reason is not None:
            return exit_reason


async def _follow_agent_async(
    ws_url: str,
    agent_id: str,
    on_status: Callable[[AgentSnapshot], None],
    on_messages: Callable[[list[dict[str, Any]]], None],
    on_reconnect: Callable[[], None] | None,
    on_partial: Callable[[dict[str, Any] | None], None] | None = None,
    max_retries: int = 5,
) -> ExitReason:
    """Follow an agent via the scoped WebSocket with reconnection support."""
    retry_count = 0
    seen_message_ids: set[str] = set()
    task_id = agent_id
    last_status_sig: list[tuple[Any, ...]] = [()]
    last_partial_sig: list[tuple[Any, ...]] = [()]
    last_waiting_options: list[list[str] | None] = [None]
    on_partial_cb: Callable[[dict[str, Any] | None], None] = on_partial or (lambda _p: None)

    while True:
        try:
            async with websockets.connect(ws_url, max_size=None) as ws:
                dump = await _receive_initial_dump(ws)

                task_views = dump.get("taskViewsByTaskId", {})
                if task_id not in task_views:
                    raise AgentNotFoundError(f"Agent {task_id} not found in scoped frame")

                snapshot = _extract_snapshot(task_id, dump)
                last_waiting_options[0] = snapshot.waiting_options

                is_reconnect = retry_count > 0
                if is_reconnect and on_reconnect is not None:
                    on_reconnect()

                last_status_sig[0] = _status_signature(snapshot)
                on_status(snapshot)

                new_messages = [m for m in snapshot.messages if m.get("id") and m["id"] not in seen_message_ids]
                for m in new_messages:
                    msg_id = m.get("id")
                    if msg_id:
                        seen_message_ids.add(msg_id)
                if new_messages:
                    on_messages(new_messages)

                retry_count = 0

                if _is_terminal_state(snapshot):
                    return ExitReason.TERMINAL_STATE
                if _is_waiting_state(snapshot):
                    return ExitReason.WAITING

                result = await _follow_loop(
                    ws,
                    task_id,
                    seen_message_ids,
                    on_status,
                    on_messages,
                    on_partial_cb,
                    last_status_sig,
                    last_partial_sig,
                    last_waiting_options,
                )
                return result

        except websockets.exceptions.InvalidStatus as e:
            raise _wrap_invalid_status(e) from e
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedError):
            retry_count += 1
            if retry_count > max_retries:
                return ExitReason.RETRY_EXHAUSTED
            delay = min(2 ** (retry_count - 1), _MAX_RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return ExitReason.CTRL_C


def follow_agent(
    base_url: str,
    session_token: str,
    agent_id: str,
    on_status: Callable[[AgentSnapshot], None],
    on_messages: Callable[[list[dict[str, Any]]], None],
    on_reconnect: Callable[[], None] | None = None,
    on_partial: Callable[[dict[str, Any] | None], None] | None = None,
    max_retries: int = 5,
) -> ExitReason:
    """Follow an agent via the scoped WebSocket, calling callbacks on status/message changes.

    on_status fires only when meaningful fields actually change (not on every
    server-side task-view bump). on_partial fires with the in-flight streaming
    chat message as it grows, and once with None when streaming completes.

    Returns an ExitReason indicating why the follow loop ended.
    """
    ws_url = _build_ws_url(base_url, session_token, scope=f"agent:{agent_id}")
    try:
        return asyncio.run(
            _follow_agent_async(
                ws_url,
                agent_id,
                on_status,
                on_messages,
                on_reconnect,
                on_partial,
                max_retries,
            )
        )
    except KeyboardInterrupt:
        return ExitReason.CTRL_C
