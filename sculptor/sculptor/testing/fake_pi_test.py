"""Unit tests for FakePi.

These cover the CLI surface PiAgent invokes (`pi --version`, `pi --mode rpc
--session-dir <dir> --session-id <id> --append-system-prompt <prompt>`), the
directive grammar embedded in prompts, the session persistence / `recall` /
`get_state` that back session resume, and the `install_fake_pi_binary` helper
that pins FakePi as the pi binary on PATH for integration tests.

The assertions exercise pi's three-channel wire shape: every
`prompt` is acknowledged with a `response` envelope; the happy path then
streams `agent_start` → a role="user" `message_end` (the prompt echo) →
`message_update`(s) → `message_end` → `agent_end` with the full `messages`
array. Envelope assertions filter by `type` rather than fixed index so the
leading user-prompt echo doesn't shift them.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import pytest

from sculptor.agents.pi_agent.output_processor import ParsedAgentEnd
from sculptor.agents.pi_agent.output_processor import ParsedMessageEnd
from sculptor.agents.pi_agent.output_processor import ParsedMessageUpdate
from sculptor.agents.pi_agent.output_processor import RpcResponse
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.testing.fake_pi import _parse_args
from sculptor.testing.fake_pi import install_fake_pi_binary

_FAKE_PI_MODULE = "sculptor.testing.fake_pi"


def _run_fake_pi(
    extra_args: list[str],
    stdin_input: str | None = None,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", _FAKE_PI_MODULE, *extra_args],
        input=stdin_input,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _parse_jsonl(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _send_prompt(message: str, prompt_id: str = "p1") -> str:
    return json.dumps({"type": "prompt", "id": prompt_id, "message": message}) + "\n"


def _send_prompt_with_images(message: str, images: list[dict], prompt_id: str = "p1") -> str:
    return json.dumps({"type": "prompt", "id": prompt_id, "message": message, "images": images}) + "\n"


def _last_assistant_text(events: list[dict]) -> str:
    end = ParsedMessageEnd.model_validate(_by_type(events, "message_end")[-1])
    assert end.message.role == "assistant"
    return str(end.message.content[0]["text"])


def _by_type(events: list[dict], event_type: str) -> list[dict]:
    return [e for e in events if e.get("type") == event_type]


def _first_update(events: list[dict]) -> ParsedMessageUpdate:
    """The first assistant streaming chunk, located by type (not index).

    The happy-path envelope leads with a role="user" `message_end`
    (the prompt echo), so the first `message_update` is not at a
    fixed position.
    """
    return ParsedMessageUpdate.model_validate(_by_type(events, "message_update")[0])


def test_fake_pi_version_reports_pinned_version() -> None:
    result = _run_fake_pi(["--version"])

    assert result.returncode == 0
    # Real pi emits its version to stderr; FakePi mirrors that. Stderr may also
    # carry incidental loguru setup output, so check for the version line as a
    # substring rather than equality.
    assert f"pi {PI_VERSION_RANGE.recommended_version}" in result.stderr
    assert result.stdout == ""


def test_fake_pi_v_short_flag_reports_pinned_version() -> None:
    result = _run_fake_pi(["-v"])

    assert result.returncode == 0
    assert f"pi {PI_VERSION_RANGE.recommended_version}" in result.stderr
    assert result.stdout == ""


def test_fake_pi_rpc_emit_text_directive_produces_full_happy_path_envelope() -> None:
    prompt = 'fake_pi:emit_text `{"text": "hello"}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(prompt),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    # Envelope order: response → agent_start → message_end(user echo) →
    # message_update(s) → message_end(assistant) → agent_end.
    response = RpcResponse.model_validate(events[0])
    assert response.command == "prompt"
    assert response.success is True
    assert response.id == "p1"
    assert events[1]["type"] == "agent_start"
    # pi records the user's prompt as a role="user" message_end at agent-run start.
    user_echo = ParsedMessageEnd.model_validate(events[2])
    assert user_echo.message.role == "user"
    update = _first_update(events)
    assert update.assistant_message_event.get("type") == "text_delta"
    assert update.assistant_message_event.get("delta") == "hello"
    end = ParsedMessageEnd.model_validate(_by_type(events, "message_end")[-1])
    assert end.message.role == "assistant"
    assert end.message.stop_reason == "stop"
    agent_end = ParsedAgentEnd.model_validate(_by_type(events, "agent_end")[0])
    assert agent_end.will_retry is False
    assert len(agent_end.messages) == 1
    assert agent_end.messages[0].role == "assistant"
    assert agent_end.messages[0].content[0]["text"] == "hello"


def test_fake_pi_rpc_stream_text_emits_multiple_text_deltas() -> None:
    prompt = 'fake_pi:stream_text `{"text": "abcdef", "chunk_size": 2}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(prompt),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    deltas = [e for e in events if e.get("type") == "message_update"]
    assert [e["assistantMessageEvent"]["delta"] for e in deltas] == ["ab", "cd", "ef"]
    # The final agent_end's message contains the joined text.
    agent_end = _by_type(events, "agent_end")[0]
    assert agent_end["messages"][0]["content"][0]["text"] == "abcdef"


def test_fake_pi_rpc_tool_call_directive_emits_toolcall_block_and_execution_lane() -> None:
    prompt = (
        'fake_pi:emit_text `{"text": "Reading. "}` '
        + 'fake_pi:tool_call `{"tool": "read", "args": {"path": "/a.txt"}, '
        + '"result": "contents", "updates": ["partial"]}` '
        + 'fake_pi:emit_text `{"text": "Done."}`'
    )
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(prompt),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)

    # The issuing assistant message ends with text + a toolCall content block,
    # stopReason "toolUse", BEFORE the tool-execution lane fires.
    assistant_ends = [e for e in _by_type(events, "message_end") if e["message"]["role"] == "assistant"]
    tool_msg = next(e for e in assistant_ends if any(b.get("type") == "toolCall" for b in e["message"]["content"]))
    assert tool_msg["message"]["stopReason"] == "toolUse"
    tool_block = next(b for b in tool_msg["message"]["content"] if b.get("type") == "toolCall")
    assert tool_block["id"] == "call_read"
    assert tool_block["name"] == "read"
    assert tool_block["arguments"] == {"path": "/a.txt"}

    # The tool-execution lane: start → update → end, correlated by id.
    start = _by_type(events, "tool_execution_start")[0]
    assert start["toolCallId"] == "call_read"
    assert start["toolName"] == "read"
    update = _by_type(events, "tool_execution_update")[0]
    assert update["partialResult"]["content"][0]["text"] == "partial"
    end = _by_type(events, "tool_execution_end")[0]
    assert end["toolCallId"] == "call_read"
    assert end["isError"] is False
    assert end["result"]["content"][0]["text"] == "contents"

    # Ordering: the toolCall message_end precedes tool_execution_start (mirrors pi).
    types = [e["type"] for e in events]
    tool_msg_idx = next(
        i
        for i, e in enumerate(events)
        if e["type"] == "message_end"
        and e["message"]["role"] == "assistant"
        and any(b.get("type") == "toolCall" for b in e["message"]["content"])
    )
    assert tool_msg_idx < types.index("tool_execution_start")


def test_fake_pi_rpc_tool_call_error_result_sets_is_error() -> None:
    prompt = 'fake_pi:tool_call `{"tool": "read", "args": {"path": "/missing"}, "result": "ENOENT", "is_error": true}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(prompt),
    )
    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    end = _by_type(events, "tool_execution_end")[0]
    assert end["isError"] is True
    assert end["result"]["content"][0]["text"] == "ENOENT"


def test_fake_pi_rpc_error_directive_emits_failure_response_and_no_session_events() -> None:
    prompt = 'fake_pi:error `{"message": "boom"}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(prompt),
    )

    # Preflight failures keep the process alive (matches real pi); exit
    # comes from stdin EOF.
    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    assert len(events) == 1
    response = RpcResponse.model_validate(events[0])
    assert response.command == "prompt"
    assert response.success is False
    assert response.error == "boom"
    assert response.id == "p1"
    # No session events when preflight fails.
    assert _by_type(events, "agent_start") == []
    assert _by_type(events, "agent_end") == []


def test_fake_pi_rpc_default_response_when_no_directives_present() -> None:
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt("hello, no directives here"),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    RpcResponse.model_validate(events[0])
    update = _first_update(events)
    assert "FakePi" in update.assistant_message_event.get("delta", "")
    ParsedMessageEnd.model_validate(_by_type(events, "message_end")[-1])
    ParsedAgentEnd.model_validate(_by_type(events, "agent_end")[0])


def test_fake_pi_parses_repeatable_skill_flags() -> None:
    # PiAgent hands pi the workspace's skill dirs as repeatable --skill flags;
    # FakePi parses them first-class so tests can assert what was passed.
    parsed = _parse_args(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", "", "--skill", "/a/skills", "--skill", "/b/skills"]
    )
    assert parsed.skill == ["/a/skills", "/b/skills"]


def test_fake_pi_accepts_skill_flags_and_runs_a_turn() -> None:
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", "", "--skill", "/some/skills"],
        stdin_input=_send_prompt("hello"),
    )
    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    RpcResponse.model_validate(events[0])
    ParsedAgentEnd.model_validate(_by_type(events, "agent_end")[0])


def test_fake_pi_echoes_followed_skill_for_skill_invocation() -> None:
    # A prompt already rewritten to pi's /skill:<name> shape (with no fake_pi:
    # directive) makes FakePi echo that it "followed" the skill, so an
    # integration test can assert PiAgent rewrote a picked /name into /skill:.
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt("/skill:fix-bug the login flow"),
    )
    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    update = _first_update(events)
    assert "followed skill: fix-bug" in update.assistant_message_event.get("delta", "")


def test_fake_pi_rpc_directives_in_system_prompt_drive_turn() -> None:
    system_prompt = 'fake_pi:emit_text `{"text": "from-system"}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", system_prompt],
        stdin_input=_send_prompt("(no per-turn directives)"),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    update = _first_update(events)
    assert update.assistant_message_event.get("delta") == "from-system"


def test_fake_pi_rpc_per_turn_directives_take_precedence_over_system_prompt() -> None:
    system_prompt = 'fake_pi:emit_text `{"text": "from-system"}`'
    turn = 'fake_pi:emit_text `{"text": "from-turn"}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", system_prompt],
        stdin_input=_send_prompt(turn),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    update = _first_update(events)
    assert update.assistant_message_event.get("delta") == "from-turn"


def test_fake_pi_report_inputs_echoes_image_count_and_mimetypes() -> None:
    """report_inputs surfaces the received images[] so image delivery is assertable."""
    images = [
        {"type": "image", "data": "AAAA", "mimeType": "image/png"},
        {"type": "image", "data": "BBBB", "mimeType": "image/gif"},
    ]
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt_with_images("fake_pi:report_inputs", images),
    )

    assert result.returncode == 0
    text = _last_assistant_text(_parse_jsonl(result.stdout))
    assert "images=2" in text
    assert "image/png" in text
    assert "image/gif" in text


def test_fake_pi_report_inputs_echoes_prompt_text_for_path_attachments() -> None:
    """Non-image attachments ride the prompt text; report_inputs echoes it back."""
    message = """<system-instructions>
