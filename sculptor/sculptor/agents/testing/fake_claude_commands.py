"""Command handler functions for FakeClaude.

Each handler takes parsed arguments and returns a list of JSONL dicts to emit
between the init and end messages.
"""

import glob as glob_module
import html
import inspect
import json
import os
import select
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.testing.fake_claude_jsonl import append_transcript_entry
from sculptor.agents.testing.fake_claude_jsonl import generate_id
from sculptor.agents.testing.fake_claude_jsonl import get_last_session_id
from sculptor.agents.testing.fake_claude_jsonl import make_assistant_message
from sculptor.agents.testing.fake_claude_jsonl import make_compact_boundary_message
from sculptor.agents.testing.fake_claude_jsonl import make_compact_status_message
from sculptor.agents.testing.fake_claude_jsonl import make_compact_summary_user_message
from sculptor.agents.testing.fake_claude_jsonl import make_end_message
from sculptor.agents.testing.fake_claude_jsonl import make_hook_callback_control_request
from sculptor.agents.testing.fake_claude_jsonl import make_init_message
from sculptor.agents.testing.fake_claude_jsonl import make_queued_command_attachment_entry
from sculptor.agents.testing.fake_claude_jsonl import make_streaming_interleaved_events
from sculptor.agents.testing.fake_claude_jsonl import make_streaming_text_events
from sculptor.agents.testing.fake_claude_jsonl import make_streaming_tool_events
from sculptor.agents.testing.fake_claude_jsonl import make_task_notification_message
from sculptor.agents.testing.fake_claude_jsonl import make_task_progress_message
from sculptor.agents.testing.fake_claude_jsonl import make_task_started_message
from sculptor.agents.testing.fake_claude_jsonl import make_task_updated_message
from sculptor.agents.testing.fake_claude_jsonl import make_text_block
from sculptor.agents.testing.fake_claude_jsonl import make_tool_result_message
from sculptor.agents.testing.fake_claude_jsonl import make_tool_use_block
from sculptor.agents.testing.fake_claude_jsonl import make_user_frame_echo
from sculptor.agents.testing.fake_claude_jsonl import make_workflow_agent_entry
from sculptor.agents.testing.fake_claude_jsonl import make_workflow_phase_entry
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM

SCULPTOR_MCP_SERVER_NAME = CLAUDE_CODE_HARNESS.mcp_server_name
SCULPTOR_MCP_ASK_TOOL_NAME = CLAUDE_CODE_HARNESS.mcp_ask_tool_name
SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_NAME = CLAUDE_CODE_HARNESS.mcp_exit_plan_mode_tool_name
SCULPTOR_MCP_ASK_TOOL_FQN = CLAUDE_CODE_HARNESS.mcp_ask_tool_fqn
SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN = CLAUDE_CODE_HARNESS.mcp_exit_plan_mode_tool_fqn
PRE_COMPACT_CALLBACK_ID = CLAUDE_CODE_HARNESS.pre_compact_callback_id

_TOOL_TEXT_PREFIX = "I'll do that."


def _emit_messages_to_stdout(messages: list[dict]) -> None:
    """Write JSONL messages directly to stdout and flush."""
    for msg in messages:
        sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _make_tool_assistant_message(
    message_id: str,
    tool_blocks: list[dict],
    emit_streaming: bool,
    parent_tool_use_id: str | None = None,
    text_prefix: str = _TOOL_TEXT_PREFIX,
) -> list[dict]:
    """Build an assistant message with text prefix + tool use blocks, optionally preceded by streaming events."""
    content_blocks = [make_text_block(text_prefix)] + tool_blocks
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(
            make_streaming_tool_events(
                message_id=message_id,
                tool_blocks=tool_blocks,
                text_prefix=text_prefix,
                parent_tool_use_id=parent_tool_use_id,
            )
        )
    messages.append(
        make_assistant_message(
            message_id=message_id,
            content_blocks=content_blocks,
            parent_tool_use_id=parent_tool_use_id,
        )
    )
    return messages


def _emit_mcp_tool_call(tool_fqn: str, arguments: dict, rpc_id: int = 1) -> str:
    """Send a `tools/call` MCP control_request on stdout and return its
    envelope ``request_id`` (used to match the eventual control_response)."""
    if tool_fqn == SCULPTOR_MCP_ASK_TOOL_FQN:
        short_name = SCULPTOR_MCP_ASK_TOOL_NAME
    elif tool_fqn == SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN:
        short_name = SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_NAME
    else:
        raise ValueError(f"Unknown Sculptor MCP tool fqn: {tool_fqn}")

    request_id = generate_id("mcp_req")
    control_request = {
        "type": "control_request",
        "request_id": request_id,
        "request": {
            "subtype": "mcp_message",
            "server_name": SCULPTOR_MCP_SERVER_NAME,
            "message": {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "method": "tools/call",
                "params": {"name": short_name, "arguments": arguments},
            },
        },
    }
    sys.stdout.write(json.dumps(control_request) + "\n")
    sys.stdout.flush()
    return request_id


def _emit_mcp_tool_call_and_wait_for_response(
    tool_use_id: str,
    tool_fqn: str,
    arguments: dict,
    timeout_seconds: float = 180.0,
    expect_error: bool = False,
) -> str:
    """Send a `tools/call` MCP control_request on stdout and block reading stdin
    until the matching control_response arrives. Returns the response text.

    By default raises ``RuntimeError`` if the MCP server returns an error
    envelope. Pass ``expect_error=True`` to return the error message string
    instead — used by the malformed-input handlers that intentionally trigger
    a JSON-RPC error to verify the MCP server's input validation.

    Raises ``RuntimeError`` if the response does not arrive within
    ``timeout_seconds``.
    """
    request_id = _emit_mcp_tool_call(tool_fqn=tool_fqn, arguments=arguments)
    return _read_mcp_control_response_text(request_id, tool_use_id, timeout_seconds, expect_error=expect_error)


# Unified stdin router.
#
# Every stdin read in FakeClaude funnels through one router so a frame that
# arrives while a cycle is held open is classified exactly once and never
# silently dropped. It reads the raw fd (via ``sys.stdin.fileno()``) into a
# single buffer: mixing ``sys.stdin``'s BufferedReader with raw ``os.read``
# splits complete lines across two invisible buffers, the flake behind SCU-783
# (a matching control_response stranded in Python's buffer where ``select`` on
# the fd can't see it). With one buffer, whatever a reader pulls off stdin but
# doesn't itself consume stays available: unparsed bytes remain in the buffer,
# and a parsed control_response destined for a different reader is stashed for
# it (see ``stash_control_response``) rather than discarded.
#
# Classification is uniform, mirroring the real CLI:
#   * an ``interrupt`` control_request exits the process (SIGTERM code);
#   * a ``control_response`` goes to whichever reader is waiting on its id,
#     stashed until that reader asks for it;
#   * a ``user`` frame arriving mid-cycle is *absorbed* — recorded as a
#     ``queued_command`` attachment and, under ``--replay-user-messages``,
#     echoed on stdout (the real CLI's mid-turn steering);
#   * anything else (a ``get_context_usage`` request, injected chrome events)
#     is ignored.
# A ``user`` frame read *between* cycles is turn-starting instead, so the
# between-cycle reader classifies it itself rather than absorbing it.

# Launch-time flags governing absorption, set by ``configure_stdin_router``.
_REPLAY_USER_MESSAGES: bool = False
_PERSIST_SESSION: bool = True

# Contents of frames absorbed mid-cycle in the current turn, in arrival order.
# ``handle_reference_absorbed`` reads this so a scripted cycle can prove it saw
# the steered content; ``clear_absorbed_frames`` resets it per cycle.
_ABSORBED_FRAMES: list[str] = []

# Sentinels returned by ``_StdinRouter.next_frame`` when no frame is available.
_STDIN_TIMEOUT = object()
_STDIN_EOF = object()


class _StdinRouter:
    """Sole owner of FakeClaude's stdin fd (see the module comment above)."""

    def __init__(self) -> None:
        self._buffer: bytes = b""
        self._eof: bool = False
        # control_responses read by a reader that wasn't waiting on them, kept
        # for whichever reader is (keyed by request id). FakeClaude waits for
        # each response synchronously, so this is usually empty; it exists so a
        # response is never dropped when one reader pulls another's off stdin.
        self._stashed_control_responses: dict[str, dict] = {}

    def reset(self) -> None:
        """Drop buffered bytes, stashed responses, and EOF (tests reuse one process)."""
        self._buffer = b""
        self._eof = False
        self._stashed_control_responses = {}

    def stash_control_response(self, request_id: str, envelope: dict) -> None:
        """Hold a control_response envelope for the reader awaiting ``request_id``."""
        self._stashed_control_responses[request_id] = envelope

    def pop_stashed_response(self, request_id: str) -> dict | None:
        """Return and remove a previously stashed response for ``request_id``, if any."""
        return self._stashed_control_responses.pop(request_id, None)

    def _pop_frame(self, flush_partial: bool = False) -> dict | None:
        """Return the next complete, parseable JSON object already buffered.

        Blank and unparseable lines (and non-object JSON) are skipped; a
        partial trailing line normally stays buffered for the next read. Pass
        ``flush_partial`` at EOF to also consume a final line that arrived
        without a trailing newline, so a last frame isn't dropped (the old
        ``for line in sys.stdin`` iterator yielded it).
        """
        while b"\n" in self._buffer or (flush_partial and self._buffer):
            if b"\n" in self._buffer:
                raw_line, _, self._buffer = self._buffer.partition(b"\n")
            else:
                raw_line, self._buffer = self._buffer, b""
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        return None

    def _fill(self, timeout: float) -> None:
        """Block up to ``timeout`` seconds for more stdin bytes into the buffer."""
        if self._eof:
            return
        try:
            fd = sys.stdin.fileno()
        except (ValueError, OSError):
            # No real fd (closed stream / non-fd stdin) — treat as end of input.
            self._eof = True
            return
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return
        chunk = os.read(fd, 8192)
        if not chunk:
            self._eof = True
            return
        self._buffer += chunk

    def next_frame(self, timeout: float) -> dict | object:
        """Return the next parsed JSON frame, else ``_STDIN_TIMEOUT`` (nothing
        arrived within ``timeout``) or ``_STDIN_EOF`` (stdin closed)."""
        frame = self._pop_frame()
        if frame is not None:
            return frame
        if not self._eof:
            self._fill(timeout)
        # At EOF, flush a final newline-less line so a last frame isn't dropped.
        frame = self._pop_frame(flush_partial=self._eof)
        if frame is not None:
            return frame
        return _STDIN_EOF if self._eof else _STDIN_TIMEOUT


_STDIN_ROUTER = _StdinRouter()


def configure_stdin_router(replay_user_messages: bool, persist_session: bool) -> None:
    """Apply launch-time flags and start each invocation from a clean slate."""
    global _REPLAY_USER_MESSAGES, _PERSIST_SESSION
    _REPLAY_USER_MESSAGES = replay_user_messages
    _PERSIST_SESSION = persist_session
    _STDIN_ROUTER.reset()
    _ABSORBED_FRAMES.clear()


def clear_absorbed_frames() -> None:
    """Reset the absorbed-frame record at the start of a cycle so each turn's
    ``reference_absorbed`` sees only the frames absorbed during that turn."""
    _ABSORBED_FRAMES.clear()


def _user_frame_content(frame: dict) -> str:
    """Extract a user frame's message content, HTML-unescaped and stripped
    (the same normalization the between-cycle reader applies to a prompt)."""
    content = frame.get("message", {}).get("content", "")
    return html.unescape(content).strip() if isinstance(content, str) else ""


def _exit_if_interrupt(frame: dict) -> None:
    """Exit with the SIGTERM code if ``frame`` is an interrupt control_request.

    Mirrors real Claude's event loop: a Stop-button click arrives as an
    ``interrupt`` control_request and tears the turn down promptly.
    """
    if (
        frame.get("type") == "control_request"
        and isinstance(frame.get("request"), dict)
        and frame["request"].get("subtype") == "interrupt"
    ):
        sys.exit(AGENT_EXIT_CODE_FROM_SIGTERM)


def _absorb_user_frame(frame: dict) -> None:
    """Record a mid-cycle user frame the way the real CLI absorbs steering.

    Appends a ``queued_command`` attachment to the session transcript (so the
    on-disk shape distinguishes an absorbed frame from a turn-starting plain
    user message) and, under ``--replay-user-messages``, echoes the frame on
    stdout — emitted here, inside the open turn before its ``result``, which is
    the steered replay position the spike pinned (as opposed to a turn-starting
    frame's echo, which lands just after a fresh ``init``).
    """
    content = _user_frame_content(frame)
    _ABSORBED_FRAMES.append(content)
    session_id = get_last_session_id()
    if _PERSIST_SESSION and session_id is not None:
        append_transcript_entry(session_id, make_queued_command_attachment_entry(session_id, content))
    if _REPLAY_USER_MESSAGES:
        _emit_event(make_user_frame_echo(content))


def _route_mid_cycle_frame(frame: dict) -> None:
    """Apply the universal side effects for a frame a mid-cycle reader is not
    itself consuming: an interrupt exits, a user frame is absorbed, a
    control_response meant for a different reader is stashed for that reader,
    and anything else (a ``get_context_usage`` request, chrome events) is
    ignored."""
    _exit_if_interrupt(frame)
    frame_type = frame.get("type")
    if frame_type == "user":
        _absorb_user_frame(frame)
    elif frame_type == "control_response":
        envelope = frame.get("response", {})
        request_id = envelope.get("request_id")
        if request_id is not None:
            _STDIN_ROUTER.stash_control_response(request_id, envelope)


