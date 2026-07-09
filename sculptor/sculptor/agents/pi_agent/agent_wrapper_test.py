"""Tests for `PiAgent` — JSONL RPC exchange and start-time error surfaces.

The tests stub the pi subprocess with a `MagicMock` `RunningProcess` so
the full RPC pump can be exercised without a real binary. Coverage
mirrors pi's three-channel envelope: command-ACK `response`
events, the `extension_ui_request` backchannel lane (ask-user-question +
plan-mode dialogs), and the `AgentSessionEvent` session-stream.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any
from typing import Callable
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from sculptor.agents.pi_agent import agent_wrapper as agent_wrapper_module
from sculptor.agents.pi_agent.agent_wrapper import PI_PROBE_SESSION_DIR_NAME
from sculptor.agents.pi_agent.agent_wrapper import PI_SESSION_DIR_NAME
from sculptor.agents.pi_agent.agent_wrapper import PI_SESSION_ID_STATE_FILE
from sculptor.agents.pi_agent.agent_wrapper import PiAgent
from sculptor.agents.pi_agent.agent_wrapper import _PI_TRANSIENT_RETRY_BASE_DELAY_SECONDS
from sculptor.agents.pi_agent.agent_wrapper import _PI_TRANSIENT_RETRY_MAX_DELAY_SECONDS
from sculptor.agents.pi_agent.agent_wrapper import _TurnState
from sculptor.agents.pi_agent.agent_wrapper import _curate_models
from sculptor.agents.pi_agent.agent_wrapper import _format_background_completion
from sculptor.agents.pi_agent.agent_wrapper import _format_subagent_completion
from sculptor.agents.pi_agent.agent_wrapper import _model_option_from_pi
from sculptor.agents.pi_agent.agent_wrapper import _render_synthesized_skill
from sculptor.agents.pi_agent.agent_wrapper import _rewrite_skill_invocation
from sculptor.agents.pi_agent.backchannel import DISMISSED_ANSWER_VALUE
from sculptor.agents.pi_agent.backchannel import PLAN_APPROVAL_DIALOG_TITLE
from sculptor.agents.pi_agent.backchannel import PLAN_APPROVAL_HEADER
from sculptor.agents.pi_agent.background import BACKGROUND_NOTIFY_MARKER
from sculptor.agents.pi_agent.background import BACKGROUND_PAYLOAD_VERSION
from sculptor.agents.pi_agent.background import parse_background_completion
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.agents.pi_agent.output_processor import AgentMessage
from sculptor.agents.pi_agent.output_processor import ParsedAgentEnd
from sculptor.agents.pi_agent.output_processor import ParsedUnknownEvent
from sculptor.agents.pi_agent.output_processor import extract_tool_call_blocks
from sculptor.agents.pi_agent.output_processor import parse_rpc_message
from sculptor.agents.pi_agent.subagent import SUBAGENT_NOTIFY_MARKER
from sculptor.agents.pi_agent.subagent import parse_subagent_completion
from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingAgentMessage
from sculptor.interfaces.agents.agent import AutoCompactingDoneAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskNotificationAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskStartedAgentMessage
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import ContextClearedMessage
from sculptor.interfaces.agents.agent import EphemeralUserMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import ModelsAvailableAgentMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import RefreshModelsUserMessage
from sculptor.interfaces.agents.agent import RemoveQueuedMessageUserMessage
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import SetModelUserMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import TurnMetricsAgentMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.errors import PiBinaryNotFoundError
from sculptor.interfaces.agents.errors import PiCrashError
from sculptor.interfaces.agents.errors import PiVersionMismatchError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import GenericToolContent
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.chat_state import make_plan_approval_question
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import ModelOption
from sculptor.state.messages import ResponseBlockAgentMessage

_PROMPT_ID = "prompt-1"


def _make_agent(
    environment: AgentExecutionEnvironment | None = None,
    on_diff_needed: Callable[[], None] | None = None,
    preselected_model: ModelOption | None = None,
) -> PiAgent:
    env = environment if environment is not None else MagicMock(spec=AgentExecutionEnvironment)
    return PiAgent(
        harness=PI_HARNESS,
        environment=env,
        task_id=TaskID(),
        config=PiAgentConfig(),
        system_prompt="",
        git_hash="deadbeef",
        on_diff_needed=on_diff_needed,
        preselected_model=preselected_model,
    )


def _make_process(lines: list[str], returncode: int = 0) -> MagicMock:
    """Stub `RunningProcess`: replays canned stdout lines then reports finished."""
    queue: Queue[tuple[str, bool]] = Queue()
    for line in lines:
        queue.put((line, True))

    process = MagicMock()
    process.get_queue.return_value = queue
    # is_finished() is polled inside the consume loop; report True only once
    # the queue has been drained.
    process.is_finished.side_effect = [False] * len(lines) + [True] * 50
    process.wait.return_value = returncode
    return process


def _event(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _assistant_msg(text: str, stop_reason: str = "stop") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stopReason": stop_reason,
    }


def _assistant_error_msg(error_message: str, text: str = "") -> dict[str, Any]:
    """An assistant message_end that ended in a turn-failure (stopReason "error").

    `error_message` (wire `errorMessage`) carries pi's provider failure reason —
    the only place a transient provider condition (overloaded/rate-limit/5xx/
    timeout) is recorded for a turn that fails without an in-stream error event.
    """
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}] if text else [],
        "stopReason": "error",
        "errorMessage": error_message,
    }


def _user_msg(text: str) -> dict[str, Any]:
    # A role="user" message carries no stopReason — pi only sets stopReason on
    # generated assistant messages. Mirrors the prompt-echo message pi emits at
    # the start of every agent run.
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _text_delta_update(delta: str, partial_text: str, content_index: int = 0) -> dict[str, Any]:
    return {
        "type": "message_update",
        "message": _assistant_msg(partial_text, stop_reason=""),
        "assistantMessageEvent": {
            "type": "text_delta",
            "contentIndex": content_index,
            "delta": delta,
        },
    }


def _tool_call_block(tool_call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    # pi's toolCall content block shape (docs/session-format.md): id, name, arguments.
    return {"type": "toolCall", "id": tool_call_id, "name": name, "arguments": arguments}


def _assistant_msg_with_content(content: list[dict[str, Any]], stop_reason: str = "toolUse") -> dict[str, Any]:
    return {"role": "assistant", "content": content, "stopReason": stop_reason}


def _tool_execution_start(tool_call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_execution_start", "toolCallId": tool_call_id, "toolName": name, "args": args}


def _tool_execution_end(tool_call_id: str, name: str, result: Any = None, is_error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool_execution_end",
        "toolCallId": tool_call_id,
        "toolName": name,
        "result": result,
        "isError": is_error,
    }


def _tool_use_blocks(messages: list) -> list[ToolUseBlock]:
    """Every ToolUseBlock across all emitted partial/response messages, in order."""
    return [
        block
        for m in messages
        if isinstance(m, (ResponseBlockAgentMessage, PartialResponseBlockAgentMessage))
        for block in m.content
        if isinstance(block, ToolUseBlock)
    ]


def _tool_result_blocks(messages: list) -> list[ToolResultBlock]:
    """Every ToolResultBlock across all emitted response messages, in order."""
    return [
        block
        for m in messages
        if isinstance(m, ResponseBlockAgentMessage)
        for block in m.content
        if isinstance(block, ToolResultBlock)
    ]


def _generic_result_text(block: ToolResultBlock) -> str:
    """Narrow a result block's content to GenericToolContent and return its text."""
    assert isinstance(block.content, GenericToolContent)
    return block.content.text


def _text_block_text(block: object) -> str:
    """Narrow a content block to TextBlock and return its text."""
    assert isinstance(block, TextBlock)
    return block.text


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Poll ``predicate`` until true; used to synchronize the two-thread interrupt
    path deterministically (no fixed sleeps)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def _abort_was_written(process: MagicMock) -> bool:
    for call in process.write_stdin.call_args_list:
        try:
            payload = json.loads(call.args[0].rstrip("\n"))
        except (json.JSONDecodeError, IndexError):
            continue
        if isinstance(payload, dict) and payload.get("type") == "abort":
            return True
    return False


def _answer(
    answers: dict[str, str],
    tool_use_id: str,
    question_data: AskUserQuestionData | None = None,
) -> UserQuestionAnswerMessage:
    return UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers=answers,
        question_data=question_data or AskUserQuestionData(questions=[], tool_use_id=tool_use_id),
        tool_use_id=tool_use_id,
    )


def _written_payloads(process: MagicMock) -> list[dict[str, Any]]:
    return [json.loads(call.args[0].rstrip("\n")) for call in process.write_stdin.call_args_list]


def _clear_env() -> MagicMock:
    """A MagicMock environment whose state path supports the post-clear session-id write."""
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_state_path.return_value = Path("/fake/state")
    return env


def _make_start_env(persisted_session_id: str | None = None) -> MagicMock:
    """A MagicMock environment that lets PiAgent.start() run past the binary /
    version preflight and into the session-launch logic.

    `persisted_session_id` None ⇒ the pi_session_id state file is absent (fresh
    launch); a value ⇒ it is present (resume launch).
    """
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_tool_binary_path.return_value = "/bin/pi"
    version_result = MagicMock()
    version_result.stdout = ""
    version_result.stderr = "pi 0.80.2\n"
    env.run_process_to_completion.return_value = version_result
    env.get_state_path.return_value = Path("/fake/state")
    env.get_system_prompt.return_value = ""
    # start() discovers skills under the working dir + home dir; give both real
    # Paths so the skill-source models validate (the dirs need not exist —
    # discovery finds none).
    env.get_working_directory.return_value = Path("/fake/working_dir")
    env.get_user_home_directory.return_value = Path("/fake/home")

    def _read_file(path: str, mode: str = "r") -> str:
        if path.endswith(PI_SESSION_ID_STATE_FILE) and persisted_session_id is not None:
            return persisted_session_id
        # removed_message_ids (base class) and an absent pi_session_id both miss.
        raise FileNotFoundError(path)

    env.read_file.side_effect = _read_file
    env.run_process_in_background.return_value = MagicMock()
    return env


def _launched_command(env: MagicMock) -> list[str]:
    env.run_process_in_background.assert_called_once()
    return list(env.run_process_in_background.call_args.args[0])


def _make_agent_with_attachments_env(tmp_path: Path, image_bytes: bytes = b"") -> tuple[PiAgent, MagicMock, Path]:
    """An agent whose environment records writes and serves ``image_bytes`` on read."""
    attachments_dir = tmp_path / "attachments"
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_attachments_path.return_value = attachments_dir
    env.read_file.return_value = image_bytes
    return _make_agent(env), env, attachments_dir


def _drain(queue: Queue) -> list:
    out: list = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


# Wire-shape fixtures for every documented event type (RPC §5/§7/§9), lifted
# from the protocol doc's examples. Each must parse to a typed variant whose
# discriminator matches.
_DOCUMENTED_EVENTS: list[dict[str, Any]] = [
    {"type": "response", "command": "prompt", "success": True, "id": _PROMPT_ID},
    {"type": "extension_ui_request", "id": "u1", "method": "select"},
    {"type": "agent_start"},
    {"type": "agent_end", "messages": [], "willRetry": False},
    {"type": "turn_start"},
    {"type": "turn_end", "message": _assistant_msg("x"), "toolResults": []},
    {"type": "message_start", "message": _assistant_msg("x", stop_reason="")},
    _text_delta_update("x", "x"),
    {"type": "message_end", "message": _assistant_msg("x")},
    {"type": "tool_execution_start", "toolCallId": "t", "toolName": "read", "args": {}},
    {"type": "tool_execution_update", "toolCallId": "t", "toolName": "read", "args": {}, "partialResult": "..."},
    {"type": "tool_execution_end", "toolCallId": "t", "toolName": "read", "result": {}, "isError": False},
    {"type": "queue_update", "steering": [], "followUp": []},
    {"type": "compaction_start", "reason": "threshold"},
    {"type": "compaction_end", "reason": "threshold", "aborted": False, "willRetry": False},
    {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3, "delayMs": 100, "errorMessage": "x"},
    {"type": "auto_retry_end", "success": True, "attempt": 1},
    {"type": "session_info_changed", "name": "sess"},
    {"type": "thinking_level_changed", "level": "high"},
    {"type": "extension_error", "extensionPath": "/x", "event": "e", "error": "boom"},
]

# Events pi-basic does not consume: each must be discarded (no emitted message,
# no PiCrashError), and the turn must still end at the following agent_end.
# compaction_start/end are deliberately ABSENT — they emit the AutoCompacting*
# chrome pair (see the compaction tests above) rather than being discarded.
_DISCARDED_EVENTS: list[dict[str, Any]] = [
    {"type": "turn_start"},
    {"type": "turn_end", "message": _assistant_msg("x"), "toolResults": []},
    {"type": "message_start", "message": _assistant_msg("x", stop_reason="")},
    {"type": "queue_update", "steering": ["a"], "followUp": []},
    {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3, "delayMs": 1, "errorMessage": "e"},
    {"type": "session_info_changed", "name": "s"},
    {"type": "thinking_level_changed", "level": "high"},
    {"type": "from_the_future"},
]

_DISCOVERED = frozenset({"fix-bug", "sculptor-workflow:review", "write-release-notes"})


def _agent_with_skill_dirs(
    monkeypatch: pytest.MonkeyPatch,
    working_dir: Path,
    home_dir: Path,
    state_dir: Path,
    plugin_dirs: list[Path],
) -> PiAgent:
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_working_directory.return_value = working_dir
    env.get_user_home_directory.return_value = home_dir
    env.get_state_path.return_value = state_dir
    # Patch where it's looked up: agent_wrapper imports get_plugin_dirs at module level.
    monkeypatch.setattr("sculptor.agents.pi_agent.agent_wrapper.get_plugin_dirs", lambda: plugin_dirs)
    return _make_agent(environment=env)


def _write_skill(skills_dir: Path, name: str) -> None:
    skill_md = skills_dir / name / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(f"---\nname: {name}\ndescription: {name} skill\n---\nBody\n")


_SA_TOOL_CALL_ID = "sa1"

_SA_TASK_ID = f"sat_{_SA_TOOL_CALL_ID}"

_SA_PGIDS = (5151, 5252)


def _subagent_child(child_id: str, status: str, events: list[dict[str, Any]], label: str = "subagent") -> dict:
    """One child entry in the wire shape sculptor_subagent.ts emits."""
    return {"childId": child_id, "label": label, "task": "do a thing", "status": status, "events": events}


def _read_child_events() -> list[dict[str, Any]]:
    return [
        {"seq": 0, "kind": "tool_call", "toolCallId": "ct1", "toolName": "read", "args": {"path": "/etc/hosts"}},
        {"seq": 1, "kind": "tool_result", "toolCallId": "ct1", "text": "127.0.0.1 localhost", "isError": False},
        {"seq": 2, "kind": "text", "text": "It has one line."},
    ]


def _subagent_start_result(
    task_id: str = _SA_TASK_ID,
    tool_call_id: str = _SA_TOOL_CALL_ID,
    label: str = "2 sub-agents",
    pgids: tuple[int, ...] = _SA_PGIDS,
    count: int = 2,
) -> dict[str, Any]:
    """The {content, details} envelope the `subagent` tool returns on launch."""
    return {
        "content": [{"type": "text", "text": f"Started {count} sub-agent(s)"}],
        "details": {
            "v": 1,
            "task": {
                "taskId": task_id,
                "toolCallId": tool_call_id,
                "label": label,
                "pgids": list(pgids),
                "count": count,
                "status": "running",
            },
        },
    }


def _subagent_notify(
    children: list[dict],
    task_id: str = _SA_TASK_ID,
    tool_call_id: str = _SA_TOOL_CALL_ID,
    status: str = "completed",
) -> dict[str, Any]:
    """The fire-and-forget completion notify the extension emits out-of-band."""
    return {
        "type": "extension_ui_request",
        "id": "uireq-sa-1",
        "method": "notify",
        "notifyType": "info" if status == "completed" else "warning",
        "message": json.dumps(
            {
                SUBAGENT_NOTIFY_MARKER: {
                    "v": 1,
                    "taskId": task_id,
                    "toolCallId": tool_call_id,
                    "status": status,
                    "children": children,
                }
            }
        ),
    }


def _child_messages(emitted: list) -> list[ResponseBlockAgentMessage]:
    return [m for m in emitted if isinstance(m, ResponseBlockAgentMessage) and m.parent_tool_use_id is not None]


def _subagent_launch_events() -> list:
    """The launch run: toolCall block → tool_execution_end with the launch payload → agent_end."""
    return [
        _event({"type": "agent_start"}),
        _event(
            {
                "type": "message_end",
                "message": _assistant_msg_with_content(
                    [_tool_call_block(_SA_TOOL_CALL_ID, "subagent", {"task": "investigate"})]
                ),
            }
        ),
        _event(_tool_execution_start(_SA_TOOL_CALL_ID, "subagent", {"task": "investigate"})),
        _event(_tool_execution_end(_SA_TOOL_CALL_ID, "subagent", result=_subagent_start_result())),
        _event({"type": "agent_end", "messages": [], "willRetry": False}),
    ]


def _main_agent_texts(emitted: list) -> list[str]:
    return [
        block.text
        for m in emitted
        if isinstance(m, ResponseBlockAgentMessage) and m.parent_tool_use_id is None
        for block in m.content
        if isinstance(block, TextBlock)
    ]


_BG_TOOL_CALL_ID = "bgtc1"

