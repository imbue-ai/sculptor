"""FakePi CLI — drop-in replacement for `pi --mode rpc` in integration tests.

Mirrors FakeClaude's command-grammar shape (`fake_pi:` directive prefix,
JSON args in backticks) but speaks pi's three-channel RPC envelope.

Per-turn emission for the happy path::

    {"type":"response","command":"prompt","success":true,"id":<echoed>}
    {"type":"agent_start"}
    {"type":"message_end","message":{"role":"user",...}}   # prompt echo
    {"type":"message_update","message":{...},"assistantMessageEvent":{...}}
    ...
    {"type":"message_end","message":{"role":"assistant",...}}
    {"type":"agent_end","messages":[...],"willRetry":false}

The leading role="user" `message_end` mirrors how real pi records the
prompt at agent-run start; PiAgent drops it (only assistant messages are
surfaced).

The preflight-failure path (`fake_pi:error`) emits a `response` with
`success:false` and no session events, matching pi's behavior
when the prompt is rejected before the agent starts (e.g. missing API
key). `abort` is acknowledged with a `response` envelope too.

CLI surface matches what ``PiAgent.start`` spawns:

    pi --mode rpc --session-dir <dir> --session-id <id> --append-system-prompt <prompt>
    pi --version

Sessions: FakePi persists a tiny JSON session keyed by ``--session-id`` inside
``--session-dir`` and reloads it on relaunch, so a ``fake_pi:recall`` directive
reproduces pre-restart content — the hook the session-resume integration test
asserts on. ``get_state`` reports the session id + message count (this is how
``PiAgent`` verifies a resume). Real pi persists a JSONL transcript; FakePi only
needs enough to prove resume continuity.

Wire-protocol reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import time
import uuid
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from sculptor.services.dependency_management_service import PI_VERSION_RANGE

# Mirrors FakeClaude's ``fake_claude:`` directive prefix; keeps the grammar
# parallel so test authors can transplant intuition between the two fakes.
_FAKE_PI_PREFIX = "fake_pi:"

_COMMAND_REGEX = re.compile(r"fake_pi:\S+(?:\s+`[^`]*`)?")

_DEFAULT_RESPONSE_TEXT = "[FakePi] Task completed."


class UnknownFakePiCommandError(ValueError):
    """Raised when an unknown ``fake_pi:`` directive is encountered."""


@dataclass
class _TurnBuilder:
    """Accumulates the text emitted by directives in a single turn."""

    chunks: list[str] = field(default_factory=list)

    def emit(self, text: str) -> None:
        self.chunks.append(text)

    @property
    def has_text(self) -> bool:
        return any(chunk != "" for chunk in self.chunks)

    @property
    def full_text(self) -> str:
        return "".join(self.chunks)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FakePi — test replacement for `pi --mode rpc`")
    parser.add_argument("-v", "--version", action="store_true")
    parser.add_argument("--mode", default=None)
    # --no-session kept for back-compat; PiAgent now spawns with the session flags.
    parser.add_argument("--no-session", action="store_true")
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--append-system-prompt", default="")
    parsed, _extra = parser.parse_known_args(argv)
    return parsed


@dataclass
class _SessionState:
    """FakePi's on-disk session, keyed by ``session_id`` within ``--session-dir``.

    A relaunched FakePi given the same dir + id reloads this, so a
    ``fake_pi:recall`` directive can reproduce the pre-restart user messages.
    Persistence is conditional on a ``--session-dir`` being supplied (so FakePi
    still works ephemerally when run without one).
    """

    session_id: str
    session_file: Path | None
    message_count: int = 0
    user_messages: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, session_dir: Path | None, session_id: str) -> "_SessionState":
        if session_dir is None:
            return cls(session_id=session_id, session_file=None)
        session_file = session_dir / f"{session_id}.fakepi.json"
        if session_file.exists():
            data = json.loads(session_file.read_text())
            return cls(
                session_id=str(data.get("sessionId", session_id)),
                session_file=session_file,
                message_count=int(data.get("messageCount", 0)),
                user_messages=list(data.get("userMessages", [])),
            )
        return cls(session_id=session_id, session_file=session_file)

    def record_turn(self, user_message: str) -> None:
        self.user_messages.append(user_message)
        # Mirror real pi: one user + one assistant message recorded per turn.
        self.message_count += 2
        self._save()

    def _save(self) -> None:
        if self.session_file is None:
            return
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(
            json.dumps(
                {
                    "sessionId": self.session_id,
                    "messageCount": self.message_count,
                    "userMessages": self.user_messages,
                }
            )
        )


def _parse_directive(directive: str) -> tuple[str, dict]:
    """Split ``fake_pi:<name> `<json>`` into ``(name, args)``.

    Mirrors FakeClaude's ``_parse_prompt`` shape: name then optional
    backtick-wrapped JSON payload.
    """
    rest = directive[len(_FAKE_PI_PREFIX) :]
    backtick_start = rest.find("`")
    if backtick_start == -1:
        name = rest.strip().split()[0] if rest.strip() else ""
        return name, {}
    name = rest[:backtick_start].strip().split()[0] if rest[:backtick_start].strip() else ""
    backtick_end = rest.rfind("`")
    if backtick_end <= backtick_start:
        return name, {}
    return name, json.loads(rest[backtick_start + 1 : backtick_end])