def read_next_user_prompt() -> str | None:
    """Block *between* cycles for the next turn-starting user frame.

    Returns the frame's (HTML-unescaped, stripped) content, or ``None`` when
    stdin closes first (EOF) so the caller exits instead of running a turn the
    user never sent. An ``interrupt`` control_request seen while idle exits with
    the SIGTERM code. A user frame here is turn-starting — it is NOT absorbed
    (absorption applies only to frames that land while a cycle is held open);
    control responses and other non-user frames are ignored while scanning.
    """
    while True:
        frame = _STDIN_ROUTER.next_frame(timeout=3600.0)
        if frame is _STDIN_TIMEOUT:
            continue
        if frame is _STDIN_EOF:
            return None
        assert isinstance(frame, dict)
        _exit_if_interrupt(frame)
        if frame.get("type") == "user":
            return _user_frame_content(frame)


def _read_mcp_control_responses(expected_request_ids: set[str], timeout_seconds: float) -> dict[str, dict]:
    """Block until an MCP ``control_response`` has arrived for every id in
    ``expected_request_ids``. Returns ``{request_id: mcp_response}``.

    Runs on the unified router, so a user frame that lands while the handler
    waits for its answer is absorbed rather than discarded, and a
    control_response meant for a different waiter (batched into the same read,
    or already seen by an earlier reader) is stashed for that waiter instead of
    being lost — the SCU-783 guarantee, extended from raw bytes to parsed frames.
    """
    remaining_ids = set(expected_request_ids)
    results: dict[str, dict] = {}
    # A response for one of our ids may already be waiting from an earlier read.
    for request_id in list(remaining_ids):
        stashed = _STDIN_ROUTER.pop_stashed_response(request_id)
        if stashed is not None:
            results[request_id] = stashed.get("response", {}).get("mcp_response", {})
            remaining_ids.discard(request_id)
    deadline = time.monotonic() + timeout_seconds
    while remaining_ids:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        frame = _STDIN_ROUTER.next_frame(timeout=min(remaining, 0.1))
        if frame is _STDIN_TIMEOUT:
            continue
        if frame is _STDIN_EOF:
            raise RuntimeError(f"stdin closed before MCP control_response(s) for request_ids={sorted(remaining_ids)}")
        assert isinstance(frame, dict)
        if frame.get("type") == "control_response":
            response = frame.get("response", {})
            request_id = response.get("request_id")
            if request_id in remaining_ids:
                results[request_id] = response.get("response", {}).get("mcp_response", {})
                remaining_ids.discard(request_id)
                continue
        # Not one of ours (a user frame, an interrupt, or another waiter's
        # response) — route it so it is absorbed / stashed, never dropped.
        _route_mid_cycle_frame(frame)
    if remaining_ids:
        raise RuntimeError(f"Timed out waiting for MCP control_response(s) for request_ids={sorted(remaining_ids)}")
    return results


def _emit_context_usage_response(request_id: str) -> None:
    """Answer a Sculptor ``get_context_usage`` control request with a fixed
    context snapshot, in the envelope shape the output processor expects
    (``_is_context_usage_response`` / ``_handle_context_usage_response``)."""
    response = {
        "type": "control_response",
        "response": {
            "request_id": request_id,
            "response": {
                "totalTokens": 120000,
                "maxTokens": 200000,
                "percentage": 60.0,
                "autoCompactThreshold": 160000,
            },
        },
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _answer_context_usage_and_wait_for_sentinel(sentinel: Path, timeout_seconds: float) -> None:
    """Block until ``sentinel`` exists, answering the ``get_context_usage``
    control request Sculptor sends after a turn-end while we wait.

    Real Claude answers that request during a background-task wait, which makes
    the output processor flush the turn's (otherwise-stashed) TurnMetrics
    mid-hold — so ``TurnMetricsAgentMessage`` is pending in message_conversion
    while the request is still open. FakeClaude's default background hold never
    answers it (``_route_mid_cycle_frame`` ignores get_context_usage), so that
    pending-metrics state — and the bugs it exposes — can't be reproduced
    end-to-end; this reproduces it.

    Reads stdin through the unified router, so a user frame that lands during
    the wait is absorbed and an interrupt still exits promptly.
    """
    answered = False
    deadline = time.monotonic() + timeout_seconds
    while True:
        if sentinel.exists():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"background_subagent pause timed out waiting for {sentinel}")
        frame = _STDIN_ROUTER.next_frame(timeout=min(remaining, 0.05))
        if frame is _STDIN_TIMEOUT:
            continue
        if frame is _STDIN_EOF:
            # stdin closed (e.g. -p mode) — keep polling the sentinel only.
            time.sleep(min(remaining, 0.05))
            continue
        assert isinstance(frame, dict)
        request = frame.get("request")
        if (
            not answered
            and frame.get("type") == "control_request"
            and isinstance(request, dict)
            and request.get("subtype") == "get_context_usage"
        ):
            request_id = frame.get("request_id")
            if isinstance(request_id, str):
                _emit_context_usage_response(request_id)
                answered = True
                continue
        # Interrupt exit, user-frame absorption, cross-waiter stashing, etc.
        _route_mid_cycle_frame(frame)


def _extract_mcp_response_text(mcp_response: dict) -> str:
    content = mcp_response.get("result", {}).get("content", [])
    if not content:
        return ""
    return content[0].get("text", "")


def _read_mcp_control_response_text(
    expected_request_id: str, tool_use_id: str, timeout_seconds: float, expect_error: bool = False
) -> str:
    """Block reading stdin until a matching MCP ``control_response`` arrives.

    See ``_read_mcp_control_responses`` for the raw-fd reading rationale.
    """
    try:
        responses = _read_mcp_control_responses({expected_request_id}, timeout_seconds)
    except RuntimeError:
        raise RuntimeError(f"Timed out waiting for MCP control_response for tool_use_id={tool_use_id}")
    mcp_response = responses[expected_request_id]
    if "error" in mcp_response:
        if expect_error:
            err = mcp_response["error"]
            return f"MCP error {err.get('code')}: {err.get('message', '')}"
        raise RuntimeError(f"MCP error response for tool_use_id={tool_use_id}: {mcp_response['error']}")
    if expect_error:
        raise RuntimeError(
            f"Expected MCP error response for tool_use_id={tool_use_id} but got success: {mcp_response}"
        )
    return _extract_mcp_response_text(mcp_response)


def handle_default(emit_streaming: bool) -> list[dict]:
    """Handle prompts without a fake_claude: prefix."""
    text = "[FakeClaude] Task completed."
    message_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=message_id, text=text))
    messages.append(
        make_assistant_message(
            message_id=message_id,
            content_blocks=[make_text_block(text)],
        )
    )
    return messages


def handle_text(args: dict, emit_streaming: bool) -> list[dict]:
    """Handle the text command."""
    text = args["text"]
    message_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=message_id, text=text))
    messages.append(
        make_assistant_message(
            message_id=message_id,
            content_blocks=[make_text_block(text)],
        )
    )
    return messages


def _emit_event(event: dict) -> None:
    """Write a single JSONL event to stdout and flush immediately."""
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def handle_stream_text(args: dict, emit_streaming: bool) -> list[dict]:
    """Handle the stream_text command — emits text incrementally with real delays.

    Unlike ``handle_text`` which returns all events at once, this handler writes
    streaming events directly to stdout with configurable delays between chunks.
    This simulates real Claude streaming behavior for integration tests that need
    to observe auto-scroll, progressive rendering, etc.

    Args:
        text: The full text to stream.
        chunk_size: Number of characters per streaming chunk (default: 20).
        delay_seconds: Seconds to wait between chunks (default: 0.1).
    """
    text = args["text"]
    chunk_size: int = args.get("chunk_size", 20)
    delay_seconds: float = args.get("delay_seconds", 0.1)

    message_id = generate_id("msg")

    if emit_streaming:
        # message_start
        _emit_event(
            {
                "type": "stream_event",
                "event": {
                    "type": "message_start",
                    "message": {
                        "id": message_id,
                        "type": "message",
                        "role": "assistant",
                        "model": "fake-claude",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
                "parent_tool_use_id": None,
            }
        )

        # content_block_start
        _emit_event(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            }
        )

        # Emit text in chunks with delays
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            _emit_event(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": chunk},
                    },
                }
            )
            time.sleep(delay_seconds)

        # content_block_stop
        _emit_event({"type": "stream_event", "event": {"type": "content_block_stop", "index": 0}})

        # message_stop
        _emit_event({"type": "stream_event", "event": {"type": "message_stop"}})

    # Return only the final assistant message (streaming events already emitted)
    return [
        make_assistant_message(
            message_id=message_id,
            content_blocks=[make_text_block(text)],
        )
    ]


def handle_write_file(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the write_file command — writes a file and returns JSONL."""
    file_path = args["file_path"]
    content = args["content"]

    full_path = Path(cwd) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name="Write",
        tool_input={"file_path": str(full_path), "content": content},
    )

    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content="File written successfully."))
    return messages


def handle_edit_file(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the edit_file command — edits a file and returns JSONL."""
    file_path = args["file_path"]
    old_string = args["old_string"]
    new_string = args["new_string"]

    full_path = Path(cwd) / file_path
    file_content = full_path.read_text()

    if old_string not in file_content:
        is_error = True
        result_content = f"old_string not found in {file_path}"
    else:
        file_content = file_content.replace(old_string, new_string, 1)
        full_path.write_text(file_content)
        is_error = False
        result_content = "File edited successfully."

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name="Edit",
        tool_input={"file_path": str(full_path), "old_string": old_string, "new_string": new_string},
    )

    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content=result_content, is_error=is_error))
    return messages


def _build_bash_tool_input(args: dict) -> dict:
    """Build the tool_input dict for a Bash tool call, including optional description."""
    tool_input: dict = {"command": args["command"]}
    if "description" in args:
        tool_input["description"] = args["description"]
    return tool_input


def _run_bash_and_make_tool_blocks(args: dict, cwd: str) -> tuple[dict, str, bool]:
    """Run a bash command and return (tool_block, output, is_error)."""
    command = args["command"]
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)  # noqa: S602
    if result.returncode != 0:
        is_error = True
        output = result.stderr or result.stdout
    else:
        is_error = False
        output = result.stdout
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name="Bash",
        tool_input=_build_bash_tool_input(args),
    )
    return tool_block, output, is_error


def handle_bash(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the bash command — runs a shell command and returns JSONL.

    When streaming is enabled, the tool_use events are flushed to stdout
    *before* the command executes so the output processor can record the
    tool start time — matching production Claude Code behaviour where the
    tool_use stream arrives before execution begins.
    """
    command = args["command"]
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(tool_id=tool_id, tool_name="Bash", tool_input=_build_bash_tool_input(args))
    message_id = generate_id("msg")

    # Build assistant message (with optional streaming events)
    assistant_messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )

    if emit_streaming:
        # Flush tool_use events immediately so the output processor
        # records the start time before the command runs.
        for msg in assistant_messages:
            _emit_event(msg)
        assistant_messages = []

    # Now run the actual command
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)  # noqa: S602
    if result.returncode != 0:
        is_error = True
        output = result.stderr or result.stdout
    else:
        is_error = False
        output = result.stdout

    tool_result_msg = make_tool_result_message(tool_use_id=tool_id, content=output, is_error=is_error)

    if emit_streaming:
        # Flush tool result immediately so the output processor captures it
        # and calculates the correct duration before the process exits.
        _emit_event(tool_result_msg)
        return assistant_messages
    else:
        messages = assistant_messages
        messages.append(tool_result_msg)
        return messages


def _wait_until(
    timeout_seconds: float,
    poll_interval: float,
    done: Callable[[], bool] | None = None,
) -> bool:
    """Wait until ``done()`` returns true or ``timeout_seconds`` elapses.

    Polls stdin throughout via the unified router: a Stop-button click arrives
    as an ``interrupt`` control_request and exits with the SIGTERM code
    (mirroring real Claude's event loop and keeping interrupt tests fast),
    while a user frame that lands during the wait is absorbed as steering
    rather than dropped. SIGTERM itself still terminates via the signal handler
    installed in ``main()`` — including on ``-p``-mode callers whose stdin is
    closed.

    With ``done`` omitted, simply waits out the full timeout. Returns whether
    ``done()`` fired before the timeout.
    """
    deadline = time.monotonic() + timeout_seconds
    while done is None or not done():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        frame = _STDIN_ROUTER.next_frame(timeout=min(remaining, poll_interval))
        if frame is _STDIN_TIMEOUT:
            continue
        if frame is _STDIN_EOF:
            # stdin closed (e.g. -p mode) — keep polling done()/timeout without it.
            time.sleep(min(remaining, poll_interval))
            continue
        assert isinstance(frame, dict)
        _route_mid_cycle_frame(frame)
    return True


def handle_sleep(args: dict, emit_streaming: bool) -> list[dict]:
    """Sleep for ``seconds`` while staying responsive to stdin interrupts.

    Tests that specifically want to exercise the SIGTERM fallback path (rather
    than the fast interrupt-control_request path) should use
    ``fake_claude:ignore_stdin`` instead.
    """
    seconds: float = args.get("seconds", 120)
    _wait_until(timeout_seconds=seconds, poll_interval=0.5)
    return []


def handle_wait_for_file(args: dict, emit_streaming: bool) -> list[dict]:
    """Block until a sentinel file appears at ``path``.

    A signalled alternative to ``handle_sleep`` for integration tests that need
    the agent to stay busy until the test explicitly releases it. Like
    ``handle_sleep``, exits with the SIGTERM exit code on a stdin interrupt
    ``control_request``. ``timeout_seconds`` is a safety cap so a forgotten
    release fails loudly instead of hanging the runner.
    """
    timeout_seconds: float = args.get("timeout_seconds", 120)
    sentinel = Path(args["path"])
    if not _wait_until(timeout_seconds=timeout_seconds, poll_interval=0.05, done=sentinel.exists):
        raise RuntimeError(f"fake_claude:wait_for_file timed out after {timeout_seconds}s waiting for {sentinel}")
    return []


def handle_reference_absorbed(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit assistant text referencing the frames absorbed so far this cycle.

    A scripted way to prove the held cycle actually saw the steered content
    (scenario 1's "a scripted directive controls whether/how the fake assistant
    references the absorbed content in its remaining output"): pair it after a
    held handler in a ``multi_step`` so absorption happens during the hold and
    this step quotes it. ``prefix`` / ``separator`` shape the text; with nothing
    absorbed the body is ``empty`` (default ``"(none)"``).
    """
    prefix: str = args.get("prefix", "Absorbed: ")
    separator: str = args.get("separator", " | ")
    empty: str = args.get("empty", "(none)")
    body = separator.join(_ABSORBED_FRAMES) if _ABSORBED_FRAMES else empty
    text = prefix + body

    message_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=message_id, text=text))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=[make_text_block(text)]))
    return messages


