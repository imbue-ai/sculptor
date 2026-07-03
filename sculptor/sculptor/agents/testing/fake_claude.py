"""FakeClaude CLI entry point — replaces claude -p during integration tests.

Reads a prompt from stdin, dispatches to command handlers, emits JSONL to
stdout, writes session file, and exits.
"""

import argparse
import html
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from uuid import uuid4

from sculptor.agents.default.claude_code_sdk.harness import compute_claude_jsonl_directory
from sculptor.agents.testing.fake_claude_commands import COMMAND_REGISTRY
from sculptor.agents.testing.fake_claude_commands import UnknownFakeClaudeCommandError
from sculptor.agents.testing.fake_claude_commands import dispatch_handler
from sculptor.agents.testing.fake_claude_commands import handle_default
from sculptor.agents.testing.fake_claude_jsonl import generate_id
from sculptor.agents.testing.fake_claude_jsonl import make_end_message
from sculptor.agents.testing.fake_claude_jsonl import make_init_message
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM

_FAKE_CLAUDE_PREFIX = "fake_claude:"

# Seconds to stall a resumed /compact so integration tests can observe the
# transient Compacting indicator before FakeClaude exits.
_COMPACT_INDICATOR_DELAY_SECONDS = 3


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments, accepting all flags that get_claude_command() passes."""
    parser = argparse.ArgumentParser(description="FakeClaude — test replacement for claude -p")
    # `-p` may appear as a bare flag (headless mode, prompt from stdin) or
    # as `-p <question>` (the forked /btw invocation passes the question
    # as an argument). Use nargs="?" so both forms parse.
    parser.add_argument("-p", nargs="?", const=True, default=False, dest="p_flag")
    parser.add_argument("--output-format", default="stream-json")
    parser.add_argument("--input-format", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dangerously-skip-permissions", action="store_true")
    parser.add_argument("--include-partial-messages", action="store_true")
    parser.add_argument("--include-hook-events", action="store_true")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--append-system-prompt", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--plugin-dir", action="append", default=[])
    # Flags specific to the /btw forked-session invocation; accepted + ignored.
    parser.add_argument("--fork-session", action="store_true")
    parser.add_argument("--no-session-persistence", action="store_true")
    parser.add_argument("--tools", default=None)
    parser.add_argument("--strict-mcp-config", action="store_true")
    parser.add_argument("--disable-slash-commands", action="store_true")
    parsed, _extra = parser.parse_known_args(argv)
    return parsed


def _parse_prompt(prompt: str) -> tuple[str | None, dict]:
    """Parse a prompt string to extract the command name and JSON args.

    Returns (command_name, args) where command_name is None for default commands.
    """
    prefix_idx = prompt.find(_FAKE_CLAUDE_PREFIX)
    if prefix_idx == -1:
        return None, {}

    rest = prompt[prefix_idx + len(_FAKE_CLAUDE_PREFIX) :]

    backtick_start = rest.find("`")
    if backtick_start == -1:
        command_name = rest.strip().split()[0] if rest.strip() else ""
        return command_name, {}

    command_name = rest[:backtick_start].strip().split()[0] if rest[:backtick_start].strip() else ""

    backtick_end = rest.rfind("`")
    if backtick_end <= backtick_start:
        return command_name, {}

    json_str = rest[backtick_start + 1 : backtick_end]
    args = json.loads(json_str)
    return command_name, args


def _extract_fake_claude_commands(text: str) -> list[str]:
    """Extract all fake_claude: commands from a text string (e.g. system prompt).

    Returns a list of command strings like 'fake_claude:text `{"text": "hello"}`'.
    """
    return re.findall(r"fake_claude:\S+(?:\s+`[^`]*`)?", text)


def _get_session_id(resume_id: str | None) -> str:
    """Return the session_id — reuse --resume value or generate a new one.

    Uses a uuid4 (not the global generate_id counter) so each FakeClaude
    invocation gets a unique session_id. The per-task JSON store at
    ``$HOME/.claude/tasks/{session_id}/`` is shared across tests on the same
    host; a unique id prevents files from leaking between tests.

    Also bumps the global generate_id counter by one. Fresh and --resume
    invocations of FakeClaude run as separate processes with a fresh,
    process-local counter starting at 1; without this bump, the very first
    msg / toolu / mcp_req id minted in a fresh invocation (``..._001``)
    collides with the corresponding id in the next --resume invocation, and
    the frontend dedupes the second tool_use out of existence. Bumping here
    keeps msg / toolu / etc. ids starting at ``..._002`` for fresh runs and
    ``..._001`` for --resume runs.
    """
    if resume_id:
        return resume_id
    generate_id("session")
    return f"session_fakeclaude_{uuid4().hex}"


def _get_session_file_path(session_id: str) -> Path:
    """Compute the session file path matching the Claude harness's layout.

    Uses the resolved CWD, which matches `ClaudeCodeHarness.get_jsonl_path`
    since the process is launched with get_working_directory() as its CWD.
    """
    resolved_cwd = Path(os.path.realpath(os.getcwd()))
    return compute_claude_jsonl_directory(Path.home(), resolved_cwd) / f"{session_id}.jsonl"


def _write_session_file(session_id: str) -> None:
    """Write the session history file so is_session_id_valid() passes."""
    session_path = _get_session_file_path(session_id)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_data = {"sessionId": session_id, "type": "user", "message": {"role": "user", "content": "test"}}
    session_path.write_text(json.dumps(session_data) + "\n")


def _emit_jsonl(messages: list[dict]) -> None:
    """Write JSONL messages to stdout."""
    for msg in messages:
        sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _dispatch_single_prompt(
    prompt: str,
    cwd: str,
    emit_streaming: bool,
    plugin_dir: str | None = None,
) -> tuple[list[dict], str]:
    """Parse and dispatch a single prompt string.

    Returns (messages, end_result) where end_result is non-empty only for the
    'warning' command (which needs to set the result text on the end message).
    """
    command_name, args = _parse_prompt(prompt)

    if command_name is None:
        return handle_default(emit_streaming=emit_streaming), ""

    if command_name == "warning":
        # Warning command: no assistant messages, just set result text on end message
        return [], args.get("message", "")

    handler = COMMAND_REGISTRY.get(command_name)
    if handler is None:
        raise UnknownFakeClaudeCommandError(f"unknown command '{command_name}'")

    return dispatch_handler(handler, args, cwd, emit_streaming, plugin_dir=plugin_dir), ""


def _install_sigterm_handler() -> None:
    """Exit with code 143 on SIGTERM, matching real claude behavior.

    Without this, Python is killed by signal 15 and reports exit code -15 to the
    parent process. The agent wrapper expects exit code 143
    (AGENT_EXIT_CODE_FROM_SIGTERM) to recognize a SIGTERM shutdown and emit a
    RequestStoppedAgentMessage instead of a RequestFailureAgentMessage.
    """
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(AGENT_EXIT_CODE_FROM_SIGTERM))


def _read_prompt_from_stream_json_stdin() -> str | None:
    """Read the next user message from stdin in stream-json format.

    Reads lines until a JSON object with ``"type": "user"`` is found, then
    returns its (HTML-unescaped, stripped) message content. An empty-content
    user frame returns ``""`` so the default handler still runs for a
    genuinely empty prompt.

    Returns ``None`` when stdin closes before another user frame arrives. The
    caller treats that as EOF and exits cleanly with nothing further emitted,
    matching the real CLI, which lingers on stdin between turns and exits only
    on EOF. (Returning ``""`` here instead would spuriously run the default
    handler for a turn the user never sent.)

    An ``interrupt`` control_request seen while idle between cycles exits with
    ``AGENT_EXIT_CODE_FROM_SIGTERM``, mirroring the graceful-interrupt exit the
    in-cycle handlers perform. Other non-user frames (context-usage requests,
    control responses, etc.) are ignored.

    ``sys.stdin`` is its own iterator, so successive calls resume where the
    previous one stopped and share one read buffer — reading a sequence of
    frames across cycles neither drops nor reorders lines.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if (
            data.get("type") == "control_request"
            and isinstance(data.get("request"), dict)
            and data["request"].get("subtype") == "interrupt"
        ):
            sys.exit(AGENT_EXIT_CODE_FROM_SIGTERM)
        if data.get("type") == "user":
            message = data.get("message", {})
            content = message.get("content", "")
            return html.unescape(content).strip() if isinstance(content, str) else ""
    return None