_BG_TASK_ID = f"bgt_{_BG_TOOL_CALL_ID}"

_BG_PGID = 4242


def _background_start_result(
    task_id: str = _BG_TASK_ID,
    tool_call_id: str = _BG_TOOL_CALL_ID,
    command: str = "sleep 1",
    label: str = "build",
    pgid: int = _BG_PGID,
) -> dict[str, Any]:
    """The {content, details} envelope the `background` tool returns on launch."""
    return {
        "content": [{"type": "text", "text": f"Started background task {label} (pid {pgid}): {command}"}],
        "details": {
            "v": BACKGROUND_PAYLOAD_VERSION,
            "task": {
                "taskId": task_id,
                "toolCallId": tool_call_id,
                "label": label,
                "command": command,
                "pgid": pgid,
                "status": "running",
            },
        },
    }


def _background_notify(
    task_id: str = _BG_TASK_ID,
    tool_call_id: str = _BG_TOOL_CALL_ID,
    status: str = "completed",
    exit_code: int = 0,
    summary: str = "build ok",
    duration_ms: int = 1500,
) -> dict[str, Any]:
    """The fire-and-forget completion notify the extension emits out-of-band."""
    return {
        "type": "extension_ui_request",
        "id": "uireq-1",
        "method": "notify",
        "notifyType": "info" if status == "completed" else "warning",
        "message": json.dumps(
            {
                BACKGROUND_NOTIFY_MARKER: {
                    "v": BACKGROUND_PAYLOAD_VERSION,
                    "taskId": task_id,
                    "toolCallId": tool_call_id,
                    "status": status,
                    "exitCode": exit_code,
                    "summary": summary,
                    "durationMs": duration_ms,
                }
            }
        ),
    }


def _bg_started(messages: list) -> list[BackgroundTaskStartedAgentMessage]:
    return [m for m in messages if isinstance(m, BackgroundTaskStartedAgentMessage)]


def _bg_notifications(messages: list) -> list[BackgroundTaskNotificationAgentMessage]:
    return [m for m in messages if isinstance(m, BackgroundTaskNotificationAgentMessage)]


def _assert_killed_pgid(agent: PiAgent, pgid: int) -> None:
    """Assert Sculptor issued an in-environment SIGTERM to the child's process group."""
    env = agent.environment
    assert isinstance(env, MagicMock)
    calls = env.run_process_to_completion.call_args_list
    commands = [c.args[0] for c in calls if c.args and isinstance(c.args[0], list)]
    assert any(f"kill -TERM -{pgid}" in part for cmd in commands for part in cmd), commands


def _assert_no_kill(agent: PiAgent) -> None:
    """Assert Sculptor issued NO in-environment kill (a backgrounded task survives)."""
    env = agent.environment
    assert isinstance(env, MagicMock)
    commands = [
        c.args[0] for c in env.run_process_to_completion.call_args_list if c.args and isinstance(c.args[0], list)
    ]
    assert not any("kill -TERM -" in part for cmd in commands for part in cmd), commands


def _summary_texts(messages: list, *, partial: bool) -> list[str]:
    kind = PartialResponseBlockAgentMessage if partial else ResponseBlockAgentMessage
    return [
        block.text
        for m in messages
        if isinstance(m, kind)
        for block in m.content
        if isinstance(block, TextBlock) and "Background task" in block.text
    ]


# The raw get_available_models payload captured live from real pi 0.78.0 (24
# Anthropic models): the obsolete claude-3-* family plus dated-pin duplicates of
# the 4.x models alongside their friendly aliases. The curation fixture below
# asserts what the switcher should be left with.
_RAW_PI_MODELS: list[dict[str, Any]] = [
    {"id": "claude-3-5-haiku-20241022", "name": "Claude Haiku 3.5", "provider": "anthropic"},
    {"id": "claude-3-5-haiku-latest", "name": "Claude Haiku 3.5 (latest)", "provider": "anthropic"},
    {"id": "claude-3-5-sonnet-20240620", "name": "Claude Sonnet 3.5", "provider": "anthropic"},
    {"id": "claude-3-5-sonnet-20241022", "name": "Claude Sonnet 3.5 v2", "provider": "anthropic"},
    {"id": "claude-3-7-sonnet-20250219", "name": "Claude Sonnet 3.7", "provider": "anthropic"},
    {"id": "claude-3-haiku-20240307", "name": "Claude Haiku 3", "provider": "anthropic"},
    {"id": "claude-3-opus-20240229", "name": "Claude Opus 3", "provider": "anthropic"},
    {"id": "claude-3-sonnet-20240229", "name": "Claude Sonnet 3", "provider": "anthropic"},
    {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5 (latest)", "provider": "anthropic"},
    {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "provider": "anthropic"},
    {"id": "claude-opus-4-0", "name": "Claude Opus 4 (latest)", "provider": "anthropic"},
    {"id": "claude-opus-4-1", "name": "Claude Opus 4.1 (latest)", "provider": "anthropic"},
    {"id": "claude-opus-4-1-20250805", "name": "Claude Opus 4.1", "provider": "anthropic"},
    {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "provider": "anthropic"},
    {"id": "claude-opus-4-5", "name": "Claude Opus 4.5 (latest)", "provider": "anthropic"},
    {"id": "claude-opus-4-5-20251101", "name": "Claude Opus 4.5", "provider": "anthropic"},
    {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "provider": "anthropic"},
    {"id": "claude-opus-4-7", "name": "Claude Opus 4.7", "provider": "anthropic"},
    {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"},
    {"id": "claude-sonnet-4-0", "name": "Claude Sonnet 4 (latest)", "provider": "anthropic"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "provider": "anthropic"},
    {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5 (latest)", "provider": "anthropic"},
    {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5", "provider": "anthropic"},
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic"},
]

# The curated, newest-first result for `_RAW_PI_MODELS`: the claude-3-* family and
# every dated-pin duplicate dropped, leaving the friendly aliases sorted newest
# major.minor first (ties broken by id for determinism).
_CURATED_PI_MODEL_IDS: list[str] = [
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-sonnet-4-0",
]


def _options_from_raw(raw: list[dict[str, Any]]) -> list[ModelOption]:
    options = [_model_option_from_pi(m) for m in raw]
    return [option for option in options if option is not None]


_MULTI_PROVIDER_OPTIONS: list[ModelOption] = [
    ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Claude Opus 4.8"),
    ModelOption(provider="openai", model_id="gpt-5", display_name="GPT-5"),
    ModelOption(provider="google", model_id="gemini-3", display_name="Gemini 3"),
]


def _models_response(raw_models: list[dict[str, Any]]) -> str:
    return _event(
        {
            "type": "response",
            "command": "get_available_models",
            "success": True,
            "id": "cmd-models",
            "data": {"models": raw_models},
        }
    )


def _state_response_with_model(model: dict[str, Any] | None) -> str:
    return _event(
        {
            "type": "response",
            "command": "get_state",
            "success": True,
            "id": "cmd-state",
            "data": {"sessionId": "s", "messageCount": 1, "model": model},
        }
    )


def _set_model_response(model: dict[str, Any]) -> str:
    return _event({"type": "response", "command": "set_model", "success": True, "id": "cmd-setmodel", "data": model})


def _make_probe_env(probe_process: MagicMock) -> MagicMock:
    """A MagicMock environment whose binary + version preflight pass and whose
    `run_process_in_background` returns `probe_process` (the canned probe RPC)."""
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_tool_binary_path.return_value = "/bin/pi"
    version_result = MagicMock()
    version_result.stdout = ""
    version_result.stderr = "pi 0.80.2\n"
    env.run_process_to_completion.return_value = version_result
    env.get_state_path.return_value = Path("/fake/state")
    env.run_process_in_background.return_value = probe_process
    return env


def _turn_metrics(messages: list) -> list[TurnMetricsAgentMessage]:
    return [m for m in messages if isinstance(m, TurnMetricsAgentMessage)]


class TestStreamingAndTurnLifecycle:
    """Text streaming, message finalization, and agent-run turn boundaries."""

    def test_text_delta_accumulates_into_partial_blocks(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("hello ", "hello ")),
                _event(_text_delta_update("world", "hello world")),
                _event({"type": "agent_end", "messages": [_assistant_msg("hello world")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        partials = [m for m in emitted if isinstance(m, PartialResponseBlockAgentMessage)]
        snapshots = [block.text for partial in partials for block in partial.content if isinstance(block, TextBlock)]
        assert snapshots == ["hello ", "hello world"]

    def test_message_end_finalizes_response_block_with_partial_ids(self) -> None:
        """The final ResponseBlock reuses the partial's `assistant_message_id` so the UI collapses them."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("done.", "done.")),
                _event({"type": "message_end", "message": _assistant_msg("done.")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("done.")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        partials = [m for m in emitted if isinstance(m, PartialResponseBlockAgentMessage)]
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert len(finals) == 1
        assert finals[0].role == "assistant"
        assert finals[0].content == (TextBlock(text="done."),)
        # ID coherence: the final must share the partial's IDs so the UI's stable-id
        # collapse can fold partial-then-final into one chat row.
        assert partials, "partials must have been emitted for IDs to match"
        assert finals[0].assistant_message_id == partials[-1].assistant_message_id
        assert finals[0].message_id == partials[-1].first_response_message_id

    def test_user_role_message_end_is_not_echoed_as_assistant_response(self) -> None:
        """pi records the user's own prompt as a role="user" message_end before the assistant streams.

        That user-role message_end must be dropped: only assistant messages carry generated
        text to surface. Otherwise the user's prompt is reflected back as an assistant chat
        bubble at the start of every turn.
        """
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "response", "command": "prompt", "success": True, "id": _PROMPT_ID}),
                _event({"type": "agent_start"}),
                # pi echoes the prompt back as a role="user" message_end here.
                _event({"type": "message_end", "message": _user_msg("who are you?")}),
                _event(_text_delta_update("I am Sculptor.", "I am Sculptor.")),
                _event({"type": "message_end", "message": _assistant_msg("I am Sculptor.")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("I am Sculptor.")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert len(finals) == 1
        assert finals[0].content == (TextBlock(text="I am Sculptor."),)

    def test_agent_end_finalizes_from_accumulator_when_message_end_did_not_fire(self) -> None:
        """If pi closes the run without a message_end (e.g. abort), agent_end emits the accumulated text."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("partial-only", "partial-only")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert len(finals) == 1
        assert finals[0].content == (TextBlock(text="partial-only"),)

    def test_consume_terminates_on_agent_end(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [_event({"type": "agent_end", "messages": [], "willRetry": False})],
        )
        # Must return without hanging.
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_message_end_is_not_a_turn_boundary_when_tool_loop_continues(self) -> None:
        """Multiple message_end events inside one agent run (tool-loop scenario) do not yield the turn."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("thinking", "thinking")),
                _event({"type": "message_end", "message": _assistant_msg("thinking", stop_reason="toolUse")}),
                _event({"type": "tool_execution_start", "toolCallId": "t1", "toolName": "read", "args": {}}),
                _event(
                    {
                        "type": "tool_execution_end",
                        "toolCallId": "t1",
                        "toolName": "read",
                        "result": {},
                        "isError": False,
                    }
                ),
                _event(_text_delta_update("done.", "done.")),
                _event({"type": "message_end", "message": _assistant_msg("done.")}),
                _event(
                    {
                        "type": "agent_end",
                        "messages": [
                            _assistant_msg("thinking", stop_reason="toolUse"),
                            _assistant_msg("done."),
                        ],
                        "willRetry": False,
                    }
                ),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        texts = [block.text for f in finals for block in f.content if isinstance(block, TextBlock)]
        # Both assistant messages with text are emitted at agent_end.
        assert texts == ["thinking", "done."]


class TestResponseEnvelope:
    """Top-level `response` envelope handling (command ACKs)."""

    def test_response_with_success_false_on_prompt_raises_pi_crash_error(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "response",
                        "command": "prompt",
                        "success": False,
                        "id": _PROMPT_ID,
                        "error": "No API key found",
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError) as exc_info:
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        assert "No API key found" in str(exc_info.value)

    def test_response_success_true_does_not_terminate_turn(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "response", "command": "prompt", "success": True, "id": _PROMPT_ID}),
                _event({"type": "agent_start"}),
                _event(_text_delta_update("hi", "hi")),
                _event({"type": "agent_end", "messages": [_assistant_msg("hi")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert len(finals) == 1

    def test_response_for_other_prompt_id_is_ignored(self) -> None:
        """Out-of-band responses (e.g. parse errors with no id) do not raise."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "response", "command": "parse", "success": False, "error": "bad json"}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


class TestTurnFailures:
    """Turn-failure surfaces (in-stream / message_end / agent_end errors)."""

    def test_in_stream_assistant_message_error_raises_pi_crash_error(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("partial ", "partial ")),
                _event(
                    {
                        "type": "message_update",
                        "message": _assistant_msg("partial ", stop_reason=""),
                        "assistantMessageEvent": {"type": "error", "reason": "upstream model failed"},
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError) as exc_info:
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        # Accumulated text is preserved in the surfaced error text.
        assert "partial" in str(exc_info.value) or "upstream" in str(exc_info.value)

    def test_message_end_with_error_stop_reason_raises_pi_crash_error(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "message_end", "message": _assistant_msg("oops", stop_reason="error")}),
            ]
        )
        with pytest.raises(PiCrashError):
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_agent_end_with_aborted_message_raises_pi_crash_error(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "agent_end",
                        "messages": [_assistant_msg("partial", stop_reason="aborted")],
                        "willRetry": False,
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError):
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


class TestTransientRetry:
    """Transient provider-error retry with backoff."""

    def test_transient_overloaded_message_end_is_retried_until_the_turn_recovers(self) -> None:
        """A transient provider error at message_end is re-prompted, not fatal.

        The first agent run ends with stopReason "error" carrying an Anthropic
        `overloaded_error` (~HTTP 529). The harness must retry the turn (re-prompt
        pi) instead of raising PiCrashError, and the retry's response finalizes the
        turn normally — so a transient overload no longer tears down the agent.
        """
        agent = _make_agent()
        overloaded = json.dumps({"type": "overloaded_error", "message": "Overloaded"})
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "message_end", "message": _assistant_error_msg(overloaded)}),
                # Retry: pi recovers and completes the turn on the re-prompt.
                _event({"type": "agent_start"}),
                _event(_text_delta_update("recovered", "recovered")),
                _event({"type": "message_end", "message": _assistant_msg("recovered")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("recovered")], "willRetry": False}),
            ]
        )

        agent._run_prompt_turn(ChatInputUserMessage(text="do the thing"))

        emitted = _drain(agent._output_messages)
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        texts = [block.text for f in finals for block in f.content if isinstance(block, TextBlock)]
        # The turn completed after the retry instead of crashing.
        assert "recovered" in texts
        assert not any(isinstance(m, RequestFailureAgentMessage) for m in emitted)
        successes = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
        assert len(successes) == 1
        assert successes[0].interrupted is False

    def test_persistent_transient_error_surfaces_retryable_failure_not_crash(self) -> None:
        """When transient retries are exhausted, the turn fails non-fatally (retryable), not crash.

        Every re-prompt hits the same overloaded_error, so the bounded retry budget is
        exhausted. The turn must surface a RequestFailureAgentMessage (the retryable
        AgentTransientError path the frontend lets the user re-run) rather than tearing
        down the agent with PiCrashError.
        """
        agent = _make_agent()
        overloaded = json.dumps({"type": "overloaded_error", "message": "Overloaded"})
        # Each attempt consumes agent_start + an errored message_end. With the retry
        # budget patched to 2, the runner makes 3 attempts (initial + 2 retries).
        error_round = [
            _event({"type": "agent_start"}),
            _event({"type": "message_end", "message": _assistant_error_msg(overloaded)}),
        ]
        agent._process = _make_process(error_round * 3)

        with (
            patch("sculptor.agents.pi_agent.agent_wrapper._PI_TRANSIENT_MAX_RETRIES", 2),
            patch.object(agent, "_transient_retry_delay_seconds", return_value=0.0),
        ):
            # Must NOT raise: the exhausted-retry path reports a failed request and the agent keeps running.
            agent._run_prompt_turn(ChatInputUserMessage(text="do the thing"))

        emitted = _drain(agent._output_messages)
        failures = [m for m in emitted if isinstance(m, RequestFailureAgentMessage)]
        assert len(failures) == 1
        # The failure carries pi's transient reason so the frontend can surface it.
        assert "overloaded" in str(failures[0].error.args[0]).lower()
        assert not any(isinstance(m, RequestSuccessAgentMessage) for m in emitted)
        # The agent did not crash: no fatal exception was captured.
        assert agent._exception is None

    def test_interrupt_during_transient_backoff_stops_retrying(self) -> None:
        """A Stop landing during the backoff bails to a retryable failure, with no re-prompt.

        The first run hits a transient overloaded_error; while the harness is backing
        off, the user interrupts (`_interrupt_pending` is set, simulated here as the
        backoff's side effect). The loop must give up immediately with a
        RequestFailure rather than re-prompting and spinning.
        """
        agent = _make_agent()
        overloaded = json.dumps({"type": "overloaded_error", "message": "Overloaded"})
        # Only one error round is queued: a re-prompt would find an empty/finished
        # queue, so the assertions below also confirm the loop did not loop again.
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "message_end", "message": _assistant_error_msg(overloaded)}),
            ]
        )

        def _interrupt_during_backoff(attempt: int) -> None:
            agent._interrupt_pending.set()

        with patch.object(agent, "_sleep_before_transient_retry", side_effect=_interrupt_during_backoff):
            agent._run_prompt_turn(ChatInputUserMessage(text="do the thing"))

        emitted = _drain(agent._output_messages)
        failures = [m for m in emitted if isinstance(m, RequestFailureAgentMessage)]
        assert len(failures) == 1
        assert "overloaded" in str(failures[0].error.args[0]).lower()
        assert not any(isinstance(m, RequestSuccessAgentMessage) for m in emitted)

    def test_sleep_before_transient_retry_returns_immediately_when_interrupt_pending(self) -> None:
        """The backoff is woken by a pending interrupt instead of waiting out the delay."""
        agent = _make_agent()
        agent._interrupt_pending.set()
        with patch.object(agent, "_transient_retry_delay_seconds", return_value=100.0):
            started = time.monotonic()
            agent._sleep_before_transient_retry(attempt=1)
            elapsed = time.monotonic() - started
        assert elapsed < 1.0

    @pytest.mark.parametrize("attempt", [1, 2, 3, 4, 8])
    def test_transient_retry_delay_stays_within_equal_jitter_bounds(self, attempt: int) -> None:
        """Backoff grows as base*2**(attempt-1), capped, with delay in [cap/2, cap]."""
        agent = _make_agent()
        cap = min(
            _PI_TRANSIENT_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
            _PI_TRANSIENT_RETRY_MAX_DELAY_SECONDS,
        )
        # Sample repeatedly so the jitter range is exercised, not a single draw.
        for _ in range(20):
            delay = agent._transient_retry_delay_seconds(attempt)
            assert cap / 2 <= delay <= cap