_TASK_DEFAULTS: dict = {
    "description": "",
    "activeForm": None,
    "status": "pending",
    "blocks": [],
    "blockedBy": [],
    "owner": None,
    "metadata": {},
}


def _resolve_tasks_dir() -> Path:
    session_id = get_last_session_id()
    if session_id is None:
        raise RuntimeError("FakeClaude session id was not set before task_create/task_update")
    # Mirror real Claude Code's path resolution. Claude honors $CLAUDE_CONFIG_DIR
    # as the base for its on-disk state; Sculptor's process_manager forwards
    # CLAUDE_* env vars to the subprocess, so the test fixture must follow the
    # same rule to stay faithful to real-world behavior.
    config_dir_override = os.environ.get("CLAUDE_CONFIG_DIR")
    config_dir = Path(config_dir_override) if config_dir_override else Path.home() / ".claude"
    tasks_dir = config_dir / "tasks" / session_id
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir


def _build_task_payload(args: dict, existing: dict | None = None) -> dict:
    payload: dict = {"id": str(args["id"]), "subject": args["subject"]} if existing is None else dict(existing)
    if existing is None:
        for field, default in _TASK_DEFAULTS.items():
            payload[field] = args.get(field, default)
    else:
        if "subject" in args:
            payload["subject"] = args["subject"]
        for field in _TASK_DEFAULTS:
            if field in args:
                payload[field] = args[field]
    return payload


def handle_task_create(args: dict, emit_streaming: bool) -> list[dict]:
    """Handle the task_create command.

    Writes the per-task JSON file under
    $HOME/.claude/tasks/{session_id}/{id}.json BEFORE emitting the
    matching TaskCreate tool_use + tool_result blocks so the output
    processor sees the file on disk by the time it reads the artifact.
    """
    payload = _build_task_payload(args)
    tasks_dir = _resolve_tasks_dir()
    (tasks_dir / f"{payload['id']}.json").write_text(json.dumps(payload, indent=2))

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name="TaskCreate",
        tool_input=dict(payload),
    )
    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content="Task created."))
    return messages


def handle_task_list(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit a read-only TaskList tool_use + tool_result. No filesystem side-effect."""
    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(tool_id=tool_id, tool_name="TaskList", tool_input=dict(args))
    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content="Tasks listed."))
    return messages


def handle_task_get(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit a read-only TaskGet tool_use + tool_result. No filesystem side-effect."""
    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(tool_id=tool_id, tool_name="TaskGet", tool_input=dict(args))
    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content="Task fetched."))
    return messages


def handle_write_corrupt_task(args: dict, emit_streaming: bool) -> list[dict]:
    """Drop a non-JSON file at $HOME/.claude/tasks/{session_id}/{id}.json.

    Exercises the reader's malformed-file tolerance. Emits a
    minimal text message so the turn registers in the chat panel.
    """
    tasks_dir = _resolve_tasks_dir()
    task_path = tasks_dir / f"{args['id']}.json"
    task_path.write_text(args.get("content", "this is not json"))

    message_id = generate_id("msg")
    return [make_assistant_message(message_id=message_id, content_blocks=[make_text_block("Corrupt task written.")])]


def handle_task_update(args: dict, emit_streaming: bool) -> list[dict]:
    """Handle the task_update command.

    Merges provided fields into any existing task JSON (creating it if
    absent). When status is 'deleted', removes the file instead.
    """
    tasks_dir = _resolve_tasks_dir()
    task_path = tasks_dir / f"{args['id']}.json"
    existing: dict | None = None
    if task_path.exists():
        existing = json.loads(task_path.read_text())

    if args.get("status") == "deleted":
        if task_path.exists():
            task_path.unlink()
        tool_input = {"id": str(args["id"]), "status": "deleted"}
    else:
        payload = _build_task_payload(args, existing=existing)
        task_path.write_text(json.dumps(payload, indent=2))
        tool_input = dict(payload)

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name="TaskUpdate",
        tool_input=tool_input,
    )
    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content="Task updated."))
    return messages


def handle_ask_user_question(args: dict, emit_streaming: bool) -> list[dict]:
    """Handle the ask_user_question command via the SDK MCP path.

    Emits an assistant message containing a ``mcp__sculptor__ask_user_question``
    tool_use block, sends the matching MCP ``tools/call`` control_request on
    stdout, blocks reading stdin until Sculptor's MCP server responds, then
    emits the resulting tool_result followed by a short follow-up assistant
    message. Real Claude continues the turn with text or further tool calls
    once it receives the user's answer; the trailing assistant message keeps
    the chat-message count consistent with the old kill-and-resume flow.
    """
    questions = args["questions"]

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": questions},
    )

    assistant_messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    _emit_messages_to_stdout(assistant_messages)

    text = _emit_mcp_tool_call_and_wait_for_response(
        tool_use_id=tool_id,
        tool_fqn=SCULPTOR_MCP_ASK_TOOL_FQN,
        arguments={"questions": questions},
    )
    follow_up_text = "[FakeClaude] Task completed."
    follow_up_id = generate_id("msg")
    follow_up: list[dict] = []
    if emit_streaming:
        follow_up.extend(make_streaming_text_events(message_id=follow_up_id, text=follow_up_text))
    follow_up.append(make_assistant_message(message_id=follow_up_id, content_blocks=[make_text_block(follow_up_text)]))
    return [make_tool_result_message(tool_use_id=tool_id, content=text), *follow_up]


def handle_ask_user_question_and_continue(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate Claude ignoring the 'stop after AskUserQuestion' instruction.

    Emits AskUserQuestion with an error tool_result (as real Claude Code SDK
    would produce), then a follow-up assistant text message — all in one
    process invocation. This reproduces the scenario where Claude treats the
    AskUserQuestion error as a rejection and keeps working.
    """
    questions = args["questions"]
    continuation_text = args.get("continuation_text", "[FakeClaude] Continued after AskUserQuestion.")

    # 1. Assistant message with mcp__sculptor__ask_user_question tool_use block
    ask_message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": questions},
    )
    messages = _make_tool_assistant_message(
        message_id=ask_message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )

    # 2. Error tool_result (as Claude Code SDK returns for unrecognized tools)
    messages.append(make_tool_result_message(tool_use_id=tool_id, content="Tool not available.", is_error=True))

    # 3. Follow-up assistant text message (Claude ignores the stop instruction)
    continuation_message_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=continuation_message_id, text=continuation_text))
    messages.append(
        make_assistant_message(
            message_id=continuation_message_id,
            content_blocks=[make_text_block(continuation_text)],
        )
    )

    return messages


def handle_ask_user_question_then_api_error(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit a Sculptor AUQ tool_use block, then immediately fail the request.

    Reproduces the SCU-530 scenario: the agent CLI asks a question via MCP, but
    the request errors out (API timeout, network partition, system suspend)
    before the user can answer. The wrapper then emits a
    ``RequestFailureAgentMessage``. The runner must clear
    ``is_waiting_for_question_answer`` on that failure so subsequent user
    messages get dispatched instead of being silently queued.
    """
    questions = args["questions"]
    error_message = args.get("message", "API Error: Request timed out")

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": questions},
    )
    assistant_messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    _emit_messages_to_stdout(assistant_messages)

    # Fail the request before any MCP control_request flow — simulates the CLI
    # hitting an API error while it was waiting on the user's answer. Mirrors
    # ``handle_api_error``: emit an error end message and exit non-zero so the
    # wrapper emits a ``RequestFailureAgentMessage``.
    error_session_id = generate_id("session")
    _emit_event(make_init_message(error_session_id))
    _emit_event(make_end_message(error_session_id, is_error=True, result=error_message))
    sys.exit(1)


def handle_ask_user_question_invalid_input(emit_streaming: bool) -> list[dict]:
    """Send a malformed ``mcp__sculptor__ask_user_question`` call to verify that
    the MCP server validates the agent's arguments and responds with a JSON-RPC
    error rather than dangling.

    The malformed input — ``multiSelect: 'false'`` (string instead of bool) —
    is the canonical agent type-typo: lenient pydantic would coerce it, strict
    rejects it. The handler expects an MCP error response, then emits an
    error tool_result and a follow-up text message simulating the agent
    receiving the failure and moving on.
    """
    bad_questions = [
        {
            "question": "Pick one",
            "header": "Color",
            "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": "cool"}],
            "multiSelect": "false",
        }
    ]

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": bad_questions},
    )
    assistant_messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    _emit_messages_to_stdout(assistant_messages)

    error_text = _emit_mcp_tool_call_and_wait_for_response(
        tool_use_id=tool_id,
        tool_fqn=SCULPTOR_MCP_ASK_TOOL_FQN,
        arguments={"questions": bad_questions},
        expect_error=True,
    )

    follow_up_text = "[FakeClaude] Got the expected MCP error and moved on."
    follow_up_id = generate_id("msg")
    follow_up: list[dict] = []
    if emit_streaming:
        follow_up.extend(make_streaming_text_events(message_id=follow_up_id, text=follow_up_text))
    follow_up.append(make_assistant_message(message_id=follow_up_id, content_blocks=[make_text_block(follow_up_text)]))
    return [make_tool_result_message(tool_use_id=tool_id, content=error_text, is_error=True), *follow_up]


def handle_enter_plan_mode(emit_streaming: bool) -> list[dict]:
    """Handle the enter_plan_mode command — emits EnterPlanMode tool use only, no tool result."""
    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name="EnterPlanMode",
        tool_input={},
    )

    return _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )


def handle_enter_plan_mode_and_ask(args: dict, emit_streaming: bool) -> list[dict]:
    """Enter plan mode and immediately ask a question — in a single CLI turn.

    Under the SDK MCP path the AUQ resolves via ``mcp__sculptor__ask_user_question``
    rather than the killed-and-resumed built-in, and the MCP flow never blocks the
    CLI mid-stream.
    """
    questions = args["questions"]

    # 1. EnterPlanMode turn — emitted normally (all events complete)
    enter_message_id = generate_id("msg")
    enter_tool_id = generate_id("toolu")
    enter_tool_block = make_tool_use_block(
        tool_id=enter_tool_id,
        tool_name="EnterPlanMode",
        tool_input={},
    )
    messages = _make_tool_assistant_message(
        message_id=enter_message_id,
        tool_blocks=[enter_tool_block],
        emit_streaming=emit_streaming,
    )

    # 2. Tool result for EnterPlanMode
    messages.append(
        make_tool_result_message(
            tool_use_id=enter_tool_id,
            content="Plan mode entered.",
        )
    )

    # 3. AUQ turn via MCP — same shape as `handle_ask_user_question`.
    ask_message_id = generate_id("msg")
    ask_tool_id = generate_id("toolu")
    ask_tool_block = make_tool_use_block(
        tool_id=ask_tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": questions},
    )
    messages.extend(
        _make_tool_assistant_message(
            message_id=ask_message_id,
            tool_blocks=[ask_tool_block],
            emit_streaming=emit_streaming,
        )
    )
    _emit_messages_to_stdout(messages)

    text = _emit_mcp_tool_call_and_wait_for_response(
        tool_use_id=ask_tool_id,
        tool_fqn=SCULPTOR_MCP_ASK_TOOL_FQN,
        arguments={"questions": questions},
    )
    follow_up_text = "[FakeClaude] Task completed."
    follow_up_id = generate_id("msg")
    follow_up: list[dict] = []
    if emit_streaming:
        follow_up.extend(make_streaming_text_events(message_id=follow_up_id, text=follow_up_text))
    follow_up.append(make_assistant_message(message_id=follow_up_id, content_blocks=[make_text_block(follow_up_text)]))
    return [make_tool_result_message(tool_use_id=ask_tool_id, content=text), *follow_up]


def handle_exit_plan_mode(emit_streaming: bool) -> list[dict]:
    """Handle the exit_plan_mode command via the SDK MCP path.

    Emits a ``mcp__sculptor__exit_plan_mode`` tool_use block, sends the
    matching MCP ``tools/call`` control_request, blocks reading stdin until
    Sculptor's MCP server responds (driven by the user's approval / revise /
    dismiss action), then emits the resulting tool_result followed by a
    short follow-up assistant message.

    The MCP tool's input schema is empty: the model writes the plan to its
    plan file (driven by the plan-mode system reminder) and calls this tool
    with no arguments. Tests that need the UI to find a plan file should use
    a prior ``write_file`` step targeting ``.claude/plans/<name>.md``.
    """
    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_block = make_tool_use_block(
        tool_id=tool_id,
        tool_name=SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN,
        tool_input={},
    )
    assistant_messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    _emit_messages_to_stdout(assistant_messages)

    text = _emit_mcp_tool_call_and_wait_for_response(
        tool_use_id=tool_id,
        tool_fqn=SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN,
        arguments={},
    )
    follow_up_text = "[FakeClaude] Task completed."
    follow_up_id = generate_id("msg")
    follow_up: list[dict] = []
    if emit_streaming:
        follow_up.extend(make_streaming_text_events(message_id=follow_up_id, text=follow_up_text))
    follow_up.append(make_assistant_message(message_id=follow_up_id, content_blocks=[make_text_block(follow_up_text)]))
    return [make_tool_result_message(tool_use_id=tool_id, content=text), *follow_up]