def _maybe_delay_for_compact_indicator(prompt: str, resume_id: str | None) -> None:
    """Stall a resumed ``/compact`` so tests can observe the Compacting indicator.

    Only the resumed-compact turn stalls; a fresh session never runs /compact.
    """
    if prompt == "/compact" and resume_id:
        time.sleep(_COMPACT_INDICATOR_DELAY_SECONDS)


def _run_cycle(
    prompt: str,
    session_id: str,
    cwd: str,
    emit_streaming: bool,
    plugin_dir: str | None,
    system_commands: list[str],
) -> int | None:
    """Run one full ``init → messages → result`` cycle for a single user frame.

    Emits the cycle's own ``init`` first — an init per cycle mirrors the real
    CLI and is the shape Sculptor's output processor expects for every turn —
    then dispatches the frame's ``fake_claude:`` directives, then the
    terminating ``result``. Emitting ``init`` up front also means the output
    processor has the session id before any handler blocks (e.g.
    ask_user_question waiting on an MCP response).

    ``system_commands`` (directives extracted from ``--append-system-prompt``)
    run before the frame's own directives. The caller passes them only for the
    first cycle, since an appended system prompt is a launch-time input, not a
    per-turn one.

    Returns an exit code if the cycle terminates the whole process (an unknown
    command → 1), or ``None`` to signal the caller may run further cycles.
    """
    _emit_jsonl([make_init_message(session_id)])

    all_messages: list[dict] = []
    end_result = ""

    # System-prompt directives run first, before the frame's own directives.
    for system_command in system_commands:
        try:
            messages, result = _dispatch_single_prompt(system_command, cwd, emit_streaming, plugin_dir=plugin_dir)
            all_messages.extend(messages)
            if result:
                end_result = result
        except UnknownFakeClaudeCommandError as e:
            sys.stderr.write(f"FakeClaude (system prompt): {e}\n")
            all_messages.append(make_end_message(session_id, is_error=True))
            _emit_jsonl(all_messages)
            return 1

    try:
        messages, result = _dispatch_single_prompt(prompt, cwd, emit_streaming, plugin_dir=plugin_dir)
        all_messages.extend(messages)
        if result:
            end_result = result
    except UnknownFakeClaudeCommandError as e:
        sys.stderr.write(f"FakeClaude: {e}\n")
        all_messages.append(make_end_message(session_id, is_error=True))
        _emit_jsonl(all_messages)
        return 1

    all_messages.append(make_end_message(session_id, result=end_result))
    _emit_jsonl(all_messages)
    return None


