"""Subprocess manager for `/btw` side-chat turns.

Spawns a single-shot `claude --fork-session ... -p <question>` run on
Haiku with all tools and MCP servers disabled. Streams the accumulated
answer back to any registered observer queues as ``BtwUpdate`` events
without touching main's persistent session state.
"""

import json
import shlex
import sys
import time
from pathlib import Path
from queue import Empty
from typing import Callable
from typing import Literal

from loguru import logger

from imbue_core.processes.local_process import RunningProcess
from imbue_core.sculptor.state.messages import LLMModel
from sculptor.agents.default.claude_code_sdk.harness import ClaudeCodeHarness
from sculptor.agents.default.constants import MODEL_SHORTNAME_MAP
from sculptor.agents.default.utils import get_state_file_contents
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.errors import ClaudeBinaryNotFoundError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.data_types import BtwUpdate

BtwState = Literal["running", "done", "error", "aborted"]

_PUBLISH_THROTTLE_SECONDS = 0.1
_READ_TIMEOUT_SECONDS = 0.1
# Cold-start cushion: `/btw` can race the main agent's first `system/init`
# handshake (which is what writes the session-id state file). The interrupt
# path handles the same race with an in-process Event; we only have the
# on-disk file because BtwService runs in a separate request thread.
DEFAULT_SESSION_ID_WAIT_SECONDS = 10.0
_SESSION_ID_POLL_INTERVAL_SECONDS = 0.05
_BTW_SYSTEM_PROMPT = (
    "You are a read-only assistant. You cannot run any tools. Answer the user's question about the conversation above."
)


class NoBtwSessionAvailable(Exception):
    """Raised when the agent has no resumable session to fork from."""