def handle_auto_compact(args: dict, plugin_dir: str | None, emit_streaming: bool) -> list[dict]:
    """Simulate auto-compaction via the stdout/stdin control protocol.

    Matches the real CLI's message sequence:
    1. PreCompact ``hook_callback`` control_request (stdout, real-time)
    2. ``control_response`` read from stdin
    3. ``system/status`` with ``compact_result: "success"``
    4. ``system/compact_boundary`` with compaction metadata
    5. ``user`` message with ``isSynthetic: true`` containing the summary
    6. Normal assistant response
    """
    delay_seconds: float = args.get("delay_seconds", 1)
    summary_text = args.get(
        "summary_text",
        "Summary of conversation so far: The user asked for help and the assistant provided it.",
    )

    session_id = generate_id("session")
    request_id = generate_id("hook_req")

    # 1. Emit PreCompact hook_callback control_request on stdout
    hook_request = make_hook_callback_control_request(
        request_id=request_id,
        callback_id=PRE_COMPACT_CALLBACK_ID,
        hook_input={
            "hook_event_name": "PreCompact",
            "trigger": "auto",
            "session_id": session_id,
        },
    )
    sys.stdout.write(json.dumps(hook_request) + "\n")
    sys.stdout.flush()

    # 2. Read the control_response from stdin (blocking)
    _read_control_response_from_stdin(request_id)

    # 3. Simulate compaction latency
    time.sleep(delay_seconds)

    # 4. Return system messages + synthetic summary + normal response
    messages: list[dict] = []
    messages.append(make_compact_status_message(session_id))
    messages.append(make_compact_boundary_message(session_id))
    messages.append(make_compact_summary_user_message(summary_text, session_id))

    text = args.get("text", "[FakeClaude] Response after auto-compaction.")
    message_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=message_id, text=text))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=[make_text_block(text)]))
    return messages


def _read_control_response_from_stdin(expected_request_id: str, timeout_seconds: float = 5.0) -> None:
    """Read stdin until a ``control_response`` for ``expected_request_id`` arrives.

    Runs on the unified router (so a mid-wait user frame is absorbed, an
    interrupt exits, and a control_response for a *different* waiter is stashed
    for it rather than dropped), but falls back silently after
    ``timeout_seconds`` — unlike the MCP reader — so FakeClaude doesn't hang if
    the output processor never acks the hook (e.g. during unit tests that mock
    stdin).
    """
    if _STDIN_ROUTER.pop_stashed_response(expected_request_id) is not None:
        return
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        frame = _STDIN_ROUTER.next_frame(timeout=min(remaining, 0.1))
        if frame is _STDIN_TIMEOUT:
            continue
        if frame is _STDIN_EOF:
            return
        assert isinstance(frame, dict)
        if (
            frame.get("type") == "control_response"
            and frame.get("response", {}).get("request_id") == expected_request_id
        ):
            return
        _route_mid_cycle_frame(frame)


def handle_auto_compact_no_summary(args: dict, plugin_dir: str | None, emit_streaming: bool) -> list[dict]:
    """Simulate auto-compaction where the CLI does NOT emit the synthetic summary.

    Like ``handle_auto_compact`` but skips the ``isSynthetic`` user message,
    testing the fallback path where the output processor dismisses the
    indicator when the assistant response arrives.
    """
    delay_seconds: float = args.get("delay_seconds", 1)

    session_id = generate_id("session")
    request_id = generate_id("hook_req")

    # 1. Emit PreCompact hook_callback control_request on stdout
    hook_request = make_hook_callback_control_request(
        request_id=request_id,
        callback_id=PRE_COMPACT_CALLBACK_ID,
        hook_input={
            "hook_event_name": "PreCompact",
            "trigger": "auto",
            "session_id": session_id,
        },
    )
    sys.stdout.write(json.dumps(hook_request) + "\n")
    sys.stdout.flush()

    # 2. Read the control_response from stdin (blocking)
    _read_control_response_from_stdin(request_id)

    # 3. Simulate compaction latency
    time.sleep(delay_seconds)

    # 4. System messages + normal response (no isSynthetic summary)
    messages: list[dict] = []
    messages.append(make_compact_status_message(session_id))
    messages.append(make_compact_boundary_message(session_id))

    text = args.get("text", "[FakeClaude] Response after auto-compaction.")
    message_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=message_id, text=text))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=[make_text_block(text)]))
    return messages


def handle_auto_compact_mid_stream(args: dict, plugin_dir: str | None, emit_streaming: bool) -> list[dict]:
    """Simulate streaming text, auto-compaction mid-stream, then more streaming text.

    Emits messages in real-time to match the real CLI's exact stdout ordering:
    1. Pre-compaction streaming text + assistant message
    2. PreCompact hook_callback control_request
    3. system/status + system/compact_boundary + isSynthetic summary
    4. Post-compaction streaming text + assistant message (returned for caller to emit)

    This tests the full end-to-end flow including message ordering after
    compaction completes.
    """
    pre_text = args.get("pre_text", "Text before compaction.")
    post_text = args.get("post_text", "Text after compaction.")
    summary_text = args.get(
        "summary_text",
        "Summary of conversation so far: The user asked for help and the assistant provided it.",
    )
    delay_seconds: float = args.get("delay_seconds", 0.5)

    session_id = generate_id("session")

    # 1. Emit pre-compaction streaming text directly to stdout
    pre_msg_id = generate_id("msg")
    if emit_streaming:
        _emit_messages_to_stdout(make_streaming_text_events(message_id=pre_msg_id, text=pre_text))
    _emit_messages_to_stdout(
        [make_assistant_message(message_id=pre_msg_id, content_blocks=[make_text_block(pre_text)])]
    )

    # 2. Emit PreCompact hook_callback and wait for response
    request_id = generate_id("hook_req")
    hook_request = make_hook_callback_control_request(
        request_id=request_id,
        callback_id=PRE_COMPACT_CALLBACK_ID,
        hook_input={
            "hook_event_name": "PreCompact",
            "trigger": "auto",
            "session_id": session_id,
        },
    )
    sys.stdout.write(json.dumps(hook_request) + "\n")
    sys.stdout.flush()
    _read_control_response_from_stdin(request_id)

    # 3. Simulate compaction latency
    time.sleep(delay_seconds)

    # 4. Emit compaction completion messages directly to stdout
    _emit_messages_to_stdout(
        [
            make_compact_status_message(session_id),
            make_compact_boundary_message(session_id),
            make_compact_summary_user_message(summary_text, session_id),
        ]
    )

    # 5. Return post-compaction response (caller emits with end message)
    post_msg_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=post_msg_id, text=post_text))
    messages.append(make_assistant_message(message_id=post_msg_id, content_blocks=[make_text_block(post_text)]))
    return messages


def handle_background_task_started(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit a system/task_started message.

    In the real Claude Code SDK, task_started can interleave mid-turn (between
    tool calls on the main thread).  Use this inside ``multi_step`` to place it
    at the correct point in the message sequence.

    Args:
        args: Must contain "task_id". Optional: "tool_use_id", "description", "task_type".
    """
    return [
        make_task_started_message(
            task_id=args["task_id"],
            tool_use_id=args.get("tool_use_id", generate_id("toolu")),
            description=args.get("description", "Background task"),
            task_type=args.get("task_type", "local_bash"),
        )
    ]


def handle_emit_task_notification(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit ONLY a system/task_notification message (no surrounding result/init/response).

    Use this inside ``multi_step`` to simulate a background task notification
    arriving mid-turn, while the main agent is still actively emitting content.
    Unlike ``background_task_notification``, this does NOT end the main request
    cycle or start a new one.

    Args:
        args: Must contain "task_id". Optional: "tool_use_id", "status", "summary".
            Pass "tool_use_id": null to omit the field, reproducing the orphaned-
            task-on-restart notification the real CLI emits (see SCU-1666). When
            "tool_use_id" is absent a placeholder id is generated instead.
    """
    return [
        make_task_notification_message(
            task_id=args["task_id"],
            tool_use_id=args.get("tool_use_id", generate_id("toolu")),
            status=args.get("status", "completed"),
            summary=args.get("summary", "Background task completed"),
        )
    ]


def handle_emit_result(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit ONLY a result/success message (no assistant/init/notification).

    Use this inside ``multi_step`` to close a turn at a controlled point — e.g.
    to end a background task's follow-up turn so a subsequent background task's
    ``task_updated`` cleanup is evaluated at that turn boundary.

    Args:
        args: Optional "session_id".
    """
    return [make_end_message(session_id=args.get("session_id"))]


def handle_emit_task_updated(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit ONLY a system/task_updated message (no surrounding result/init/response).

    Use this inside ``multi_step`` to simulate a background task reporting a
    terminal state via task_updated WITHOUT a following task_notification — the
    real CLI does this when a task finishes while it is busy emitting another
    turn. For a subagent (task_type ``local_agent``) the CLI still has a
    follow-up notification/turn to deliver afterwards, so the harness must not
    treat this task_updated as the end of the session.

    Args:
        args: Must contain "task_id". Optional: "status" (default "completed").
    """
    return [
        make_task_updated_message(
            task_id=args["task_id"],
            status=args.get("status", "completed"),
        )
    ]


def handle_background_task_notification(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit task_notification + init + assistant response for a completed background task.

    In the real Claude Code SDK, task_notification always arrives after the main
    thread's result/success.  This command emits:
    1. result/success — ends the main thread's request cycle
    2. system/task_notification — background task completed
    3. system/init — new request cycle for the background response
    4. Assistant text message — the response to the background task result

    Args:
        args: Must contain "task_id" and "response_text".
              Optional: "tool_use_id", "status", "summary".
    """
    task_id = args["task_id"]
    tool_use_id = args.get("tool_use_id", generate_id("toolu"))
    response_text = args["response_text"]
    status = args.get("status", "completed")
    description = args.get("description", "Background task")
    summary = args.get("summary", f'Background command "{description}" completed (exit code 0)')

    session_id = generate_id("session")
    messages: list[dict] = []

    # 1. End the main thread's request cycle
    messages.append(make_end_message(session_id=session_id))

    # 2. task_notification
    messages.append(
        make_task_notification_message(
            task_id=task_id,
            tool_use_id=tool_use_id,
            status=status,
            summary=summary,
        )
    )

    # 3. New init for the background response cycle
    messages.append(make_init_message(session_id=session_id))

    # 4. Assistant response to the background task result
    message_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=message_id, text=response_text))
    messages.append(
        make_assistant_message(
            message_id=message_id,
            content_blocks=[make_text_block(response_text)],
        )
    )

    return messages


def handle_notification_turn_then_response(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit a task-notification turn *followed by* the user's own message turn.

    Reproduces SCU-1660: a Monitor background task completes just as a new user
    prompt is dispatched, so the CLI delivers the pending ``<task-notification>``
    as its own turn (init -> assistant -> result) BEFORE processing the user's
    message. Everything below sits inside a single FakeClaude invocation (one
    CLI process), between the process's own opening ``init`` and the closing
    ``end`` that ``fake_claude.main()`` appends — that closing ``end`` is the
    user turn's result.

    Frame order returned by this handler:
      1. system/task_notification (the Monitor completion, delivered first)
      2. notification turn: init -> assistant(ack) -> result
      3. user turn: init -> assistant(text) -> assistant(Bash tool_use) ->
         tool_result -> assistant(continuation)

    The notification turn's ``result`` is the trap: if the output processor
    treats it as terminal, the loop exits and the CLI is torn down before the
    user turn's frames are processed, silently abandoning the request after its
    first tool result.

    Args:
        args: Optional "task_id", "tool_use_id", "summary", "ack_text",
              "user_pre_text", "user_tool_command", "user_post_text".
    """
    task_id = args.get("task_id", "task_monitor_1")
    tool_use_id = args.get("tool_use_id", generate_id("toolu"))
    summary = args.get("summary", "Background task completed")
    ack_text = args.get("ack_text", "This is just the stale Monitor task being cleaned up.")
    user_pre_text = args.get("user_pre_text", "I'll fetch the latest state of that branch.")
    user_tool_command = args.get("user_tool_command", "git fetch origin")
    user_post_text = args.get("user_post_text", "Done — merged and repushed.")

    session_id = generate_id("session")
    user_tool_id = generate_id("toolu")
    messages: list[dict] = []

    # 1. The completed Monitor task's notification, delivered ahead of the user turn.
    messages.append(
        make_task_notification_message(
            task_id=task_id,
            tool_use_id=tool_use_id,
            status="completed",
            summary=summary,
        )
    )

    # 2. Notification turn: init -> assistant(ack) -> result.
    messages.append(make_init_message(session_id=session_id))
    ack_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=ack_msg_id, text=ack_text))
    messages.append(make_assistant_message(message_id=ack_msg_id, content_blocks=[make_text_block(ack_text)]))
    messages.append(make_end_message(session_id=session_id))

    # 3. User turn: init -> text -> Bash tool_use -> tool_result -> continuation.
    messages.append(make_init_message(session_id=session_id))
    pre_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=pre_msg_id, text=user_pre_text))
    messages.append(make_assistant_message(message_id=pre_msg_id, content_blocks=[make_text_block(user_pre_text)]))

    tool_block = make_tool_use_block(tool_id=user_tool_id, tool_name="Bash", tool_input={"command": user_tool_command})
    tool_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_tool_events(message_id=tool_msg_id, tool_blocks=[tool_block]))
    messages.append(make_assistant_message(message_id=tool_msg_id, content_blocks=[tool_block]))
    messages.append(make_tool_result_message(tool_use_id=user_tool_id, content="Fetched new commits."))

    post_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=post_msg_id, text=user_post_text))
    messages.append(make_assistant_message(message_id=post_msg_id, content_blocks=[make_text_block(user_post_text)]))

    return messages