def _extract_directives(text: str) -> list[str]:
    """Return every ``fake_pi:`` directive present in ``text``, in order."""
    return _COMMAND_REGEX.findall(text or "")


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _assistant_message(text: str, stop_reason: str = "stop") -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stopReason": stop_reason,
    }


def _user_message(text: str) -> dict:
    # Real pi records the user's prompt as a role="user" message (no stopReason)
    # and emits a message_end for it at agent-run start. PiAgent must drop that
    # echo; FakePi reproduces it so the drop stays under test.
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _emit_response(command: str, success: bool, prompt_id: str | None, error: str | None = None) -> None:
    payload: dict = {"type": "response", "command": command, "success": success}
    if prompt_id:
        payload["id"] = prompt_id
    if error is not None:
        payload["error"] = error
    _emit(payload)


def _emit_text_delta(text: str, partial: str, content_index: int = 0) -> None:
    _emit(
        {
            "type": "message_update",
            "message": _assistant_message(partial, stop_reason=""),
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": content_index,
                "delta": text,
            },
        }
    )


def _emit_message_end(text: str) -> None:
    _emit({"type": "message_end", "message": _assistant_message(text)})


def _tool_text_payload(text: str) -> dict:
    """pi's tool result / partialResult envelope: {content:[{type:text,text}]}."""
    return {"content": [{"type": "text", "text": text}]}


def _emit_user_message_end(text: str) -> None:
    _emit({"type": "message_end", "message": _user_message(text)})


def _emit_agent_end(text: str) -> None:
    _emit(
        {
            "type": "agent_end",
            "messages": [_assistant_message(text)] if text else [],
            "willRetry": False,
        }
    )


def _handle_emit_text(args: dict, builder: _TurnBuilder, state: _SessionState) -> None:
    text = args.get("text", "")
    accumulated = builder.full_text + text
    _emit_text_delta(text, accumulated)
    builder.emit(text)


def _handle_stream_text(args: dict, builder: _TurnBuilder, state: _SessionState) -> None:
    text: str = args.get("text", "")
    chunk_size: int = int(args.get("chunk_size", 8))
    delay_seconds: float = float(args.get("delay_seconds", 0.0))
    if chunk_size <= 0:
        chunk_size = max(1, len(text))
    for offset in range(0, len(text), chunk_size):
        chunk = text[offset : offset + chunk_size]
        accumulated = builder.full_text + chunk
        _emit_text_delta(chunk, accumulated)
        builder.emit(chunk)
        if delay_seconds > 0:
            time.sleep(delay_seconds)


