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

The in-run failure path (`fake_pi:turn_error`) instead accepts the prompt
(`response success:true`), starts the agent, then ends the assistant message
with `stopReason:"error"` and an empty body carrying the reason on
`errorMessage` — matching pi's wire shape when a turn fails mid-run (e.g. the
selected model's provider has no key). PiAgent surfaces that reason as a
clean, actionable error.

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

The `fake_pi:ui_request` directive scripts the interactive-backchannel lane:
it emits an `extension_ui_request` (the shape the `sculptor_backchannel`
extension's dialogs produce), blocks until the matching
`extension_ui_response` arrives on stdin, then streams the answer back as
assistant text — exercising the full ask-user-question / plan-approval
round-trip without loading any real extension.

CLI surface matches what ``PiAgent.start`` spawns:

    pi --mode rpc --session-dir <dir> --session-id <id> --append-system-prompt <prompt>
    pi --version

Sessions: FakePi persists a tiny JSON session keyed by ``--session-id`` inside
``--session-dir`` and reloads it on relaunch, so a ``fake_pi:recall`` directive
reproduces pre-restart content — the hook the session-resume integration test
asserts on. ``get_state`` reports the session id + message count (this is how
``PiAgent`` verifies a resume). A ``new_session`` command resets that state to a
fresh id with empty history (mirroring pi's ``/clear``), so a post-reset
``recall`` finds nothing and ``get_state`` reports the new id with messageCount
0 — the hook the context-reset integration test asserts on. Real pi persists a
JSONL transcript; FakePi only needs enough to prove resume + reset continuity.

Model selection: ``get_available_models`` returns a fixed catalog (``_FAKE_PI_MODELS``)
and ``get_state`` reports a current model, so PiAgent surfaces them onto task state
and the chat switcher offers pi's own models. ``set_model`` echoes the chosen model
back and updates the current model, so a switch persists for a following ``get_state``
— the hook the model-selection integration test asserts on. The ``fake_pi:report_model``
directive echoes that current model into the turn text, so a test can assert a switch
reached pi (the turn ran under it), not just that the switcher's display updated.

Wire-protocol reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import threading
import time
import uuid
from collections.abc import Callable
from collections.abc import Iterable
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Event

from pydantic import Field

from sculptor.foundation.pydantic_serialization import MutableModel
from sculptor.services.pi_version import PI_PINNED_VERSION

# Mirrors FakeClaude's ``fake_claude:`` directive prefix; keeps the grammar
# parallel so test authors can transplant intuition between the two fakes.
_FAKE_PI_PREFIX = "fake_pi:"

_COMMAND_REGEX = re.compile(r"fake_pi:\S+(?:\s+`[^`]*`)?")

_DEFAULT_RESPONSE_TEXT = "[FakePi] Task completed."

# Polling cadence (seconds) for abort-preemptible waits and the main command
# loop: directive handlers re-check the abort flag and the loop re-checks for
# stdin EOF at this interval, so neither blocks indefinitely.
_POLL_INTERVAL_SECONDS = 0.05

# A prompt rewritten to pi's skill-invocation shape (`/skill:<name> [args]`).
# When such a prompt carries no `fake_pi:` directive, FakePi echoes that it
# "followed" the skill so tests can assert PiAgent rewrote a picked `/name`
# into `/skill:<name>` (FakePi only ever sees the already-rewritten text).
_SKILL_INVOCATION_REGEX = re.compile(r"^/skill:(\S+)")
_SKILL_FOLLOWED_PREFIX = "[FakePi] followed skill: "

# The fixed model catalog `get_available_models` reports — pi's `Model` wire shape
# ({id, name, provider}). Display names are deliberately FakePi-specific (not any
# Claude `getModelLongName` label) so a test can assert pi's own models populate the
# switcher and Claude's hardcoded names do not. The ids skip the blacklisted /
# dated-pin shapes PiAgent curates away, so the catalog survives curation intact.
_FAKE_PI_MODELS: list[dict[str, str]] = [
    {"id": "fake-pi-opus-4-8", "name": "FakePi Opus 4.8", "provider": "anthropic"},
    {"id": "fake-pi-sonnet-4-6", "name": "FakePi Sonnet 4.6", "provider": "anthropic"},
    {"id": "fake-pi-haiku-4-5", "name": "FakePi Haiku 4.5", "provider": "anthropic"},
]

# Env var a test sets (via update_environment) to override the reported catalog with
# a JSON array of {id, name, provider} entries — e.g. to span multiple providers and
# exercise the authenticated-set filter, or `[]` to model a no-authenticated-providers
# state (empty catalog + no current model).
_FAKE_PI_CATALOG_ENV_VAR = "FAKE_PI_CATALOG"


def _resolve_fake_pi_models() -> list[dict[str, str]]:
    """Return the catalog `get_available_models` reports.

    A JSON list in `FAKE_PI_CATALOG` is honored verbatim, including the empty list
    (which models "no authenticated providers"). Falls back to the fixed
    `_FAKE_PI_MODELS` when the var is unset or not a JSON list, so existing pi
    integration tests are unaffected.
    """
    raw = os.environ.get(_FAKE_PI_CATALOG_ENV_VAR)
    if not raw:
        return _FAKE_PI_MODELS
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _FAKE_PI_MODELS
    if not isinstance(parsed, list):
        return _FAKE_PI_MODELS
    return parsed


def _default_fake_pi_current_model() -> dict[str, str]:
    """The model `get_state` reports as current (the first catalog entry, mirroring
    pi defaulting to its newest model); an empty catalog reports no current model."""
    models = _resolve_fake_pi_models()
    return dict(models[0]) if models else {}


def _skill_invocation_name(prompt_text: str) -> str | None:
    """Return the skill name if ``prompt_text`` is a ``/skill:<name>`` invocation."""
    match = _SKILL_INVOCATION_REGEX.match(prompt_text.strip())
    return match.group(1) if match else None


class UnknownFakePiCommandError(ValueError):
    """Raised when an unknown ``fake_pi:`` directive is encountered."""


class _TurnAborted(Exception):
    """Raised inside a directive when an ``abort`` preempts the running turn."""


class FakePiWaitTimeoutError(RuntimeError):
    """Raised when a ``fake_pi:wait_for_file`` directive's sentinel never appears."""


# stdout is written from two threads (the stdin reader emits the abort ack; the
# main loop emits turn events), so serialize whole lines to avoid interleaving.
_STDOUT_LOCK = threading.Lock()

# `extension_ui_response` payloads, routed here from the background stdin reader
# so a blocked `ui_request` directive can collect its answer while the reader
# keeps handling out-of-band `abort`. The reader is the single stdin consumer,
# and the directive handler is registry-dispatched, so this module-level queue
# is how the two connect.
_UI_RESPONSE_QUEUE: "Queue[dict]" = Queue()


class _TurnBuilder(MutableModel):
    """Accumulates the text emitted by directives in a single turn.

    Carries the turn's received inputs (the prompt text and any `images[]`
    blocks) so the ``report_inputs`` directive can echo them back — that echo
    is how integration tests assert image/attachment delivery without a model.
    """

    prompt_id: str | None = None
    chunks: list[str] = Field(default_factory=list)
    prompt_text: str = ""
    images: list[dict] = Field(default_factory=list)
    _ui_counter: int = 0
    # Set by the `background` directive: it emits the launching run's `agent_end`
    # itself (the launch yields immediately; the completion fires out-of-band on a
    # daemon thread), so `_run_turn` must NOT emit its own trailing agent_end.
    suppress_turn_end: bool = False

    def emit(self, text: str) -> None:
        self.chunks.append(text)

    def reset(self) -> None:
        """Drop accumulated text — used after flushing a message_end mid-turn."""
        self.chunks = []

    def next_ui_request_id(self) -> str:
        """A fresh extension_ui_request id, unique within the turn."""
        self._ui_counter += 1
        return f"{self.prompt_id or 'turn'}-ui-{self._ui_counter}"

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


class _SessionState(MutableModel):
    """FakePi's on-disk session, keyed by ``session_id`` within ``--session-dir``.

    A relaunched FakePi given the same dir + id reloads this, so a
    ``fake_pi:recall`` directive can reproduce the pre-restart user messages.
    Persistence is conditional on a ``--session-dir`` being supplied (so FakePi
    still works ephemerally when run without one).
    """

    session_id: str
    session_file: Path | None
    message_count: int = 0
    user_messages: list[str] = Field(default_factory=list)
    # The model `get_state` reports as current; a `set_model` updates it in place.
    # In-memory only (not persisted): the model-selection test exercises a switch
    # within one process, and PiAgent re-fetches the model at every start.
    current_model: dict[str, str] = Field(default_factory=_default_fake_pi_current_model)

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

    def start_new_session(self) -> None:
        """Mirror pi's `new_session`: a fresh session id with empty history.

        The prior session file is left on disk (pi keeps it); this state now
        points at a NEW id + file, so a following `get_state` reports the new id
        with messageCount 0, `recall` finds no prior context, and a later resume
        of the new id finds it empty.
        """
        self.session_id = uuid.uuid4().hex
        self.message_count = 0
        self.user_messages = []
        if self.session_file is not None:
            self.session_file = self.session_file.parent / f"{self.session_id}.fakepi.json"
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
    # `usage` mirrors real pi's per-assistant-message token report (RPC Types
    # "AssistantMessage"); PiAgent sums it across a run for the turn footer. Only
    # a cleanly-stopped message carries it: a streaming partial has no settled
    # usage yet, and an aborted/errored turn reports no token counts.
    message: dict = {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stopReason": stop_reason,
    }
    if stop_reason == "stop":
        message["usage"] = {"input": 100, "output": 50, "cacheRead": 0, "cacheWrite": 0}
    return message


def _user_message(text: str) -> dict:
    # Real pi records the user's prompt as a role="user" message (no stopReason)
    # and emits a message_end for it at agent-run start. PiAgent must drop that
    # echo; FakePi reproduces it so the drop stays under test.
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _emit_response(
    command: str, success: bool, prompt_id: str | None, error: str | None = None, data: dict | None = None
) -> None:
    payload: dict = {"type": "response", "command": command, "success": success}
    if prompt_id:
        payload["id"] = prompt_id
    if error is not None:
        payload["error"] = error
    if data is not None:
        payload["data"] = data
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


def _emit_error_message_end(error_message: str) -> None:
    """Emit pi's in-run failure boundary: an assistant `message_end` with an
    empty body, `stopReason:"error"`, and the reason on `errorMessage`.

    Mirrors what real pi emits when a turn fails mid-run (e.g. the selected
    model's provider has no key): no in-stream error event, no content, the
    reason carried only on `errorMessage`. PiAgent raises on consuming this.
    """
    _emit(
        {
            "type": "message_end",
            "message": {"role": "assistant", "content": [], "stopReason": "error", "errorMessage": error_message},
        }
    )


def _emit_agent_end(text: str) -> None:
    _emit(
        {
            "type": "agent_end",
            "messages": [_assistant_message(text)] if text else [],
            "willRetry": False,
        }
    )


def _emit_reaction_turn(ack: str) -> None:
    """Emit the out-of-band reaction turn pi runs when the extension wakes the agent
    via `sendUserMessage` after a completion: an assistant acknowledgement bracketed
    by agent_start/agent_end, so Sculptor consumes it as the auto-resume reaction."""
    _emit({"type": "agent_start"})
    _emit(
        {
            "type": "message_end",
            "message": {"role": "assistant", "content": [{"type": "text", "text": ack}], "stopReason": "stop"},
        }
    )
    _emit_agent_end(ack)


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


def _emit_compaction_start(reason: str) -> None:
    _emit({"type": "compaction_start", "reason": reason})


def _emit_compaction_end(reason: str, aborted: bool, will_retry: bool) -> None:
    # `result` mirrors real pi's manual-compact result shape (feasibility §5);
    # PiAgent does not read it (Claude renders no equivalent), but FakePi emits
    # it for wire fidelity.
    _emit(
        {
            "type": "compaction_end",
            "reason": reason,
            "aborted": aborted,
            "willRetry": will_retry,
            "result": {"summary": "", "firstKeptEntryId": "", "tokensBefore": 0, "details": {}},
        }
    )


def _handle_compaction(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    """Emit a compaction_start/end pair mid-turn.

    Mirrors real pi's compaction wire shape (feasibility §5): manual,
    threshold, and overflow all reuse the same two events, differing only in
    ``reason`` (and overflow's ``willRetry:true``). The pair drives Sculptor's
    AutoCompacting* messages → the StatusPill "Compacting" chrome.

    Optional ``wait_path`` blocks between start and end on a sentinel file (as
    ``fake_pi:wait_for_file`` does) so an integration test can observe the
    "Compacting" pill while compaction is held open, then release it and watch
    the pill clear. The compaction events carry no text, so the surrounding
    turn still falls back to the default response when no text directive runs.
    """
    reason = str(args.get("reason", "threshold"))
    aborted = bool(args.get("aborted", False))
    will_retry = bool(args.get("will_retry", False))
    _emit_compaction_start(reason)
    wait_path = args.get("wait_path")
    if wait_path:
        timeout_seconds = float(args.get("timeout_seconds", 120))
        sentinel = Path(wait_path)
        deadline = time.monotonic() + timeout_seconds
        while not sentinel.exists():
            if abort_event.is_set():
                raise _TurnAborted()
            if time.monotonic() >= deadline:
                raise RuntimeError(f"fake_pi:compaction timed out after {timeout_seconds}s waiting for {sentinel}")
            time.sleep(0.05)
    _emit_compaction_end(reason, aborted=aborted, will_retry=will_retry)


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


def _handle_subagent(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    """Script a sub-agent tool call and its out-of-band completion (yield-early).

    Reproduces the wire shape `sculptor_subagent.ts` emits, without spawning real
    child `pi` processes: the `subagent` toolCall block + tool-execution lane whose
    `result.details` carry the versioned LAUNCH payload (`{v, task}`, parsed by
    `subagent.py`), then the launching run's `agent_end`. The launching turn ENDS
    there — the user is unblocked and keeps chatting while the children run (the
    agent does not hold the turn open). Because this directive emits the run's
    `agent_end` itself, it sets ``builder.suppress_turn_end`` so `_run_turn` does
    not emit a second end.

    The completion `notify` (the structured marker Sculptor maps to nested child
    messages + a BackgroundTaskNotification) is emitted OUT-OF-BAND on a daemon
    thread — after an optional `wait_path` hold — so fake pi stays responsive to the
    user's next prompt while the children "run". Sculptor surfaces it via its
    idle-drain. With no `wait_path` the completion fires right after the launch
    turn's `agent_end`, so it is genuinely out-of-band.

    Args (all optional)::

        {"id": "sa1",                   # parent tool-call id
         "task": "...",                 # the single-task argument
         "children": [                  # per-child completion snapshots
             {"childId": "c0", "label": "subagent", "task": "...",
              "status": "done",
              "events": [{"seq":0,"kind":"tool_call","toolCallId":"ct1",
                          "toolName":"read","args":{...}},
                         {"seq":1,"kind":"text","text":"..."}]}],
         "status": "completed",         # or "failed"
         "pgids": [123], "wait_path": "...", "timeout_seconds": 120}

    With no `children` a single trivial done child is scripted so the simplest
    directive still renders a nested group.
    """
    tool_call_id = str(args.get("id") or "sa1")
    task_id = f"sat_{tool_call_id}"
    children = args.get("children")
    if not isinstance(children, list) or not children:
        children = [
            {
                "childId": "c0",
                "label": "subagent",
                "task": "investigate",
                "status": "done",
                "events": [{"seq": 0, "kind": "text", "text": "Sub-agent finished."}],
            }
        ]
    task_arg = {"task": str(args.get("task", "investigate"))}
    count = len(children)
    label = "subagent" if count == 1 else f"{count} sub-agents"
    pgids = args.get("pgids") if isinstance(args.get("pgids"), list) else []

    # Launch: close the issuing assistant message with the subagent toolCall block,
    # then the tool-execution lane carrying the structured LAUNCH payload.
    content: list[dict] = []
    if builder.full_text:
        content.append({"type": "text", "text": builder.full_text})
    content.append({"type": "toolCall", "id": tool_call_id, "name": "subagent", "arguments": task_arg})
    _emit({"type": "message_end", "message": {"role": "assistant", "content": content, "stopReason": "toolUse"}})
    builder.chunks.clear()
    _emit({"type": "tool_execution_start", "toolCallId": tool_call_id, "toolName": "subagent", "args": task_arg})
    start_result = _tool_text_payload(f"Started {count} sub-agent(s)")
    # `"v": 1` MUST match SUBAGENT_PAYLOAD_VERSION (subagent.py / sculptor_subagent.ts).
    start_result["details"] = {
        "v": 1,
        "task": {
            "taskId": task_id,
            "toolCallId": tool_call_id,
            "label": label,
            "pgids": pgids,
            "count": count,
            "status": "running",
        },
    }
    _emit(
        {
            "type": "tool_execution_end",
            "toolCallId": tool_call_id,
            "toolName": "subagent",
            "result": start_result,
            "isError": False,
        }
    )

    # End the launching run NOW (yield-early): the user is unblocked while the
    # children run. Suppress _run_turn's trailing end (we emitted agent_end here).
    _emit_agent_end(builder.full_text)
    builder.suppress_turn_end = True

    status = str(args.get("status", "completed"))
    # `"sculptorSubagentTask"` MUST match SUBAGENT_NOTIFY_MARKER (subagent.py).
    completion = {
        "v": 1,
        "taskId": task_id,
        "toolCallId": tool_call_id,
        "status": status,
        "children": children,
    }
    notify_event = {
        "type": "extension_ui_request",
        "id": builder.next_ui_request_id(),
        "method": "notify",
        "notifyType": "info" if status == "completed" else "warning",
        "message": json.dumps({"sculptorSubagentTask": completion}, separators=(",", ":")),
    }
    # Optionally script the auto-resume reaction turn pi runs when the extension
    # wakes the agent (sendUserMessage) after the completion notify.
    reaction = args.get("reaction")

    def _emit_completion() -> None:
        _emit(notify_event)
        if isinstance(reaction, str) and reaction:
            _emit_reaction_turn(reaction)

    wait_path = args.get("wait_path")
    if wait_path:
        # Hold the completion on a daemon thread until a sentinel file appears, so a
        # test can send a mid-flight prompt (which fake pi answers, since this turn
        # already returned) before the children "complete". `_emit` serializes on
        # _STDOUT_LOCK, so the out-of-band notify never interleaves a later turn.
        timeout_seconds = float(args.get("timeout_seconds", 120))

        def _emit_completion_when_ready() -> None:
            sentinel = Path(wait_path)
            deadline = time.monotonic() + timeout_seconds
            while not sentinel.exists():
                if time.monotonic() >= deadline:
                    return  # give up; the test's completion assertion will fail loudly
                time.sleep(0.05)
            _emit_completion()

        threading.Thread(target=_emit_completion_when_ready, name="fake-pi-subagent-completion", daemon=True).start()
    else:
        # No hold: emit right after the launch run's agent_end. Sculptor has already
        # yielded the turn there, so this is still genuinely out-of-band (its
        # idle-drain surfaces it) — but synchronous, so a one-shot headless run
        # observes it before exiting on EOF.
        _emit_completion()


def _handle_background(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    """Script a background-task tool call and its out-of-band completion (yield-early).

    Reproduces the wire shape `sculptor_background.ts` emits, without spawning a
    real process: the `background` toolCall block + tool-execution lane whose
    `result.details` carry the versioned launch payload (`{v, task}`, parsed by
    `background.py`), then the launching run's `agent_end`. The launching turn ENDS
    there — the user is unblocked and keeps chatting while the task runs (the agent
    does not hold the turn open). Because this directive emits the run's `agent_end`
    itself, it sets ``builder.suppress_turn_end`` so `_run_turn` does not emit a
    second end.

    The completion `notify` (the structured marker Sculptor maps to a
    BackgroundTaskNotification) is emitted OUT-OF-BAND — after the launch turn's
    `agent_end`, so Sculptor surfaces it via its idle-drain rather than within the
    turn. With a `wait_path` it is held on a daemon thread until the sentinel file
    appears (so a test can send a mid-flight prompt first); with no `wait_path` it
    is emitted synchronously right after `agent_end`, so a one-shot headless run
    observes it before exiting on EOF.

    Args (all optional): `id` (tool-call id), `command`, `label`, `pgid`,
    `status` ("completed"/"failed"), `exit_code`, `summary`, `duration_ms`,
    `wait_path`, `timeout_seconds`.
    """
    tool_call_id = str(args.get("id") or "bgtc1")
    task_id = f"bgt_{tool_call_id}"
    command = str(args.get("command", "sleep 1"))
    label = str(args.get("label", "background"))
    pgid = int(args.get("pgid", 0))
    arguments = {"command": command, "label": label}

    # Launch: close the issuing assistant message with the toolCall block, then
    # the tool-execution lane carrying the structured launch payload.
    content: list[dict] = []
    if builder.full_text:
        content.append({"type": "text", "text": builder.full_text})
    content.append({"type": "toolCall", "id": tool_call_id, "name": "background", "arguments": arguments})
    _emit({"type": "message_end", "message": {"role": "assistant", "content": content, "stopReason": "toolUse"}})
    builder.chunks.clear()
    _emit({"type": "tool_execution_start", "toolCallId": tool_call_id, "toolName": "background", "args": arguments})
    start_result = _tool_text_payload(f"Started background task {label} (pid {pgid}): {command}")
    # `"v": 1` MUST match BACKGROUND_PAYLOAD_VERSION (background.py / sculptor_background.ts).
    start_result["details"] = {
        "v": 1,
        "task": {
            "taskId": task_id,
            "toolCallId": tool_call_id,
            "label": label,
            "command": command,
            "pgid": pgid,
            "status": "running",
        },
    }
    _emit(
        {
            "type": "tool_execution_end",
            "toolCallId": tool_call_id,
            "toolName": "background",
            "result": start_result,
            "isError": False,
        }
    )

    # End the launching run NOW (yield-early): the user is unblocked while the task
    # runs. Suppress _run_turn's trailing end (we emitted agent_end ourselves).
    _emit_agent_end(builder.full_text)
    builder.suppress_turn_end = True

    status = str(args.get("status", "completed"))
    # `"sculptorBackgroundTask"` MUST match BACKGROUND_NOTIFY_MARKER (background.py).
    completion = {
        "v": 1,
        "taskId": task_id,
        "toolCallId": tool_call_id,
        "status": status,
        "exitCode": int(args.get("exit_code", 0)),
        "summary": str(args.get("summary", "background task done")),
        "durationMs": int(args.get("duration_ms", 1000)),
    }
    notify_event = {
        "type": "extension_ui_request",
        "id": builder.next_ui_request_id(),
        "method": "notify",
        "notifyType": "info" if status == "completed" else "warning",
        "message": json.dumps({"sculptorBackgroundTask": completion}, separators=(",", ":")),
    }
    # Optionally script the auto-resume reaction turn pi runs when the extension
    # wakes the agent (sendUserMessage) after the completion notify.
    reaction = args.get("reaction")

    def _emit_completion() -> None:
        _emit(notify_event)
        if isinstance(reaction, str) and reaction:
            _emit_reaction_turn(reaction)

    wait_path = args.get("wait_path")
    if wait_path:
        # Hold the completion on a daemon thread until a sentinel file appears, so a
        # test can send a mid-flight prompt (which fake pi answers, since this turn
        # already returned) before the task "completes". `_emit` serializes on
        # _STDOUT_LOCK, so the out-of-band notify never interleaves a later turn.
        timeout_seconds = float(args.get("timeout_seconds", 120))

        def _emit_completion_when_ready() -> None:
            sentinel = Path(wait_path)
            deadline = time.monotonic() + timeout_seconds
            while not sentinel.exists():
                if time.monotonic() >= deadline:
                    return  # give up; the test's completion assertion will fail loudly
                time.sleep(0.05)
            _emit_completion()

        threading.Thread(target=_emit_completion_when_ready, name="fake-pi-bg-completion", daemon=True).start()
    else:
        # No hold: emit right after the launch run's agent_end. Sculptor has already
        # yielded the turn there, so this is still genuinely out-of-band (its
        # idle-drain surfaces it) — but synchronous, so a one-shot headless run
        # observes it before exiting on EOF.
        _emit_completion()


def _handle_sleep(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    seconds = float(args.get("seconds", 0))
    if seconds <= 0:
        return
    # Poll in small steps so an abort can preempt the sleep.
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if abort_event.is_set():
            raise _TurnAborted()
        time.sleep(_POLL_INTERVAL_SECONDS)


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


def _handle_report_model(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    """Echo the model FakePi is running this turn (its session `current_model`).

    Lets a test assert that a model switch actually reached pi — that the turn ran
    under the selected model — not merely that the switcher's display updated.
    """
    model_id = state.current_model.get("id", "") if state.current_model else ""
    summary = f"[FakePi] current_model={model_id}"
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
            raise FakePiWaitTimeoutError(
                f"fake_pi:wait_for_file timed out after {timeout_seconds}s waiting for {sentinel}"
            )
        time.sleep(_POLL_INTERVAL_SECONDS)


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


def _read_extension_ui_response(expected_id: str, abort_event: Event) -> dict:
    """Collect the matching `extension_ui_response` routed from the stdin reader.

    The background reader enqueues `extension_ui_response` payloads on
    `_UI_RESPONSE_QUEUE`; a set `abort_event` (an `abort` command or stdin EOF)
    resolves as a cancellation — mirroring how the real backchannel dialog
    unblocks when the client answers or the turn is aborted. A payload carrying
    `cancelled` (the client's dismissal, or the reader's EOF sentinel) is itself
    a cancellation.
    """
    while not abort_event.is_set():
        try:
            payload = _UI_RESPONSE_QUEUE.get(timeout=0.05)
        except Empty:
            continue
        if payload.get("cancelled"):
            return payload
        if payload.get("id") == expected_id:
            return payload
    return {"cancelled": True}


def _handle_ui_request(args: dict, builder: _TurnBuilder, abort_event: Event, state: _SessionState) -> None:
    """Emit a backchannel dialog, block for the answer, echo it into the turn.

    Scripts the real extension's blocking-dialog lane without loading any
    extension: emit `extension_ui_request {method,title,options}`, wait for the
    matching `extension_ui_response` (routed from the stdin reader), then stream
    the answer back as assistant text so a test can assert the agent used it. A
    `message_end` is flushed first (mirroring pi ending the assistant message
    that carried the tool call) so the post-answer text streams as a fresh
    assistant message.

    `state` is unused (backchannel dialogs are not session-dependent) but the
    signature matches the shared directive-handler contract.

    Args: `method` ("select"/"input"), `title`, optional `options`, optional
    `answer_prefix` (default "ANSWER="), optional `dismissed_text`.
    """
    _emit_message_end(builder.full_text)
    builder.reset()
    request_id = builder.next_ui_request_id()
    event: dict = {"type": "extension_ui_request", "id": request_id, "method": args.get("method", "select")}
    if "title" in args:
        event["title"] = args["title"]
    if "options" in args:
        event["options"] = args["options"]
    _emit(event)
    response = _read_extension_ui_response(request_id, abort_event)
    if response.get("cancelled"):
        answer_text = str(args.get("dismissed_text", "[dismissed]"))
    else:
        answer_text = str(response.get("value", ""))
    rendered = str(args.get("answer_prefix", "ANSWER=")) + answer_text
    _emit_text_delta(rendered, builder.full_text + rendered)
    builder.emit(rendered)


_COMMAND_REGISTRY: dict[str, Callable[[dict, _TurnBuilder, Event, _SessionState], None]] = {
    "emit_text": _handle_emit_text,
    "stream_text": _handle_stream_text,
    "tool_call": _handle_tool_call,
    "subagent": _handle_subagent,
    "background": _handle_background,
    "sleep": _handle_sleep,
    "wait_for_file": _handle_wait_for_file,
    "recall": _handle_recall,
    "report_inputs": _handle_report_inputs,
    "report_model": _handle_report_model,
    "compaction": _handle_compaction,
    "ui_request": _handle_ui_request,
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


def _find_turn_error_directive(directives: Iterable[str]) -> str | None:
    """If any `fake_pi:turn_error` directive is present, return its message."""
    for directive in directives:
        name, args = _parse_directive(directive)
        if name == "turn_error":
            return str(args.get("message", "fake_pi turn error"))
    return None


def _emit_state(prompt_id: str | None, state: _SessionState) -> None:
    """Answer a `get_state` command with pi's `RpcSessionState` shape (RPC §5.1).

    Populates the fields PiAgent reads: ``sessionId`` (always) and
    ``messageCount`` (>0 after a resumed turn) for resume verification,
    ``sessionFile`` when persisted, and ``model`` (the current model) which
    PiAgent surfaces as the switcher's selection.
    """
    data: dict = {
        "sessionId": state.session_id,
        "messageCount": state.message_count,
        "model": state.current_model,
    }
    if state.session_file is not None:
        data["sessionFile"] = str(state.session_file)
    payload: dict = {"type": "response", "command": "get_state", "success": True, "data": data}
    if prompt_id:
        payload["id"] = prompt_id
    _emit(payload)


def _emit_available_models(prompt_id: str | None) -> None:
    """Answer a `get_available_models` command with the fixed catalog (RPC §5.1).

    Returns `_FAKE_PI_MODELS` under `data.models`, the shape PiAgent maps to
    `ModelOption`s and curates for the switcher.
    """
    payload: dict = {
        "type": "response",
        "command": "get_available_models",
        "success": True,
        "data": {"models": _resolve_fake_pi_models()},
    }
    if prompt_id:
        payload["id"] = prompt_id
    _emit(payload)


def _emit_set_model(prompt_id: str | None, model: dict[str, str]) -> None:
    """Acknowledge a `set_model` command, echoing the now-current model in `data`.

    Mirrors pi returning the selected `Model`; PiAgent reads it as the new current
    model. An unknown model id is rejected with `success:false` (pi's `Model not
    found` shape) so the failure-toast path stays exercisable.
    """
    known = any(candidate["id"] == model["id"] for candidate in _resolve_fake_pi_models())
    if not known:
        payload = {
            "type": "response",
            "command": "set_model",
            "success": False,
            "error": f"Model not found: {model.get('provider', '')}/{model['id']}",
        }
    else:
        payload = {"type": "response", "command": "set_model", "success": True, "data": model}
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
    turn_error_message = _find_turn_error_directive(directives)
    if turn_error_message is not None:
        # In-run failure: the prompt is accepted and the agent starts, but the
        # turn ends in error (see _emit_error_message_end). PiAgent raises on the
        # error message_end, so no agent_end follows.
        _emit_response("prompt", success=True, prompt_id=prompt_id)
        _emit({"type": "agent_start"})
        _emit_user_message_end(prompt_text)
        _emit_error_message_end(turn_error_message)
        return
    builder = _TurnBuilder(prompt_id=prompt_id, prompt_text=prompt_text, images=images)
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
    if builder.suppress_turn_end:
        # The `background` directive already emitted the launching run's
        # `agent_end` and the completion notify (the held-open shape); do not
        # emit a second end.
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
            elif event_type == "extension_ui_response":
                # Out-of-band: route to a blocked `ui_request` directive (see
                # _handle_ui_request); the main loop never processes these.
                _UI_RESPONSE_QUEUE.put(payload)
            elif event_type in ("prompt", "get_state", "new_session", "get_available_models", "set_model"):
                # In-order: queued so get_state / new_session / set_model observe
                # preceding turns' state (and a switch lands strictly between turns).
                command_queue.put(payload)
        # Unblock any `ui_request` still waiting when stdin closes at shutdown.
        _UI_RESPONSE_QUEUE.put({"cancelled": True})
        stdin_closed.set()

    reader = threading.Thread(target=_read_stdin, name="fake_pi-stdin-reader", daemon=True)
    reader.start()

    exit_code = 0
    while True:
        try:
            payload = command_queue.get(timeout=_POLL_INTERVAL_SECONDS)
        except Empty:
            if stdin_closed.is_set() and command_queue.empty():
                break
            continue
        command_id = payload.get("id") if isinstance(payload.get("id"), str) else None
        if payload.get("type") == "get_state":
            _emit_state(command_id, state)
            continue
        if payload.get("type") == "get_available_models":
            _emit_available_models(command_id)
            continue
        if payload.get("type") == "set_model":
            # Update the current model so a following get_state reflects the switch,
            # then ack with the now-current model (mirrors pi's set_model).
            requested = {
                "id": str(payload.get("modelId", "")),
                "name": str(payload.get("modelId", "")),
                "provider": str(payload.get("provider", "anthropic")),
            }
            known = next((m for m in _resolve_fake_pi_models() if m["id"] == requested["id"]), None)
            if known is not None:
                state.current_model = dict(known)
            _emit_set_model(command_id, known if known is not None else requested)
            continue
        if payload.get("type") == "new_session":
            # Mirror pi's `/clear`: reset to a fresh session with empty history,
            # then ack. `data.cancelled` is always false here (no extensions to
            # veto the switch); PiAgent reads the new id via a following get_state.
            state.start_new_session()
            _emit_response("new_session", success=True, prompt_id=command_id, data={"cancelled": False})
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
        sys.stderr.write(f"pi {PI_PINNED_VERSION}\n")
        return 0

    if parsed.mode != "rpc":
        sys.stderr.write(f"fake_pi: unsupported --mode {parsed.mode!r}; only 'rpc' is implemented.\n")
        return 2

    session_dir = Path(parsed.session_dir) if parsed.session_dir else None
    # Pi adopts the exact --session-id; fall back to a generated id when absent
    # (real pi picks one too when only --session-dir is given).
    session_id = parsed.session_id or uuid.uuid4().hex
    return _run_rpc_loop(parsed.append_system_prompt, session_dir, session_id)


# Answer `--version` in the wrapper, before exec'ing Python: `_check_pi_version`
# allows `pi --version` only a 5s timeout, which the `python -m
# sculptor.testing.fake_pi` interpreter + `sculptor`-import startup can blow on a
# contended host, failing the launch. Mirror `fake_pi.main`'s `pi <version>` stderr line.
_BINARY_WRAPPER_TEMPLATE = """#!/bin/bash
case "$1" in
--version|-v) echo "pi {version}" >&2; exit 0;;
esac
exec {python} -m sculptor.testing.fake_pi "$@"
"""


def install_fake_pi_binary(fake_bin_dir: Path) -> Path:
    """Install FakePi as a ``pi`` binary in ``fake_bin_dir``.

    Writes a bash wrapper that answers ``--version`` directly and otherwise execs
    ``python -m sculptor.testing.fake_pi`` with the current interpreter. Returns
    the absolute path to the wrapper so callers can pin it into
    ``DependencyPaths.pi`` — pinning the absolute path mirrors
    ``install_default_claude_stub`` and avoids PATH-ordering races when
    subprocesses mutate PATH.
    """
    binary_path = fake_bin_dir / "pi"
    binary_path.write_text(
        _BINARY_WRAPPER_TEMPLATE.format(
            python=shlex.quote(sys.executable),
            version=PI_PINNED_VERSION,
        )
    )
    binary_path.chmod(0o755)
    return binary_path


if __name__ == "__main__":
    sys.exit(main())
