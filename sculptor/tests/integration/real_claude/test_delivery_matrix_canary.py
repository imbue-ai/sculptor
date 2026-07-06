"""Real-CLI canary pinning the stream-json message-delivery matrix.

The in-turn-messages work (follow-ups + steering) builds directly on delivery
semantics that live entirely inside the Claude CLI's ``--input-format
stream-json`` protocol, not in Sculptor's wrapper. This canary drives the real
CLI the same way the wrapper does — staggered ``type:"user"`` frames written to
a live stdin — and asserts the four behaviors the feature depends on. A pinned
CLI version bump that changes any of them must fail here, loudly, rather than
surface later as corrupted chat UX.

The four behaviors (each a separate test, empirically verified against the CLI
version named in ``_VERIFIED_CLI_VERSION``):

1. Mid-turn frame -> steering. A frame written while a turn is blocked on a
   slow foreground tool is absorbed into that turn: exactly one ``result`` is
   emitted, and the transcript records the frame as an ``attachment`` of type
   ``queued_command`` (not a plain user message).
2. Between-turns frame -> plain turn. A frame written after a turn's ``result``
   (while a background task still runs) starts a fresh turn with full
   authority: the transcript records an ordinary ``{"role":"user"}`` message
   and zero ``queued_command`` entries.
3. Reaction turn. When the background task completes, the CLI emits
   ``task_updated`` + ``task_notification`` and spontaneously runs a reaction
   turn ending in its own ``result`` — even though an unrelated user turn ran
   in between.
4. EOF exit. An idle CLI with no pending tasks exits promptly on stdin close
   without emitting further messages.

Each scenario asserts on BOTH the stdout stream (result count, event order,
and absence of an input-frame replay) and the session JSONL transcript
(``queued_command`` attachment vs plain user message) — the transcript is the
definitive record of how a frame was delivered. Replay detection targets the
``--replay-user-messages`` shape (a string-content ``user`` event), not a raw
stdout scan: in ``--verbose`` the model routinely quotes an injected
instruction in its own ``assistant`` output, which is not an echo. Timing
preconditions are asserted explicitly so a timing miss (e.g. an injection
landing after the turn's ``result`` and silently testing scenario 2 instead of
scenario 1) fails loudly instead of passing vacuously.

These are deliberately cheap: a haiku-class model and ``sleep``-based tools.
The delivery contract (result count, queued_command vs plain user) is
deterministic; model word-choice is not, so content assertions are kept to
what the CLI guarantees. Whether the model actually calls the tool a scenario
needs (a slow in-flight tool to steer into; a background task to react to) is
also model-dependent, so the setup is retried on a fresh session and only the
delivery assertions past a confirmed setup are hard failures.
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Callable

import pytest

from sculptor.agents.default.claude_code_sdk.harness import compute_claude_jsonl_directory
from tests.integration.real_claude.helpers import real_claude

# The CLI these behaviors were empirically verified against. Surfaced in every
# failure's diagnostics next to the installed version (see _diagnostics) so a
# red canary immediately shows which CLI it actually ran against.
_VERIFIED_CLI_VERSION = "2.1.198"


@functools.cache
def _installed_cli_version() -> str:
    """``claude --version`` (cached), for triage when the canary goes red."""
    if _CLAUDE_BINARY is None:
        return "unknown (claude not on PATH)"
    try:
        completed = subprocess.run([_CLAUDE_BINARY, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unknown ({exc})"
    return completed.stdout.strip() or completed.stderr.strip() or "unknown"


# Cheap, deterministic-enough model for the canary. Must be a valid --model
# shortname the CLI accepts.
_MODEL = "claude-haiku-4-5-20251001"

# Prefix every frame with a framing note; matches the real-Claude suite's habit
# of improving instruction compliance for automated tests.
_TEST_PREFIX = (
    "[SCULPTOR-CANARY-TEST] Automated integration test of the Claude CLI "
    + "stream-json delivery protocol, not a real user request. Follow the "
    + "instructions exactly as given. "
)

# Unique, model-unlikely markers embedded in the *injected* frames. Used to
# locate the frame in the transcript and to check it is not replayed on stdout
# (see stdout_input_echoes for why raw-stdout scanning would be a false match).
_STEER_MARKER = "ZZ-INJECT-3471"
_FOLLOWUP_MARKER = "QQ-FOLLOWUP-8842"

# A background sleep long enough that turn 1 (the launch turn) must finish well
# before it does; if the model runs it in the foreground instead, turn 1's
# result arrives only after this elapses and the timing precondition trips.
_BG_SLEEP_SECONDS = 25

# Turn 1 of the between-turns scenario must complete faster than this for the
# background task to still be running when the follow-up is delivered. A
# foreground sleep would push it past _BG_SLEEP_SECONDS.
_LAUNCH_TURN_MAX_SECONDS = 20.0

# An idle CLI must exit within this window of stdin close. The real regression
# (CLI ignores EOF and lingers) blows far past it; the bound just gives a
# clearer message than the outer pytest timeout.
_EOF_EXIT_MAX_SECONDS = 15.0

# The model occasionally answers without running the tool the scenario needs
# (no in-flight turn to steer into; no background task to react to). That is a
# model choice, not a CLI-delivery change, so retry the setup on a fresh session
# rather than failing. Only the delivery assertions past a confirmed setup are
# hard failures.
_MAX_SETUP_ATTEMPTS = 4

_CLAUDE_BINARY = shutil.which("claude")

pytestmark = pytest.mark.skipif(
    _CLAUDE_BINARY is None,
    reason="real `claude` CLI not on PATH",
)


@dataclass
class _StreamEvent:
    """One line of stream-json stdout, timestamped when the reader observed it.

    ``monotonic`` is the reader-thread arrival time (time.monotonic); it is the
    basis for every timing precondition. ``obj`` is None for the rare
    unparseable line (kept as ``raw`` for diagnostics).
    """

    monotonic: float
    raw: str
    obj: dict | None


def _is_init(obj: dict) -> bool:
    return obj.get("type") == "system" and obj.get("subtype") == "init"


def _is_result(obj: dict) -> bool:
    return obj.get("type") == "result"


def _is_bash_sleep_tool_use(obj: dict) -> bool:
    """A ``Bash`` tool_use whose command runs ``sleep`` — the slow in-flight turn.

    Matching the specific slow call (not any tool_use) keeps a fast tool the
    model might emit first — e.g. TodoWrite — from being mistaken for the
    in-flight turn, which would land the injection near turn-end.
    """
    if obj.get("type") != "assistant":
        return False
    for block in obj.get("message", {}).get("content", []):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
            command = (block.get("input") or {}).get("command", "")
            if isinstance(command, str) and "sleep" in command:
                return True
    return False


def _is_task_started(obj: dict) -> bool:
    return obj.get("type") == "system" and obj.get("subtype") == "task_started"


def _is_task_updated(obj: dict) -> bool:
    return obj.get("type") == "system" and obj.get("subtype") == "task_updated"


def _is_task_completed(obj: dict) -> bool:
    return (
        obj.get("type") == "system" and obj.get("subtype") == "task_notification" and obj.get("status") == "completed"
    )


def _is_bash_sleep_or_result(obj: dict) -> bool:
    return _is_bash_sleep_tool_use(obj) or _is_result(obj)


def _assistant_text(obj: dict) -> str:
    content = obj.get("message", {}).get("content", [])
    return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


@dataclass
class _StreamJsonSession:
    """Drives one ``claude`` invocation over the stream-json stdin/stdout wire.

    Frames are written to a live stdin at test-chosen moments (usually keyed off
    an observed stdout event, so the mid-turn vs between-turns distinction is
    exact rather than sleep-timed). A daemon reader thread drains stdout
    line-by-line via ``readline`` — iterating the pipe would read-ahead buffer
    and delay event observation, breaking the injection timing — recording each
    line with its arrival timestamp. stderr is drained on its own thread so a
    chatty CLI can't deadlock on a full pipe.

    The CLI emits no stdout at all — not even ``system/init`` — until it reads
    its first stdin frame, so every scenario sends its opening prompt before
    awaiting init.
    """

    cwd: Path
    model: str = _MODEL

    _process: subprocess.Popen | None = field(default=None, init=False)
    _events: list[_StreamEvent] = field(default_factory=list, init=False)
    _stderr: list[str] = field(default_factory=list, init=False)
    # Guards _events/_stderr and wakes waiters as each stdout line arrives, so
    # waits block on the reader rather than polling with time.sleep.
    _cond: threading.Condition = field(default_factory=threading.Condition, init=False)
    _reader: threading.Thread | None = field(default=None, init=False)
    _stderr_reader: threading.Thread | None = field(default=None, init=False)

    def __enter__(self) -> "_StreamJsonSession":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.kill()
            # Suppress so a slow teardown can't raise while unwinding a failing
            # assertion and mask the original error.
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=10)
        for thread in (self._reader, self._stderr_reader):
            if thread is not None:
                thread.join(timeout=5)

    def start(self) -> None:
        assert _CLAUDE_BINARY is not None
        # The CLI slugifies the resolved cwd for the transcript path; /tmp is a
        # symlink to /private/tmp on macOS, so resolve before spawning.
        self.cwd = self.cwd.resolve()
        env = dict(os.environ)
        # The default test harness forces a placeholder ANTHROPIC_API_KEY that
        # actively blocks the CLI's OAuth flow; drop it so ~/.claude auth wins,
        # mirroring the real_claude conftest's hide_keys=False intent.
        if "HIDDEN" in env.get("ANTHROPIC_API_KEY", ""):
            env.pop("ANTHROPIC_API_KEY")
        self._process = subprocess.Popen(
            [
                _CLAUDE_BINARY,
                "-p",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
                "--dangerously-skip-permissions",
                "--model",
                self.model,
            ],
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_reader.start()

    def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            for line in iter(self._process.stdout.readline, ""):
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    obj: dict | None = json.loads(line)
                except json.JSONDecodeError:
                    obj = None
                with self._cond:
                    self._events.append(_StreamEvent(time.monotonic(), line, obj))
                    self._cond.notify_all()
        finally:
            # Wake waiters when stdout closes (process exit) so they can observe
            # the exit instead of blocking until their timeout.
            with self._cond:
                self._cond.notify_all()

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in iter(self._process.stderr.readline, ""):
            with self._cond:
                self._stderr.append(line.rstrip("\n"))

    def events(self) -> list[_StreamEvent]:
        with self._cond:
            return list(self._events)

    def stdout_input_echoes(self, needle: str) -> list[str]:
        """User-input frames replayed verbatim on stdout (the replay shape).

        ``--replay-user-messages`` echoes each input frame back as a
        ``type:"user"`` event whose message content is a plain string. Without
        it, no such echo appears. This deliberately does not scan raw stdout: in
        ``--verbose`` the model routinely quotes an injected instruction in its
        own ``assistant`` thinking/text, and tool results arrive as list-content
        user events — neither is an input echo, so matching on those would be a
        false positive.

        Narrow by construction: if the replay shape ever changes (e.g. to
        list-content), this negative check could pass vacuously. It is a
        secondary signal — the load-bearing delivery assertion is the
        transcript (queued_command attachment vs plain user message), which
        would still catch a delivery regression.
        """
        echoes = []
        for event in self.events():
            if event.obj is None or event.obj.get("type") != "user":
                continue
            content = event.obj.get("message", {}).get("content")
            if isinstance(content, str) and needle in content:
                echoes.append(content)
        return echoes

    def stderr_text(self) -> str:
        with self._cond:
            return "\n".join(self._stderr)

    def send_frame(self, content: str) -> float:
        """Write one user frame to stdin; return its monotonic write time."""
        assert self._process is not None and self._process.stdin is not None
        frame = json.dumps({"type": "user", "message": {"role": "user", "content": content}})
        write_time = time.monotonic()
        try:
            self._process.stdin.write(frame + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:  # process already exited
            raise AssertionError(
                f"Failed to write frame — the CLI exited early.\nstderr:\n{self.stderr_text()}"
            ) from exc
        return write_time

    def close_stdin(self) -> None:
        assert self._process is not None and self._process.stdin is not None
        self._process.stdin.close()

    def session_id(self) -> str:
        for event in self.events():
            if event.obj is not None and _is_init(event.obj):
                return event.obj["session_id"]
        raise AssertionError(f"No system/init event with a session_id observed.\n{self._diagnostics()}")

    def result_count(self) -> int:
        return sum(1 for e in self.events() if e.obj is not None and _is_result(e.obj))

    def has_event(self, predicate: Callable[[dict], bool]) -> bool:
        return any(e.obj is not None and predicate(e.obj) for e in self.events())

    def wait_for_event(
        self,
        predicate: Callable[[dict], bool],
        timeout: float,
        description: str,
    ) -> _StreamEvent:
        """Return the first observed event matching ``predicate``, else fail."""

        def satisfied(events: list[_StreamEvent]) -> _StreamEvent | None:
            for event in events:
                if event.obj is not None and predicate(event.obj):
                    return event
            return None

        return self._wait_until(satisfied, timeout, description)

    def wait_for_result_count(self, count: int, timeout: float, description: str) -> _StreamEvent:
        """Return the ``count``-th ``result`` event once it appears, else fail."""

        def satisfied(events: list[_StreamEvent]) -> _StreamEvent | None:
            results = [e for e in events if e.obj is not None and _is_result(e.obj)]
            return results[count - 1] if len(results) >= count else None

        return self._wait_until(satisfied, timeout, description)

    def _wait_until(
        self,
        satisfied: Callable[[list[_StreamEvent]], _StreamEvent | None],
        timeout: float,
        description: str,
    ) -> _StreamEvent:
        """Block on the reader condition until ``satisfied``, exit, or timeout.

        Waking on each stdout line (rather than a fixed poll interval) keeps
        event-driven frame injection tight and needs no ``time.sleep``.
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                hit = satisfied(self._events)
                if hit is not None:
                    return hit
                if self._process is not None and self._process.poll() is not None:
                    raise AssertionError(
                        f"CLI exited (code {self._process.returncode}) before: {description}\n{self._diagnostics()}"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(
                        f"Timed out after {timeout}s waiting for: {description}\n{self._diagnostics()}"
                    )
                self._cond.wait(timeout=remaining)

    def wait_for_exit(self, timeout: float) -> tuple[int, float]:
        """Wait for the process to exit; return (returncode, seconds waited)."""
        assert self._process is not None
        start = time.monotonic()
        try:
            returncode = self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(f"CLI did not exit within {timeout}s of stdin close.\n{self._diagnostics()}") from exc
        return returncode, time.monotonic() - start

    def assistant_texts_between(self, start: float, end: float) -> list[str]:
        return [
            _assistant_text(e.obj)
            for e in self.events()
            if e.obj is not None and e.obj.get("type") == "assistant" and start < e.monotonic <= end
        ]

    def _diagnostics(self) -> str:
        summary = []
        for event in self.events():
            if event.obj is None:
                summary.append(f"  {event.monotonic:8.2f}  <unparseable> {event.raw[:80]}")
                continue
            obj = event.obj
            label = obj.get("type", "?")
            subtype = obj.get("subtype")
            if subtype:
                label = f"{label}/{subtype}"
            if obj.get("type") == "assistant":
                content = obj.get("message", {}).get("content", [])
                label += " " + str([b.get("type") for b in content if isinstance(b, dict)])
            summary.append(f"  {event.monotonic:8.2f}  {label}")
        stderr = self.stderr_text()
        stderr_block = f"\nstderr:\n{stderr}" if stderr else ""
        version_line = (
            f"claude --version: {_installed_cli_version()} (canary verified against {_VERIFIED_CLI_VERSION})\n"
        )
        return version_line + "stdout events:\n" + "\n".join(summary) + stderr_block


def _read_transcript(cwd: Path, session_id: str) -> list[dict]:
    """Parse the session JSONL the CLI wrote for ``session_id``.

    Uses Sculptor's own path logic (``compute_claude_jsonl_directory``) so the
    canary tracks the same slug convention the product relies on, with a
    session-id glob fallback in case that logic ever drifts from the CLI.
    """
    expected = compute_claude_jsonl_directory(Path.home(), cwd.resolve()) / f"{session_id}.jsonl"
    path: Path | None = expected if expected.exists() else None
    if path is None:
        projects_root = compute_claude_jsonl_directory(Path.home(), cwd.resolve()).parent
        matches = list(projects_root.glob(f"**/{session_id}.jsonl"))
        path = matches[0] if matches else None
    assert path is not None, (
        f"No transcript found for session {session_id} (looked at {expected} and its projects tree)"
    )
    entries: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _queued_command_prompts(transcript: list[dict]) -> list[str]:
    """Prompts of ``queued_command`` attachment entries (the steering shape).

    The transcript carries other ``attachment`` types (tool/skill listings), so
    match on the nested ``attachment.type``, not the top-level entry type.
    """
    prompts = []
    for entry in transcript:
        attachment = entry.get("attachment")
        if (
            entry.get("type") == "attachment"
            and isinstance(attachment, dict)
            and attachment.get("type") == "queued_command"
        ):
            prompts.append(attachment.get("prompt", ""))
    return prompts


def _plain_user_texts(transcript: list[dict]) -> list[str]:
    """Text of ordinary user-authored messages (excludes tool_result frames)."""
    texts = []
    for entry in transcript:
        if entry.get("type") != "user":
            continue
        content = entry.get("message", {}).get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            texts.append(
                " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            )
    return texts


@real_claude
@pytest.mark.timeout(180)
def test_mid_turn_frame_becomes_steering_queued_command(tmp_path: Path) -> None:
    """Scenario 1: a frame injected mid-turn is absorbed as a queued_command.

    Turn is blocked on a slow foreground ``Bash: sleep``; the second frame is
    written while the tool runs. Exactly one ``result`` is emitted, the frame is
    not replayed as an input echo on stdout, and the transcript records it as a
    ``queued_command`` attachment rather than a plain user message. The final
    reply word is NOT asserted: mid-turn steering has soft authority, so the
    model may keep its original instruction (and routinely quotes the injected
    instruction in its thinking, which is why echo detection targets the replay
    shape rather than scanning raw stdout).
    """
    for _attempt in range(_MAX_SETUP_ATTEMPTS):
        with _StreamJsonSession(tmp_path) as session:
            session.send_frame(
                _TEST_PREFIX
                + "Do a Bash tool call that runs exactly: sleep 12. Do not skip it and "
                + "do not simulate it — actually run the command and wait for it to "
                + "finish. Only then reply with exactly the single word WAKE."
            )
            session.wait_for_event(_is_init, timeout=30, description="system/init")
            # Inject only once the turn is genuinely in-flight on the slow Bash sleep,
            # so the frame is mid-turn by construction (the tool won't return for
            # ~12s). If the model answers without that tool — or emits a fast tool
            # first and then the result — the turn's result arrives before the slow
            # tool_use, which is a setup miss, so retry on a fresh session.
            setup = session.wait_for_event(
                _is_bash_sleep_or_result, timeout=60, description="Bash sleep tool_use or turn result"
            )
            if _is_result(setup.obj):
                continue
            inject_time = session.send_frame(
                _TEST_PREFIX
                + f"NEW INSTRUCTION while you wait (marker {_STEER_MARKER}): your "
                + "final reply must be exactly the single word BANANA instead."
            )
            result = session.wait_for_result_count(1, timeout=120, description="turn result")

            # Timing precondition: the injection landed before the turn's result.
            # If it landed after, we'd be silently testing the between-turns case.
            assert inject_time < result.monotonic, (
                f"Injection ({inject_time:.2f}) landed at/after the turn result "
                + f"({result.monotonic:.2f}) — this is testing scenario 2, not mid-turn steering.\n"
                + session._diagnostics()
            )

            session.close_stdin()
            session.wait_for_exit(timeout=30)

            # stdout: exactly one turn, and the injected frame is not replayed.
            assert session.result_count() == 1, (
                f"Expected exactly 1 result (mid-turn absorption), got {session.result_count()}.\n"
                + session._diagnostics()
            )
            echoes = session.stdout_input_echoes(_STEER_MARKER)
            assert echoes == [], f"Injected frame was replayed on stdout without --replay-user-messages: {echoes}"

            # transcript: delivered as a queued_command attachment, not a plain turn.
            transcript = _read_transcript(session.cwd, session.session_id())
            queued = _queued_command_prompts(transcript)
            assert any(_STEER_MARKER in prompt for prompt in queued), (
                f"Injected frame not recorded as a queued_command attachment. queued_command prompts: {queued}"
            )
            plain_with_marker = [t for t in _plain_user_texts(transcript) if _STEER_MARKER in t]
            assert plain_with_marker == [], (
                f"Injected frame was recorded as a plain user message, not steering: {plain_with_marker}"
            )
            return
    pytest.fail(
        f"Model never ran the slow Bash tool across {_MAX_SETUP_ATTEMPTS} attempts; cannot exercise mid-turn steering. "
        + f"(claude --version: {_installed_cli_version()})"
    )


@real_claude
@pytest.mark.timeout(300)
def test_between_turns_frame_is_plain_followup_then_reaction_turn(tmp_path: Path) -> None:
    """Scenarios 2 + 3: between-turns follow-up, then a reaction turn.

    Turn 1 launches a background ``Bash`` task and ends at its own ``result``
    while the task still runs. A frame written then starts a plain new turn with
    full authority (transcript: ordinary user message, zero queued_command). When
    the background task later completes, the CLI emits task_updated +
    task_notification and spontaneously runs a reaction turn — three results in
    all, with an unrelated user turn in between.
    """
    for _attempt in range(_MAX_SETUP_ATTEMPTS):
        with _StreamJsonSession(tmp_path) as session:
            launch_time = session.send_frame(
                _TEST_PREFIX
                + "Do a Bash tool call with run_in_background set to true that runs: "
                + f"sleep {_BG_SLEEP_SECONDS} && echo TASKDONE. Do not wait for it — "
                + "immediately after launching it, reply with exactly the single word "
                + "LAUNCHED and nothing else."
            )
            session.wait_for_event(_is_init, timeout=30, description="system/init")
            result1 = session.wait_for_result_count(1, timeout=90, description="turn 1 result (LAUNCHED)")
            launch_elapsed = result1.monotonic - launch_time

            # Setup: turn 1 must end (LAUNCHED) while a background task it started is
            # still running. If the model foregrounded the sleep (turn 1 only ends
            # after _BG_SLEEP_SECONDS), ran no task at all, or the task already
            # finished, this is not a between-turns frame — retry on a fresh session.
            if (
                launch_elapsed >= _LAUNCH_TURN_MAX_SECONDS
                or not session.has_event(_is_task_started)
                or session.has_event(_is_task_completed)
            ):
                continue

            followup_time = session.send_frame(
                _TEST_PREFIX
                + f"While we wait for that task (marker {_FOLLOWUP_MARKER}): reply "
                + "with exactly the single word BANANA and nothing else."
            )
            assert result1.monotonic < followup_time  # between-turns by construction
            result2 = session.wait_for_result_count(2, timeout=90, description="turn 2 result (follow-up)")

            # Scenario 3: task completion emits task_updated + task_notification and
            # drives a fresh reaction turn. Pin the full shape: task_updated precedes
            # the notification, and the reaction turn is its own init -> ... -> result
            # cycle after the notification (each turn re-emits system/init).
            task_updated = session.wait_for_event(_is_task_updated, timeout=120, description="background task_updated")
            completion = session.wait_for_event(
                _is_task_completed, timeout=120, description="background task_notification (completed)"
            )
            assert task_updated.monotonic <= completion.monotonic, (
                "task_updated did not precede the task_notification.\n" + session._diagnostics()
            )
            result3 = session.wait_for_result_count(3, timeout=90, description="reaction turn result")
            assert result3.monotonic > completion.monotonic, (
                "Reaction-turn result arrived before the task completion notification.\n" + session._diagnostics()
            )
            reaction_init = next(
                (
                    e
                    for e in session.events()
                    if e.obj is not None
                    and _is_init(e.obj)
                    and completion.monotonic <= e.monotonic <= result3.monotonic
                ),
                None,
            )
            assert reaction_init is not None, (
                "Reaction turn did not open a fresh system/init cycle after the task notification.\n"
                + session._diagnostics()
            )

            session.close_stdin()
            session.wait_for_exit(timeout=30)

            assert session.result_count() == 3, (
                f"Expected 3 results (launch, follow-up, reaction), got {session.result_count()}.\n"
                + session._diagnostics()
            )
            followup_echoes = session.stdout_input_echoes(_FOLLOWUP_MARKER)
            assert followup_echoes == [], (
                f"Follow-up frame was replayed on stdout without --replay-user-messages: {followup_echoes}"
            )
            # Full authority: the follow-up ran as its own turn and was obeyed.
            turn2_texts = session.assistant_texts_between(result1.monotonic, result2.monotonic)
            assert any("BANANA" in text for text in turn2_texts), (
                f"Follow-up turn did not produce the instructed reply. turn 2 assistant text: {turn2_texts}"
            )

            # transcript: plain user message, and zero queued_command entries.
            transcript = _read_transcript(session.cwd, session.session_id())
            assert _queued_command_prompts(transcript) == [], (
                f"A between-turns follow-up must not be recorded as steering: {_queued_command_prompts(transcript)}"
            )
            plain_with_marker = [t for t in _plain_user_texts(transcript) if _FOLLOWUP_MARKER in t]
            assert plain_with_marker, "Follow-up frame was not recorded as a plain user message."
            return
    pytest.fail(
        f"Model never launched a still-running background task in a fast turn 1 across {_MAX_SETUP_ATTEMPTS} attempts. "
        + f"(claude --version: {_installed_cli_version()})"
    )


@real_claude
@pytest.mark.timeout(120)
def test_idle_cli_exits_promptly_on_stdin_eof(tmp_path: Path) -> None:
    """Scenario 4: an idle CLI exits promptly on stdin close, silently.

    Sculptor owns close timing — the CLI exits only on stdin EOF. After a single
    turn completes and the CLI goes idle with no pending tasks, closing stdin
    must exit the process promptly and emit no further messages.
    """
    with _StreamJsonSession(tmp_path) as session:
        session.send_frame(_TEST_PREFIX + "Reply with exactly the single word READY and nothing else.")
        session.wait_for_event(_is_init, timeout=30, description="system/init")
        result = session.wait_for_event(_is_result, timeout=90, description="turn result")

        session.close_stdin()
        returncode, exit_elapsed = session.wait_for_exit(timeout=30)

        assert returncode == 0, f"CLI exited non-zero ({returncode}) on stdin close.\n{session.stderr_text()}"
        assert exit_elapsed < _EOF_EXIT_MAX_SECONDS, (
            f"CLI took {exit_elapsed:.1f}s to exit after stdin close; expected prompt exit."
        )
        assert session.result_count() == 1, (
            f"Expected exactly 1 result, got {session.result_count()}.\n" + session._diagnostics()
        )
        # No further turn output after the idle CLI was told to close.
        post_result = [
            e
            for e in session.events()
            if e.obj is not None
            and e.monotonic > result.monotonic
            and e.obj.get("type") in ("assistant", "user", "result")
        ]
        assert post_result == [], (
            f"CLI emitted messages after going idle + stdin close: {[e.obj.get('type') for e in post_result]}\n"
            + session._diagnostics()
        )
