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
key).

`abort` is acknowledged with a `response` envelope and, like real pi, leaves
the process alive for the next prompt — it does NOT exit. If a turn is in
flight, abort preempts it and emits an `agent_end` whose assistant message
carries `stopReason:"aborted"` plus whatever partial text the directives
produced. To let abort interrupt a turn blocked in a
directive (`fake_pi:sleep` / `wait_for_file`), stdin is read on a background
thread that sets an abort flag the directive handlers poll between steps —
kept deterministic via sentinel-file pauses, never wall-clock races. The
process exits on stdin EOF (Sculptor closes stdin at shutdown).

FakePi accepts the `prompt` command's optional `images[]` field (real pi's
base64 `ImageContent` blocks) but never decodes them — it has no model. The
`fake_pi:report_inputs` directive echoes the received image count + mimeTypes
and the prompt text so integration tests can assert image/attachment delivery
end-to-end without a real upstream model.

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
import threading
import time
import uuid
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Event

from sculptor.services.dependency_management_service import PI_VERSION_RANGE

# Mirrors FakeClaude's ``fake_claude:`` directive prefix; keeps the grammar
# parallel so test authors can transplant intuition between the two fakes.
_FAKE_PI_PREFIX = "fake_pi:"

_COMMAND_REGEX = re.compile(r"fake_pi:\S+(?:\s+`[^`]*`)?")

_DEFAULT_RESPONSE_TEXT = "[FakePi] Task completed."

# A prompt rewritten to pi's skill-invocation shape (`/skill:<name> [args]`).
# When such a prompt carries no `fake_pi:` directive, FakePi echoes that it
# "followed" the skill so tests can assert PiAgent rewrote a picked `/name`
# into `/skill:<name>` (FakePi only ever sees the already-rewritten text).
_SKILL_INVOCATION_REGEX = re.compile(r"^/skill:(\S+)")
_SKILL_FOLLOWED_PREFIX = "[FakePi] followed skill: "


def _skill_invocation_name(prompt_text: str) -> str | None:
    """Return the skill name if ``prompt_text`` is a ``/skill:<name>`` invocation."""
    match = _SKILL_INVOCATION_REGEX.match(prompt_text.strip())
    return match.group(1) if match else None


class UnknownFakePiCommandError(ValueError):
    """Raised when an unknown ``fake_pi:`` directive is encountered."""


class _TurnAborted(Exception):
    """Raised inside a directive when an ``abort`` preempts the running turn."""


# stdout is written from two threads (the stdin reader emits the abort ack; the
# main loop emits turn events), so serialize whole lines to avoid interleaving.
_STDOUT_LOCK = threading.Lock()


@dataclass
class _TurnBuilder:
    """Accumulates the text emitted by directives in a single turn.

    Carries the turn's received inputs (the prompt text and any `images[]`
    blocks) so the ``report_inputs`` directive can echo them back — that echo
    is how integration tests assert image/attachment delivery without a model.
    """

    chunks: list[str] = field(default_factory=list)
    prompt_text: str = ""
    images: list[dict] = field(default_factory=list)

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
    # PiAgent passes the workspace's skill source dirs as repeatable --skill
    # flags. Parse them first-class (rather than swallowing them into _extra) so
    # tests can assert which paths were handed to pi.
    parser.add_argument("--skill", action="append", default=[], dest="skill")
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
    line = json.dumps(event, separators=(",", ":")) + "\n"
    with _STDOUT_LOCK:
        sys.stdout.write(line)
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


def _emit_aborted_agent_end(text: str) -> None:
    """Emit the interrupted-turn boundary: an `agent_end` whose assistant message
    carries `stopReason:"aborted"` plus the partial text streamed so far.

    Real pi keeps partial content blocks on the aborted message and fires
    `agent_end` with `willRetry:false`. PiAgent treats this as the interrupted
    boundary (no `PiCrashError`) while an interrupt is pending.
    """
    _emit(
        {
            "type": "agent_end",
            "messages": [_assistant_message(text, stop_reason="aborted")],
            "willRetry": False,
        }
    )