def handle_subagent(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate a subagent (Agent tool) call.

    Produces the full JSONL sequence:
    1. Main agent assistant message with text + Agent tool_use
    2. Subagent assistant message with text (parent_tool_use_id set)
    3. Agent tool_result (user message)
    4. Main agent follow-up assistant message with summary text

    Args:
        args: Must contain "subagent_result". Optional: "description", "prompt", "summary_text".
    """
    description = args.get("description", "Explore the codebase")
    prompt = args.get("prompt", "Find relevant files")
    subagent_result = args["subagent_result"]
    summary_text = args.get("summary_text", "[FakeClaude] Here is the summary of the subagent's findings.")

    # IDs
    main_msg_id = generate_id("msg")
    agent_tool_id = generate_id("toolu")
    subagent_msg_id = generate_id("msg")
    summary_msg_id = generate_id("msg")

    # 1. Main agent: text + Agent tool_use
    agent_tool_block = make_tool_use_block(
        tool_id=agent_tool_id,
        tool_name="Agent",
        tool_input={"prompt": prompt, "description": description},
    )
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(
            make_streaming_tool_events(
                message_id=main_msg_id,
                tool_blocks=[agent_tool_block],
                text_prefix="I'll use a subagent to help with this.",
            )
        )
    messages.append(
        make_assistant_message(
            message_id=main_msg_id,
            content_blocks=[make_text_block("I'll use a subagent to help with this."), agent_tool_block],
        )
    )

    # 2. Subagent response (with parent_tool_use_id)
    if emit_streaming:
        messages.extend(
            make_streaming_text_events(
                message_id=subagent_msg_id,
                text=subagent_result,
                parent_tool_use_id=agent_tool_id,
            )
        )
    messages.append(
        make_assistant_message(
            message_id=subagent_msg_id,
            content_blocks=[make_text_block(subagent_result)],
            parent_tool_use_id=agent_tool_id,
        )
    )

    # 3. Agent tool_result (main agent context, no parent_tool_use_id)
    # The content is str() of the subagent's response content blocks, matching real SDK behavior
    raw_result = str([{"type": "text", "text": subagent_result}])
    messages.append(make_tool_result_message(tool_use_id=agent_tool_id, content=raw_result))

    # 4. Main agent summary
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=summary_msg_id, text=summary_text))
    messages.append(
        make_assistant_message(
            message_id=summary_msg_id,
            content_blocks=[make_text_block(summary_text)],
        )
    )

    return messages


def _emit_subagent_launch_and_inverted_ask(
    questions: list[dict],
    description: str,
    emit_streaming: bool,
) -> tuple[str, str, str]:
    """Launch an Agent tool call whose subagent asks a question via MCP,
    replaying the real CLI's SUBAGENT event ordering.

    For main-agent MCP calls the CLI emits the assistant message (carrying the
    tool_use block) BEFORE the ``tools/call`` control_request. For subagent
    calls the order is INVERTED: the control_request reaches stdout first and
    the sidechain assistant line follows (observed on Claude Code 2.1.170).
    Sculptor must pair the two regardless of order.

    Emits (in order): the main-agent assistant message with the Agent
    tool_use; the MCP ``tools/call`` control_request; the sidechain assistant
    message with the AUQ tool_use. Subagent output reaches the parent stream
    as full non-streamed assistant lines, so the sidechain message carries no
    streaming events.

    Returns ``(agent_tool_id, ask_tool_id, mcp_request_id)`` — the caller
    blocks on the response and emits the post-answer messages.
    """
    main_msg_id = generate_id("msg")
    agent_tool_id = generate_id("toolu")
    ask_tool_id = generate_id("toolu")
    subagent_msg_id = generate_id("msg")

    # 1. Main agent: text + Agent tool_use
    agent_tool_block = make_tool_use_block(
        tool_id=agent_tool_id,
        tool_name="Agent",
        tool_input={"prompt": "Ask the user and report their answer", "description": description},
    )
    _emit_messages_to_stdout(
        _make_tool_assistant_message(
            message_id=main_msg_id,
            tool_blocks=[agent_tool_block],
            emit_streaming=emit_streaming,
            text_prefix="I'll use a subagent to help with this.",
        )
    )

    # 2. The subagent's MCP tools/call — BEFORE the sidechain assistant line.
    mcp_request_id = _emit_mcp_tool_call(
        tool_fqn=SCULPTOR_MCP_ASK_TOOL_FQN,
        arguments={"questions": questions},
    )

    # 3. The sidechain assistant line carrying the AUQ tool_use block.
    ask_tool_block = make_tool_use_block(
        tool_id=ask_tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": questions},
    )
    _emit_messages_to_stdout(
        [
            make_assistant_message(
                message_id=subagent_msg_id,
                content_blocks=[ask_tool_block],
                parent_tool_use_id=agent_tool_id,
            )
        ]
    )
    return agent_tool_id, ask_tool_id, mcp_request_id


def _make_subagent_answer_messages(
    agent_tool_id: str,
    ask_tool_id: str,
    answer_text: str,
    subagent_label: str,
) -> list[dict]:
    """Build the post-answer message tail for a subagent AUQ: the sidechain
    tool_result, and the Agent tool_result echoing which answer the subagent
    received (tests assert on the echo to verify answer routing)."""
    subagent_reply = f"[FakeClaude {subagent_label}] Received answer: {answer_text}"
    return [
        make_tool_result_message(tool_use_id=ask_tool_id, content=answer_text, parent_tool_use_id=agent_tool_id),
        make_tool_result_message(tool_use_id=agent_tool_id, content=str([{"type": "text", "text": subagent_reply}])),
    ]


def handle_subagent_ask_user_question(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate a subagent (Agent tool) asking the user a question via MCP.

    Replays the inverted subagent event ordering (see
    ``_emit_subagent_launch_and_inverted_ask``), blocks until Sculptor's MCP
    server delivers the user's answer, then emits the tool results and a main
    agent summary echoing the received answer.

    Args:
        args: Must contain "questions" (AUQ questions list). Optional:
              "description".
    """
    questions = args["questions"]
    description = args.get("description", "Ask the user a question")

    agent_tool_id, ask_tool_id, mcp_request_id = _emit_subagent_launch_and_inverted_ask(
        questions=questions, description=description, emit_streaming=emit_streaming
    )

    answer_text = _read_mcp_control_response_text(mcp_request_id, ask_tool_id, timeout_seconds=180.0)

    messages = _make_subagent_answer_messages(
        agent_tool_id=agent_tool_id,
        ask_tool_id=ask_tool_id,
        answer_text=answer_text,
        subagent_label="subagent",
    )
    summary_text = f"[FakeClaude] Subagent finished. Received answer: {answer_text}"
    summary_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=summary_msg_id, text=summary_text))
    messages.append(make_assistant_message(message_id=summary_msg_id, content_blocks=[make_text_block(summary_text)]))
    return messages


def handle_ask_user_question_then_subagent_ask(args: dict, emit_streaming: bool) -> list[dict]:
    """A main-agent AUQ (normal ordering, answered first) followed by a
    subagent AUQ with the inverted subagent event ordering — all in one turn.

    Guards against the MCP server's answered-question replay cache serving the
    already-delivered FIRST answer to the subagent's DIFFERENT second
    question. The final summary echoes both answers so the test can assert the
    subagent received the answer to ITS question, not the cached one.

    Args:
        args: Must contain "first_questions" and "second_questions".
    """
    first_questions = args["first_questions"]
    second_questions = args["second_questions"]

    # Main-agent AUQ with the normal (assistant line first) ordering.
    first_msg_id = generate_id("msg")
    first_tool_id = generate_id("toolu")
    first_block = make_tool_use_block(
        tool_id=first_tool_id,
        tool_name=SCULPTOR_MCP_ASK_TOOL_FQN,
        tool_input={"questions": first_questions},
    )
    _emit_messages_to_stdout(
        _make_tool_assistant_message(message_id=first_msg_id, tool_blocks=[first_block], emit_streaming=emit_streaming)
    )
    first_answer = _emit_mcp_tool_call_and_wait_for_response(
        tool_use_id=first_tool_id,
        tool_fqn=SCULPTOR_MCP_ASK_TOOL_FQN,
        arguments={"questions": first_questions},
    )
    _emit_messages_to_stdout([make_tool_result_message(tool_use_id=first_tool_id, content=first_answer)])

    # Subagent AUQ with the inverted ordering.
    agent_tool_id, ask_tool_id, mcp_request_id = _emit_subagent_launch_and_inverted_ask(
        questions=second_questions, description="Ask a follow-up question", emit_streaming=emit_streaming
    )
    second_answer = _read_mcp_control_response_text(mcp_request_id, ask_tool_id, timeout_seconds=180.0)

    messages = _make_subagent_answer_messages(
        agent_tool_id=agent_tool_id,
        ask_tool_id=ask_tool_id,
        answer_text=second_answer,
        subagent_label="subagent",
    )
    summary_text = f"[FakeClaude] Subagent finished. Subagent received answer: {second_answer}"
    summary_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=summary_msg_id, text=summary_text))
    messages.append(make_assistant_message(message_id=summary_msg_id, content_blocks=[make_text_block(summary_text)]))
    return messages


def handle_two_subagents_ask_user_question(args: dict, emit_streaming: bool) -> list[dict]:
    """Two concurrent subagents each asking a DIFFERENT question via MCP, with
    the inverted subagent event ordering, interleaved as observed in the real
    freeze trace: tools/call A, sidechain line A, tools/call B, sidechain
    line B.

    Blocks until BOTH answers arrive, then emits per-subagent echoes so the
    test can assert each subagent received the answer to its own question
    (a single-slot pairing would cross the wires).

    Args:
        args: Must contain "first_questions" and "second_questions".
    """
    first_questions = args["first_questions"]
    second_questions = args["second_questions"]

    agent_a_id, ask_a_id, request_a_id = _emit_subagent_launch_and_inverted_ask(
        questions=first_questions, description="Subagent A question", emit_streaming=emit_streaming
    )
    agent_b_id, ask_b_id, request_b_id = _emit_subagent_launch_and_inverted_ask(
        questions=second_questions, description="Subagent B question", emit_streaming=emit_streaming
    )

    responses = _read_mcp_control_responses({request_a_id, request_b_id}, timeout_seconds=180.0)
    answer_a = _extract_mcp_response_text(responses[request_a_id])
    answer_b = _extract_mcp_response_text(responses[request_b_id])

    messages = _make_subagent_answer_messages(
        agent_tool_id=agent_a_id, ask_tool_id=ask_a_id, answer_text=answer_a, subagent_label="subagent A"
    )
    messages.extend(
        _make_subagent_answer_messages(
            agent_tool_id=agent_b_id, ask_tool_id=ask_b_id, answer_text=answer_b, subagent_label="subagent B"
        )
    )
    summary_text = f"[FakeClaude] Subagent A received answer: {answer_a} | Subagent B received answer: {answer_b}"
    summary_msg_id = generate_id("msg")
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=summary_msg_id, text=summary_text))
    messages.append(make_assistant_message(message_id=summary_msg_id, content_blocks=[make_text_block(summary_text)]))
    return messages