def main(argv: list[str] | None = None) -> int:
    """Run FakeClaude: read prompt(s), dispatch directives, emit JSONL, write session file.

    In ``--input-format stream-json`` mode (the standard main-agent path) one
    invocation hosts many turns: it runs a full scripted cycle per user frame
    read from stdin and exits 0 when stdin closes. The other input modes — a
    ``-p <question>`` argument (e.g. /btw's forked invocation) or a plain piped
    prompt — run a single cycle. This mirrors the real CLI, which lingers on
    stdin between turns and exits only on EOF; single-frame usage is the
    degenerate case where exactly one cycle runs before EOF.
    """
    _install_sigterm_handler()
    parsed = _parse_args(argv)

    emit_streaming = parsed.include_partial_messages
    cwd = os.getcwd()
    # FakeClaude handlers only inspect a single plugin_dir for testing. The real
    # Claude CLI accepts multiple --plugin-dir flags (Sculptor passes one for the
    # sculptor plugin and one for the sculptor-workflow plugin); we collapse to
    # the first here since no handler actually reads multiple.
    plugin_dir = parsed.plugin_dir[0] if parsed.plugin_dir else None
    session_id = _get_session_id(parsed.resume)

    # `--no-session-persistence` (used by /btw's forked invocation) means we
    # must leave the resumed session file untouched and not write a new one.
    if not parsed.no_session_persistence:
        _write_session_file(session_id)

    # fake_claude: directives embedded in the appended system prompt are a
    # launch-time input, so they run once — on the first cycle only.
    system_commands = _extract_fake_claude_commands(parsed.append_system_prompt) if parsed.append_system_prompt else []

    # `-p <question>` carries the prompt on argv (e.g. the /btw forked
    # invocation) — a single cycle, no stdin loop.
    if isinstance(parsed.p_flag, str):
        _maybe_delay_for_compact_indicator(parsed.p_flag, parsed.resume)
        exit_code = _run_cycle(parsed.p_flag, session_id, cwd, emit_streaming, plugin_dir, system_commands)
        return exit_code if exit_code is not None else 0

    # Stream-json stdin (the standard main-agent path): one scripted cycle per
    # user frame, exiting 0 when stdin closes.
    if parsed.input_format == "stream-json":
        is_first_cycle = True
        while True:
            prompt = _read_prompt_from_stream_json_stdin()
            if prompt is None:
                # stdin closed while idle between cycles — exit silently.
                return 0
            _maybe_delay_for_compact_indicator(prompt, parsed.resume)
            cycle_system_commands = system_commands if is_first_cycle else []
            exit_code = _run_cycle(prompt, session_id, cwd, emit_streaming, plugin_dir, cycle_system_commands)
            if exit_code is not None:
                return exit_code
            is_first_cycle = False

    # Non-stream-json single-shot: a plain piped prompt, or nothing on a tty.
    prompt = html.unescape(sys.stdin.read()).strip() if not sys.stdin.isatty() else ""
    _maybe_delay_for_compact_indicator(prompt, parsed.resume)
    exit_code = _run_cycle(prompt, session_id, cwd, emit_streaming, plugin_dir, system_commands)
    return exit_code if exit_code is not None else 0


if __name__ == "__main__":
    sys.exit(main())