def get_btw_claude_command(
    claude_binary_path: str,
    main_session_id: str,
    question: str,
    is_fake_claude: bool = False,
) -> list[str]:
    """Build the forked-claude shell command for a single /btw turn.

    All flags are load-bearing — see architecture.md §4.4.2. The command
    uses an ``exec`` envelope so SIGTERM is delivered directly to claude
    rather than to bash. Set ``is_fake_claude=True`` to swap the real
    binary for the in-process ``fake_claude.py`` script used by tests.
    """
    if is_fake_claude:
        script_path = Path(__file__).parent.parent.parent / "testing" / "fake_claude.py"
        executable = f"{shlex.quote(sys.executable)} {shlex.quote(str(script_path))}"
    else:
        executable = f"env IS_SANDBOX=1 {shlex.quote(claude_binary_path)}"
    model_shortname = MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_4_HAIKU]
    flags = [
        f"exec {executable}",
        f"--resume {shlex.quote(main_session_id)}",
        "--fork-session",
        "--no-session-persistence",
        f"-p {shlex.quote(question)}",
        f"--model {shlex.quote(model_shortname)}",
        f"--tools {shlex.quote('')}",
        "--strict-mcp-config",
        "--disable-slash-commands",
        f"--append-system-prompt {shlex.quote(_BTW_SYSTEM_PROMPT)}",
        "--output-format=stream-json",
        "--include-partial-messages",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    return ["bash", "-c", " ".join(flags)]


class BtwProcessManager:
    """Spawns and streams output for /btw side-chat subprocesses.

    Each ``run_btw`` call is blocking and intended to be scheduled on a
    dedicated thread by the caller. Every emitted ``BtwUpdate`` is
    handed to the injected ``publish`` callable, which typically fans
    the event out to the process-wide observer-queue registry owned by
    ``BtwService``.

    ``abort()`` terminates the running subprocess and causes the in-flight
    ``run_btw`` call to publish a terminal ``state="aborted"`` update. It
    is safe to call from a thread other than the one running ``run_btw``.
    """

    def __init__(
        self,
        environment: AgentExecutionEnvironment,
        task_id: TaskID,
        workspace_id: WorkspaceID,
        publish: Callable[[BtwUpdate], None],
        harness: ClaudeCodeHarness,
        is_fake_claude: bool = False,
    ) -> None:
        self._environment = environment
        self._task_id = task_id
        self._workspace_id = workspace_id
        self._publish = publish
        self._harness: ClaudeCodeHarness = harness
        self._is_fake_claude = is_fake_claude
        self._process: RunningProcess | None = None
        self._aborted: bool = False

    def abort(self) -> None:
        """SIGTERM the running subprocess so ``run_btw`` exits promptly with state="aborted"."""
        self._aborted = True
        process = self._process
        if process is None:
            return
        try:
            if not process.is_finished():
                process.terminate(force_kill_seconds=5.0)
        except Exception as exc:
            logger.opt(exception=exc).warning("Error while aborting /btw subprocess")

    def run_btw(self, question: str, request_id: str) -> None:
        main_session_id = self.read_session_id()
        if main_session_id is None:
            raise NoBtwSessionAvailable(f"Agent {self._task_id} has no session file to fork from")

        binary_path = self._environment.get_tool_binary_path(self._harness.binary_dependency)
        if binary_path is None and not self._is_fake_claude:
            raise ClaudeBinaryNotFoundError()

        command = get_btw_claude_command(
            claude_binary_path=binary_path or "",
            main_session_id=main_session_id,
            question=question,
            is_fake_claude=self._is_fake_claude,
        )
        logger.info("Executing /btw claude command: {}", " ".join(command))

        answer = ""
        self._publish(self._build_update(request_id=request_id, state="running", answer=answer))

        # SCU-211: isolate the /btw CLI in its own process group so abort
        # cascades to any foreground subprocesses it spawned (e.g. sh behind
        # a Bash tool). Without this, abort sends SIGTERM/SIGKILL only to the
        # CLI's PID and any descendants are orphaned.
        process = self._environment.run_process_in_background(
            command,
            secrets={},
            open_stdin=False,
            isolate_process_group=True,
        )
        self._process = process
        if self._aborted:
            # An abort can land between command construction and subprocess
            # spawn — propagate it now so we don't leak the just-launched pid.
            try:
                if not process.is_finished():
                    process.terminate(force_kill_seconds=5.0)
            except Exception as exc:
                logger.opt(exception=exc).warning("Error while aborting /btw subprocess")
        output_queue = process.get_queue()
        last_publish = time.monotonic()
        error_message: str | None = None
        try:
            while not process.is_finished() or not output_queue.empty():
                try:
                    line, is_stdout = output_queue.get(timeout=_READ_TIMEOUT_SECONDS)
                except Empty:
                    continue
                if not is_stdout:
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                delta_text = _extract_text_delta(stripped)
                if not delta_text:
                    continue
                answer += delta_text
                now = time.monotonic()
                if now - last_publish >= _PUBLISH_THROTTLE_SECONDS:
                    last_publish = now
                    self._publish(self._build_update(request_id=request_id, state="running", answer=answer))
        except Exception as exc:
            logger.opt(exception=exc).warning("Error while reading /btw output")
            error_message = str(exc)

        returncode = process.wait()
        if self._aborted:
            self._publish(self._build_update(request_id=request_id, state="aborted", answer=answer))
            return
        if returncode != 0 and error_message is None:
            stderr_tail = process.read_stderr()[-500:]
            error_message = f"claude exited with code {returncode}: {stderr_tail}".strip()

        if error_message is not None:
            self._publish(
                self._build_update(request_id=request_id, state="error", answer=answer, error_message=error_message)
            )
        else:
            self._publish(self._build_update(request_id=request_id, state="done", answer=answer))

    def read_session_id(self) -> str | None:
        session_id_state_file = self._harness.session_id_state_file_name
        validated_session_id_state_file = self._harness.validated_session_id_state_file_name
        primary = get_state_file_contents(self._environment, session_id_state_file)
        if primary:
            return primary
        fallback = get_state_file_contents(self._environment, validated_session_id_state_file)
        if fallback:
            return fallback
        return None

    def wait_for_session_id(self, timeout: float = DEFAULT_SESSION_ID_WAIT_SECONDS) -> str | None:
        """Poll the on-disk session-id file for up to ``timeout`` seconds.

        Returns the session id once it appears, or ``None`` if the deadline
        passes first. Used by ``BtwService`` to absorb the cold-start race
        between the user firing ``/btw`` and the main agent's first
        ``system/init`` payload landing on disk.
        """
        deadline = time.monotonic() + timeout
        while True:
            session_id = self.read_session_id()
            if session_id is not None:
                return session_id
            if time.monotonic() >= deadline:
                return None
            time.sleep(_SESSION_ID_POLL_INTERVAL_SECONDS)

    def _build_update(
        self,
        request_id: str,
        state: BtwState,
        answer: str,
        error_message: str | None = None,
    ) -> BtwUpdate:
        return BtwUpdate(
            workspace_id=self._workspace_id,
            agent_id=self._task_id,
            request_id=request_id,
            state=state,
            answer=answer,
            error_message=error_message,
        )


def _extract_text_delta(line: str) -> str | None:
    """Extract `text_delta.text` from a stream-json line, if present."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "stream_event":
        return None
    event = data.get("event")
    if not isinstance(event, dict) or event.get("type") != "content_block_delta":
        return None
    delta = event.get("delta")
    if not isinstance(delta, dict) or delta.get("type") != "text_delta":
        return None
    text = delta.get("text")
    if not isinstance(text, str):
        return None
    return text