class TestInterruptAndAbort:
    """Interrupts, abort boundaries, and escalation."""

    def test_push_message_interrupt_is_handled_and_sends_abort(self) -> None:
        """InterruptProcessUserMessage is handled (returns True), writes `abort` to stdin,
        and resolves its own request so the frontend's /interrupt POST returns."""
        agent = _make_agent()
        process = MagicMock()
        agent._process = process
        interrupt = InterruptProcessUserMessage()
        handled = agent._push_message(interrupt)
        assert handled is True
        # With no turn in flight, the interrupt has nothing to escalate against and
        # emits its own terminal directly, so it disarms the interrupt flags rather
        # than leaving them set to mislabel a later between-turns request — handled
        # via `_handle_user_message`, which reads but does not reset them.
        assert not agent._was_interrupted.is_set()
        assert not agent._interrupt_pending.is_set()
        assert _abort_was_written(process)
        # The interrupt request itself must be completed (request_id == the interrupt
        # message id) — `await_message_response` blocks the /interrupt POST until then,
        # leaving the StatusPill stuck in "stopping".
        emitted = _drain(agent._output_messages)
        completions = [
            m for m in emitted if isinstance(m, RequestSuccessAgentMessage) and m.request_id == interrupt.message_id
        ]
        assert len(completions) == 1
        # This control action is not itself an interrupted generation turn.
        assert completions[0].interrupted is False

    def test_interrupt_mid_turn_resolves_interrupted_and_finalizes_partial(self) -> None:
        """Interrupt during a turn: abort is written, the aborted boundary finalizes
        the partial text without raising, and the turn resolves interrupted=True."""
        agent = _make_agent()
        out_queue: Queue[tuple[str, bool]] = Queue()
        out_queue.put((_event({"type": "agent_start"}), True))
        out_queue.put((_event(_text_delta_update("partial", "partial")), True))
        process = MagicMock()
        process.get_queue.return_value = out_queue
        process.is_finished.return_value = False
        agent._process = process

        # Drive the turn on a worker thread and interrupt from this (request-handling)
        # thread once the partial has streamed — the real two-thread interrupt path.
        worker = threading.Thread(target=agent._run_prompt_turn, args=(ChatInputUserMessage(text="long task"),))
        worker.start()
        try:
            _wait_until(lambda: agent._output_messages.qsize() >= 2)
            agent._request_interrupt()
            # pi's abort-induced boundary: an assistant message with stopReason aborted.
            out_queue.put(
                (
                    _event(
                        {
                            "type": "agent_end",
                            "messages": [_assistant_msg("partial", stop_reason="aborted")],
                            "willRetry": False,
                        }
                    ),
                    True,
                )
            )
            worker.join(timeout=5.0)
        finally:
            if worker.is_alive():
                agent._shutdown_event.set()
                worker.join(timeout=5.0)
        assert not worker.is_alive(), "interrupted turn did not resolve"

        assert _abort_was_written(process)
        emitted = _drain(agent._output_messages)
        successes = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
        assert len(successes) == 1
        assert successes[0].interrupted is True
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert len(finals) == 1
        assert finals[0].content == (TextBlock(text="partial"),)

    def test_interrupt_with_no_turn_in_flight_does_not_poison_next_turn(self) -> None:
        """A stale interrupt (no turn in flight) must not mark the NEXT turn interrupted."""
        agent = _make_agent()
        # An interrupt that raced in with no turn in flight leaves both flags set.
        agent._was_interrupted.set()
        agent._interrupt_pending.set()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("hello", "hello")),
                _event({"type": "agent_end", "messages": [_assistant_msg("hello")], "willRetry": False}),
            ]
        )
        agent._run_prompt_turn(ChatInputUserMessage(text="fresh turn"))
        emitted = _drain(agent._output_messages)
        successes = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
        assert len(successes) == 1
        assert successes[0].interrupted is False

    def test_interrupt_with_no_turn_in_flight_resolves_stuck_request(self) -> None:
        """SCU-1560: Stop on an idle-but-RUNNING agent must resolve the orphaned turn.

        When a turn's RequestStarted was emitted but no terminal RequestSuccess ever
        followed (e.g. the prior process died mid-turn), the task stays RUNNING with
        no turn actively draining pi's stdout. Pressing Stop must NOT be a silent
        no-op: it must emit RequestSuccess(interrupted=True) for the in-flight
        request so the task settles to READY, instead of the status pill bouncing
        "Stopping" -> "Thinking" with nothing changed.

        Mirrors Claude's interrupt_current_message no-op branch
        (process_manager.py:_resolve_in_flight_request_as_interrupted).
        """
        agent = _make_agent()
        agent._process = MagicMock()
        # A turn is in flight from the frontend's point of view (RequestStarted with
        # no terminal completion) but no turn is actively draining pi's stdout.
        in_flight_id = AgentMessageID()
        agent._in_flight_request_id = in_flight_id
        assert not agent._turn_in_flight.is_set()

        handled = agent._push_message(InterruptProcessUserMessage())

        assert handled is True
        emitted = _drain(agent._output_messages)
        # The orphaned chat request is resolved, so derived state moves RUNNING -> READY.
        resolved = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage) and m.request_id == in_flight_id]
        assert len(resolved) == 1
        assert resolved[0].interrupted is True

    def test_idle_interrupt_does_not_poison_next_clear_context(self) -> None:
        """An interrupt with no turn in flight must not leave interrupt state set.

        A chat turn resets interrupt state at its start, but the between-turns
        control paths (/clear, set_model) do not — they only read it via
        `_handle_user_message`. So a lingering `_was_interrupted` from an idle
        interrupt would wrongly mark the next /clear's RequestSuccess as interrupted.
        """
        env = _clear_env()
        agent = _make_agent(env)
        agent._session_id = "old-session"
        agent._in_flight_request_id = AgentMessageID()
        process = _make_process(
            [
                _event(
                    {
                        "type": "response",
                        "command": "new_session",
                        "success": True,
                        "id": "cmd-new",
                        "data": {"cancelled": False},
                    }
                ),
                _event(
                    {
                        "type": "response",
                        "command": "get_state",
                        "success": True,
                        "id": "cmd-state",
                        "data": {"sessionId": "new-session", "messageCount": 0},
                    }
                ),
            ]
        )
        agent._process = process

        # Idle interrupt (no turn in flight): reconciles the orphaned request.
        agent._request_interrupt()

        clear = ClearContextUserMessage(message_id=AgentMessageID())
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-new", "cmd-state"]):
            agent._handle_clear_context(clear)

        emitted = _drain(agent._output_messages)
        clear_successes = [
            m for m in emitted if isinstance(m, RequestSuccessAgentMessage) and m.request_id == clear.message_id
        ]
        assert len(clear_successes) == 1
        assert clear_successes[0].interrupted is False

    def test_aborted_agent_end_with_interrupt_pending_finalizes_without_crash(self) -> None:
        """`stopReason:"aborted"` on agent_end is the expected boundary when interrupt-pending — finalize, don't raise."""
        agent = _make_agent()
        agent._interrupt_pending.set()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("partial", "partial")),
                _event(
                    {
                        "type": "agent_end",
                        "messages": [_assistant_msg("partial", stop_reason="aborted")],
                        "willRetry": False,
                    }
                ),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        finals = [m for m in _drain(agent._output_messages) if isinstance(m, ResponseBlockAgentMessage)]
        assert len(finals) == 1
        assert finals[0].content == (TextBlock(text="partial"),)

    def test_aborted_message_end_with_interrupt_pending_finalizes_without_crash(self) -> None:
        """`stopReason:"aborted"` on message_end finalizes the partial when interrupt-pending."""
        agent = _make_agent()
        agent._interrupt_pending.set()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("partial", "partial")),
                _event({"type": "message_end", "message": _assistant_msg("partial", stop_reason="aborted")}),
                _event(
                    {
                        "type": "agent_end",
                        "messages": [_assistant_msg("partial", stop_reason="aborted")],
                        "willRetry": False,
                    }
                ),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        finals = [m for m in _drain(agent._output_messages) if isinstance(m, ResponseBlockAgentMessage)]
        # message_end finalizes the partial and resets the accumulator, so agent_end
        # does not double-emit.
        assert len(finals) == 1
        assert finals[0].content == (TextBlock(text="partial"),)

    def test_aborted_message_end_without_interrupt_pending_raises_pi_crash_error(self) -> None:
        """Without an interrupt pending, `stopReason:"aborted"` is an unexpected failure — it crashes."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "message_end", "message": _assistant_msg("oops", stop_reason="aborted")}),
            ]
        )
        with pytest.raises(PiCrashError):
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_escalate_interrupt_terminates_process_when_pending_and_running(self) -> None:
        agent = _make_agent()
        agent._interrupt_pending.set()
        process = MagicMock()
        process.is_finished.return_value = False
        agent._process = process
        agent._escalate_interrupt()
        process.terminate.assert_called_once()

    def test_escalate_interrupt_is_noop_when_interrupt_already_resolved(self) -> None:
        agent = _make_agent()
        # interrupt-pending cleared → the turn already ended after the abort.
        process = MagicMock()
        process.is_finished.return_value = False
        agent._process = process
        agent._escalate_interrupt()
        process.terminate.assert_not_called()

    def test_escalate_interrupt_is_noop_when_process_already_finished(self) -> None:
        agent = _make_agent()
        agent._interrupt_pending.set()
        process = MagicMock()
        process.is_finished.return_value = True
        agent._process = process
        agent._escalate_interrupt()
        process.terminate.assert_not_called()

    def test_await_interrupt_escalation_cancelled_within_grace_does_not_terminate(self) -> None:
        agent = _make_agent()
        agent._interrupt_pending.set()
        process = MagicMock()
        process.is_finished.return_value = False
        agent._process = process
        cancel = threading.Event()
        cancel.set()  # the turn ended within the grace window
        agent._await_interrupt_escalation(cancel)
        process.terminate.assert_not_called()

    def test_escalation_terminate_lets_turn_resolve_via_process_exit(self) -> None:
        """No agent_end → SIGTERM → the process-exit fallback resolves the turn."""
        agent = _make_agent()
        agent._interrupt_pending.set()
        out_queue: Queue[tuple[str, bool]] = Queue()
        process = MagicMock()
        process.get_queue.return_value = out_queue
        finished = {"value": False}
        process.is_finished.side_effect = lambda: finished["value"]
        process.terminate.side_effect = lambda: finished.__setitem__("value", True)
        agent._process = process

        agent._escalate_interrupt()
        process.terminate.assert_called_once()
        # The dispatcher's `process.is_finished() and queue empty` fallback returns.
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_finalize_pending_answers_marks_interrupted_on_failure(self) -> None:
        agent = _make_agent()
        request_id = AgentMessageID()
        agent._pending_answer_request_ids = [request_id]
        agent._finalize_pending_answers(interrupted=True)
        successes = [m for m in _drain(agent._output_messages) if isinstance(m, RequestSuccessAgentMessage)]
        assert [(m.request_id, m.interrupted) for m in successes] == [(request_id, True)]

    @pytest.mark.parametrize(
        "end_payload",
        [
            {"type": "compaction_end", "reason": "manual", "aborted": True, "willRetry": False},
            {
                "type": "compaction_end",
                "reason": "threshold",
                "aborted": False,
                "willRetry": False,
                "errorMessage": "compaction failed",
            },
        ],
        ids=["aborted", "error_message"],
    )
    def test_compaction_end_aborted_or_errored_still_clears_without_inventing_failure(
        self, end_payload: dict[str, Any]
    ) -> None:
        """aborted / error_message on compaction_end must still clear the pill and must not raise.

        A compaction failure is surfaced only if pi itself ends the run in error
        (the agent_end / message_end paths) — the compaction handler never invents one.
        """
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "compaction_start", "reason": end_payload["reason"]}),
                _event(end_payload),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        # Must not raise.
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        assert len([m for m in emitted if isinstance(m, AutoCompactingDoneAgentMessage)]) == 1
        # No failure invented (a failed compaction is not turn-terminal on its own).
        assert not [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]

    def test_interrupt_does_not_kill_subagent_task(self) -> None:
        """Stopping a turn must NOT kill a running sub-agent task: it is independent of the
        turn that launched it, so it survives the interrupt."""
        agent = _make_agent()
        agent._interrupt_pending.set()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("typing", "typing")),
                _event(
                    {
                        "type": "agent_end",
                        "messages": [_assistant_msg("typing", stop_reason="aborted")],
                        "willRetry": False,
                    }
                ),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        _assert_no_kill(agent)
        assert _SA_TASK_ID in agent._subagent_tasks

    def test_interrupt_does_not_kill_background_task(self) -> None:
        """Stopping a turn must NOT kill a background task: the task is independent of the
        turn that launched it, so it survives the interrupt."""
        agent = _make_agent()
        agent._interrupt_pending.set()
        agent._background_tasks[_BG_TASK_ID] = _BG_PGID
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("typing", "typing")),
                _event(
                    {
                        "type": "agent_end",
                        "messages": [_assistant_msg("typing", stop_reason="aborted")],
                        "willRetry": False,
                    }
                ),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        _assert_no_kill(agent)
        assert _BG_TASK_ID in agent._background_tasks


class TestAutoRetry:
    """pi's auto_retry_end handling."""

    def test_auto_retry_end_failure_raises_pi_crash_error(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "auto_retry_end",
                        "success": False,
                        "attempt": 3,
                        "finalError": "rate limited after 3 attempts",
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError) as exc_info:
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        assert "rate limited" in str(exc_info.value)

    def test_auto_retry_end_success_does_not_yield_turn(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "auto_retry_end", "success": True, "attempt": 2}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