def _handle_emit_text(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    text = args.get("text", "")
    accumulated = builder.full_text + text
    _emit_text_delta(text, accumulated)
    builder.emit(text)


def _handle_stream_text(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    text: str = args.get("text", "")
    chunk_size: int = int(args.get("chunk_size", 8))
    delay_seconds: float = float(args.get("delay_seconds", 0.0))
    if chunk_size <= 0:
        chunk_size = max(1, len(text))
    for offset in range(0, len(text), chunk_size):
        if abort_event.is_set():
            raise _TurnAborted()
        chunk = text[offset : offset + chunk_size]
        accumulated = builder.full_text + chunk
        _emit_text_delta(chunk, accumulated)
        builder.emit(chunk)
        if delay_seconds > 0:
            time.sleep(delay_seconds)


def _handle_tool_call(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
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


def _handle_sleep(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    seconds = float(args.get("seconds", 0))
    if seconds <= 0:
        return
    # Poll in small steps so an abort can preempt the sleep.
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if abort_event.is_set():
            raise _TurnAborted()
        time.sleep(0.05)


def _handle_report_inputs(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    """Echo the inputs FakePi received this turn so tests can assert delivery.

    Surfaces the `images[]` count and mimeTypes (image-input delivery) and the
    full received prompt text — which, for non-image attachments, carries the
    path-instructions block prompt assembly prepends (attachment delivery).
    FakePi has no model and never reads the files; the real-pi suite covers
    that the content is actually used.
    """
    mime_types = ",".join(str(image.get("mimeType", "")) for image in builder.images)
    summary = f"[FakePi] images={len(builder.images)}; mimeTypes=[{mime_types}]; prompt={builder.prompt_text}"
    accumulated = builder.full_text + summary
    _emit_text_delta(summary, accumulated)
    builder.emit(summary)


def _handle_wait_for_file(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    timeout_seconds = float(args.get("timeout_seconds", 120))
    sentinel = Path(args["path"])
    deadline = time.monotonic() + timeout_seconds
    while not sentinel.exists():
        if abort_event.is_set():
            raise _TurnAborted()
        if time.monotonic() >= deadline:
            raise RuntimeError(f"fake_pi:wait_for_file timed out after {timeout_seconds}s waiting for {sentinel}")
        time.sleep(0.05)


def _handle_recall(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
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


_COMMAND_REGISTRY: dict[str, Callable[[dict, _TurnBuilder, Event, _SessionState], None]] = {
    "emit_text": _handle_emit_text,
    "stream_text": _handle_stream_text,
    "tool_call": _handle_tool_call,
    "sleep": _handle_sleep,
    "wait_for_file": _handle_wait_for_file,
    "recall": _handle_recall,
    "report_inputs": _handle_report_inputs,
}


def _dispatch_directives(
    directives: Iterable[str], builder: _TurnBuilder, abort_event: Event, state: _SessionState
) -> None:
    for directive in directives:
        if abort_event.is_set():
            raise _TurnAborted()
        name, args = _parse_directive(directive)
        handler = _COMMAND_REGISTRY.get(name)
        if handler is None:
            raise UnknownFakePiCommandError(f"unknown command '{name}'")
        handler(args, builder, abort_event, state)


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
    images: list[dict],
    turn_directives: list[str],
    system_directives: list[str],
    abort_event: Event,
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
    records nothing. If ``abort_event`` is set while the turn is running, the
    turn is preempted and emits the interrupted boundary (`agent_end` with
    `stopReason:"aborted"` plus the partial text streamed so far) in place of
    the happy-path end.
    """
    directives = turn_directives or system_directives
    error_message = _find_error_directive(directives)
    if error_message is not None:
        _emit_response("prompt", success=False, prompt_id=prompt_id, error=error_message)
        return
    builder = _TurnBuilder(prompt_text=prompt_text, images=images)
    _emit_response("prompt", success=True, prompt_id=prompt_id)
    _emit({"type": "agent_start"})
    _emit_user_message_end(prompt_text)
    try:
        _dispatch_directives(directives, builder, abort_event, state)
        # An abort that lands after the last directive (or during a non-blocking
        # one) is caught here before the happy-path end is emitted.
        if abort_event.is_set():
            raise _TurnAborted()
    except _TurnAborted:
        # Record the (partial) turn for resume, like a completed one.
        _emit_aborted_agent_end(builder.full_text)
        state.record_turn(prompt_text)
        return
    if not builder.has_text:
        skill_name = _skill_invocation_name(prompt_text)
        fallback = f"{_SKILL_FOLLOWED_PREFIX}{skill_name}" if skill_name is not None else _DEFAULT_RESPONSE_TEXT
        _emit_text_delta(fallback, fallback)
        builder.emit(fallback)
    full_text = builder.full_text
    _emit_message_end(full_text)
    _emit_agent_end(full_text)
    state.record_turn(prompt_text)


def _run_rpc_loop(system_prompt: str, session_dir: Path | None, session_id: str) -> int:
    """Drive the RPC loop, reading stdin on a background thread.

    Only `abort` is handled out-of-band by the reader thread (it acks the abort
    and sets ``abort_event``, which the directive handlers poll, so it can
    preempt a turn blocked in a directive). `prompt` and `get_state` are queued
    and handled IN ORDER by the main loop, so `get_state` reflects the message
    count of every preceding turn (PiAgent reads it to verify a resume). Real pi
    stays alive after abort, so the loop keeps going; the process exits on stdin
    EOF (Sculptor closes stdin at shutdown).
    """
    system_directives = _extract_directives(system_prompt)
    # Load (or initialize) the session once at startup; a relaunch with the same
    # dir + id reloads the prior transcript so `recall` / get_state see it.
    state = _SessionState.load(session_dir, session_id)
    command_queue: Queue[dict] = Queue()
    abort_event = Event()
    stdin_closed = Event()

    def _read_stdin() -> None:
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
            command_id = payload.get("id") if isinstance(payload.get("id"), str) else None
            if event_type == "abort":
                # Out-of-band: ack and signal any in-flight turn to wind down; do
                # NOT exit (real pi stays alive — see module docstring).
                _emit_response("abort", success=True, prompt_id=command_id)
                abort_event.set()
            elif event_type in ("prompt", "get_state"):
                # In-order: queued so get_state observes preceding turns' state.
                command_queue.put(payload)
        stdin_closed.set()

    reader = threading.Thread(target=_read_stdin, name="fake_pi-stdin-reader", daemon=True)
    reader.start()

    exit_code = 0
    while True:
        try:
            payload = command_queue.get(timeout=0.05)
        except Empty:
            if stdin_closed.is_set() and command_queue.empty():
                break
            continue
        command_id = payload.get("id") if isinstance(payload.get("id"), str) else None
        if payload.get("type") == "get_state":
            _emit_state(command_id, state)
            continue
        # A fresh turn clears any abort that raced in between turns (mirrors
        # PiAgent clearing interrupt-pending when it sends the next prompt).
        abort_event.clear()
        message_text = payload.get("message", "") or ""
        raw_images = payload.get("images")
        images = raw_images if isinstance(raw_images, list) else []
        turn_directives = _extract_directives(message_text)
        try:
            _run_turn(command_id, message_text, images, turn_directives, system_directives, abort_event, state)
        except UnknownFakePiCommandError as e:
            _emit_response("prompt", success=False, prompt_id=command_id, error=str(e))
            exit_code = 1
            break
    return exit_code


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