def handle_background_subagent(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate a background subagent (Agent tool with run_in_background=true).

    Models the real SDK flow where the Agent tool returns immediately with
    "Async agent launched", the subagent runs in its OWN CLI process (so its
    messages are NOT streamed back to the parent), and the main agent is
    notified on completion via task_notification.

    The notification carries only metadata (status, summary, usage.duration_ms,
    output_file) — the subagent's actual content sits in output_file and is
    not surfaced to the parent's message stream. This matches what we observe
    from real Claude (see SCU-1151).

    Produces the JSONL sequence:
    1. Main agent assistant message with text + Agent tool_use
    2. Agent tool_result (immediate "Async agent launched" response)
    3. task_started event
    4. Main agent "launched" text and turn end (result/success)
    5. task_notification
    6. New request cycle (init + summary text)

    When ``pause_path`` is set, the handler flushes the messages produced
    through step 4 to stdout, then blocks until the sentinel file appears
    before emitting the task_notification + summary in step 5/6.  This lets
    tests deterministically observe the harness in its "waiting for
    background notification" state — i.e. the agent has emitted its final
    result/success but the request has not yet completed because a
    background task is still in flight. Use ``FakeClaudePause`` from the
    testing helpers to get a sentinel path and call ``release()`` to unblock.

    Args:
        args: Optional: "description", "prompt", "summary_text", "launched_text",
              "notification_summary", "pause_path", "answer_context_usage".
              ("subagent_result" is accepted for backward compatibility with
              older tests but no longer emitted — real Claude does not stream
              the subagent's reply to the parent.)

              "answer_context_usage" (bool, default False): while paused, answer
              Sculptor's get_context_usage control request so the turn's metrics
              flush mid-hold (TurnMetricsAgentMessage pending while the request
              stays open) — the state needed to reproduce SCU-1820 end-to-end.
    """
    description = args.get("description", "Explore the codebase")
    prompt = args.get("prompt", "Find relevant files")
    summary_text = args.get("summary_text", "[FakeClaude] Here is the summary of the background subagent's findings.")
    launched_text = args.get("launched_text", "Background subagent launched. Let me continue while it runs.")
    notification_summary = args.get("notification_summary", f'Agent "{description}" completed')
    pause_path: str | None = args.get("pause_path")
    # When set, answer Sculptor's get_context_usage control request during the
    # pause so the turn's metrics are flushed (TurnMetricsAgentMessage becomes
    # pending) while the request is still open — matching real Claude. Off by
    # default so existing pause-based tests keep their old message stream.
    answer_context_usage: bool = args.get("answer_context_usage", False)

    # IDs
    main_msg_id = generate_id("msg")
    agent_tool_id = generate_id("toolu")
    subagent_msg_id = generate_id("msg")
    launched_msg_id = generate_id("msg")
    summary_msg_id = generate_id("msg")
    task_id = generate_id("task")
    session_id = generate_id("session")

    # 1. Main agent: text + Agent tool_use
    agent_tool_block = make_tool_use_block(
        tool_id=agent_tool_id,
        tool_name="Agent",
        tool_input={"prompt": prompt, "description": description, "run_in_background": True},
    )
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(
            make_streaming_tool_events(
                message_id=main_msg_id,
                tool_blocks=[agent_tool_block],
                text_prefix="I'll use a background subagent to help with this.",
            )
        )
    messages.append(
        make_assistant_message(
            message_id=main_msg_id,
            content_blocks=[make_text_block("I'll use a background subagent to help with this."), agent_tool_block],
        )
    )

    # 2. Agent tool_result (immediate "launched" response)
    raw_result = f"Async agent launched successfully.\nagentId: {subagent_msg_id}"
    messages.append(make_tool_result_message(tool_use_id=agent_tool_id, content=raw_result))

    # 3. task_started event
    messages.append(
        make_task_started_message(
            task_id=task_id,
            tool_use_id=agent_tool_id,
            description=description,
            task_type="agent",
        )
    )

    # 4. Main agent "launched" text and turn end.  The subagent's reply is
    # NOT emitted here — real Claude streams subagent content to its own
    # separate JSONL transcript (referenced via the notification's
    # output_file), never to the parent's stream.
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=launched_msg_id, text=launched_text))
    messages.append(
        make_assistant_message(
            message_id=launched_msg_id,
            content_blocks=[make_text_block(launched_text)],
        )
    )
    messages.append(make_end_message(session_id=session_id))

    # Optional pause to let tests observe the "waiting for background
    # notification" state.  After step 4 the CLI has emitted result/success
    # (so the output processor's found_final_message is True) but the
    # background task is still pending — the harness sits idle until the
    # task_notification below arrives.  Without this pause the notification
    # follows the result/success in the same emit batch and the wait state
    # is invisible to a test.  Signaled (not wall-clock) so the wait survives
    # arbitrary CI load between the test's "go" and "release" steps.
    if pause_path is not None:
        _emit_messages_to_stdout(messages)
        messages = []
        sentinel = Path(pause_path)
        if answer_context_usage:
            _answer_context_usage_and_wait_for_sentinel(sentinel, timeout_seconds=120)
        elif not _wait_until(timeout_seconds=120, poll_interval=0.05, done=sentinel.exists):
            raise RuntimeError(f"background_subagent pause timed out waiting for {sentinel}")

    # 5. task_notification — carries only metadata; no subagent content.
    messages.append(
        make_task_notification_message(
            task_id=task_id,
            tool_use_id=agent_tool_id,
            status="completed",
            summary=notification_summary,
        )
    )

    # 6. New request cycle: init + main agent summary
    messages.append(make_init_message(session_id=session_id))
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=summary_msg_id, text=summary_text))
    messages.append(
        make_assistant_message(
            message_id=summary_msg_id,
            content_blocks=[make_text_block(summary_text)],
        )
    )

    return messages


def handle_workflow_run(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate the Workflow tool's full background-task lifecycle.

    Models the real CLI flow (verified against stream-json captured from
    Claude Code 2.1.198 workflow sessions): the Workflow tool_result returns
    immediately ("launched in background"), the run streams
    system/task_progress events whose ``workflow_progress`` payloads are
    DELTAS — the first carries the phase plus the initial agent entries,
    later ones carry only the entries whose state changed — and completion
    arrives via task_notification followed by a fresh request cycle where
    the agent summarizes the result.

    Produces the JSONL sequence:
    1. Main agent assistant message with text + Workflow tool_use
    2. Workflow tool_result (immediate "launched in background" response)
    3. task_started event (task_type=local_workflow, workflow_name)
    4. task_progress with the initial tree (one agent in progress, one queued)
    5. Main agent "launched" text and turn end (result/success)
    6. task_progress deltas completing each agent, one payload per agent
    7. task_notification
    8. New request cycle (init + summary text)

    When ``pause_path`` is set, messages through step 5 are flushed to stdout
    and the handler blocks until the sentinel file appears before emitting
    steps 6-8, so tests can observe the running pill/popover deterministically.
    Use ``FakeClaudePause`` for the sentinel and call ``release()`` to unblock.

    Args:
        args: Optional: "workflow_name", "launched_text", "summary_text",
              "notification_summary", "pause_path".
    """
    workflow_name = args.get("workflow_name", "review-changes")
    launched_text = args.get("launched_text", "Workflow launched. I'll report back when it completes.")
    summary_text = args.get("summary_text", "[FakeClaude] Workflow finished. Here is the summary.")
    notification_summary = args.get("notification_summary", f'Workflow "{workflow_name}" completed')
    pause_path: str | None = args.get("pause_path")

    main_msg_id = generate_id("msg")
    workflow_tool_id = generate_id("toolu")
    launched_msg_id = generate_id("msg")
    summary_msg_id = generate_id("msg")
    task_id = generate_id("task")
    session_id = generate_id("session")

    phase_entry = make_workflow_phase_entry(index=0, title="Review")
    initial_tree = [
        phase_entry,
        make_workflow_agent_entry(
            index=0,
            label="review:bugs",
            phase_index=0,
            phase_title="Review",
            state="progress",
            tokens=3100,
            tool_calls=4,
            last_tool_summary="Grep: TODO in src/",
            prompt_preview="Review the diff for bugs",
        ),
        make_workflow_agent_entry(
            index=1,
            label="review:perf",
            phase_index=0,
            phase_title="Review",
            state="start",
            prompt_preview="Review the diff for perf issues",
        ),
    ]
    # Completion deltas: one payload per agent, carrying ONLY that agent's
    # entry — mirroring how the real CLI streams state changes.
    bugs_done_delta = [
        make_workflow_agent_entry(
            index=0,
            label="review:bugs",
            phase_index=0,
            phase_title="Review",
            state="done",
            tokens=9800,
            tool_calls=11,
            duration_ms=61200,
            result_preview="Found 2 bugs",
            prompt_preview="Review the diff for bugs",
        ),
    ]
    perf_done_delta = [
        make_workflow_agent_entry(
            index=1,
            label="review:perf",
            phase_index=0,
            phase_title="Review",
            state="done",
            tokens=7200,
            tool_calls=6,
            duration_ms=48000,
            result_preview="No perf issues",
            prompt_preview="Review the diff for perf issues",
        ),
    ]

    # 1. Main agent: text + Workflow tool_use
    workflow_tool_block = make_tool_use_block(
        tool_id=workflow_tool_id,
        tool_name="Workflow",
        tool_input={"script": f"export const meta = {{name: '{workflow_name}'}}"},
    )
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(
            make_streaming_tool_events(
                message_id=main_msg_id,
                tool_blocks=[workflow_tool_block],
                text_prefix="I'll run a workflow for this.",
            )
        )
    messages.append(
        make_assistant_message(
            message_id=main_msg_id,
            content_blocks=[make_text_block("I'll run a workflow for this."), workflow_tool_block],
        )
    )

    # 2. Workflow tool_result (immediate "launched" response)
    raw_result = f"Workflow launched in background. Task ID: {task_id}\nYou will be notified when it completes."
    messages.append(make_tool_result_message(tool_use_id=workflow_tool_id, content=raw_result))

    # 3. task_started event
    messages.append(
        make_task_started_message(
            task_id=task_id,
            tool_use_id=workflow_tool_id,
            description=workflow_name,
            task_type="local_workflow",
            workflow_name=workflow_name,
        )
    )

    # 4. Mid-turn task_progress with the initial tree.
    messages.append(
        make_task_progress_message(
            task_id=task_id,
            tool_use_id=workflow_tool_id,
            description="Review: review:bugs",
            total_tokens=3100,
            tool_uses=4,
            duration_ms=12000,
            last_tool_name="Grep",
            workflow_progress=initial_tree,
        )
    )

    # 5. Main agent "launched" text and turn end. The workflow keeps running
    # in the background, so the output loop stays open for the notification.
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=launched_msg_id, text=launched_text))
    messages.append(
        make_assistant_message(
            message_id=launched_msg_id,
            content_blocks=[make_text_block(launched_text)],
        )
    )
    messages.append(make_end_message(session_id=session_id))

    # Optional pause so tests can observe the running pill/popover before the
    # workflow completes. Signaled (not wall-clock) so the wait survives
    # arbitrary CI load between the test's "go" and "release" steps.
    if pause_path is not None:
        _emit_messages_to_stdout(messages)
        messages = []
        sentinel = Path(pause_path)
        if not _wait_until(timeout_seconds=120, poll_interval=0.05, done=sentinel.exists):
            raise RuntimeError(f"workflow_run pause timed out waiting for {sentinel}")

    # 6. Completion deltas — one payload per agent, like the real CLI.
    messages.append(
        make_task_progress_message(
            task_id=task_id,
            tool_use_id=workflow_tool_id,
            description="Review: review:bugs done",
            total_tokens=12900,
            tool_uses=11,
            duration_ms=61200,
            workflow_progress=bugs_done_delta,
        )
    )
    messages.append(
        make_task_progress_message(
            task_id=task_id,
            tool_use_id=workflow_tool_id,
            description="Review: done",
            total_tokens=17000,
            tool_uses=17,
            duration_ms=63210,
            workflow_progress=perf_done_delta,
        )
    )

    # 7. task_notification
    messages.append(
        make_task_notification_message(
            task_id=task_id,
            tool_use_id=workflow_tool_id,
            status="completed",
            summary=notification_summary,
            duration_ms=63210,
        )
    )

    # 8. New request cycle: init + main agent summary
    messages.append(make_init_message(session_id=session_id))
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id=summary_msg_id, text=summary_text))
    messages.append(
        make_assistant_message(
            message_id=summary_msg_id,
            content_blocks=[make_text_block(summary_text)],
        )
    )

    return messages


def handle_auto_bg_bash(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit the auto-background-promotion sequence for a slow foreground Bash call.

    When the real Claude CLI detects that a foreground Bash tool call is taking
    "too long" (roughly >=2.5s), it auto-promotes it to a ``local_bash``
    background task and emits ``task_started`` + ``task_notification`` events
    alongside the normal ``tool_use``/``tool_result`` pair — all sharing the
    same ``tool_use_id``.  The exact stdout sequence (captured by diffing a
    ``sleep 3`` against a ``sleep 1`` invocation with the real CLI):

        assistant       content=[tool_use id=X name=Bash]
        system/task_started        tool_use_id=X  task_type=local_bash
        system/task_notification   tool_use_id=X  status=completed
        user            content=[tool_result tool_use_id=X]
        assistant       content=[text "Done."]

    No ``result``/``init`` boundary is inserted between the notification and
    the tool_result; the whole thing is one continuous request cycle.  This is
    what makes the auto-bg case distinct from ``background_task_notification``
    (which simulates a *true* background task, where ``tool_result`` already
    delivered "Command running in background" earlier and ``task_notification``
    kicks off a fresh request cycle).

    Args:
        args: Optional ``command`` (default ``sleep 3 && echo done``),
              ``description`` (default ``Sleep 3 seconds``),
              ``output`` (default ``done``),
              ``follow_up`` (default ``Done.``).
    """
    command = args.get("command", "sleep 3 && echo done")
    description = args.get("description", "Sleep 3 seconds")
    output = args.get("output", "done")
    follow_up = args.get("follow_up", "Done.")

    task_id = generate_id("task")
    tool_use_id = generate_id("toolu")

    tool_use_block = make_tool_use_block(
        tool_id=tool_use_id,
        tool_name="Bash",
        tool_input={"command": command, "description": description},
    )

    first_assistant_message_id = generate_id("msg")
    first_assistant = make_assistant_message(
        message_id=first_assistant_message_id,
        content_blocks=[tool_use_block],
    )

    second_assistant_message_id = generate_id("msg")
    second_assistant = make_assistant_message(
        message_id=second_assistant_message_id,
        content_blocks=[make_text_block(follow_up)],
    )

    return [
        first_assistant,
        make_task_started_message(
            task_id=task_id,
            tool_use_id=tool_use_id,
            description=description,
            task_type="local_bash",
        ),
        make_task_notification_message(
            task_id=task_id,
            tool_use_id=tool_use_id,
            status="completed",
            summary=description,
        ),
        make_tool_result_message(tool_use_id=tool_use_id, content=output),
        second_assistant,
    ]


def handle_read_file(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the read_file command — reads a file and returns JSONL with a Read tool_use.

    If the file doesn't exist, creates it with ``content`` (required in that case).
    Returns cat -n formatted output matching real Claude Code Read tool behaviour.

    Args:
        args: Must contain "file_path". Optional: "content" (to pre-create the file),
              "limit" (max lines to read).
    """
    file_path = args["file_path"]
    content = args.get("content")
    limit: int | None = args.get("limit")

    full_path = Path(cwd) / file_path
    if content is not None:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    file_content = full_path.read_text()
    lines = file_content.splitlines()
    if limit is not None:
        lines = lines[:limit]

    # Format as cat -n (line_number\tcontent)
    numbered = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines))

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_input: dict = {"file_path": str(full_path)}
    if limit is not None:
        tool_input["limit"] = limit
    tool_block = make_tool_use_block(tool_id=tool_id, tool_name="Read", tool_input=tool_input)

    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content=numbered))
    return messages