def _handle_tool_call(args: dict, builder: _TurnBuilder, state: _SessionState) -> None:
    """Emit one tool call: close the current assistant message with a toolCall
    block, then stream the tool-execution lane (start → updates → end).

    Args (all but ``tool`` optional)::

        {"tool": "read"|"write"|"bash"|"edit"|<other>,
         "args": {...},          # the tool's arguments (pi's arg schema)
         "result": "...",        # tool_execution_end result text
         "details": {...},       # optional result.details (e.g. {patch} for edit)
         "is_error": false,
         "updates": ["...", ...],# accumulated partialResult snapshots
         "id": "call_1"}         # tool-call id (defaults from the tool name)

    Mirrors real pi's ordering: the assistant message that issues the call ends
    (``stopReason:"toolUse"``) carrying both its text-so-far and the ``toolCall``
    content block, BEFORE the matching ``tool_execution_start`` — so the
    reconciliation path (toolCall block + lane events → one rendered block) is
    exercised. The text builder is reset so any subsequent text becomes a new
    assistant message.
    """
    tool = str(args.get("tool", ""))
    tool_args = args.get("args", {})
    if not isinstance(tool_args, dict):
        tool_args = {}
    tool_call_id = str(args.get("id") or f"call_{tool or 'tool'}")
    result_text = str(args.get("result", ""))
    is_error = bool(args.get("is_error", False))
    details = args.get("details")
    updates = args.get("updates", [])
    if not isinstance(updates, list):
        updates = []

    # Close the issuing assistant message with text-so-far + the toolCall block.
    content: list[dict] = []
    if builder.full_text:
        content.append({"type": "text", "text": builder.full_text})
    content.append({"type": "toolCall", "id": tool_call_id, "name": tool, "arguments": tool_args})
    _emit({"type": "message_end", "message": {"role": "assistant", "content": content, "stopReason": "toolUse"}})
    builder.chunks.clear()

    # Tool-execution lane.
    _emit({"type": "tool_execution_start", "toolCallId": tool_call_id, "toolName": tool, "args": tool_args})
    for update in updates:
        _emit(
            {
                "type": "tool_execution_update",
                "toolCallId": tool_call_id,
                "toolName": tool,
                "args": tool_args,
                "partialResult": _tool_text_payload(str(update)),
            }
        )
    end_result = _tool_text_payload(result_text)
    if isinstance(details, dict):
        # Real pi nests file-tool diff metadata under result.details (e.g. an
        # edit's {patch}); mirror that so the rendering adapter is exercised.
        end_result["details"] = details
    _emit(
        {
            "type": "tool_execution_end",
            "toolCallId": tool_call_id,
            "toolName": tool,
            "result": end_result,
            "isError": is_error,
        }
    )


def _handle_sleep(args: dict, builder: _TurnBuilder, state: _SessionState) -> None:
    seconds = float(args.get("seconds", 0))
    if seconds > 0:
        time.sleep(seconds)


def _handle_wait_for_file(args: dict, builder: _TurnBuilder, state: _SessionState) -> None:
    timeout_seconds = float(args.get("timeout_seconds", 120))
    sentinel = Path(args["path"])
    deadline = time.monotonic() + timeout_seconds
    while not sentinel.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError(f"fake_pi:wait_for_file timed out after {timeout_seconds}s waiting for {sentinel}")
        time.sleep(0.05)


def _handle_recall(args: dict, builder: _TurnBuilder, state: _SessionState) -> None:
    """Emit the user messages remembered from BEFORE this turn.

    Recall succeeds only if the prior session was reloaded from disk by
    ``--session-id`` — i.e. the resume worked. Directives run before the
    current turn is recorded, so ``state.user_messages`` holds only earlier
    turns. With no prior context (fresh / failed resume) it emits a sentinel the
    test can assert the ABSENCE of.
    """
    if state.user_messages:
        builder.emit("RECALL:" + " | ".join(state.user_messages))
    else:
        builder.emit("RECALL:NO_PRIOR_CONTEXT")


_COMMAND_REGISTRY: dict[str, Callable[[dict, _TurnBuilder, _SessionState], None]] = {
    "emit_text": _handle_emit_text,
    "stream_text": _handle_stream_text,
    "tool_call": _handle_tool_call,
    "sleep": _handle_sleep,
    "wait_for_file": _handle_wait_for_file,
    "recall": _handle_recall,
}


def _dispatch_directives(directives: Iterable[str], builder: _TurnBuilder, state: _SessionState) -> None:
    for directive in directives:
        name, args = _parse_directive(directive)
        handler = _COMMAND_REGISTRY.get(name)
        if handler is None:
            raise UnknownFakePiCommandError(f"unknown command '{name}'")
        handler(args, builder, state)


def _find_error_directive(directives: Iterable[str]) -> str | None:
    """If any `fake_pi:error` directive is present, return its message."""
    for directive in directives:
        name, args = _parse_directive(directive)
        if name == "error":
            return str(args.get("message", "fake_pi error"))
    return None


def _emit_state(prompt_id: str | None, state: _SessionState) -> None:
    """Answer a `get_state` command with pi's `RpcSessionState` shape (RPC §5.1).

    Only the fields PiAgent's resume verification reads are populated:
    ``sessionId`` (always) and ``messageCount`` (>0 after a resumed turn);
    ``sessionFile`` when the session is persisted.
    """
    data: dict = {"sessionId": state.session_id, "messageCount": state.message_count}
    if state.session_file is not None:
        data["sessionFile"] = str(state.session_file)
    payload: dict = {"type": "response", "command": "get_state", "success": True, "data": data}
    if prompt_id:
        payload["id"] = prompt_id
    _emit(payload)


