"""Parse the Sculptor background-task extension's structured lifecycle payloads.

pi-core has no background-execution primitive, so Sculptor ships a pinned
extension (`extensions/sculptor_background.ts`) that registers a `background`
tool. The tool starts a shell command in the background and returns IMMEDIATELY
(the agent keeps control; the turn does not block), then reports completion
out-of-band. Two payloads cross the wire, both parsed here:

START — the tool result's `{content, details}` envelope, with the task under
`details`:

    {"v": 1, "task": {"taskId", "toolCallId", "label", "command",
                      "pgid", "status": "running"}}

COMPLETION — a fire-and-forget `notify` whose `message` string is JSON carrying
the marker key:

    {"sculptorBackgroundTask": {"v": 1, "taskId", "toolCallId",
                                "status": "completed"|"failed",
                                "exitCode", "summary", "durationMs"}}

The adapter (`agent_wrapper`) maps START onto `BackgroundTaskStartedAgentMessage`
(+ records the child's `pgid` so a mid-flight interrupt can SIGTERM that group in
the environment) and COMPLETION onto `BackgroundTaskNotificationAgentMessage`.

Parsing is permissive — these payloads cross a subprocess / extension boundary,
so a malformed value or unknown version yields `None` (the caller then treats the
`background` tool call as an ordinary tool with no background lifecycle).

Wire contract shared with `extensions/sculptor_background.ts`: the version, the
marker key, and the field names below MUST match what that extension emits.
Changing one means editing both in the same change.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

# Payload schema version (the `v` field); a payload with a different `v` is
# treated as unparseable. MUST match `BACKGROUND_PAYLOAD_VERSION` in
# `extensions/sculptor_background.ts`.
BACKGROUND_PAYLOAD_VERSION: int = 1

# Top-level key under which the completion payload rides the `notify` message
# string. MUST match `BACKGROUND_NOTIFY_MARKER` in `extensions/sculptor_background.ts`.
BACKGROUND_NOTIFY_MARKER: str = "sculptorBackgroundTask"

# Completion statuses that mean the task has finished.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed"})


class BackgroundTaskStart(BaseModel):
    """The launch snapshot from a `background` tool's result `details`."""

    task_id: str
    tool_call_id: str
    label: str = "background"
    command: str = ""
    # The child's process-group id (it is spawned detached, so pgid == pid). The
    # adapter records it so a mid-flight interrupt can SIGTERM the group in the
    # environment without touching the pi process. -1 when the spawn produced no
    # pid (the child failed to start).
    pgid: int = -1
    status: str = "running"


class BackgroundTaskCompletion(BaseModel):
    """The completion snapshot from the out-of-band `notify` marker."""

    task_id: str
    tool_call_id: str
    status: str
    exit_code: int | None = None
    summary: str = ""
    duration_ms: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


def _coerce_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_background_start(payload: Any) -> BackgroundTaskStart | None:
    """Parse the `background` tool result envelope into a launch snapshot.

    `payload` is a `tool_execution_end.result` — the `{content, details}`
    envelope. The structured task lives under `details.task`. Returns `None`
    (the call then renders as an ordinary tool with no background lifecycle)
    when the envelope carries no recognized, version-matched task.
    """
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    if details.get("v") != BACKGROUND_PAYLOAD_VERSION:
        return None
    task = details.get("task")
    if not isinstance(task, dict):
        return None
    task_id = task.get("taskId")
    tool_call_id = task.get("toolCallId")
    if not isinstance(task_id, str) or not task_id:
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    # A spawn that produced no pid (the child failed to start) coerces to -1.
    pgid = _coerce_int(task.get("pgid"))
    return BackgroundTaskStart(
        task_id=task_id,
        tool_call_id=tool_call_id,
        label=task.get("label") if isinstance(task.get("label"), str) and task.get("label") else "background",
        command=task.get("command") if isinstance(task.get("command"), str) else "",
        pgid=pgid if pgid is not None else -1,
        status=task.get("status") if isinstance(task.get("status"), str) else "running",
    )


def parse_background_completion(message: Any) -> BackgroundTaskCompletion | None:
    """Parse a `notify` message string into a completion snapshot.

    `message` is the `extension_ui_request.message` of a fire-and-forget
    `notify`. It is JSON carrying `{BACKGROUND_NOTIFY_MARKER: {...}}`. Returns
    `None` for any notify that is not our background marker (a foreign/ordinary
    notify), so the caller can ignore it.
    """
    if not isinstance(message, str) or not message:
        return None
    try:
        decoded = json.loads(message)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    payload = decoded.get(BACKGROUND_NOTIFY_MARKER)
    if not isinstance(payload, dict):
        return None
    if payload.get("v") != BACKGROUND_PAYLOAD_VERSION:
        return None
    task_id = payload.get("taskId")
    tool_call_id = payload.get("toolCallId")
    status = payload.get("status")
    if not isinstance(task_id, str) or not task_id:
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    if not isinstance(status, str) or not status:
        return None
    return BackgroundTaskCompletion(
        task_id=task_id,
        tool_call_id=tool_call_id,
        status=status,
        exit_code=_coerce_int(payload.get("exitCode")),
        summary=payload.get("summary") if isinstance(payload.get("summary"), str) else "",
        duration_ms=_coerce_int(payload.get("durationMs")),
    )