class TestToolRendering:
    """Tool-call rendering and workspace-diff refresh."""

    def test_tool_call_renders_use_block_while_running_and_result_when_done(self) -> None:
        """A read tool call: the issuing message's toolCall block becomes a ToolUseBlock
        (name + input, shown while running) and tool_execution_end becomes its result."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("Reading. ", "Reading. ")),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content(
                            [
                                {"type": "text", "text": "Reading. "},
                                _tool_call_block("t1", "read", {"path": "/repo/a.txt"}),
                            ]
                        ),
                    }
                ),
                _event(_tool_execution_start("t1", "read", {"path": "/repo/a.txt"})),
                _event(
                    {
                        "type": "tool_execution_update",
                        "toolCallId": "t1",
                        "toolName": "read",
                        "args": {"path": "/repo/a.txt"},
                        "partialResult": {"content": [{"type": "text", "text": "file contents"}]},
                    }
                ),
                _event(
                    _tool_execution_end("t1", "read", result={"content": [{"type": "text", "text": "file contents"}]})
                ),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)

        # While running: a ToolUseBlock with the mapped Claude name + adapted input.
        use_blocks = _tool_use_blocks(emitted)
        assert any(b.id == "t1" and b.name == "Read" and b.input == {"file_path": "/repo/a.txt"} for b in use_blocks)
        # When done: a ToolResultBlock correlated by id, non-error, with result text.
        result_blocks = _tool_result_blocks(emitted)
        assert len(result_blocks) == 1
        result = result_blocks[0]
        assert result.tool_use_id == "t1"
        assert result.tool_name == "Read"
        assert result.is_error is False
        assert isinstance(result.content, GenericToolContent)
        assert result.content.text == "file contents"

    @pytest.mark.parametrize(
        "pi_name, pi_args, claude_name, claude_input",
        [
            ("read", {"path": "/r.txt"}, "Read", {"file_path": "/r.txt"}),
            ("write", {"path": "/w.txt", "content": "x"}, "Write", {"file_path": "/w.txt", "content": "x"}),
            ("bash", {"command": "ls"}, "Bash", {"command": "ls"}),
            (
                "edit",
                {"path": "/e.txt", "edits": [{"oldText": "a", "newText": "b"}]},
                "Edit",
                {"file_path": "/e.txt", "old_string": "a", "new_string": "b"},
            ),
        ],
    )
    def test_core_tool_use_block_maps_name_and_input(
        self, pi_name: str, pi_args: dict[str, Any], claude_name: str, claude_input: dict[str, Any]
    ) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content([_tool_call_block("t1", pi_name, pi_args)]),
                    }
                ),
                _event(_tool_execution_end("t1", pi_name, result="ok")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)
        use_blocks = _tool_use_blocks(emitted)
        assert any(b.id == "t1" and b.name == claude_name and b.input == claude_input for b in use_blocks)

    def test_multi_edit_tool_renders_as_multiedit(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content(
                            [
                                _tool_call_block(
                                    "t1",
                                    "edit",
                                    {
                                        "path": "/e.txt",
                                        "edits": [
                                            {"oldText": "a", "newText": "b"},
                                            {"oldText": "c", "newText": "d"},
                                        ],
                                    },
                                )
                            ]
                        ),
                    }
                ),
                _event(_tool_execution_end("t1", "edit", result="ok")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        use_blocks = _tool_use_blocks(_drain(agent._output_messages))
        block = next(b for b in use_blocks if b.id == "t1")
        assert block.name == "MultiEdit"
        assert block.input == {
            "file_path": "/e.txt",
            "edits": [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": "d"}],
        }

    def test_unknown_tool_renders_generically_unmapped(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content(
                            [_tool_call_block("t1", "frobnicate", {"widget": "gadget"})]
                        ),
                    }
                ),
                _event(_tool_execution_end("t1", "frobnicate", result="done")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        use_blocks = _tool_use_blocks(_drain(agent._output_messages))
        block = next(b for b in use_blocks if b.id == "t1")
        # Unknown tools pass through unmapped (rendered generically by the frontend).
        assert block.name == "frobnicate"
        assert block.input == {"widget": "gadget"}

    def test_text_tool_text_interleaving_in_one_message(self) -> None:
        """Final content preserves the order text → tool → text within one assistant message."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content(
                            [
                                {"type": "text", "text": "before"},
                                _tool_call_block("t1", "bash", {"command": "ls"}),
                                {"type": "text", "text": "after"},
                            ]
                        ),
                    }
                ),
                _event(_tool_execution_end("t1", "bash", result="output")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        finals = [m for m in _drain(agent._output_messages) if isinstance(m, ResponseBlockAgentMessage)]
        # The finalized assistant message interleaves text, tool use, text in order.
        interleaved = next(f for f in finals if any(isinstance(b, ToolUseBlock) for b in f.content))
        kinds = [type(b).__name__ for b in interleaved.content]
        assert kinds == ["TextBlock", "ToolUseBlock", "TextBlock"]
        assert _text_block_text(interleaved.content[0]) == "before"
        assert _text_block_text(interleaved.content[2]) == "after"

    def test_error_result_renders_as_error(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content([_tool_call_block("t1", "read", {"path": "/missing"})]),
                    }
                ),
                _event(_tool_execution_end("t1", "read", result="ENOENT: no such file", is_error=True)),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        result_blocks = _tool_result_blocks(_drain(agent._output_messages))
        assert len(result_blocks) == 1
        assert result_blocks[0].is_error is True
        assert _generic_result_text(result_blocks[0]) == "ENOENT: no such file"

    def test_in_message_toolcall_and_lane_start_reconcile_to_one_block(self) -> None:
        """A toolCall content block and the lane's tool_execution_start with the same
        id are the SAME call — the ToolUseBlock is rendered once (from message_end),
        and tool_execution_start does not render a duplicate."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("x", "x")),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg_with_content(
                            [{"type": "text", "text": "x"}, _tool_call_block("t1", "read", {"path": "/a"})]
                        ),
                    }
                ),
                _event(_tool_execution_start("t1", "read", {"path": "/a"})),
                _event(_tool_execution_end("t1", "read", result="ok")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)
        # Exactly one partial introduces the ToolUseBlock for t1 (message_end's); the
        # lane's start for the already-registered id emits no further partial.
        partials_with_t1 = [
            m
            for m in emitted
            if isinstance(m, PartialResponseBlockAgentMessage)
            and any(isinstance(b, ToolUseBlock) and b.id == "t1" for b in m.content)
        ]
        assert len(partials_with_t1) == 1
        # And exactly one result block.
        assert len(_tool_result_blocks(emitted)) == 1

    def test_orphan_lane_tool_renders_from_start_when_no_toolcall_block(self) -> None:
        """A lane event with no matching toolCall block (not expected from real pi)
        still renders — tool_execution_start creates the ToolUseBlock so the call is
        never silently dropped; a read tool fires no diff refresh."""
        on_diff_needed = MagicMock()
        agent = _make_agent(on_diff_needed=on_diff_needed)
        agent._process = _make_process(
            [
                _event(_tool_execution_start("t1", "read", {"path": "/a"})),
                _event(_tool_execution_end("t1", "read", result="contents")),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)
        assert any(b.id == "t1" and b.name == "Read" for b in _tool_use_blocks(emitted))
        result_blocks = _tool_result_blocks(emitted)
        assert len(result_blocks) == 1
        assert _generic_result_text(result_blocks[0]) == "contents"
        on_diff_needed.assert_not_called()

    @pytest.mark.parametrize("tool_name", ["edit", "write", "bash"])
    def test_file_change_tool_execution_end_refreshes_diff(self, tool_name: str) -> None:
        """A successful edit/write/bash tool triggers a single workspace-diff refresh."""
        on_diff_needed = MagicMock()
        agent = _make_agent(on_diff_needed=on_diff_needed)
        agent._process = _make_process(
            [
                _event({"type": "tool_execution_start", "toolCallId": "t1", "toolName": tool_name, "args": {}}),
                _event(
                    {
                        "type": "tool_execution_end",
                        "toolCallId": "t1",
                        "toolName": tool_name,
                        "result": {},
                        "isError": False,
                    }
                ),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        on_diff_needed.assert_called_once()

    def test_errored_file_change_tool_execution_end_does_not_refresh_diff(self) -> None:
        """A failed file-mutating tool (isError) must not refresh the diff."""
        on_diff_needed = MagicMock()
        agent = _make_agent(on_diff_needed=on_diff_needed)
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "tool_execution_end",
                        "toolCallId": "t1",
                        "toolName": "edit",
                        "result": {},
                        "isError": True,
                    }
                ),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        on_diff_needed.assert_not_called()


class TestExtensionUiAndErrors:
    """Backchannel dialog requests and extension errors."""

    def test_extension_ui_select_request_emits_ask_user_question(self) -> None:
        """A backchannel `select` dialog becomes an AskUserQuestion and holds the turn."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "extension_ui_request",
                        "id": "ui-1",
                        "method": "select",
                        "title": "Tea or coffee?",
                        "options": ["tea", "coffee"],
                    }
                ),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        questions = [m for m in emitted if isinstance(m, AskUserQuestionAgentMessage)]
        assert len(questions) == 1
        data = questions[0].question_data
        assert data.tool_use_id == "ui-1"
        assert len(data.questions) == 1
        assert data.questions[0].question == "Tea or coffee?"
        assert [opt.label for opt in data.questions[0].options] == ["tea", "coffee"]

    def test_extension_ui_input_request_emits_free_form_question(self) -> None:
        """An `input` dialog (no options) becomes a free-form AskUserQuestion."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "extension_ui_request", "id": "ui-2", "method": "input", "title": "Your name?"}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        questions = [m for m in _drain(agent._output_messages) if isinstance(m, AskUserQuestionAgentMessage)]
        assert len(questions) == 1
        assert questions[0].question_data.questions[0].question == "Your name?"
        assert questions[0].question_data.questions[0].options == []

    def test_plan_approval_select_request_emits_plan_approval_question(self) -> None:
        """The plan-approval sentinel title maps to the canonical plan-approval question."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "extension_ui_request",
                        "id": "plan-1",
                        "method": "select",
                        "title": PLAN_APPROVAL_DIALOG_TITLE,
                        "options": ["Approve plan"],
                    }
                ),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        questions = [m for m in _drain(agent._output_messages) if isinstance(m, AskUserQuestionAgentMessage)]
        assert len(questions) == 1
        # Same canonical question Claude's ExitPlanMode synthesizes — header drives
        # the frontend's "Waiting for plan approval".
        assert questions[0].question_data.questions[0].header == PLAN_APPROVAL_HEADER

    def test_extension_ui_fire_and_forget_method_is_ignored(self) -> None:
        """Non-dialog methods (notify/setStatus/…) need no response and emit nothing."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "extension_ui_request", "id": "n-1", "method": "notify", "message": "hi"}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        # Only the turn footer's metrics (emitted at agent_end); the notify emits nothing.
        emitted = _drain(agent._output_messages)
        assert all(isinstance(m, TurnMetricsAgentMessage) for m in emitted)

    def test_extension_error_from_foreign_extension_is_logged_and_non_terminal(self) -> None:
        agent = _make_agent()
        # No extension whose path matches _loaded_extension_paths (empty) → foreign.
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "extension_error",
                        "extensionPath": "/some/foreign/ext",
                        "event": "some-callback",
                        "error": "ext threw",
                    }
                ),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        # Must not raise; must reach agent_end.
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_extension_error_from_our_extension_fails_loud(self) -> None:
        """Fail-loud posture: an error from the pinned backchannel extension fails the turn."""
        agent = _make_agent()
        agent._loaded_extension_paths = ("/state/sculptor_backchannel.ts",)
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "extension_error",
                        "extensionPath": "/state/sculptor_backchannel.ts",
                        "event": "tool_execute",
                        "error": "backchannel boom",
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError, match="backchannel boom"):
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_deliver_answer_writes_extension_ui_response_and_starts_request(self) -> None:
        agent = _make_agent()
        process = MagicMock()
        agent._process = process
        agent._pending_ui_request_id = "ui-1"
        answer = _answer({"Tea or coffee?": "coffee"}, "ui-1")
        agent._deliver_question_answer(answer)

        # The answer's own request is started immediately; its success is deferred.
        started = [m for m in _drain(agent._output_messages) if isinstance(m, RequestStartedAgentMessage)]
        assert [m.request_id for m in started] == [answer.message_id]
        assert agent._pending_answer_request_ids == [answer.message_id]
        assert agent._pending_ui_request_id is None
        # The matching extension_ui_response carries the selected value.
        assert _written_payloads(process) == [{"type": "extension_ui_response", "id": "ui-1", "value": "coffee"}]


class TestBackchannelAnswersAndPlanMode:
    """Backchannel answer delivery and plan mode."""

    def test_push_message_handles_question_answer_returns_true(self) -> None:
        """A question answer is handled by the backchannel, not dead-lettered."""
        agent = _make_agent()
        agent._process = MagicMock()
        with expect_exact_logged_errors([]):
            assert agent._push_message(_answer({"q": "a"}, "t1")) is True

    def test_deliver_answer_with_no_pending_dialog_skips(self) -> None:
        agent = _make_agent()
        process = MagicMock()
        agent._process = process
        answer = _answer({"q": "a"}, "stale")
        agent._deliver_question_answer(answer)

        skipped = [m for m in _drain(agent._output_messages) if isinstance(m, RequestSkippedAgentMessage)]
        assert [m.request_id for m in skipped] == [answer.message_id]
        assert process.write_stdin.call_count == 0

    def test_deliver_dismissed_answer_sends_cancellation(self) -> None:
        agent = _make_agent()
        process = MagicMock()
        agent._process = process
        agent._pending_ui_request_id = "ui-9"
        agent._deliver_question_answer(_answer({"Pick one": DISMISSED_ANSWER_VALUE}, "ui-9"))
        assert _written_payloads(process) == [{"type": "extension_ui_response", "id": "ui-9", "cancelled": True}]

    def test_deliver_plan_approval_clears_plan_mode(self) -> None:
        agent = _make_agent()
        process = MagicMock()
        agent._process = process
        agent._is_in_plan_mode = True
        agent._pending_ui_request_id = "plan-1"
        question_data = make_plan_approval_question(tool_use_id="plan-1")
        answer = _answer({question_data.questions[0].question: "Approve plan"}, "plan-1", question_data=question_data)
        agent._deliver_question_answer(answer)

        emitted = _drain(agent._output_messages)
        plan_msgs = [m for m in emitted if isinstance(m, PlanModeAgentMessage)]
        assert len(plan_msgs) == 1 and plan_msgs[0].is_in_plan_mode is False
        assert agent._is_in_plan_mode is False
        assert _written_payloads(process) == [
            {"type": "extension_ui_response", "id": "plan-1", "value": "Approve plan"}
        ]

    def test_deliver_plan_revision_keeps_plan_mode(self) -> None:
        """A revision (free-form, not the approve label) does not exit plan mode."""
        agent = _make_agent()
        process = MagicMock()
        agent._process = process
        agent._is_in_plan_mode = True
        agent._pending_ui_request_id = "plan-2"
        question_data = make_plan_approval_question(tool_use_id="plan-2")
        answer = _answer(
            {question_data.questions[0].question: "Please add a rollback step"}, "plan-2", question_data=question_data
        )
        agent._deliver_question_answer(answer)

        emitted = _drain(agent._output_messages)
        assert not [m for m in emitted if isinstance(m, PlanModeAgentMessage)]
        assert agent._is_in_plan_mode is True
        assert _written_payloads(process) == [
            {"type": "extension_ui_response", "id": "plan-2", "value": "Please add a rollback step"}
        ]

    def test_finalize_pending_answers_emits_deferred_success(self) -> None:
        agent = _make_agent()
        request_id = AgentMessageID()
        agent._pending_answer_request_ids = [request_id]
        agent._finalize_pending_answers(interrupted=False)

        successes = [m for m in _drain(agent._output_messages) if isinstance(m, RequestSuccessAgentMessage)]
        assert [(m.request_id, m.interrupted) for m in successes] == [(request_id, False)]
        assert agent._pending_answer_request_ids == []

    def test_plan_mode_tracking_and_prompt_preamble(self) -> None:
        agent = _make_agent()
        # Entering plan mode prepends the preamble to the prompt text.
        enter = ChatInputUserMessage(text="add a feature", enter_plan_mode=True)
        agent._update_plan_mode_from_message(enter)
        assert agent._is_in_plan_mode is True
        prompt = agent._build_prompt_text(enter)
        assert prompt.endswith("add a feature")
        assert "PLAN MODE" in prompt and "exit_plan_mode" in prompt

        # Leaving plan mode drops the preamble.
        leave = ChatInputUserMessage(text="never mind", exit_plan_mode=True)
        agent._update_plan_mode_from_message(leave)
        assert agent._is_in_plan_mode is False
        assert agent._build_prompt_text(leave) == "never mind"


class TestRpcPlumbing:
    """Low-level RPC read/write plumbing."""

    def test_consume_ignores_non_json_and_unknown_event_types(self) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                "not json at all",
                _event({"type": "queue_update", "steering": [], "followUp": []}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    def test_send_rpc_writes_json_line_to_stdin(self) -> None:
        agent = _make_agent()
        fake_process = MagicMock()
        agent._process = fake_process
        agent._send_rpc({"type": "prompt", "id": "p1", "message": "hi"})
        fake_process.write_stdin.assert_called_once()
        written = fake_process.write_stdin.call_args.args[0]
        assert json.loads(written.rstrip("\n")) == {"type": "prompt", "id": "p1", "message": "hi"}


class TestPushMessageDispatch:
    """`_push_message` control-message dispatch."""

    def test_push_message_enqueues_chat_input_returns_true(self) -> None:
        agent = _make_agent()
        chat = ChatInputUserMessage(text="hi")
        assert agent._push_message(chat) is True
        assert agent._input_agent_messages.get_nowait() is chat

    def test_push_message_dead_letters_unhandled_control_messages(self) -> None:
        """A control message pi has no handler for — and that the base class won't
        handle either — is dead-lettered: logged loudly and returned unhandled. This
        is the inverse of an allowlist of unsupported types (impossible: you cannot
        enumerate what you do not yet know about); pi recognizes what it handles and
        rejects the rest. EphemeralUserMessage stands in for a future unsupported
        control surface that reaches the end of `_push_message`."""
        agent = _make_agent()
        with expect_exact_logged_errors(["PiAgent dropping unhandled control message"]):
            handled = agent._push_message(EphemeralUserMessage(object_type="UnsupportedForTest"))
        assert handled is False

    def test_push_message_does_not_dead_letter_base_class_handled_types(self) -> None:
        """StopAgent and RemoveQueued are handled by the base class after the False
        return (see DefaultAgentWrapper.push_message), so they must NOT be
        dead-lettered here."""
        agent = _make_agent()
        with expect_exact_logged_errors([]):
            assert agent._push_message(StopAgentUserMessage()) is False
            assert agent._push_message(RemoveQueuedMessageUserMessage(target_message_id=AgentMessageID())) is False

    def test_push_message_resume_resolves_in_flight_request(self) -> None:
        """A resume message resolves the orphaned in-flight request so the UI unsticks.

        The previous process died mid-turn leaving the original chat message with a
        RequestStarted but no terminal RequestSuccess. PiAgent handles the resume by
        emitting RequestSuccess for that ORIGINAL message id (for_user_message_id),
        marked interrupted — no dead-letter error, returns handled.
        """
        agent = _make_agent()
        stuck_id = AgentMessageID()
        with expect_exact_logged_errors([]):
            handled = agent._push_message(ResumeAgentResponseRunnerMessage(for_user_message_id=stuck_id))
        assert handled is True
        emitted = agent._output_messages.get_nowait()
        assert isinstance(emitted, RequestSuccessAgentMessage)
        assert emitted.request_id == stuck_id
        assert emitted.interrupted is True

    def test_push_message_enqueues_clear_context_returns_true(self) -> None:
        """A ClearContextUserMessage goes on the same FIFO as chat turns — handled, not dead-lettered."""
        agent = _make_agent()
        clear = ClearContextUserMessage(message_id=AgentMessageID())
        with expect_exact_logged_errors([]):
            handled = agent._push_message(clear)
        assert handled is True
        assert agent._input_agent_messages.get_nowait() is clear

    def test_push_message_enqueues_set_model_returns_true(self) -> None:
        """A SetModelUserMessage goes on the same FIFO as chat turns — handled, not dead-lettered."""
        agent = _make_agent()
        set_model = SetModelUserMessage(message_id=AgentMessageID(), provider="anthropic", model_id="claude-haiku-4-5")
        with expect_exact_logged_errors([]):
            handled = agent._push_message(set_model)
        assert handled is True
        assert agent._input_agent_messages.get_nowait() is set_model

    def test_push_message_enqueues_refresh_models_returns_true(self) -> None:
        """A RefreshModelsUserMessage goes on the same FIFO as chat turns — handled, not dead-lettered."""
        agent = _make_agent()
        refresh = RefreshModelsUserMessage(message_id=AgentMessageID())
        with expect_exact_logged_errors([]):
            handled = agent._push_message(refresh)
        assert handled is True
        assert agent._input_agent_messages.get_nowait() is refresh


class TestClearContext:
    """Context reset (/clear → new_session)."""

    def test_clear_context_sends_new_session_persists_id_and_emits_cleared(self) -> None:
        """A successful /clear sends new_session, persists the post-clear session id, emits ContextCleared + RequestSuccess."""
        env = _clear_env()
        agent = _make_agent(env)
        agent._session_id = "old-session"
        process = _make_process(
            [
                _event(
                    {
                        "type": "response",
                        "command": "new_session",
                        "success": True,
                        "id": "cmd-new",
                        "data": {"cancelled": False},
                    }
                ),
                _event(
                    {
                        "type": "response",
                        "command": "get_state",
                        "success": True,
                        "id": "cmd-state",
                        "data": {"sessionId": "new-session", "messageCount": 0},
                    }
                ),
            ]
        )
        agent._process = process
        # generate_id is called for the new_session command id, then the get_state request id.
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-new", "cmd-state"]):
            agent._handle_clear_context(ClearContextUserMessage(message_id=AgentMessageID()))

        # new_session was written to pi's stdin, id-correlated.
        writes = [call.args[0] for call in process.write_stdin.call_args_list]
        assert any('"type":"new_session"' in w and '"cmd-new"' in w for w in writes)
        # The post-clear session id replaced the persisted one so a later resume targets it.
        assert agent._session_id == "new-session"
        env.write_file.assert_called_once_with(str(Path("/fake/state") / PI_SESSION_ID_STATE_FILE), "new-session")
        # Emitted: ContextCleared (UX parity) + terminal RequestSuccess, no failure.
        emitted = _drain(agent._output_messages)
        assert any(isinstance(m, ContextClearedMessage) for m in emitted)
        assert any(isinstance(m, RequestSuccessAgentMessage) for m in emitted)
        assert not any(isinstance(m, RequestFailureAgentMessage) for m in emitted)

    def test_clear_context_failure_on_success_false_reports_without_crashing(self) -> None:
        """new_session success:false → RequestFailure, no ContextCleared, no id rewrite, handler does not raise."""
        env = _clear_env()
        agent = _make_agent(env)
        agent._process = _make_process(
            [
                _event(
                    {"type": "response", "command": "new_session", "success": False, "id": "cmd-new", "error": "boom"}
                )
            ]
        )
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-new"]):
            # Must NOT raise out of the handler — the AgentClientError path reports and continues.
            agent._handle_clear_context(ClearContextUserMessage(message_id=AgentMessageID()))
        emitted = _drain(agent._output_messages)
        assert any(isinstance(m, RequestFailureAgentMessage) for m in emitted)
        assert not any(isinstance(m, ContextClearedMessage) for m in emitted)
        env.write_file.assert_not_called()

    def test_clear_context_failure_on_cancelled_veto(self) -> None:
        """new_session success:true but data.cancelled:true (an extension veto) → failed reset."""
        env = _clear_env()
        agent = _make_agent(env)
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "response",
                        "command": "new_session",
                        "success": True,
                        "id": "cmd-new",
                        "data": {"cancelled": True},
                    }
                )
            ]
        )
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-new"]):
            agent._handle_clear_context(ClearContextUserMessage(message_id=AgentMessageID()))
        emitted = _drain(agent._output_messages)
        assert any(isinstance(m, RequestFailureAgentMessage) for m in emitted)
        assert not any(isinstance(m, ContextClearedMessage) for m in emitted)
        env.write_file.assert_not_called()

    def test_clear_context_failure_on_no_response(self) -> None:
        """No new_session ack (process exited / timeout) → failed reset, no crash."""
        env = _clear_env()
        agent = _make_agent(env)
        # Empty queue + is_finished True ⇒ _consume_until_command_response returns None at once.
        agent._process = _make_process([])
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-new"]):
            agent._handle_clear_context(ClearContextUserMessage(message_id=AgentMessageID()))
        emitted = _drain(agent._output_messages)
        assert any(isinstance(m, RequestFailureAgentMessage) for m in emitted)
        assert not any(isinstance(m, ContextClearedMessage) for m in emitted)
        env.write_file.assert_not_called()

    def test_clear_context_runs_after_an_in_flight_chat_turn(self) -> None:
        """FIFO ordering: a /clear queued behind a chat turn runs after the turn ends.

        Both go through `_input_agent_messages`, and `_process_message_queue` handles
        one at a time, so the turn's `_consume_until_turn_end` completes before the
        clear's `_handle_clear_context` is dispatched.
        """
        agent = _make_agent()
        agent._process = MagicMock()
        order: list[str] = []
        with (
            patch.object(agent, "_consume_until_turn_end", side_effect=lambda prompt_id="": order.append("turn")),
            patch.object(agent, "_handle_clear_context", side_effect=lambda message: order.append("clear")),
        ):
            agent._input_agent_messages.put(ChatInputUserMessage(text="hi"))
            agent._input_agent_messages.put(ClearContextUserMessage(message_id=AgentMessageID()))
            worker = threading.Thread(target=agent._process_message_queue)
            worker.start()
            deadline = time.monotonic() + 5.0
            while len(order) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            agent._shutdown_event.set()
            worker.join(timeout=5.0)
        assert order == ["turn", "clear"]


class TestSetModel:
    """Model switching (set_model)."""

    def test_set_model_success_emits_new_current_model_and_resolves(self) -> None:
        """A successful set_model sends the RPC, re-emits the catalog with the new current model, and RequestSuccess."""
        agent = _make_agent()
        agent._available_models = (
            ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Claude Opus 4.8"),
            ModelOption(provider="anthropic", model_id="claude-haiku-4-5", display_name="Claude Haiku 4.5"),
        )
        process = _make_process(
            [
                _event(
                    {
                        "type": "response",
                        "command": "set_model",
                        "success": True,
                        "id": "cmd-set",
                        "data": {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "provider": "anthropic"},
                    }
                )
            ]
        )
        agent._process = process
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-set"]):
            agent._handle_set_model(
                SetModelUserMessage(message_id=AgentMessageID(), provider="anthropic", model_id="claude-haiku-4-5")
            )

        # set_model was written to pi's stdin, id-correlated, carrying provider + modelId.
        writes = [call.args[0] for call in process.write_stdin.call_args_list]
        assert any('"type":"set_model"' in w and '"cmd-set"' in w and '"claude-haiku-4-5"' in w for w in writes)

        emitted = _drain(agent._output_messages)
        carriers = [m for m in emitted if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(carriers) == 1
        carrier = carriers[0]
        # The catalog is unchanged; only the current model follows the switch.
        assert [option.model_id for option in carrier.available_models] == ["claude-opus-4-8", "claude-haiku-4-5"]
        assert carrier.current_model is not None
        assert carrier.current_model.model_id == "claude-haiku-4-5"
        # Terminal RequestSuccess, no failure.
        assert any(isinstance(m, RequestSuccessAgentMessage) for m in emitted)
        assert not any(isinstance(m, RequestFailureAgentMessage) for m in emitted)

    def test_set_model_failure_on_success_false_surfaces_error_and_rolls_back(self) -> None:
        """set_model success:false → RequestFailure AND a corrective carrier restoring the
        switcher to pi's actual current model, without the handler raising out.

        The set-model endpoint writes the requested model onto task state before the
        switch is confirmed (so the switcher responds immediately), so a rejected
        switch must roll the switcher back to the model pi is really on rather than
        leave it stranded on the model that did not take."""
        agent = _make_agent()
        agent._available_models = (
            ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Opus"),
            ModelOption(provider="anthropic", model_id="claude-haiku-4-5", display_name="Haiku"),
        )
        actual = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        agent._process = _make_process(
            [
                _event(
                    {
                        "type": "response",
                        "command": "set_model",
                        "success": False,
                        "id": "cmd-set",
                        "error": "Model not found: anthropic/claude-nope",
                    }
                ),
                _state_response_with_model(actual),
            ]
        )
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-set", "cmd-state"]):
            # Must NOT raise out of the handler — the AgentClientError path reports and continues.
            agent._handle_set_model(
                SetModelUserMessage(message_id=AgentMessageID(), provider="anthropic", model_id="claude-nope")
            )
        emitted = _drain(agent._output_messages)
        failures = [m for m in emitted if isinstance(m, RequestFailureAgentMessage)]
        assert len(failures) == 1
        # The failure carries pi's error so the frontend can toast it.
        assert "Model not found" in str(failures[0].error.args[0])
        # The switcher is rolled back to pi's real current model, undoing the optimistic write.
        carriers = [m for m in emitted if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(carriers) == 1
        assert carriers[0].current_model is not None
        assert carriers[0].current_model.model_id == "claude-opus-4-8"

    def test_set_model_failure_on_no_response_surfaces_error(self) -> None:
        """No set_model ack (process exited / timeout) → failed request, no carrier, no crash."""
        agent = _make_agent()
        # Empty queue + is_finished True ⇒ _consume_until_command_response returns None at once.
        agent._process = _make_process([])
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-set"]):
            agent._handle_set_model(
                SetModelUserMessage(message_id=AgentMessageID(), provider="anthropic", model_id="claude-haiku-4-5")
            )
        emitted = _drain(agent._output_messages)
        assert any(isinstance(m, RequestFailureAgentMessage) for m in emitted)
        assert not any(isinstance(m, ModelsAvailableAgentMessage) for m in emitted)

    def test_set_model_runs_after_an_in_flight_chat_turn(self) -> None:
        """FIFO ordering: a set_model queued behind a chat turn runs after the turn ends.

        Same one-at-a-time guarantee as the context reset, so the set_model RPC's
        response is consumed only between turns.
        """
        agent = _make_agent()
        agent._process = MagicMock()
        order: list[str] = []
        with (
            patch.object(agent, "_consume_until_turn_end", side_effect=lambda prompt_id="": order.append("turn")),
            patch.object(agent, "_handle_set_model", side_effect=lambda message: order.append("set_model")),
        ):
            agent._input_agent_messages.put(ChatInputUserMessage(text="hi"))
            agent._input_agent_messages.put(
                SetModelUserMessage(message_id=AgentMessageID(), provider="anthropic", model_id="claude-haiku-4-5")
            )
            worker = threading.Thread(target=agent._process_message_queue)
            worker.start()
            deadline = time.monotonic() + 5.0
            while len(order) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            agent._shutdown_event.set()
            worker.join(timeout=5.0)
        assert order == ["turn", "set_model"]


class TestStartAndSessionResume:
    """Process start, session resume verification, and version probe."""

    def test_start_fresh_session_mints_and_persists_id_with_session_flags(self) -> None:
        env = _make_start_env(persisted_session_id=None)
        agent = _make_agent(env)
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", return_value="sess-fresh-1"):
            agent.start(secrets={})
        command = _launched_command(env)
        # The old ephemeral flag is gone; a per-task session dir + Sculptor-pinned id ship instead.
        assert "--no-session" not in command
        assert "--session-dir" in command
        assert command[command.index("--session-dir") + 1] == str(Path("/fake/state") / PI_SESSION_DIR_NAME)
        assert "--session-id" in command
        assert command[command.index("--session-id") + 1] == "sess-fresh-1"
        # The pinned backchannel extension also ships: discovery off, our `-e` set on.
        assert "--no-extensions" in command
        assert "-e" in command
        # The minted id is persisted up front so a crash during the first turn still leaves a
        # resumable id (write_file is also called once to materialize the extension into the env).
        session_id_path = str(Path("/fake/state") / PI_SESSION_ID_STATE_FILE)
        assert any(c.args == (session_id_path, "sess-fresh-1") for c in env.write_file.call_args_list)

    def test_start_resume_reuses_persisted_id_and_verifies_without_rewriting(self) -> None:
        env = _make_start_env(persisted_session_id="resume-7")
        agent = _make_agent(env)
        with patch.object(agent, "_verify_resumed_session") as mock_verify:
            agent.start(secrets={})
        command = _launched_command(env)
        assert command[command.index("--session-id") + 1] == "resume-7"
        # Resume must NOT re-persist the session id (it is unchanged) and MUST verify the
        # resume. write_file may still be called to materialize the pinned extension into
        # the env — only the session-id path must be untouched.
        session_id_path = str(Path("/fake/state") / PI_SESSION_ID_STATE_FILE)
        assert all(c.args[0] != session_id_path for c in env.write_file.call_args_list)
        mock_verify.assert_called_once_with("resume-7")

    def test_verify_resumed_session_logs_loud_on_empty_session(self) -> None:
        """An empty session on a resume launch means the on-disk file was lost — log loud."""
        agent = _make_agent()
        with patch.object(agent, "_request_state_blocking", return_value={"sessionId": "abc", "messageCount": 0}):
            with expect_exact_logged_errors(["PiAgent expected to resume pi session"]):
                agent._verify_resumed_session("abc")

    def test_verify_resumed_session_logs_loud_on_session_id_mismatch(self) -> None:
        agent = _make_agent()
        with patch.object(agent, "_request_state_blocking", return_value={"sessionId": "other", "messageCount": 3}):
            with expect_exact_logged_errors(["PiAgent resume mismatch"]):
                agent._verify_resumed_session("abc")

    def test_verify_resumed_session_logs_loud_when_no_state_response(self) -> None:
        agent = _make_agent()
        with patch.object(agent, "_request_state_blocking", return_value=None):
            with expect_exact_logged_errors(["PiAgent could not verify resumed pi session"]):
                agent._verify_resumed_session("abc")

    def test_verify_resumed_session_ok_logs_no_error(self) -> None:
        agent = _make_agent()
        with patch.object(agent, "_request_state_blocking", return_value={"sessionId": "abc", "messageCount": 4}):
            with expect_exact_logged_errors([]):
                agent._verify_resumed_session("abc")

    def test_request_state_blocking_returns_session_state_from_matching_response(self) -> None:
        agent = _make_agent()
        response = _event(
            {
                "type": "response",
                "command": "get_state",
                "success": True,
                "id": "rs-req",
                "data": {"sessionId": "abc", "messageCount": 3},
            }
        )
        agent._process = _make_process([response])
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", return_value="rs-req"):
            state = agent._request_state_blocking(timeout=2.0)
        assert state == {"sessionId": "abc", "messageCount": 3}

    def test_start_raises_pi_binary_not_found_when_path_unresolved(self) -> None:
        env = MagicMock(spec=AgentExecutionEnvironment)
        env.get_tool_binary_path.return_value = None
        agent = _make_agent(env)
        with pytest.raises(PiBinaryNotFoundError):
            agent.start(secrets={})

    def test_start_raises_pi_version_mismatch_when_out_of_range(self) -> None:
        env = MagicMock(spec=AgentExecutionEnvironment)
        env.get_tool_binary_path.return_value = "/bin/pi"
        version_result = MagicMock()
        # Real pi emits --version to stderr (not stdout), so route it there.
        version_result.stdout = ""
        version_result.stderr = "pi 0.50.0\n"
        env.run_process_to_completion.return_value = version_result
        agent = _make_agent(env)
        with pytest.raises(PiVersionMismatchError) as exc_info:
            agent.start(secrets={})
        assert exc_info.value.pinned_version == "0.80.2"
        assert exc_info.value.detected_version == "0.50.0"
        # The message must point the user at the self-healing fix (managed install).
        assert "Managed" in str(exc_info.value)

    def test_check_pi_version_reads_version_from_stderr_only_emission(self) -> None:
        """Real pi emits --version to stderr; the version probe must read both channels."""
        env = MagicMock(spec=AgentExecutionEnvironment)
        version_result = MagicMock()
        version_result.stdout = ""
        version_result.stderr = "0.78.0\n"
        env.run_process_to_completion.return_value = version_result
        agent = _make_agent(env)

        detected = agent._check_pi_version("/bin/pi")

        assert detected == "0.78.0"


class TestPromptAssembly:
    """Prompt payload assembly (files + images)."""

    def test_build_prompt_payload_text_only_has_no_images(self, tmp_path: Path) -> None:
        agent, _env, _dir = _make_agent_with_attachments_env(tmp_path)
        payload = agent._build_prompt_payload("p1", ChatInputUserMessage(text="hello"))
        assert payload == {"type": "prompt", "id": "p1", "message": "hello"}
        assert "images" not in payload

    def test_build_prompt_payload_image_rides_images_field(self, tmp_path: Path) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\nblue-pixels"
        source = tmp_path / "blue.png"
        source.write_bytes(image_bytes)
        agent, env, attachments_dir = _make_agent_with_attachments_env(tmp_path, image_bytes=image_bytes)

        payload = agent._build_prompt_payload("p1", ChatInputUserMessage(text="what color?", files=[str(source)]))

        # The prompt text is unchanged — the image does not appear as a path too.
        assert payload["message"] == "what color?"
        assert payload["images"] == [
            {"type": "image", "data": base64.b64encode(image_bytes).decode("ascii"), "mimeType": "image/png"}
        ]
        # Bytes are read back from the saved environment copy, not the upload dir.
        env.read_file.assert_called_once_with(str(attachments_dir / "blue.png"), mode="rb")

    def test_build_prompt_payload_non_image_rides_prompt_text(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.txt"
        source.write_bytes(b"sentinel-XYZ")
        agent, _env, attachments_dir = _make_agent_with_attachments_env(tmp_path)

        payload = agent._build_prompt_payload("p1", ChatInputUserMessage(text="read it", files=[str(source)]))

        assert "images" not in payload
        assert str(attachments_dir / "notes.txt") in payload["message"]
        assert "The user has attached these files" in payload["message"]
        assert payload["message"].endswith("read it")

    def test_build_prompt_payload_image_and_path_split_exclusively(self, tmp_path: Path) -> None:
        image_bytes = b"\x89PNGdata"
        img = tmp_path / "shot.png"
        img.write_bytes(image_bytes)
        doc = tmp_path / "doc.md"
        doc.write_bytes(b"# heading")
        agent, _env, attachments_dir = _make_agent_with_attachments_env(tmp_path, image_bytes=image_bytes)

        payload = agent._build_prompt_payload("p1", ChatInputUserMessage(text="both", files=[str(img), str(doc)]))

        # Image only in images[]; doc only in the prompt text — never both.
        assert len(payload["images"]) == 1
        assert payload["images"][0]["mimeType"] == "image/png"
        assert str(attachments_dir / "doc.md") in payload["message"]
        assert "shot.png" not in payload["message"]

    def test_build_prompt_payload_skips_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.txt"  # never created
        agent, _env, _dir = _make_agent_with_attachments_env(tmp_path)
        payload = agent._build_prompt_payload("p1", ChatInputUserMessage(text="hi", files=[str(missing)]))
        # Nothing delivered; the turn proceeds with just the user text.
        assert payload == {"type": "prompt", "id": "p1", "message": "hi"}

    def test_unprocessable_image_error_reaches_user_no_silent_drop(self) -> None:
        """An image the model can't process fails loud through the standard failed-turn path.

        Pi surfaces the API rejection as an assistant message with
        stopReason="error"; PiAgent raises PiCrashError carrying that text so the
        failure is visible to the user (REQ-CAP-IMAGE-INPUT's no-silent-drop bar)
        rather than the image being silently dropped.
        """
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": _assistant_msg("API error 400: Could not process image", stop_reason="error"),
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError) as exc_info:
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        assert "Could not process image" in str(exc_info.value)

    def test_message_end_error_surfaces_pi_reason_not_generic_placeholder(self) -> None:
        """A turn that ends in error with no body must surface pi's real reason.

        Mirrors the real pi wire shape for a provider-auth failure (selecting a
        model whose provider has no key): pi emits no in-stream error event and an
        empty assistant message carrying the failure on ``errorMessage`` with
        ``stopReason:"error"``. PiAgent must lift that reason into a clean,
        actionable message rather than the generic "pi message ended in error"
        placeholder (which drops pi's reason entirely).
        """
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "message_end",
                        "message": {
                            "role": "assistant",
                            "content": [],
                            "stopReason": "error",
                            "errorMessage": "401 Authentication Fails, Your api key: ****0000 is invalid",
                        },
                    }
                ),
            ]
        )
        with pytest.raises(PiCrashError) as exc_info:
            agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        text = str(exc_info.value)
        # The generic placeholder must NOT be what the user sees.
        assert "pi message ended in error" not in text
        # An auth / unavailable-model failure leads with actionable guidance.
        assert "another model" in text.lower() or "different model" in text.lower()
        # pi's real reason is preserved as detail so debugging isn't lost.
        assert "401" in text or "Authentication" in text


class TestCompaction:
    """Compaction chrome (compaction_start/end → AutoCompacting* pair)."""

    def test_compaction_start_then_end_shows_then_clears_the_pill(self) -> None:
        """A compaction_start→end pair emits AutoCompacting then Done (pill shows, then clears)."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "compaction_start", "reason": "threshold"}),
                _event({"type": "compaction_end", "reason": "threshold", "aborted": False, "willRetry": False}),
                _event(_text_delta_update("done.", "done.")),
                _event({"type": "message_end", "message": _assistant_msg("done.")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("done.")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        compacting = [i for i, m in enumerate(emitted) if isinstance(m, AutoCompactingAgentMessage)]
        done = [i for i, m in enumerate(emitted) if isinstance(m, AutoCompactingDoneAgentMessage)]
        assert len(compacting) == 1
        # Exactly one Done — the explicit end, with no duplicate from stick-prevention.
        assert len(done) == 1
        # Shows before it clears.
        assert compacting[0] < done[0]
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert finals and finals[0].content == (TextBlock(text="done."),)

    def test_compaction_start_without_end_emits_done_on_process_exit(self) -> None:
        """Process dies mid-compaction (start, no end, no agent_end): the pill must not stick."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "compaction_start", "reason": "threshold"}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        assert any(isinstance(m, AutoCompactingAgentMessage) for m in emitted)
        # Stick-prevention: a Done is synthesized on exit so is_auto_compacting clears.
        assert any(isinstance(m, AutoCompactingDoneAgentMessage) for m in emitted)

    def test_compaction_end_without_start_emits_done_idempotently(self) -> None:
        """A compaction_end with no preceding start (resumed mid-stream) emits Done harmlessly."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "compaction_end", "reason": "threshold", "aborted": False, "willRetry": False}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        assert len([m for m in emitted if isinstance(m, AutoCompactingDoneAgentMessage)]) == 1
        assert not any(isinstance(m, AutoCompactingAgentMessage) for m in emitted)

    def test_compaction_end_with_will_retry_extends_the_turn(self) -> None:
        """overflow compaction (willRetry:true) clears the pill but does not end the turn — pi re-runs the prompt."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event({"type": "compaction_start", "reason": "overflow"}),
                _event({"type": "compaction_end", "reason": "overflow", "aborted": False, "willRetry": True}),
                # The turn continues: pi re-runs and streams the real response.
                _event(_text_delta_update("after retry", "after retry")),
                _event({"type": "message_end", "message": _assistant_msg("after retry")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("after retry")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        emitted = _drain(agent._output_messages)
        # Compaction cycled (shows then clears) ...
        assert any(isinstance(m, AutoCompactingAgentMessage) for m in emitted)
        assert len([m for m in emitted if isinstance(m, AutoCompactingDoneAgentMessage)]) == 1
        # ... and the turn extended past it to deliver the post-compaction response.
        finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
        assert finals and finals[-1].content == (TextBlock(text="after retry"),)


class TestEventParsing:
    """RPC event parsing and unconsumed-event handling."""

    @pytest.mark.parametrize("payload", _DOCUMENTED_EVENTS, ids=lambda p: str(p["type"]))
    def test_parse_rpc_message_types_each_documented_event(self, payload: dict[str, Any]) -> None:
        parsed = parse_rpc_message(payload)
        assert not isinstance(parsed, ParsedUnknownEvent), f"{payload['type']} should parse to a typed model"
        assert parsed.type == payload["type"]

    def test_parse_rpc_message_returns_unknown_for_unrecognized_type(self) -> None:
        payload = {"type": "from_the_future", "data": 1}
        parsed = parse_rpc_message(payload)
        assert isinstance(parsed, ParsedUnknownEvent)
        assert parsed.raw == payload

    def test_parse_rpc_message_returns_unknown_for_missing_or_malformed_shape(self) -> None:
        # No discriminator at all, and a known type whose required field is absent.
        assert isinstance(parse_rpc_message({"no": "type"}), ParsedUnknownEvent)
        assert isinstance(parse_rpc_message({"type": "message_update"}), ParsedUnknownEvent)

    @pytest.mark.parametrize("payload", _DISCARDED_EVENTS, ids=lambda p: str(p["type"]))
    def test_unconsumed_event_is_discarded_and_turn_still_ends(self, payload: dict[str, Any]) -> None:
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event(payload),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        # Must not raise and must not hang — the agent_end terminates the turn.
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        # The only message emitted is the turn footer's metrics at agent_end; the
        # discarded event itself contributes nothing.
        emitted = _drain(agent._output_messages)
        assert all(isinstance(m, TurnMetricsAgentMessage) for m in emitted)

    def test_extract_tool_call_blocks_returns_only_tool_call_blocks(self) -> None:
        message = AgentMessage(
            role="assistant",
            content=[
                {"type": "text", "text": "hi"},
                {"type": "toolCall", "toolName": "read", "args": {}},
            ],
        )
        blocks = extract_tool_call_blocks(message)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "toolCall"


class TestSkills:
    """Skill discovery, invocation rewriting, and launch args."""

    def test_rewrite_skill_invocation_rewrites_a_discovered_skill(self) -> None:
        assert _rewrite_skill_invocation("/fix-bug", _DISCOVERED) == "/skill:fix-bug"

    def test_rewrite_skill_invocation_preserves_arguments(self) -> None:
        assert _rewrite_skill_invocation("/fix-bug the login flow", _DISCOVERED) == "/skill:fix-bug the login flow"

    def test_rewrite_skill_invocation_strips_plugin_namespace(self) -> None:
        # pi registers plugin skills un-namespaced, so the <plugin>: prefix the
        # picker shows is dropped when rewriting to pi's shape.
        assert _rewrite_skill_invocation("/sculptor-workflow:review", _DISCOVERED) == "/skill:review"

    def test_rewrite_skill_invocation_leaves_unknown_name_untouched(self) -> None:
        assert _rewrite_skill_invocation("/not-a-skill", _DISCOVERED) == "/not-a-skill"

    def test_rewrite_skill_invocation_ignores_pseudo_skills(self) -> None:
        # Pseudo-skills are handled frontend-side and never appear in the discovered
        # set, so they are never rewritten even if one reaches the prompt.
        for pseudo in ("/clear", "/copy", "/btw why is the sky blue"):
            assert _rewrite_skill_invocation(pseudo, _DISCOVERED) == pseudo

    def test_rewrite_skill_invocation_leaves_plain_slash_text_untouched(self) -> None:
        # A leading slash that is not a discovered skill name (e.g. a path) passes through.
        assert _rewrite_skill_invocation("/usr/local/bin matters", _DISCOVERED) == "/usr/local/bin matters"

    def test_rewrite_skill_invocation_leaves_non_slash_text_untouched(self) -> None:
        assert _rewrite_skill_invocation("fix-bug please", _DISCOVERED) == "fix-bug please"

    def test_rewrite_skill_invocation_handles_multiline_prompt(self) -> None:
        assert _rewrite_skill_invocation("/fix-bug\nextra context", _DISCOVERED) == "/skill:fix-bug\nextra context"

    def test_rewrite_skill_invocation_empty_discovered_set_is_noop(self) -> None:
        assert _rewrite_skill_invocation("/fix-bug", frozenset()) == "/fix-bug"

    def test_build_skill_launch_args_passes_existing_skill_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        _write_skill(repo / ".claude" / "skills", "fix-bug")
        _write_skill(home / ".claude" / "skills", "deploy")
        agent = _agent_with_skill_dirs(monkeypatch, repo, home, tmp_path / "state", plugin_dirs=[])

        args = agent._build_skill_launch_args()

        # Repo skills dir precedes home skills dir (discovery order); the absent
        # .claude/commands dirs are skipped quietly.
        assert args == [
            "--skill",
            str(repo / ".claude" / "skills"),
            "--skill",
            str(home / ".claude" / "skills"),
        ]

    def test_build_skill_launch_args_puts_plugin_skills_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        plugin = tmp_path / "plugin"
        _write_skill(plugin / "skills", "help")
        _write_skill(repo / ".claude" / "skills", "fix-bug")
        agent = _agent_with_skill_dirs(monkeypatch, repo, home, tmp_path / "state", plugin_dirs=[plugin])

        args = agent._build_skill_launch_args()

        assert args[:2] == ["--skill", str(plugin / "skills")]
        assert args[2:] == ["--skill", str(repo / ".claude" / "skills")]

    def test_build_skill_launch_args_no_sources_is_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _agent_with_skill_dirs(
            monkeypatch, tmp_path / "repo", tmp_path / "home", tmp_path / "state", plugin_dirs=[]
        )
        assert agent._build_skill_launch_args() == []

    def test_build_skill_launch_args_synthesizes_loose_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        state = tmp_path / "state"
        commands_dir = repo / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "fix-style.md").write_text("---\ndescription: Fix style issues\n---\nDo the thing.\n")
        (commands_dir / "no-frontmatter.md").write_text("Just a body.\n")
        agent = _agent_with_skill_dirs(monkeypatch, repo, home, state, plugin_dirs=[])

        args = agent._build_skill_launch_args()

        # The synthesized wrapper dir is passed as a single --skill, under the state
        # dir (not under .claude), so discover_skills never lists it a second time.
        synthesized_root = state / "pi_skills"
        assert args == ["--skill", str(synthesized_root)]
        # Each loose command becomes a SKILL.md directory named after the file stem.
        fix_style = (synthesized_root / "fix-style" / "SKILL.md").read_text()
        assert "Do the thing." in fix_style
        assert '"fix-style"' in fix_style
        assert '"Fix style issues"' in fix_style
        # A command with no frontmatter still loads — a description is synthesized
        # (pi refuses a skill with none).
        no_fm = (synthesized_root / "no-frontmatter" / "SKILL.md").read_text()
        assert "Just a body." in no_fm
        assert "no-frontmatter" in no_fm

    def test_render_synthesized_skill_escapes_frontmatter(self) -> None:
        # Colons / newlines in the description must not break the YAML frontmatter.
        rendered = _render_synthesized_skill("my-cmd", "Does X: then\nY", "Body text")
        assert '\nname: "my-cmd"\n' in rendered
        assert '\ndescription: "Does X: then Y"\n' in rendered
        assert rendered.endswith("Body text")


class TestSubagents:
    """Sub-agents (yield-early launch → out-of-band nested completion)."""

    def test_subagent_launch_yields_turn_immediately(self) -> None:
        """A `subagent` call surfaces as a started task and the launch turn ENDS right away
        (yield-early): the user is unblocked while the children run. The task is tracked at
        the agent level, and a completion that arrives AFTER agent_end is NOT consumed by
        the launch turn (it is surfaced out-of-band later)."""
        agent = _make_agent()
        agent._process = _make_process(
            _subagent_launch_events()
            + [_event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())]))]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)

        started = _bg_started(emitted)
        assert len(started) == 1
        assert started[0].background_task_id == _SA_TASK_ID
        assert started[0].tool_use_id == _SA_TOOL_CALL_ID
        # The launch turn ended at agent_end without draining the completion.
        assert _bg_notifications(emitted) == []
        assert _child_messages(emitted) == []
        assert agent._subagent_tasks.get(_SA_TASK_ID) == _SA_PGIDS

    def test_subagent_parent_renders_as_agent_block_with_launch_ack(self) -> None:
        """The pi `subagent` tool maps to Claude's `Agent` (so the frontend pills it); the
        launch turn renders the parent block and its "Started …" result acknowledgement."""
        agent = _make_agent()
        agent._process = _make_process(_subagent_launch_events())
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)

        use_blocks = _tool_use_blocks(emitted)
        assert any(b.id == _SA_TOOL_CALL_ID and b.name == "Agent" for b in use_blocks)
        results = [
            b
            for m in emitted
            if isinstance(m, ResponseBlockAgentMessage)
            for b in m.content
            if isinstance(b, ToolResultBlock)
        ]
        assert any(str(b.tool_use_id) == _SA_TOOL_CALL_ID for b in results)

    def test_subagent_completion_in_turn_reconciles(self) -> None:
        """A task that completes while a user turn is in flight is reconciled into that turn
        (nested children + notification), and stops being tracked."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())])),
                _event({"type": "agent_end", "messages": [_assistant_msg("done")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)

        children = _child_messages(emitted)
        assert len(children) == 1
        assert children[0].parent_tool_use_id == _SA_TOOL_CALL_ID
        notes = _bg_notifications(emitted)
        assert len(notes) == 1
        assert notes[0].tool_use_id == _SA_TOOL_CALL_ID
        assert _SA_TASK_ID not in agent._subagent_tasks

    def test_subagent_idle_drain_surfaces_completion_out_of_band(self) -> None:
        """Between turns, a sub-agent completion is surfaced in its own request cycle
        (RequestStarted → nested children + notification → RequestSuccess) so it renders
        live while the user is idle."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [_event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())]))]
        )

        agent._drain_idle_background_events()
        emitted = _drain(agent._output_messages)

        assert any(isinstance(m, RequestStartedAgentMessage) for m in emitted)
        assert any(isinstance(m, RequestSuccessAgentMessage) for m in emitted)
        assert len(_child_messages(emitted)) == 1
        notes = _bg_notifications(emitted)
        assert len(notes) == 1
        types = [type(m).__name__ for m in emitted]
        assert types.index("RequestStartedAgentMessage") < types.index("BackgroundTaskNotificationAgentMessage")
        assert types.index("BackgroundTaskNotificationAgentMessage") < types.index("RequestSuccessAgentMessage")
        assert _SA_TASK_ID not in agent._subagent_tasks

    def test_subagent_completion_emits_nested_child_with_parent_attribution(self) -> None:
        """A completed child becomes its own ChatMessage carrying parent_tool_use_id = the
        parent Agent tool id, with the child's own tool call + result + text nested."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [_event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())]))]
        )
        agent._drain_idle_background_events()
        emitted = _drain(agent._output_messages)

        children = _child_messages(emitted)
        assert len(children) == 1
        child_msg = children[0]
        assert child_msg.parent_tool_use_id == _SA_TOOL_CALL_ID
        names = [b.name for b in child_msg.content if isinstance(b, ToolUseBlock)]
        results = [b for b in child_msg.content if isinstance(b, ToolResultBlock)]
        texts = [b.text for b in child_msg.content if isinstance(b, TextBlock)]
        assert names == ["Read"]
        assert results and str(results[0].tool_use_id) == "sa1:c0:ct1"
        assert "It has one line." in texts

    def test_subagent_completion_emits_one_child_message_per_child_in_parallel(self) -> None:
        """Two parallel children each become their own attributed nested message."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [
                _event(
                    _subagent_notify(
                        [
                            _subagent_child("c0", "done", _read_child_events(), label="subagent 1"),
                            _subagent_child("c1", "done", _read_child_events(), label="subagent 2"),
                        ]
                    )
                )
            ]
        )
        agent._drain_idle_background_events()
        emitted = _drain(agent._output_messages)

        children = _child_messages(emitted)
        assert {m.parent_tool_use_id for m in children} == {_SA_TOOL_CALL_ID}
        assert len(children) == 2

    def test_subagent_completion_failed_surfaces_error_status_and_child(self) -> None:
        """A sub-agent that finishes failed surfaces status="failed" on the completion
        notification and still renders the (failed) child nested under the parent — so a
        failure is visible, not silently dropped."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        error_child = _subagent_child("c0", "error", [], label="scout")
        agent._process = _make_process([_event(_subagent_notify([error_child], status="failed"))])

        agent._drain_idle_background_events()
        emitted = _drain(agent._output_messages)

        notes = _bg_notifications(emitted)
        assert len(notes) == 1
        assert notes[0].status == "failed"
        children = _child_messages(emitted)
        assert len(children) == 1
        # An error child with no events still surfaces as an attributed "failed" bubble.
        texts = [b.text for b in children[0].content if isinstance(b, TextBlock)]
        assert any("failed" in text.lower() for text in texts)
        assert _SA_TASK_ID not in agent._subagent_tasks

    def test_shutdown_cancels_subagent_tasks(self) -> None:
        """`_cancel_all_background_tasks` SIGTERMs each sub-agent child's group in-environment."""
        agent = _make_agent()
        agent._process = _make_process([])
        agent._subagent_tasks["sat_x"] = (777, 888)
        agent._cancel_all_background_tasks()
        assert agent._subagent_tasks == {}
        _assert_killed_pgid(agent, 777)
        _assert_killed_pgid(agent, 888)

    def test_idle_drain_rejects_pi_initiated_agent_start(self) -> None:
        """Pi never self-starts a run (Sculptor is the only turn-initiator — the
        SCU-1776 invariant), so an `agent_start` between turns is a protocol
        violation: logged loud, not consumed as a turn. The completion before it
        still surfaces normally and its wake still enqueues."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [
                _event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())])),
                _event({"type": "agent_start"}),
            ]
        )
        with expect_exact_logged_errors(["PiAgent saw a pi-initiated agent_start between turns"]):
            agent._drain_idle_background_events()
        emitted = _drain(agent._output_messages)

        assert len(_bg_notifications(emitted)) == 1
        # Exactly the completion's own request cycle — no reaction turn was consumed.
        types = [type(m).__name__ for m in emitted]
        assert types.count("RequestStartedAgentMessage") == 1
        assert types.count("RequestSuccessAgentMessage") == 1


class TestBackgroundTasks:
    """Background tasks (yield-early launch → out-of-band completion)."""

    def test_background_launch_yields_turn_immediately(self) -> None:
        """A `background` call surfaces as a started task and the launch turn ENDS right
        away (yield-early): the user is unblocked while the task runs. The task is tracked
        at the agent level, and a completion notify arriving AFTER agent_end is NOT
        consumed by the launch turn (it is surfaced out-of-band later)."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    _tool_execution_start(_BG_TOOL_CALL_ID, "background", {"command": "sleep 1", "label": "build"})
                ),
                _event(_tool_execution_end(_BG_TOOL_CALL_ID, "background", result=_background_start_result())),
                _event({"type": "agent_end", "messages": [_assistant_msg("on it")], "willRetry": False}),
                # A completion that arrives after agent_end must NOT be drained by this
                # turn — yield-early means the turn already returned at agent_end.
                _event(_background_notify()),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)

        started = _bg_started(emitted)
        assert len(started) == 1
        assert started[0].background_task_id == _BG_TASK_ID
        assert started[0].tool_use_id == _BG_TOOL_CALL_ID
        assert started[0].description == "sleep 1"
        assert started[0].task_type == "build"

        # The turn ended at agent_end without waiting for completion, so no
        # notification was emitted by this turn and the task is still tracked.
        assert _bg_notifications(emitted) == []
        assert _BG_TASK_ID in agent._background_tasks

    def test_agent_end_yields_even_with_pending_background_task(self) -> None:
        """`_handle_agent_end` returns True (ends the turn) even while a background task runs."""
        agent = _make_agent()
        agent._background_tasks[_BG_TASK_ID] = _BG_PGID
        end = ParsedAgentEnd(type="agent_end", messages=[], will_retry=False)
        assert agent._handle_agent_end(end, _TurnState(prompt_id=_PROMPT_ID)) is True

    def test_background_completion_in_turn_reconciles(self) -> None:
        """A task that completes while a user turn is in flight is reconciled into that
        turn (notification + summary), and stops being tracked."""
        agent = _make_agent()
        agent._background_tasks[_BG_TASK_ID] = _BG_PGID
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_background_notify()),
                _event({"type": "agent_end", "messages": [_assistant_msg("done")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
        emitted = _drain(agent._output_messages)

        notes = _bg_notifications(emitted)
        assert len(notes) == 1
        assert notes[0].background_task_id == _BG_TASK_ID
        assert notes[0].duration_seconds == 1.5
        assert any("completed" in s for s in _summary_texts(emitted, partial=False))
        # Streamed as a partial too, so the LIVE reducer renders it (not only on reload).
        assert _summary_texts(emitted, partial=True)
        assert _BG_TASK_ID not in agent._background_tasks

    def test_idle_drain_surfaces_completion_out_of_band(self) -> None:
        """Between turns, a completion notify is surfaced in its own request cycle
        (RequestStarted → notification + summary → RequestSuccess) so it renders live
        while the user is idle."""
        agent = _make_agent()
        agent._background_tasks[_BG_TASK_ID] = _BG_PGID
        agent._process = _make_process([_event(_background_notify(status="failed", exit_code=1, summary="boom"))])

        agent._drain_idle_background_events()
        emitted = _drain(agent._output_messages)

        assert any(isinstance(m, RequestStartedAgentMessage) for m in emitted)
        assert any(isinstance(m, RequestSuccessAgentMessage) for m in emitted)
        notes = _bg_notifications(emitted)
        assert len(notes) == 1 and notes[0].status == "failed"
        # The order is RequestStarted ... RequestSuccess, with the notification between.
        types = [type(m).__name__ for m in emitted]
        assert types.index("RequestStartedAgentMessage") < types.index("BackgroundTaskNotificationAgentMessage")
        assert types.index("BackgroundTaskNotificationAgentMessage") < types.index("RequestSuccessAgentMessage")
        assert any("failed" in s for s in _summary_texts(emitted, partial=False))
        assert _BG_TASK_ID not in agent._background_tasks

    def test_shutdown_cancels_background_tasks(self) -> None:
        """`_cancel_all_background_tasks` SIGTERMs each child's group in-environment and clears tracking."""
        agent = _make_agent()
        agent._process = _make_process([])
        agent._background_tasks["bgt_x"] = 999
        agent._cancel_all_background_tasks()
        assert agent._background_tasks == {}
        _assert_killed_pgid(agent, 999)


class TestModelCuration:
    """Model catalog curation rules."""

    def test_curate_models_drops_blacklist_and_dated_and_sorts_newest_first(self) -> None:
        """Curation drops obsolete claude-3-* + dated-pin duplicates, newest-first."""
        curated = _curate_models(_options_from_raw(_RAW_PI_MODELS), current_model=None)
        assert [option.model_id for option in curated] == _CURATED_PI_MODEL_IDS
        # Display names ride through from pi's `name`, and provider is preserved.
        opus_4_8 = next(option for option in curated if option.model_id == "claude-opus-4-8")
        assert opus_4_8.display_name == "Claude Opus 4.8"
        assert opus_4_8.provider == "anthropic"

    def test_curate_models_keeps_current_model_even_when_a_rule_would_drop_it(self) -> None:
        """The current model is never dropped — the switcher must not show an empty selection."""
        current = ModelOption(provider="anthropic", model_id="claude-3-opus-20240229", display_name="Claude Opus 3")
        curated = _curate_models(_options_from_raw(_RAW_PI_MODELS), current_model=current)
        assert current in curated
        # Everything else still curated; only the blacklisted current survives the blacklist.
        assert "claude-3-5-haiku-20241022" not in {option.model_id for option in curated}

    def test_curate_models_keeps_current_model_absent_from_catalog(self) -> None:
        """A current model pi did not list is appended so it can still be shown selected."""
        current = ModelOption(provider="anthropic", model_id="claude-opus-9-9", display_name="Claude Opus 9.9")
        curated = _curate_models(_options_from_raw(_RAW_PI_MODELS), current_model=current)
        assert current in curated
        # Newest major.minor wins, so the fictional 9.9 sorts to the front.
        assert curated[0].model_id == "claude-opus-9-9"

    def test_curate_models_filters_to_single_authenticated_provider(self) -> None:
        """Only options whose provider is in the authenticated set survive."""
        curated = _curate_models(_MULTI_PROVIDER_OPTIONS, current_model=None, authenticated_providers={"anthropic"})
        assert {option.provider for option in curated} == {"anthropic"}
        assert [option.model_id for option in curated] == ["claude-opus-4-8"]

    def test_curate_models_filters_to_multiple_authenticated_providers(self) -> None:
        curated = _curate_models(
            _MULTI_PROVIDER_OPTIONS, current_model=None, authenticated_providers={"anthropic", "openai"}
        )
        assert {option.provider for option in curated} == {"anthropic", "openai"}

    def test_curate_models_empty_authenticated_set_yields_empty(self) -> None:
        """An empty authenticated set drops everything (this drives the empty-state CTA)."""
        curated = _curate_models(_MULTI_PROVIDER_OPTIONS, current_model=None, authenticated_providers=set())
        assert curated == []

    def test_curate_models_retains_current_model_even_when_provider_unauthenticated(self) -> None:
        """The current model is always offered, even if its provider isn't authenticated."""
        current = ModelOption(provider="openai", model_id="gpt-5", display_name="GPT-5")
        curated = _curate_models(_MULTI_PROVIDER_OPTIONS, current_model=current, authenticated_providers={"anthropic"})
        assert current in curated
        assert "gemini-3" not in {option.model_id for option in curated}

    def test_curate_models_filter_preserves_blacklist_and_sort(self) -> None:
        """The authenticated filter layers on top of the existing blacklist/sort rules."""
        curated = _curate_models(
            _options_from_raw(_RAW_PI_MODELS), current_model=None, authenticated_providers={"anthropic"}
        )
        # _RAW_PI_MODELS are all anthropic, so the filter is a no-op here and the curated
        # list matches the unfiltered curation exactly.
        assert [option.model_id for option in curated] == _CURATED_PI_MODEL_IDS

    def test_model_option_from_pi_defaults_provider_and_name(self) -> None:
        # Missing provider defaults to anthropic; missing name falls back to the id.
        option = _model_option_from_pi({"id": "claude-opus-4-8"})
        assert option == ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="claude-opus-4-8")
        # A row with no usable id is dropped.
        assert _model_option_from_pi({"name": "no id"}) is None


class TestModelCatalogFetch:
    """Start-time catalog fetch and refresh."""

    def test_fetch_models_into_state_emits_curated_catalog_and_current_model(self) -> None:
        """At start the agent fetches + curates pi's catalog and emits it with the current model."""
        agent = _make_agent()
        current_raw = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        agent._process = _make_process([_models_response(_RAW_PI_MODELS), _state_response_with_model(current_raw)])
        with (
            patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-models", "cmd-state"]),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            agent._fetch_models_into_state()

        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        message = emitted[0]
        assert [option.model_id for option in message.available_models] == _CURATED_PI_MODEL_IDS
        assert message.current_model is not None
        assert message.current_model.model_id == "claude-opus-4-8"

    def test_fetch_models_into_state_switches_off_deauthenticated_current_model(self) -> None:
        """A refresh after a provider disconnect switches the agent off the now-unauthorized
        current model onto an authenticated one, so the user is not stranded on a model
        they can no longer run."""
        agent = _make_agent()
        raw = [
            {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"},
            {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"},
        ]
        current_openrouter = {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}
        anthropic_replacement = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        agent._process = _make_process(
            [
                _models_response(raw),
                _state_response_with_model(current_openrouter),
                _set_model_response(anthropic_replacement),
            ]
        )
        with (
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.generate_id",
                side_effect=["cmd-models", "cmd-state", "cmd-setmodel"],
            ),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            agent._fetch_models_into_state()

        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        message = emitted[0]
        assert message.current_model is not None
        assert message.current_model.provider == "anthropic"
        assert message.current_model.model_id == "claude-opus-4-8"
        # The unusable openrouter model is no longer offered in the switcher.
        assert "openai/gpt-4o" not in {option.model_id for option in message.available_models}

    def test_fetch_models_into_state_drops_unauthenticated_current_when_no_alternative(self) -> None:
        """When the disconnected provider was the only one, the now-unusable current model
        is dropped and an empty catalog is emitted (driving the switcher's empty state).
        No set_model is sent — there is nothing authenticated to switch to (the process is
        primed with only the models + state responses, so a set_model call would error)."""
        agent = _make_agent()
        raw = [{"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}]
        current_openrouter = {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}
        agent._process = _make_process([_models_response(raw), _state_response_with_model(current_openrouter)])
        with (
            patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-models", "cmd-state"]),
            patch("sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value=set()),
        ):
            agent._fetch_models_into_state()

        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        assert emitted[0].current_model is None
        assert list(emitted[0].available_models) == []

    def test_fetch_models_into_state_emits_empty_catalog_when_pi_lists_no_models(self) -> None:
        """No catalog + no current model (no authenticated providers) → an empty catalog is
        emitted, so the pi switcher shows its 'no usable model' empty state rather than
        falling back to the built-in Claude list."""
        agent = _make_agent()
        agent._process = _make_process([_models_response([]), _state_response_with_model(None)])
        with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-models", "cmd-state"]):
            agent._fetch_models_into_state()
        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        assert list(emitted[0].available_models) == []
        assert emitted[0].current_model is None

    def test_fetch_models_into_state_adopts_preselected_model_over_pi_default(self) -> None:
        """A model the user selected before the agent went live (preselected_model)
        is applied to pi at start and surfaced as current, instead of pi's own default.

        Without this, a pre-message switch would flicker back to pi's default the
        moment the first turn starts the agent, then re-apply on the queued switch.
        """
        preselected = ModelOption(provider="anthropic", model_id="claude-sonnet-4-6", display_name="Claude Sonnet 4.6")
        agent = _make_agent(preselected_model=preselected)
        pi_default = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        adopted = {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic"}
        process = _make_process(
            [_models_response(_RAW_PI_MODELS), _state_response_with_model(pi_default), _set_model_response(adopted)]
        )
        agent._process = process
        with (
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.generate_id",
                side_effect=["cmd-models", "cmd-state", "cmd-setmodel"],
            ),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            agent._fetch_models_into_state()

        # A set_model RPC adopted the preselected model on pi's side.
        writes = [call.args[0] for call in process.write_stdin.call_args_list]
        assert any('"type":"set_model"' in w and '"claude-sonnet-4-6"' in w for w in writes)

        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        assert emitted[0].current_model is not None
        assert emitted[0].current_model.model_id == "claude-sonnet-4-6"

    def test_fetch_models_into_state_ignores_preselected_model_absent_from_catalog(self) -> None:
        """A preselected model pi no longer offers (e.g. its provider was deauthorized)
        is not adopted — the switcher falls back to pi's default rather than a model
        that cannot run. No set_model RPC is sent for the unavailable model."""
        preselected = ModelOption(provider="openrouter", model_id="openai/gpt-4o", display_name="GPT-4o")
        agent = _make_agent(preselected_model=preselected)
        pi_default = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        process = _make_process([_models_response(_RAW_PI_MODELS), _state_response_with_model(pi_default)])
        agent._process = process
        with (
            patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-models", "cmd-state"]),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            agent._fetch_models_into_state()

        writes = [call.args[0] for call in process.write_stdin.call_args_list]
        assert not any('"type":"set_model"' in w for w in writes)
        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        assert emitted[0].current_model is not None
        assert emitted[0].current_model.model_id == "claude-opus-4-8"

    def test_fetch_models_into_state_skips_set_model_when_preselected_is_pi_default(self) -> None:
        """When the preselected model already matches pi's default, no redundant
        set_model RPC is sent — the default is surfaced directly."""
        preselected = ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Claude Opus 4.8")
        agent = _make_agent(preselected_model=preselected)
        pi_default = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        process = _make_process([_models_response(_RAW_PI_MODELS), _state_response_with_model(pi_default)])
        agent._process = process
        with (
            patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-models", "cmd-state"]),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            agent._fetch_models_into_state()

        writes = [call.args[0] for call in process.write_stdin.call_args_list]
        assert not any('"type":"set_model"' in w for w in writes)
        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert emitted[0].current_model is not None
        assert emitted[0].current_model.model_id == "claude-opus-4-8"

    def test_handle_refresh_models_re_fetches_and_re_emits_catalog(self) -> None:
        """A delivered refresh re-runs the fetch between turns and re-emits the catalog.

        This is the live-refresh carrier the credential-change flows (login/logout
        close, paste-key write) broadcast so the picker reflects the new auth.json
        without a restart.
        """
        agent = _make_agent()
        current_raw = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        agent._process = _make_process([_models_response(_RAW_PI_MODELS), _state_response_with_model(current_raw)])
        with (
            patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", side_effect=["cmd-models", "cmd-state"]),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            agent._handle_refresh_models(RefreshModelsUserMessage(message_id=AgentMessageID()))

        emitted = [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]
        assert len(emitted) == 1
        assert [option.model_id for option in emitted[0].available_models] == _CURATED_PI_MODEL_IDS
        assert emitted[0].current_model is not None
        assert emitted[0].current_model.model_id == "claude-opus-4-8"


class TestModelProbe:
    """The pre-message get_available_models probe."""

    def test_fetch_available_models_probe_returns_curated_catalog_and_current_model(self) -> None:
        """The pre-message probe launches pi, fetches + curates the catalog, and returns
        it with the current model — without leaving the agent's message-loop process set."""
        current_raw = {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
        probe_process = _make_process([_models_response(_RAW_PI_MODELS), _state_response_with_model(current_raw)])
        env = _make_probe_env(probe_process)
        agent = _make_agent(env)
        with (
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.generate_id",
                side_effect=["probe-sess", "cmd-models", "cmd-state"],
            ),
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value={"anthropic"}
            ),
        ):
            available_models, current_model = agent.fetch_available_models_probe(secrets={})

        assert [option.model_id for option in available_models] == _CURATED_PI_MODEL_IDS
        assert current_model is not None and current_model.model_id == "claude-opus-4-8"
        # The probe shuts its process down and does NOT leave it as the agent's
        # message-loop process (start() owns that), so the normal lifecycle is intact.
        probe_process.close_stdin.assert_called_once()
        probe_process.terminate.assert_called_once()
        assert agent._process is None
        # No ModelsAvailableAgentMessage is emitted — the probe returns its result
        # directly (the run-agent handler persists it), it does not stream a carrier.
        assert not [m for m in _drain(agent._output_messages) if isinstance(m, ModelsAvailableAgentMessage)]

    def test_fetch_available_models_probe_launches_distinct_probe_session_dir(self) -> None:
        """The probe spawns a minimal `pi --mode rpc` against a throwaway probe session
        dir (never the real PI_SESSION_DIR_NAME) with no extensions / skills / prompt."""
        probe_process = _make_process(
            [_models_response(_RAW_PI_MODELS), _state_response_with_model({"id": "claude-opus-4-8"})]
        )
        env = _make_probe_env(probe_process)
        agent = _make_agent(env)
        with patch(
            "sculptor.agents.pi_agent.agent_wrapper.generate_id",
            side_effect=["probe-sess", "cmd-models", "cmd-state"],
        ):
            agent.fetch_available_models_probe(secrets={})

        env.run_process_in_background.assert_called_once()
        command = list(env.run_process_in_background.call_args.args[0])
        assert command[:3] == ["/bin/pi", "--mode", "rpc"]
        session_dir = command[command.index("--session-dir") + 1]
        assert session_dir == str(Path("/fake/state") / PI_PROBE_SESSION_DIR_NAME)
        assert session_dir != str(Path("/fake/state") / PI_SESSION_DIR_NAME)
        # A distinct, probe-scoped id; never the persisted real session id.
        assert command[command.index("--session-id") + 1] == "probe-probe-sess"
        # Minimal launch: discovery off, and no -e / --append-system-prompt / --skill.
        assert "--no-extensions" in command
        assert "-e" not in command
        assert "--append-system-prompt" not in command
        assert "--skill" not in command

    def test_fetch_available_models_probe_returns_empty_when_binary_missing(self) -> None:
        """No pi binary → empty result (the switcher falls back to defaults), no launch."""
        env = MagicMock(spec=AgentExecutionEnvironment)
        env.get_tool_binary_path.return_value = None
        agent = _make_agent(env)
        assert agent.fetch_available_models_probe(secrets={}) == ([], None)
        env.run_process_in_background.assert_not_called()

    def test_fetch_available_models_probe_returns_empty_on_version_mismatch(self) -> None:
        """An out-of-range pi version → empty result, and the probe never launches a process."""
        env = MagicMock(spec=AgentExecutionEnvironment)
        env.get_tool_binary_path.return_value = "/bin/pi"
        version_result = MagicMock()
        version_result.stdout = ""
        version_result.stderr = "pi 0.1.0\n"
        env.run_process_to_completion.return_value = version_result
        agent = _make_agent(env)
        assert agent.fetch_available_models_probe(secrets={}) == ([], None)
        env.run_process_in_background.assert_not_called()

    def test_fetch_available_models_probe_returns_empty_when_pi_lists_no_models(self) -> None:
        """Empty catalog + no current model → empty result and the probe still shuts down."""
        probe_process = _make_process([_models_response([]), _state_response_with_model(None)])
        env = _make_probe_env(probe_process)
        agent = _make_agent(env)
        with patch(
            "sculptor.agents.pi_agent.agent_wrapper.generate_id",
            side_effect=["probe-sess", "cmd-models", "cmd-state"],
        ):
            assert agent.fetch_available_models_probe(secrets={}) == ([], None)
        probe_process.close_stdin.assert_called_once()
        probe_process.terminate.assert_called_once()
        assert agent._process is None

    def test_fetch_available_models_probe_drops_unauthenticated_current_when_no_alternative(self) -> None:
        """A selected model whose only provider is now unauthenticated is dropped by the
        probe (nothing authenticated to fall back to), so the switcher reaches its empty
        state instead of offering a single unusable model — the deleted-auth.json case."""
        raw = [{"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}]
        current_openrouter = {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}
        probe_process = _make_process([_models_response(raw), _state_response_with_model(current_openrouter)])
        env = _make_probe_env(probe_process)
        agent = _make_agent(env)
        with (
            patch(
                "sculptor.agents.pi_agent.agent_wrapper.generate_id",
                side_effect=["probe-sess", "cmd-models", "cmd-state"],
            ),
            patch("sculptor.agents.pi_agent.agent_wrapper.compute_authenticated_provider_ids", return_value=set()),
        ):
            assert agent.fetch_available_models_probe(secrets={}) == ([], None)


class TestTurnFooterMetrics:
    """Per-turn footer metrics (TurnMetricsAgentMessage at agent_end)."""

    def test_agent_end_emits_turn_metrics_with_summed_token_usage(self) -> None:
        """A completed turn emits one TurnMetricsAgentMessage carrying wall-clock
        duration and this turn's token totals (summed across the run's assistant
        messages), so the frontend renders the per-turn footer that Claude shows."""
        agent = _make_agent()
        msg_a = {**_assistant_msg("part one."), "usage": {"input": 100, "output": 40}}
        msg_b = {**_assistant_msg("part two."), "usage": {"input": 30, "output": 10}}
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("part two.", "part two.")),
                _event({"type": "message_end", "message": msg_b}),
                _event({"type": "agent_end", "messages": [msg_a, msg_b], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        metrics = _turn_metrics(_drain(agent._output_messages))
        assert len(metrics) == 1
        turn = metrics[0].turn_metrics
        assert turn.input_tokens == 130
        assert turn.output_tokens == 50
        assert turn.duration_seconds >= 0.0
        assert turn.changed_files == []

    def test_agent_end_emits_turn_metrics_without_tokens_when_usage_absent(self) -> None:
        """An agent_end whose messages carry no usage (e.g. an interrupted turn) still
        emits metrics — duration only — so the footer renders without token counts."""
        agent = _make_agent()
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("hi.", "hi.")),
                _event({"type": "message_end", "message": _assistant_msg("hi.")}),
                _event({"type": "agent_end", "messages": [], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        metrics = _turn_metrics(_drain(agent._output_messages))
        assert len(metrics) == 1
        turn = metrics[0].turn_metrics
        assert turn.input_tokens is None
        assert turn.output_tokens is None

    def test_turn_metrics_reports_git_relative_changed_files_from_diff_tracker(self) -> None:
        """changed_files comes from the DiffTracker's tree-diff (git-relative, all
        tools including bash) — not from tool args — and the tree is re-baselined
        for the next turn."""
        agent = _make_agent()
        tracker = MagicMock()
        tracker.get_changed_file_paths.return_value = ["src/a.py", "scripts/gen.sh"]
        agent._diff_tracker = tracker
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("done.", "done.")),
                _event({"type": "message_end", "message": _assistant_msg("done.")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("done.")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        metrics = _turn_metrics(_drain(agent._output_messages))
        assert len(metrics) == 1
        # Whatever the tree-diff reports (git-relative, tool-agnostic), verbatim.
        assert metrics[0].turn_metrics.changed_files == ["src/a.py", "scripts/gen.sh"]
        # The baseline is advanced so the next turn diffs from this turn's end.
        tracker.update_initial_tree_sha.assert_called_once()

    def test_turn_metrics_changed_files_empty_when_no_diff_tracker(self) -> None:
        """With no DiffTracker (e.g. before start()), changed_files degrades to empty
        rather than raising."""
        agent = _make_agent()
        assert agent._diff_tracker is None
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update("done.", "done.")),
                _event({"type": "message_end", "message": _assistant_msg("done.")}),
                _event({"type": "agent_end", "messages": [_assistant_msg("done.")], "willRetry": False}),
            ]
        )
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        metrics = _turn_metrics(_drain(agent._output_messages))
        assert len(metrics) == 1
        assert metrics[0].turn_metrics.changed_files == []

    def test_ensure_diff_baseline_creates_tracker_once(self) -> None:
        """The diff baseline is captured lazily on the first turn and reused after."""
        agent = _make_agent()
        with patch("sculptor.agents.pi_agent.agent_wrapper.DiffTracker") as tracker_cls:
            agent._ensure_diff_baseline()
            first = agent._diff_tracker
            agent._ensure_diff_baseline()
        assert first is not None
        assert agent._diff_tracker is first
        tracker_cls.assert_called_once_with(agent.environment)


class TestSculptorInitiatedWake:
    """SCU-1776: completion wake-ups are Sculptor-initiated, serialized on the input FIFO.

    The extensions' pi-side `sendUserMessage(deliverAs:"followUp")` wake-up raced
    Sculptor's prompt pump: landing mid-run it spliced reaction turns into the run,
    deferring `agent_end` (the wrapper's only turn boundary) indefinitely — queued
    user messages starved and Stop escalated to SIGTERM. The fix makes Sculptor the
    only turn-initiator: surfacing a completion enqueues a `_ReactionWakeMessage`
    onto the same FIFO as user messages, and servicing it drives an ordinary
    prompt turn in its own request cycle.

    `_ReactionWakeMessage` / `_run_wake_turn` are resolved via `getattr` so that,
    before the fix exists, exactly these tests fail with AttributeError at
    runtime — a static reference would fail module collection and `just
    typecheck` for the whole file on the failing-test commit.
    """

    @staticmethod
    def _wake_message(text: str) -> Any:
        wake_cls = getattr(agent_wrapper_module, "_ReactionWakeMessage")  # noqa: B009
        return wake_cls(text=text)

    @staticmethod
    def _is_wake(message: Any) -> bool:
        return type(message).__name__ == "_ReactionWakeMessage"

    def test_subagent_completion_from_idle_drain_enqueues_wake_on_input_fifo(self) -> None:
        """A sub-agent completion surfaced by the idle-drain enqueues one wake message
        on the input FIFO, carrying the same summary text the completion notification
        renders (one completion fact, one rendering)."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        notify = _subagent_notify([_subagent_child("c0", "done", _read_child_events())])
        agent._process = _make_process([_event(notify)])

        agent._drain_idle_background_events()

        queued = _drain(agent._input_agent_messages)
        wakes = [m for m in queued if self._is_wake(m)]
        assert len(wakes) == 1
        completion = parse_subagent_completion(notify["message"])
        assert completion is not None
        assert wakes[0].text == _format_subagent_completion(completion)

    def test_subagent_completion_in_turn_enqueues_wake_on_input_fifo(self) -> None:
        """A completion that reconciles into an in-flight turn also enqueues the wake:
        it is serviced from the FIFO after this turn (and any earlier-queued user
        messages), never spliced into the current run."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())])),
                _event({"type": "agent_end", "messages": [_assistant_msg("done")], "willRetry": False}),
            ]
        )

        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

        queued = _drain(agent._input_agent_messages)
        assert len(queued) == 1 and self._is_wake(queued[0]), queued

    def test_background_completion_enqueues_wake_on_input_fifo(self) -> None:
        """A background-task completion enqueues a wake whose text is the notification
        summary (which carries the output tail), mirroring the sub-agent contract."""
        agent = _make_agent()
        agent._background_tasks[_BG_TASK_ID] = _BG_PGID
        notify = _background_notify()
        agent._process = _make_process([_event(notify)])

        agent._drain_idle_background_events()

        queued = _drain(agent._input_agent_messages)
        wakes = [m for m in queued if self._is_wake(m)]
        assert len(wakes) == 1
        completion = parse_background_completion(notify["message"])
        assert completion is not None
        assert wakes[0].text == _format_background_completion(completion)

    def test_wake_enqueues_behind_already_queued_user_message(self) -> None:
        """FIFO serialization is the fix's core guarantee: a user message queued before
        the completion is serviced FIRST; the wake lands behind it (the old pi-side
        followUp ran reaction turns ahead of queued user messages — the bug)."""
        agent = _make_agent()
        agent._subagent_tasks[_SA_TASK_ID] = _SA_PGIDS
        user_message = ChatInputUserMessage(text="answer me first")
        assert agent._push_message(user_message) is True
        agent._process = _make_process(
            [_event(_subagent_notify([_subagent_child("c0", "done", _read_child_events())]))]
        )

        agent._drain_idle_background_events()

        queued = _drain(agent._input_agent_messages)
        assert len(queued) == 2, queued
        assert queued[0] is user_message
        assert self._is_wake(queued[1])

    def test_wake_turn_sends_prompt_in_own_request_cycle(self) -> None:
        """Servicing a wake sends its text verbatim as an ordinary `prompt` RPC and
        brackets the consumed turn in its own RequestStarted → RequestSuccess cycle
        (a fresh request id — the wake is not a reply to any user message)."""
        agent = _make_agent()
        ack = "Both sub-agents finished; continuing."
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(_text_delta_update(ack, ack)),
                _event({"type": "message_end", "message": _assistant_msg(ack)}),
                _event({"type": "agent_end", "messages": [_assistant_msg(ack)], "willRetry": False}),
            ]
        )
        wake = self._wake_message("Sub-agents completed: 1 done, 0 failed (of 1).")

        getattr(agent, "_run_wake_turn")(wake)  # noqa: B009

        sent = [json.loads(call.args[0]) for call in agent._process.write_stdin.call_args_list]
        prompts = [payload for payload in sent if payload.get("type") == "prompt"]
        assert len(prompts) == 1
        assert prompts[0]["message"] == wake.text

        emitted = _drain(agent._output_messages)
        assert isinstance(emitted[0], RequestStartedAgentMessage)
        assert isinstance(emitted[-1], RequestSuccessAgentMessage)
        assert emitted[-1].request_id == emitted[0].request_id
        assert emitted[-1].interrupted is False
        assert any(ack in text for text in _main_agent_texts(emitted))

    def test_wake_turn_pi_crash_is_nonfatal(self) -> None:
        """A wake turn that fails (PiCrashError) must not tear down the agent: the
        failure is logged and its request cycle resolves interrupted=True, so the
        message-processing loop lives on to serve the next user message."""
        agent = _make_agent()
        # An unexpected stopReason:"aborted" (no interrupt pending) raises
        # PiCrashError inside the consume loop — the crash shape from the field.
        agent._process = _make_process(
            [
                _event({"type": "agent_start"}),
                _event(
                    {
                        "type": "agent_end",
                        "messages": [_assistant_msg("boom", stop_reason="aborted")],
                        "willRetry": False,
                    }
                ),
            ]
        )
        wake = self._wake_message("Background task completed (exit code 0).")

        getattr(agent, "_run_wake_turn")(wake)  # must NOT raise  # noqa: B009

        emitted = _drain(agent._output_messages)
        assert isinstance(emitted[0], RequestStartedAgentMessage)
        assert isinstance(emitted[-1], RequestSuccessAgentMessage)
        assert emitted[-1].interrupted is True