def _run_turn(
    prompt_id: str | None,
    prompt_text: str,
    turn_directives: list[str],
    system_directives: list[str],
    state: _SessionState,
) -> None:
    """Emit the wire sequence for one user turn.

    Per-turn directives take precedence over persistent system-prompt
    directives. If a `fake_pi:error` directive is present, emit a
    preflight-failure `response` and stop — matching pi's actual
    behavior when the prompt is rejected before any agent run begins
    (no session events follow). Otherwise emit the happy path:
    response → agent_start → message_end(user prompt echo) →
    message_update(s) → message_end → agent_end. The leading role="user"
    message_end mirrors how pi records the prompt at agent-run start
    (PiAgent drops it). If no directive emits text, fall back to a
    deterministic default.

    The turn is recorded into ``state`` AFTER emission, so a `recall`
    directive in this turn sees only prior turns, and so a preflight error
    records nothing.
    """
    directives = turn_directives or system_directives
    error_message = _find_error_directive(directives)
    if error_message is not None:
        _emit_response("prompt", success=False, prompt_id=prompt_id, error=error_message)
        return
    builder = _TurnBuilder()
    _emit_response("prompt", success=True, prompt_id=prompt_id)
    _emit({"type": "agent_start"})
    _emit_user_message_end(prompt_text)
    _dispatch_directives(directives, builder, state)
    if not builder.has_text:
        _emit_text_delta(_DEFAULT_RESPONSE_TEXT, _DEFAULT_RESPONSE_TEXT)
        builder.emit(_DEFAULT_RESPONSE_TEXT)
    full_text = builder.full_text
    _emit_message_end(full_text)
    _emit_agent_end(full_text)
    state.record_turn(prompt_text)


def _run_rpc_loop(system_prompt: str, session_dir: Path | None, session_id: str) -> int:
    system_directives = _extract_directives(system_prompt)
    # Load (or initialize) the session once at startup; a relaunch with the same
    # dir + id reloads the prior transcript so `recall` / get_state see it.
    state = _SessionState.load(session_dir, session_id)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = payload.get("type")
        prompt_id = payload.get("id") if isinstance(payload.get("id"), str) else None
        if event_type == "get_state":
            _emit_state(prompt_id, state)
            continue
        if event_type == "abort":
            _emit_response("abort", success=True, prompt_id=prompt_id)
            return 0
        if event_type != "prompt":
            continue
        message_text = payload.get("message", "") or ""
        turn_directives = _extract_directives(message_text)
        try:
            _run_turn(prompt_id, message_text, turn_directives, system_directives, state)
        except UnknownFakePiCommandError as e:
            _emit_response("prompt", success=False, prompt_id=prompt_id, error=str(e))
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parsed = _parse_args(argv)

    if parsed.version:
        # WHY: real pi emits --version to stderr, not stdout; FakePi mirrors that.
        sys.stderr.write(f"pi {PI_VERSION_RANGE.recommended_version}\n")
        return 0

    if parsed.mode != "rpc":
        sys.stderr.write(f"fake_pi: unsupported --mode {parsed.mode!r}; only 'rpc' is implemented.\n")
        return 2

    session_dir = Path(parsed.session_dir) if parsed.session_dir else None
    # Pi adopts the exact --session-id; fall back to a generated id when absent
    # (real pi picks one too when only --session-dir is given).
    session_id = parsed.session_id or uuid.uuid4().hex
    return _run_rpc_loop(parsed.append_system_prompt, session_dir, session_id)


_BINARY_WRAPPER_TEMPLATE = """#!/bin/bash
exec {python} -m sculptor.testing.fake_pi "$@"
"""


def install_fake_pi_binary(fake_bin_dir: Path) -> Path:
    """Install FakePi as a ``pi`` binary in ``fake_bin_dir``.

    Writes a bash wrapper that execs ``python -m sculptor.testing.fake_pi``
    with the current interpreter. Returns the absolute path to the wrapper
    so callers can pin it into ``DependencyPaths.pi`` — pinning the absolute
    path mirrors ``install_default_claude_stub`` and avoids PATH-ordering
    races when subprocesses mutate PATH.
    """
    binary_path = fake_bin_dir / "pi"
    binary_path.write_text(_BINARY_WRAPPER_TEMPLATE.format(python=shlex.quote(sys.executable)))
    binary_path.chmod(0o755)
    return binary_path


if __name__ == "__main__":
    sys.exit(main())
