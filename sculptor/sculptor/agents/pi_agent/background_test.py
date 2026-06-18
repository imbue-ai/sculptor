"""Tests for the background-task lifecycle parsers.

Fixtures follow the wire shapes `extensions/sculptor_background.ts` emits:
- START rides a tool result envelope's `details`:
  `{v, task:{taskId, toolCallId, label, command, pgid, status}}`.
- COMPLETION rides a fire-and-forget `notify` message string:
  `{sculptorBackgroundTask:{v, taskId, toolCallId, status, exitCode, summary,
  durationMs}}`.
Both parsers must be permissive (the payloads cross an extension / subprocess
boundary) and reject a version skew rather than mis-parse.
"""

from __future__ import annotations

import json

from sculptor.agents.pi_agent.background import BACKGROUND_NOTIFY_MARKER
from sculptor.agents.pi_agent.background import BACKGROUND_PAYLOAD_VERSION
from sculptor.agents.pi_agent.background import parse_background_completion
from sculptor.agents.pi_agent.background import parse_background_start


def _start_envelope(task: object) -> dict:
    """Wrap a structured `task` in the {content, details} result envelope."""
    return {
        "content": [{"type": "text", "text": "Started background task build (pid 4242): make"}],
        "details": {"v": BACKGROUND_PAYLOAD_VERSION, "task": task},
    }


def _completion_message(**overrides: object) -> str:
    payload: dict = {
        "v": BACKGROUND_PAYLOAD_VERSION,
        "taskId": "bgt_tc1",
        "toolCallId": "tc1",
        "status": "completed",
        "exitCode": 0,
        "summary": "build ok",
        "durationMs": 1500,
    }
    payload.update(overrides)
    return json.dumps({BACKGROUND_NOTIFY_MARKER: payload})


# --- start payload --------------------------------------------------------


def test_parse_well_formed_start() -> None:
    started = parse_background_start(
        _start_envelope(
            {
                "taskId": "bgt_tc1",
                "toolCallId": "tc1",
                "label": "build",
                "command": "make",
                "pgid": 4242,
                "status": "running",
            }
        )
    )
    assert started is not None
    assert started.task_id == "bgt_tc1"
    assert started.tool_call_id == "tc1"
    assert started.label == "build"
    assert started.command == "make"
    assert started.pgid == 4242
    assert started.status == "running"


def test_parse_start_version_mismatch_returns_none() -> None:
    # An extension/binary skew must degrade to a plain tool call, never mis-parse.
    payload = {
        "content": [],
        "details": {"v": BACKGROUND_PAYLOAD_VERSION + 1, "task": {"taskId": "x", "toolCallId": "y"}},
    }
    assert parse_background_start(payload) is None


def test_parse_start_missing_ids_returns_none() -> None:
    assert parse_background_start(_start_envelope({"toolCallId": "tc1"})) is None  # no taskId
    assert parse_background_start(_start_envelope({"taskId": "bgt_tc1"})) is None  # no toolCallId
    assert parse_background_start(_start_envelope({"taskId": "", "toolCallId": "tc1"})) is None  # empty


def test_parse_start_missing_or_bad_envelope_returns_none() -> None:
    assert parse_background_start({"content": [{"type": "text", "text": "x"}]}) is None  # no details
    assert parse_background_start({"details": "not-a-dict"}) is None
    assert parse_background_start({"details": {"v": BACKGROUND_PAYLOAD_VERSION, "task": "not-a-dict"}}) is None
    assert parse_background_start(None) is None
    assert parse_background_start("bare string") is None


def test_parse_start_defaults_and_coercion() -> None:
    # A spawn that produced no pid (failed to start) coerces pgid to -1; missing
    # optional fields fall back to defaults rather than raising.
    started = parse_background_start(_start_envelope({"taskId": "bgt_tc1", "toolCallId": "tc1"}))
    assert started is not None
    assert started.label == "background"
    assert started.command == ""
    assert started.pgid == -1
    assert started.status == "running"
    # A bool must not be accepted as the pgid int.
    bool_pgid = parse_background_start(_start_envelope({"taskId": "bgt_tc1", "toolCallId": "tc1", "pgid": True}))
    assert bool_pgid is not None and bool_pgid.pgid == -1


# --- completion payload ---------------------------------------------------


def test_parse_well_formed_completion() -> None:
    completion = parse_background_completion(_completion_message())
    assert completion is not None
    assert completion.task_id == "bgt_tc1"
    assert completion.tool_call_id == "tc1"
    assert completion.status == "completed"
    assert completion.exit_code == 0
    assert completion.summary == "build ok"
    assert completion.duration_ms == 1500
    assert completion.is_terminal is True


def test_parse_failed_completion_is_terminal() -> None:
    completion = parse_background_completion(_completion_message(status="failed", exitCode=1, summary="boom"))
    assert completion is not None
    assert completion.status == "failed"
    assert completion.exit_code == 1
    assert completion.is_terminal is True


def test_parse_completion_ignores_foreign_notify() -> None:
    # A foreign / ordinary notify (no marker) must be ignored, not mis-parsed.
    assert parse_background_completion(json.dumps({"someOtherExtension": {"v": 1}})) is None
    assert parse_background_completion("a plain human notification") is None
    assert parse_background_completion("") is None
    assert parse_background_completion(None) is None
    assert parse_background_completion(123) is None


def test_parse_completion_version_mismatch_returns_none() -> None:
    assert parse_background_completion(_completion_message(v=BACKGROUND_PAYLOAD_VERSION + 1)) is None


def test_parse_completion_missing_required_fields_returns_none() -> None:
    assert (
        parse_background_completion(json.dumps({BACKGROUND_NOTIFY_MARKER: {"v": BACKGROUND_PAYLOAD_VERSION}})) is None
    )
    assert (
        parse_background_completion(
            json.dumps({BACKGROUND_NOTIFY_MARKER: {"v": BACKGROUND_PAYLOAD_VERSION, "taskId": "x"}})
        )
        is None
    )  # no toolCallId / status


def test_parse_completion_optional_fields_default() -> None:
    # exitCode (e.g. killed by signal) and durationMs may be absent.
    message = json.dumps(
        {
            BACKGROUND_NOTIFY_MARKER: {
                "v": BACKGROUND_PAYLOAD_VERSION,
                "taskId": "t",
                "toolCallId": "tc",
                "status": "failed",
            }
        }
    )
    completion = parse_background_completion(message)
    assert completion is not None
    assert completion.exit_code is None
    assert completion.duration_ms is None
    assert completion.summary == ""