def handle_glob(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the glob command — runs a glob pattern and returns JSONL with a Glob tool_use.

    Args:
        args: Must contain "pattern". Optional: "path" (directory to search in).
    """

    pattern = args["pattern"]
    search_path = args.get("path", cwd)
    full_pattern = str(Path(search_path) / pattern)

    matches = sorted(glob_module.glob(full_pattern, recursive=True))
    # Return paths relative to search_path, matching real Claude Code output
    result_lines = []
    for match in matches:
        try:
            rel = str(Path(match).relative_to(search_path))
        except ValueError:
            rel = match
        result_lines.append(rel)
    result_content = "\n".join(result_lines)

    message_id = generate_id("msg")
    tool_id = generate_id("toolu")
    tool_input: dict = {"pattern": pattern}
    if args.get("path"):
        tool_input["path"] = search_path
    tool_block = make_tool_use_block(tool_id=tool_id, tool_name="Glob", tool_input=tool_input)

    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_id, content=result_content))
    return messages


def handle_text_and_bash(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the text_and_bash command — a single assistant message with custom text + bash tool.

    Unlike multi_step with text + bash (which produces two separate assistant messages),
    this produces ONE assistant message containing both the text and tool_use blocks,
    matching how real Claude Code behaves when it outputs text then calls a tool.
    """
    text = args["text"]
    tool_block, output, is_error = _run_bash_and_make_tool_blocks(args, cwd)
    message_id = generate_id("msg")
    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=[tool_block],
        emit_streaming=emit_streaming,
        text_prefix=text,
    )
    messages.append(make_tool_result_message(tool_use_id=tool_block["id"], content=output, is_error=is_error))
    return messages


_INLINE_EMITTING_COMMANDS: frozenset[str] = frozenset(
    {
        "ask_user_question",
        "exit_plan_mode",
        "ask_user_question_and_continue",
        "ask_user_question_invalid_input",
        "enter_plan_mode_and_ask",
        # wait_for_file does not emit inline, but it blocks indefinitely, so any
        # prior steps' messages must be flushed BEFORE it parks — mirroring real
        # Claude, which emits the assistant message before executing a blocking
        # tool. Restart tests rely on this: a backend killed while the agent is
        # parked must already have persisted the prior steps' ResponseBlocks,
        # otherwise the in-flight turn has no partial response to resume from
        # (see v1.py's is_partial_agent_response walk).
        "wait_for_file",
    }
)


def handle_multi_step(args: dict, cwd: str, emit_streaming: bool, plugin_dir: str | None = None) -> list[dict]:
    """Handle the multi_step command — dispatches each step to the appropriate handler.

    Steps that emit inline (the SDK MCP AUQ / ExitPlanMode handlers send a
    ``tools/call`` control_request and block on the response) need any prior
    steps' assistant / tool_result messages to be visible to the output
    processor first, so they can match up the tool_use_id correctly. Flush
    the accumulated returned messages right before invoking each such
    handler.
    """
    steps = args["steps"]
    messages: list[dict] = []

    for step in steps:
        command_name = step["command"]
        step_args = step.get("args", {})
        handler = COMMAND_REGISTRY.get(command_name)
        if handler is None:
            raise UnknownFakeClaudeCommandError(f"Unknown command in multi_step: {command_name}")
        if command_name in _INLINE_EMITTING_COMMANDS and messages:
            _emit_messages_to_stdout(messages)
            messages = []
        messages.extend(dispatch_handler(handler, step_args, cwd, emit_streaming, plugin_dir=plugin_dir))

    return messages


def handle_interleaved_tools(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the interleaved_tools command — arbitrary ordered text and
    tool_use blocks within a single assistant message.

    ``args`` must contain a ``blocks`` list; each entry is one of:
      - ``{"type": "text", "text": "..."}`` — pass ``""`` to emit a
        zero-delta streaming text block (the SDK event shape that exercises
        the empty-TextBlock leak path in the streaming pipeline).
      - ``{"type": "tool", "tool_name": "...", "tool_input": {...}}``

    Unlike ``parallel_tools``, this command does not force a text prefix at
    index 0 and preserves the caller-specified block order across streaming
    indices.
    """
    blocks_spec = args["blocks"]
    message_id = generate_id("msg")

    stream_blocks: list[dict] = []
    assistant_content: list[dict] = []
    tool_infos: list[tuple[str, dict]] = []

    for block_spec in blocks_spec:
        if block_spec["type"] == "text":
            text = block_spec["text"]
            stream_blocks.append({"type": "text", "text": text})
            assistant_content.append(make_text_block(text))
        elif block_spec["type"] == "tool":
            tool_id = generate_id("toolu")
            tool_name = block_spec["tool_name"]
            tool_input = block_spec["tool_input"]
            stream_blocks.append({"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input})
            assistant_content.append(make_tool_use_block(tool_id=tool_id, tool_name=tool_name, tool_input=tool_input))
            tool_infos.append((tool_id, block_spec))
        else:
            raise ValueError(f"Unsupported block type in interleaved_tools: {block_spec['type']!r}")

    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_interleaved_events(message_id=message_id, blocks=stream_blocks))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=assistant_content))

    for tool_id, tool_spec in tool_infos:
        tool_name = tool_spec["tool_name"]
        tool_input = tool_spec["tool_input"]
        result_content, is_error = _execute_tool_side_effect(tool_name, tool_input, cwd)
        messages.append(make_tool_result_message(tool_use_id=tool_id, content=result_content, is_error=is_error))

    return messages


def handle_parallel_tools(args: dict, cwd: str, emit_streaming: bool) -> list[dict]:
    """Handle the parallel_tools command — multiple tool use blocks in one assistant message."""
    tools = args["tools"]

    message_id = generate_id("msg")
    tool_blocks: list[dict] = []
    tool_infos: list[tuple[str, dict]] = []

    for tool_spec in tools:
        tool_id = generate_id("toolu")
        tool_name = tool_spec["tool_name"]
        tool_input = tool_spec["tool_input"]
        tool_blocks.append(make_tool_use_block(tool_id=tool_id, tool_name=tool_name, tool_input=tool_input))
        tool_infos.append((tool_id, tool_spec))

    messages = _make_tool_assistant_message(
        message_id=message_id,
        tool_blocks=tool_blocks,
        emit_streaming=emit_streaming,
    )

    for tool_id, tool_spec in tool_infos:
        tool_name = tool_spec["tool_name"]
        tool_input = tool_spec["tool_input"]
        result_content, is_error = _execute_tool_side_effect(tool_name, tool_input, cwd)
        messages.append(make_tool_result_message(tool_use_id=tool_id, content=result_content, is_error=is_error))

    return messages


def _execute_tool_side_effect(tool_name: str, tool_input: dict, cwd: str) -> tuple[str, bool]:
    """Execute the side effect of a tool and return (result_content, is_error)."""
    if tool_name == "Write":
        file_path = tool_input["file_path"]
        content = tool_input["content"]
        full_path = Path(cwd) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return "File written successfully.", False
    elif tool_name == "Edit":
        file_path = tool_input["file_path"]
        full_path = Path(cwd) / file_path
        try:
            file_content = full_path.read_text()
        except FileNotFoundError:
            return f"Error: file not found: {file_path}", True
        old_string = tool_input["old_string"]
        new_string = tool_input["new_string"]
        if old_string not in file_content:
            return f"old_string not found in {file_path}", True
        file_content = file_content.replace(old_string, new_string, 1)
        full_path.write_text(file_content)
        return "File edited successfully.", False
    elif tool_name == "Bash":
        command = tool_input["command"]
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)  # noqa: S602
        if result.returncode != 0:
            return result.stderr or result.stdout, True
        return result.stdout, False
    elif tool_name == "Read":
        file_path = tool_input["file_path"]
        full_path = Path(cwd) / file_path
        try:
            file_content = full_path.read_text()
        except FileNotFoundError:
            return f"Error: file not found: {file_path}", True
        lines = file_content.splitlines()
        limit = tool_input.get("limit")
        if limit is not None:
            lines = lines[:limit]
        numbered = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines))
        return numbered, False
    elif tool_name == "Glob":
        pattern = tool_input["pattern"]
        search_path = tool_input.get("path", cwd)
        full_pattern = str(Path(search_path) / pattern)
        matches = sorted(glob_module.glob(full_pattern, recursive=True))
        result_lines = []
        for match in matches:
            try:
                rel = str(Path(match).relative_to(search_path))
            except ValueError:
                rel = match
            result_lines.append(rel)
        return "\n".join(result_lines), False
    elif tool_name == "TaskCreate":
        return "Task created.", False
    elif tool_name == "TaskUpdate":
        return "Task updated.", False
    elif tool_name == "TaskList":
        return "Tasks listed.", False
    elif tool_name == "TaskGet":
        return "Task fetched.", False
    else:
        return f"Tool {tool_name} executed.", False


def dispatch_handler(
    handler: Callable[..., list[dict]],
    args: dict,
    cwd: str,
    emit_streaming: bool,
    plugin_dir: str | None = None,
) -> list[dict]:
    """Call a handler with the appropriate signature based on its parameters."""
    sig = inspect.signature(handler)
    params = set(sig.parameters.keys())
    kwargs: dict[str, object] = {"emit_streaming": emit_streaming}
    if "args" in params:
        kwargs["args"] = args
    if "cwd" in params:
        kwargs["cwd"] = cwd
    if "plugin_dir" in params:
        kwargs["plugin_dir"] = plugin_dir
    return handler(**kwargs)


def handle_emit_garbage(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit non-JSON garbage to stdout, simulating a broken Anthropic API response.

    Outputs a valid text message first, then writes raw garbage bytes directly
    to stdout. The output processor should surface a clean error instead of
    crashing silently.
    """
    text = args.get("text", "Normal text before garbage")
    garbage = args.get("garbage", "THIS IS NOT JSON {{{invalid>>> \x00\xff")

    message_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id, text))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=[make_text_block(text)]))

    # Write the valid messages, then inject raw garbage directly to stdout
    # before returning (the caller will append make_end_message, which will
    # never be reached by the parser because it chokes on the garbage first).
    for msg in messages:
        sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.write(garbage + "\n")
    sys.stdout.flush()
    # Return empty — we already wrote everything manually
    return []


def handle_hang(args: dict, emit_streaming: bool) -> list[dict]:
    """Block forever without producing output, simulating a non-responsive Claude.

    The process emits nothing after the init message and never exits.
    The only way to recover is SIGTERM (via the Stop button).
    Uses ``time.sleep`` so the SIGTERM handler installed by ``main()`` fires
    immediately (unlike ``subprocess.run`` which may mask the signal).
    """
    seconds: float = args.get("seconds", 3600)
    time.sleep(seconds)
    return []


def handle_ignore_stdin(args: dict, emit_streaming: bool) -> list[dict]:
    """Emit a normal response but never read from stdin, simulating stdin backpressure.

    After emitting the response, blocks for ``seconds`` without reading stdin.
    If the caller tries to write to our stdin (e.g. a follow-up message or
    interrupt), the pipe buffer will fill up.  The queue-based stdin writer
    should prevent this from blocking Sculptor's event processing loop.
    """
    text = args.get("text", "Response from ignore_stdin command")
    seconds: float = args.get("seconds", 30)

    message_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id, text))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=[make_text_block(text)]))

    # Emit the response messages immediately (the caller appends make_end_message)
    for msg in messages:
        sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

    # Now block without reading stdin — if Sculptor writes to our stdin,
    # the OS pipe buffer fills up (~64KB on macOS / Linux).
    time.sleep(seconds)
    return []