The user has attached these files. Read them before proceeding.
/env/attachments/notes.txt
</system-instructions>

read it fake_pi:report_inputs"""
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(message),
    )

    assert result.returncode == 0
    text = _last_assistant_text(_parse_jsonl(result.stdout))
    # No images this turn, but the attached path is delivered in the prompt text.
    assert "images=0" in text
    assert "/env/attachments/notes.txt" in text


def test_fake_pi_accepts_images_field_on_happy_path_without_report_directive() -> None:
    """A prompt carrying images[] but no report directive still runs the happy path."""
    images = [{"type": "image", "data": "AAAA", "mimeType": "image/png"}]
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt_with_images('fake_pi:emit_text `{"text": "ok"}`', images),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    assert _first_update(events).assistant_message_event.get("delta") == "ok"
    assert len(_by_type(events, "agent_end")) == 1


def test_fake_pi_rpc_abort_with_no_turn_acks_and_exits_on_eof() -> None:
    """An abort with no turn in flight is acked; the process then exits on stdin
    EOF (it does NOT terminate on the abort itself — real pi stays alive)."""
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=json.dumps({"type": "abort", "id": "a1"}) + "\n",
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    assert len(events) == 1
    response = RpcResponse.model_validate(events[0])
    assert response.command == "abort"
    assert response.success is True
    assert response.id == "a1"


def _read_until(stream: object, predicate: Callable[[dict], bool], timeout: float = 10.0) -> dict:
    """Read JSONL lines from a live fake_pi stdout until ``predicate`` matches.

    Blocking ``readline`` keeps this deterministic: each event is consumed in
    order, with no fixed sleeps.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = stream.readline()  # type: ignore[attr-defined]
        if not line:
            raise AssertionError("fake_pi closed stdout before the predicate matched")
        stripped = line.strip()
        if not stripped:
            continue
        event = json.loads(stripped)
        if predicate(event):
            return event
    raise AssertionError("timed out waiting for predicate")


