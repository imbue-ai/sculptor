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
from sculptor.agents.testing.fake_claude_commands import _dispatch_handler
from sculptor.agents.testing.fake_claude_commands import handle_default
from sculptor.agents.testing.fake_claude_jsonl import generate_id
from sculptor.agents.testing.fake_claude_jsonl import make_end_message
from sculptor.agents.testing.fake_claude_jsonl import make_init_message
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM

_FAKE_CLAUDE_PREFIX = "fake_claude:"


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
    parsed, extra = parser.parse_known_args(argv)
    parsed.prompt = None
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

    return _dispatch_handler(handler, args, cwd, emit_streaming, plugin_dir=plugin_dir), ""


def _install_sigterm_handler() -> None:
    """Exit with code 143 on SIGTERM, matching real claude behavior.

    Without this, Python is killed by signal 15 and reports exit code -15 to the
    parent process. The agent wrapper expects exit code 143
    (AGENT_EXIT_CODE_FROM_SIGTERM) to recognize a SIGTERM shutdown and emit a
    RequestStoppedAgentMessage instead of a RequestFailureAgentMessage.
    """
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(AGENT_EXIT_CODE_FROM_SIGTERM))


def _read_prompt_from_stream_json_stdin() -> str:
    """Read a user message from stdin in stream-json format.

    Reads lines from stdin until a JSON object with "type": "user" is found,
    then extracts and returns the message content. Ignores control_request
    messages (e.g. interrupts) and other non-user message types.
    Returns empty string if stdin is closed without a user message.
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
        if data.get("type") == "user":
            message = data.get("message", {})
            content = message.get("content", "")
            return html.unescape(content).strip() if isinstance(content, str) else ""
    return ""


def main(argv: list[str] | None = None) -> int:
    """Run FakeClaude: read prompt, dispatch command, emit JSONL, write session file."""
    _install_sigterm_handler()
    parsed = _parse_args(argv)

    # `-p <question>` carries the prompt on argv (e.g. the /btw forked
    # invocation). Otherwise read from stdin using the stream-json protocol
    # (the standard main-agent path).
    if isinstance(parsed.p_flag, str):
        prompt = parsed.p_flag
    elif parsed.input_format == "stream-json":
        prompt = _read_prompt_from_stream_json_stdin()
    elif not sys.stdin.isatty():
        prompt = html.unescape(sys.stdin.read()).strip()
    else:
        prompt = ""

    # Add a delay during compact operations so that integration tests can
    # observe transient UI states like the Compacting indicator.
    if prompt == "/compact" and parsed.resume:
        time.sleep(3)

    emit_streaming = parsed.include_partial_messages
    session_id = _get_session_id(parsed.resume)
    cwd = os.getcwd()

    # Emit the init message immediately so the output processor gets the
    # session ID before any handler might block (e.g. ask_user_question
    # waiting for the kill signal).
    _emit_jsonl([make_init_message(session_id)])
    # `--no-session-persistence` (used by /btw's forked invocation) means we
    # must leave the resumed session file untouched and not write a new one.
    if not parsed.no_session_persistence:
        _write_session_file(session_id)

    all_messages: list[dict] = []
    end_result = ""

    # FakeClaude handlers only inspect a single plugin_dir for testing. The real
    # Claude CLI accepts multiple --plugin-dir flags (Sculptor passes one for the
    # sculptor plugin and one for the sculptor-workflow plugin); we collapse to
    # the first here since no handler actually reads multiple.
    plugin_dir = parsed.plugin_dir[0] if parsed.plugin_dir else None

    # Execute any fake_claude: commands found in the system prompt first
    if parsed.append_system_prompt:
        system_commands = _extract_fake_claude_commands(parsed.append_system_prompt)
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

    # Execute the stdin prompt
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