def handle_api_error(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate a transient API error (e.g. 429 rate limit).

    Emits an init message followed by an error end message with ``is_error=True``,
    then exits with code 1.  The output processor raises ``AgentTransientError``
    (a subclass of ``AgentClientError``), which the agent wrapper catches and
    converts to a ``RequestFailureAgentMessage``.  The task shows an error block
    in the chat but the agent remains running and can accept follow-up messages.

    Args:
        delay_seconds: Optional delay before emitting the error.  Useful in
            integration tests that need to navigate away from the workspace
            before the error fires.
    """
    delay_seconds: float = args.get("delay_seconds", 0)
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    error_message = args.get("message", "API Error: 429 Rate limited")
    session_id = generate_id("session")

    _emit_event(make_init_message(session_id))
    _emit_event(make_end_message(session_id, is_error=True, result=error_message))

    # Exit immediately so the caller doesn't append a duplicate end message.
    sys.exit(1)


def handle_usage_limit(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate the Claude CLI reaching the account usage limit (SCU-1129).

    When the account usage limit is hit, the real CLI emits a
    ``rate_limit_event`` frame whose ``rate_limit_info.status`` is ``"rejected"``
    and then *pauses* — it keeps the process alive (waiting for the limit to
    reset) without ever emitting a terminating ``result`` message.  The frame
    shape here mirrors the Claude Code v2.x schema
    (``status`` / ``resetsAt`` / ``rateLimitType``); the CLI's own SDK adapter
    logs "Ignoring rate_limit_event message", so on the wire the frame is purely
    informational and carries no end-of-turn signal.

    This models that behavior exactly: emit the rejected frame, then block
    without producing a result.  Absent any handling of the frame, Sculptor's
    output processor ignores it, ``found_final_message`` never flips, and the
    "Thinking..." indicator spins forever.

    Args:
        resets_at: Unix timestamp (seconds) when the limit resets.  ``0`` (the
            default) omits a concrete reset time from the frame.
        seconds: How long to block after emitting the frame.  Defaults to the
            same "block effectively forever" value as ``handle_hang`` — the
            process never exits on its own; it is reaped by the SIGTERM the
            process manager sends when the turn is settled or torn down (the
            ``main()`` handler turns that into a clean exit).  This is not a
            window the test races against: the fix ends the turn as soon as it
            reads the rejected frame, well before this elapses.
    """
    resets_at: int = args.get("resets_at", 0)
    block_seconds: float = args.get("seconds", 3600)
    session_id = generate_id("session")

    rate_limit_info: dict = {"status": "rejected", "rateLimitType": "five_hour"}
    if resets_at:
        rate_limit_info["resetsAt"] = resets_at

    _emit_event(
        {
            "type": "rate_limit_event",
            "rate_limit_info": rate_limit_info,
            "uuid": generate_id("uuid"),
            "session_id": session_id,
        }
    )

    # Pause without emitting a terminating result, mirroring the CLI waiting for
    # the limit to reset.
    time.sleep(block_seconds)
    return []


def handle_crash(args: dict, emit_streaming: bool) -> list[dict]:
    """Simulate an unrecoverable agent crash that puts the task into ERROR state.

    Emits an init message followed by a ``tool_result`` (user) message with no
    assistant turn in flight.  ``_parse_tool_result_response`` asserts a turn is
    active (``current_turn_id is not None``), so this raises ``AssertionError``,
    which is **not** an ``AgentClientError``.  The agent wrapper re-raises
    anything that isn't an ``AgentClientError``, so the exception propagates out
    of the turn and puts the task into ERROR state — unlike a recoverable API
    error, which surfaces an error block and leaves the agent running.

    (This deliberately does not rely on a malformed message shape: the output
    processor now normalizes those and contains any parser exception as a
    warning, so a bad message alone no longer crashes the turn.)

    Args:
        pause_path: Optional sentinel path (see ``FakeClaudePause``).  When set,
            the crash blocks until the test touches the file, so the test can
            navigate away first and then release it — the crash fires while the
            workspace is unfocused, with no wall-clock race.  Preferred over
            ``delay_seconds`` for that "crash while backgrounded" pattern.
        delay_seconds: Optional wall-clock delay before emitting the crash.
    """
    pause_path: str | None = args.get("pause_path")
    if pause_path is not None:
        sentinel = Path(pause_path)
        if not _wait_until(timeout_seconds=120, poll_interval=0.05, done=sentinel.exists):
            raise RuntimeError(f"fake_claude:crash timed out after 120s waiting for {sentinel}")
    else:
        delay_seconds: float = args.get("delay_seconds", 0)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    session_id = generate_id("session")

    _emit_event(make_init_message(session_id))

    # A tool_result arriving with no assistant turn in flight violates the output
    # processor's ``current_turn_id is not None`` invariant and raises
    # AssertionError — a non-AgentClientError the wrapper treats as an
    # unrecoverable crash.
    _emit_event(make_tool_result_message(tool_use_id=generate_id("toolu"), content="crash"))

    sys.exit(1)


def handle_error_then_hang(args: dict, emit_streaming: bool, cwd: str) -> list[dict]:
    """Emit an error end message then block, simulating a Claude CLI that
    reports an API error but stays alive waiting for more stdin input.

    This exercises the code path where ``build_and_process_output`` raises
    ``AgentClientError`` due to ``is_error=True`` on the end message.  Because
    the process cleanup code (``close_stdin``/``wait``/``terminate``) lives
    *outside* the try-finally in ``_read_output_from_process``, the exception
    causes cleanup to be skipped entirely and the process is never terminated.

    Writes the process PID to a file so the test can verify whether the
    process was terminated after the turn.  The ``pid_file`` arg may be an
    absolute path (for cross-directory access from tests) or a relative name
    resolved against *cwd*.
    """
    seconds: float = args.get("seconds", 3600)
    error_text = args.get("error", "Internal error")
    pid_file = args.get("pid_file", ".error_then_hang.pid")

    # Write our PID so the test can verify whether we were terminated.
    pid_path = Path(pid_file) if Path(pid_file).is_absolute() else Path(cwd) / pid_file
    pid_path.write_text(str(os.getpid()))

    # Write the error end message directly to stdout (bypassing the normal
    # main() flow which would append a non-error end message after we return).
    end_msg = make_end_message(session_id=None, is_error=True, result=error_text)
    sys.stdout.write(json.dumps(end_msg) + "\n")
    sys.stdout.flush()

    # Stay alive — the real Claude CLI keeps its stdin loop running after
    # emitting a result, waiting for more messages.  If the process manager
    # never calls close_stdin() or terminate(), this process leaks.
    time.sleep(seconds)
    return []


def handle_succeed_then_hang(args: dict, emit_streaming: bool, cwd: str) -> list[dict]:
    """Emit a complete successful response (including end message) directly to
    stdout, then block — simulating a Claude CLI that finishes its output but
    the process stays alive (e.g. a backgrounded child process keeps it open).

    This exercises the shutdown path in ``_read_output_from_process`` where
    ``build_and_process_output`` completes *without* error, but the process
    doesn't exit after stdin is closed, forcing ``_shutdown_process`` to
    escalate to SIGTERM.  After SIGTERM the process has a non-zero exit code
    (143), and the exit-code diagnostic code should *not* treat this as a
    failure — the response was already fully captured.

    Writes the process PID to a file so the test can verify the process was
    terminated and inspect the outcome.
    """
    text = args.get("text", "Successful response")
    seconds: float = args.get("seconds", 3600)
    pid_file = args.get("pid_file", ".succeed_then_hang.pid")

    # Write our PID so the test can verify whether we were terminated.
    pid_path = Path(pid_file) if Path(pid_file).is_absolute() else Path(cwd) / pid_file
    pid_path.write_text(str(os.getpid()))

    # Build a complete response: assistant message + end message.
    message_id = generate_id("msg")
    messages: list[dict] = []
    if emit_streaming:
        messages.extend(make_streaming_text_events(message_id, text))
    messages.append(make_assistant_message(message_id=message_id, content_blocks=[make_text_block(text)]))
    messages.append(make_end_message(session_id=None))

    # Write everything directly to stdout so build_and_process_output sees a
    # complete, successful turn.  We bypass the normal main() return flow
    # because we need to hang *after* the end message is emitted.
    for msg in messages:
        sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

    # Stay alive — simulates a backgrounded child process keeping the CLI
    # open.  The process manager should close stdin, wait 5s, then SIGTERM.
    time.sleep(seconds)
    return []


def handle_spawn_subprocess_and_hang(args: dict, emit_streaming: bool, cwd: str) -> list[dict]:
    """Spawn a long-running subprocess via ``Popen`` (no auto-cleanup), record its
    PID, then sleep.

    Used to verify SCU-211: foreground subprocesses spawned by the agent must
    be killed when the user clicks Stop. Unlike ``handle_bash`` which uses
    ``subprocess.run`` (whose internal ``except`` clause SIGKILLs the child
    when an exception — including the SystemExit from the SIGTERM handler —
    propagates), this handler leaks the child on exit. That mirrors what
    happens when an agent spawns a subprocess via ``Popen`` without tracking
    it, which is the realistic leak scenario.

    The child is ``sh -c <command>``; the default command writes ``$$`` to the
    PID file then ``exec sleep <child_seconds>``, so the recorded PID belongs
    to the long-running process Stop must kill (not an exited shell).
    """
    pid_file = args["pid_file"]
    child_seconds: float = args.get("child_seconds", 300)
    hang_seconds: float = args.get("hang_seconds", 60)
    command = args.get("command", f"exec sleep {child_seconds}")

    # stdout/stderr go to DEVNULL so the child doesn't keep FakeClaude's pipes
    # open (which would tie its lifetime to our fds).
    proc = subprocess.Popen(  # noqa: S603,S607
        ["sh", "-c", command],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    pid_path = Path(pid_file) if Path(pid_file).is_absolute() else Path(cwd) / pid_file
    pid_path.write_text(str(proc.pid))

    # Stay alive so the agent appears to still be working when the test clicks
    # Stop. The SIGTERM handler installed in ``main()`` exits cleanly via
    # ``sys.exit``; ``Popen.__del__`` does NOT kill the child, so the
    # subprocess is orphaned unless Sculptor's shutdown path kills the whole
    # process group.
    time.sleep(hang_seconds)
    return []


def handle_spawn_sigterm_immune_subprocess_and_hang(args: dict, emit_streaming: bool, cwd: str) -> list[dict]:
    """Spawn a foreground subprocess that IGNORES SIGTERM, make FakeClaude itself
    ignore SIGTERM too, record the child's PID, then hang.

    Models the SCU-1340 scenario: the agent CLI is blocked on a foreground
    subprocess (e.g. a Bash tool) whose process traps/ignores SIGTERM, so Stop's
    SIGTERM cascade does not stop it — only escalation to SIGKILL on the whole
    process group will. Because FakeClaude *also* ignores SIGTERM here, the
    message-processing worker thread stays alive through Stop's SIGTERM phase,
    forcing the SIGKILL phase to fire — which is exactly the escalation under
    test. Both processes are reaped only when SIGKILL reaches the agent CLI's
    process group.

    Contrast ``handle_spawn_subprocess_and_hang``, whose child dies cleanly on
    SIGTERM (the SCU-211 leak scenario). The child's PID is written to
    ``pid_file`` so the test can probe whether Stop reaped it.
    """
    pid_file = args["pid_file"]
    hang_seconds: float = args.get("hang_seconds", 60)

    # Make THIS process (the fake agent CLI) survive SIGTERM, overriding the
    # handler main() installed. Only SIGKILL on the process group stops it.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    # The child shell traps (ignores) SIGTERM and loops forever; ``$$`` is the
    # trapping shell's own PID, so the recorded PID belongs to a SIGTERM-immune
    # process that only SIGKILL can reap.
    child_command = "trap '' TERM; while true; do sleep 1; done"
    proc = subprocess.Popen(  # noqa: S603,S607
        ["sh", "-c", child_command],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    pid_path = Path(pid_file) if Path(pid_file).is_absolute() else Path(cwd) / pid_file
    pid_path.write_text(str(proc.pid))

    # Hang without reading stdin so the stdin-interrupt path is a no-op and Stop
    # must fall through to the SIGTERM→SIGKILL signal escalation.
    time.sleep(hang_seconds)
    return []


class UnknownFakeClaudeCommandError(ValueError):
    """Raised when an unknown fake_claude command is encountered."""


COMMAND_REGISTRY: dict[str, Callable[..., list[dict]]] = {
    "text": handle_text,
    "stream_text": handle_stream_text,
    "write_file": handle_write_file,
    "edit_file": handle_edit_file,
    "bash": handle_bash,
    "text_and_bash": handle_text_and_bash,
    "sleep": handle_sleep,
    "wait_for_file": handle_wait_for_file,
    "reference_absorbed": handle_reference_absorbed,
    "task_create": handle_task_create,
    "task_update": handle_task_update,
    "task_list": handle_task_list,
    "task_get": handle_task_get,
    "write_corrupt_task": handle_write_corrupt_task,
    "ask_user_question": handle_ask_user_question,
    "ask_user_question_and_continue": handle_ask_user_question_and_continue,
    "ask_user_question_invalid_input": handle_ask_user_question_invalid_input,
    "ask_user_question_then_api_error": handle_ask_user_question_then_api_error,
    "enter_plan_mode": handle_enter_plan_mode,
    "enter_plan_mode_and_ask": handle_enter_plan_mode_and_ask,
    "exit_plan_mode": handle_exit_plan_mode,
    "auto_compact": handle_auto_compact,
    "auto_compact_no_summary": handle_auto_compact_no_summary,
    "auto_compact_mid_stream": handle_auto_compact_mid_stream,
    "background_task_started": handle_background_task_started,
    "background_task_notification": handle_background_task_notification,
    "emit_task_notification": handle_emit_task_notification,
    "emit_task_updated": handle_emit_task_updated,
    "emit_result": handle_emit_result,
    "notification_turn_then_response": handle_notification_turn_then_response,
    "auto_bg_bash": handle_auto_bg_bash,
    "multi_step": handle_multi_step,
    "parallel_tools": handle_parallel_tools,
    "interleaved_tools": handle_interleaved_tools,
    "emit_garbage": handle_emit_garbage,
    "hang": handle_hang,
    "ignore_stdin": handle_ignore_stdin,
    "api_error": handle_api_error,
    "usage_limit": handle_usage_limit,
    "crash": handle_crash,
    "error_then_hang": handle_error_then_hang,
    "succeed_then_hang": handle_succeed_then_hang,
    "spawn_subprocess_and_hang": handle_spawn_subprocess_and_hang,
    "spawn_sigterm_immune_subprocess_and_hang": handle_spawn_sigterm_immune_subprocess_and_hang,
    "subagent": handle_subagent,
    "subagent_ask_user_question": handle_subagent_ask_user_question,
    "ask_user_question_then_subagent_ask": handle_ask_user_question_then_subagent_ask,
    "two_subagents_ask_user_question": handle_two_subagents_ask_user_question,
    "background_subagent": handle_background_subagent,
    "workflow_run": handle_workflow_run,
    "read_file": handle_read_file,
    "glob": handle_glob,
}