def test_fake_pi_rpc_abort_preempts_blocked_turn_and_process_stays_alive(tmp_path: Path) -> None:
    """An abort sent while a turn is blocked in a directive preempts it (emitting
    the `stopReason:"aborted"` boundary) and the process serves the next prompt.

    Driven over a live stdin pipe so the abort lands AFTER the turn is in flight
    (deterministic — no racing the reader against the turn-start abort reset).
    """
    never = tmp_path / "never-created"
    blocking = f'fake_pi:wait_for_file `{{"path": "{never}"}}`'
    follow_up = 'fake_pi:emit_text `{"text": "after-abort"}`'

    proc = subprocess.Popen(
        [sys.executable, "-m", _FAKE_PI_MODULE, "--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None and proc.stdout is not None
    try:
        # Start the turn that blocks on a sentinel file that never appears.
        proc.stdin.write(_send_prompt(blocking, prompt_id="p1"))
        proc.stdin.flush()
        _read_until(proc.stdout, lambda e: e.get("type") == "agent_start")
        # Interrupt: the blocked wait_for_file must bail with the aborted boundary.
        proc.stdin.write(json.dumps({"type": "abort", "id": "a1"}) + "\n")
        proc.stdin.flush()
        aborted_end = _read_until(proc.stdout, lambda e: e.get("type") == "agent_end")
        assert aborted_end["messages"][0]["stopReason"] == "aborted"
        # The same process serves a follow-up prompt — it did NOT exit on abort.
        proc.stdin.write(_send_prompt(follow_up, prompt_id="p2"))
        proc.stdin.flush()
        done_end = _read_until(proc.stdout, lambda e: e.get("type") == "agent_end")
        assert done_end["messages"][0]["content"][0]["text"] == "after-abort"
    finally:
        proc.stdin.close()
        proc.wait(timeout=10.0)
    assert proc.returncode == 0


def test_fake_pi_rpc_unknown_directive_emits_failure_response_and_exits_nonzero() -> None:
    prompt = "fake_pi:nonexistent"
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(prompt),
    )

    assert result.returncode != 0
    events = _parse_jsonl(result.stdout)
    response = RpcResponse.model_validate(events[-1])
    assert response.success is False
    assert "nonexistent" in (response.error or "")


def test_fake_pi_rpc_handles_multiple_turns_in_sequence() -> None:
    first = 'fake_pi:emit_text `{"text": "one"}`'
    second = 'fake_pi:emit_text `{"text": "two"}`'
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(first, prompt_id="p1") + _send_prompt(second, prompt_id="p2"),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    responses = _by_type(events, "response")
    assert [r["id"] for r in responses] == ["p1", "p2"]
    deltas = [e["assistantMessageEvent"]["delta"] for e in events if e.get("type") == "message_update"]
    assert deltas == ["one", "two"]
    agent_ends = _by_type(events, "agent_end")
    assert len(agent_ends) == 2


def test_fake_pi_recall_resumes_prior_user_message_across_relaunch(tmp_path: Path) -> None:
    """A relaunched FakePi (same --session-dir/--session-id) recalls a planted message.

    This is the unit-level mirror of the session-resume integration flow: the
    first process persists the planted message; a SECOND process given the same
    dir + id reloads it, so `fake_pi:recall` reproduces the sentinel.
    """
    session_dir = tmp_path / "pi_session"
    session_flags = ["--mode", "rpc", "--session-dir", str(session_dir), "--session-id", "sid-1"]
    plant = _run_fake_pi(
        session_flags + ["--append-system-prompt", ""], stdin_input=_send_prompt("Remember SENTINEL-9")
    )
    assert plant.returncode == 0
    # Fresh process — same dir + id — resumes and recalls.
    recall = _run_fake_pi(session_flags + ["--append-system-prompt", ""], stdin_input=_send_prompt("fake_pi:recall"))
    assert recall.returncode == 0
    text = _last_assistant_text(_parse_jsonl(recall.stdout))
    assert "SENTINEL-9" in text


def test_fake_pi_recall_without_prior_session_reports_no_context(tmp_path: Path) -> None:
    """A fresh session id has nothing to recall — the absence sentinel, not a crash."""
    session_dir = tmp_path / "pi_session"
    result = _run_fake_pi(
        [
            "--mode",
            "rpc",
            "--session-dir",
            str(session_dir),
            "--session-id",
            "brand-new",
            "--append-system-prompt",
            "",
        ],
        stdin_input=_send_prompt("fake_pi:recall"),
    )
    assert result.returncode == 0
    assert "NO_PRIOR_CONTEXT" in _last_assistant_text(_parse_jsonl(result.stdout))


def test_fake_pi_get_state_reports_session_id_and_message_count(tmp_path: Path) -> None:
    """get_state echoes the pinned session id and a message count that grows with turns.

    PiAgent's resume verification reads exactly these fields.
    """
    session_dir = tmp_path / "pi_session"
    session_flags = ["--mode", "rpc", "--session-dir", str(session_dir), "--session-id", "sid-state"]
    # One turn, then get_state in the SAME process: messageCount reflects the turn.
    same_proc = _run_fake_pi(
        session_flags + ["--append-system-prompt", ""],
        stdin_input=_send_prompt("hello") + json.dumps({"type": "get_state", "id": "gs"}) + "\n",
    )
    assert same_proc.returncode == 0
    state = next(e for e in _parse_jsonl(same_proc.stdout) if e.get("command") == "get_state")
    assert state["success"] is True
    assert state["id"] == "gs"
    assert state["data"]["sessionId"] == "sid-state"
    assert state["data"]["messageCount"] == 2
    # A relaunch loads the persisted count BEFORE any new turn (what PiAgent checks on resume).
    resumed = _run_fake_pi(
        session_flags + ["--append-system-prompt", ""],
        stdin_input=json.dumps({"type": "get_state", "id": "gs2"}) + "\n",
    )
    resumed_state = next(e for e in _parse_jsonl(resumed.stdout) if e.get("command") == "get_state")
    assert resumed_state["data"]["sessionId"] == "sid-state"
    assert resumed_state["data"]["messageCount"] == 2


def test_fake_pi_rpc_rejects_non_rpc_mode_with_exit_2() -> None:
    result = _run_fake_pi(["--mode", "something-else"])

    assert result.returncode == 2


def test_install_fake_pi_binary_writes_executable_returning_pinned_version(tmp_path: Path) -> None:
    binary = install_fake_pi_binary(tmp_path)

    assert binary == tmp_path / "pi"
    assert binary.is_file()
    assert binary.stat().st_mode & 0o111

    result = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    assert result.returncode == 0
    # Real pi emits its version to stderr; FakePi mirrors that.
    assert f"pi {PI_VERSION_RANGE.recommended_version}" in result.stderr


def test_install_fake_pi_binary_executes_rpc_mode_through_wrapper(tmp_path: Path) -> None:
    binary = install_fake_pi_binary(tmp_path)
    prompt = 'fake_pi:emit_text `{"text": "wrapped"}`'

    result = subprocess.run(
        [str(binary), "--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        input=_send_prompt(prompt),
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    update = _first_update(events)
    assert update.assistant_message_event.get("delta") == "wrapped"


@pytest.mark.parametrize(
    "directive,expected_first_delta",
    [
        ('fake_pi:emit_text `{"text": "alpha"}`', "alpha"),
        ('fake_pi:stream_text `{"text": "beta", "chunk_size": 4}`', "beta"),
    ],
)
def test_fake_pi_command_grammar_matches_fake_claude_shape(directive: str, expected_first_delta: str) -> None:
    """Directive shape mirrors FakeClaude: ``fake_pi:<name> `<json>``.

    Documents the cross-fake parity so future maintainers don't drift the
    grammars apart accidentally.
    """
    result = _run_fake_pi(
        ["--mode", "rpc", "--no-session", "--append-system-prompt", ""],
        stdin_input=_send_prompt(directive),
    )

    assert result.returncode == 0
    events = _parse_jsonl(result.stdout)
    update = _first_update(events)
    assert update.assistant_message_event.get("delta") == expected_first_delta
