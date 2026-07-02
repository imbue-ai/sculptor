"""In-process MCP server for Sculptor's `mcp__sculptor__ask_user_question`
and `mcp__sculptor__exit_plan_mode` tools.

The Claude CLI registers this server via `--mcp-config` and routes all
`tools/call` invocations back to us as `control_request` envelopes with
`subtype == "mcp_message"`. We dispatch by JSON-RPC method, hold
`tools/call` requests against a registry keyed by Claude's `tool_use_id`,
and resolve them via `deliver_answer` when the user answers in the UI.
"""

import threading
from collections.abc import Callable
from typing import Any

from loguru import logger
from pydantic import ValidationError

from sculptor.agents.default.claude_code_sdk.harness import ClaudeCodeHarness
from sculptor.agents.default.claude_code_sdk.mcp_result_formatters import format_ask_user_question_result
from sculptor.agents.default.claude_code_sdk.mcp_result_formatters import format_exit_plan_mode_result
from sculptor.agents.default.claude_code_sdk.mcp_schemas import build_mcp_tools
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.state.chat_state import UserQuestion

_MCP_PROTOCOL_VERSION = "2024-11-05"
_MCP_SERVER_VERSION = "0.0.1"

_JSONRPC_METHOD_NOT_FOUND = -32601
_JSONRPC_INVALID_PARAMS = -32602


_MIN_QUESTIONS = 1
_MAX_QUESTIONS = 4
_MIN_OPTIONS = 2
_MAX_OPTIONS = 10


def _validate_arguments(tool_fqn: str, ask_tool_fqn: str, arguments: Any) -> str | None:
    """Check the agent's ``tools/call`` arguments against our schema.

    Returns ``None`` if valid, or a human-readable error string describing the
    mismatch. The string is forwarded to the agent in the JSON-RPC error
    envelope so it has enough signal to retry with corrected types.

    Type-shape validation here is mirrored in display surfaces (output
    processor, message conversion, derived task status) via the harness's
    ``is_valid_ask_user_question_input`` capability method so a rejected call
    doesn't leave a phantom panel or yellow waiting state. Size constraints
    (``minItems``/``maxItems`` from the JSON schema) live only here — the
    display surfaces don't re-enforce them.

    ``mcp__sculptor__exit_plan_mode`` accepts any object input per its
    advertised schema (the model doesn't supply the plan content; the
    harness injects it from disk), so no per-field validation is performed.
    """
    if not isinstance(arguments, dict):
        return f"Invalid params: 'arguments' must be an object, got {type(arguments).__name__}"

    if tool_fqn == ask_tool_fqn:
        if "questions" not in arguments:
            return "Invalid params: missing required field 'questions'"
        questions = arguments["questions"]
        if not isinstance(questions, list):
            return f"Invalid params: 'questions' must be an array, got {type(questions).__name__}"
        if not _MIN_QUESTIONS <= len(questions) <= _MAX_QUESTIONS:
            return f"Invalid params: 'questions' must contain {_MIN_QUESTIONS}-{_MAX_QUESTIONS} items, got {len(questions)}"
        # ``strict=True`` so we reject e.g. ``multiSelect: 'false'`` as a
        # string. Pydantic's default (lenient) mode coerces the string into a
        # bool, which masks the agent's type mistake instead of flagging it.
        try:
            for question in questions:
                if isinstance(question, dict):
                    options = question.get("options")
                    if isinstance(options, list) and not _MIN_OPTIONS <= len(options) <= _MAX_OPTIONS:
                        return f"Invalid params: each question's 'options' must contain {_MIN_OPTIONS}-{_MAX_OPTIONS} items, got {len(options)}"
                UserQuestion.model_validate(question, strict=True)
        except ValidationError as e:
            return f"Invalid params for 'questions': {e}"
        return None

    return None


class PendingCall(SerializableModel):
    """A `tools/call` request that is being held until the user answers."""

    control_request_id: str
    mcp_message_id: int | str
    tool_fqn: str
    tool_use_id: str
    arguments: dict[str, Any] = {}


class ExpectedCall(SerializableModel):
    """A registered tool_use awaiting its matching `tools/call` request.

    ``tool_input`` is the ToolUseBlock's input from the assistant stream,
    used to pair by content. ``None`` acts as a wildcard (matches any
    arguments of the same tool).
    """

    tool_use_id: str
    tool_fqn: str
    tool_input: dict[str, Any] | None = None


class UnmatchedCall(SerializableModel):
    """A `tools/call` that arrived before its tool_use registration.

    For SUBAGENT tool calls the CLI emits the `tools/call` control_request
    BEFORE the sidechain assistant message that carries the ToolUseBlock —
    the inverse of the main-agent ordering. The call is held here until
    ``register_tool_use_id`` pairs it; dropping it would leave the subagent
    blocked forever on a response that never comes, freezing the turn.
    """

    control_request_id: str
    mcp_message_id: int | str
    tool_fqn: str
    arguments: dict[str, Any]


class SculptorMcpServer:
    """Receives MCP `control_request` envelopes from the Claude CLI.

    `handle_message` runs on the output-processor thread. `deliver_answer`
    runs on the task-handler thread. The internal pending-call registry is
    guarded by a lock so the two paths can coexist.

    Pairing model: a `tools/call` request does not carry Claude's
    ``tool_use_id``, so calls are paired with ToolUseBlocks from the
    assistant stream by tool name + arguments. Either side may arrive
    first — the main agent emits the assistant message before the
    `tools/call`, while subagents emit them in the opposite order — so both
    an expectation queue (registrations awaiting calls) and an
    unmatched-call queue (calls awaiting registrations) are kept.
    """

    def __init__(
        self,
        respond: Callable[[str, dict[str, Any]], None],
        harness: ClaudeCodeHarness,
    ) -> None:
        self._respond = respond
        self._harness: ClaudeCodeHarness = harness
        self._lock = threading.Lock()
        self._pending: dict[str, PendingCall] = {}
        # Cache the most recently delivered formatted answer. Served back
        # for duplicate ``tools/call`` requests within the same Q&A
        # (CLI-driven replay after `--resume` re-emits the dangling
        # tool_use with a fresh ``tool_use_id``, so a tool_use_id-keyed
        # cache wouldn't match). Invalidated when a fresh AUQ panel is
        # shown via ``register_tool_use_id``, and guarded by the delivered
        # call's arguments so a NEW question (e.g. from a subagent) is never
        # answered with the previous question's answer.
        self._last_delivered_text: str | None = None
        self._last_delivered_arguments: dict[str, Any] | None = None
        self._has_new_auq_since_last_delivery: bool = False
        self._expected_calls: list[ExpectedCall] = []
        self._unmatched_calls: list[UnmatchedCall] = []

    def set_respond(self, respond: Callable[[str, dict[str, Any]], None]) -> None:
        """Rebind the stdin-write callback. Called from each new
        `ClaudeOutputProcessor.__init__` so the long-lived MCP server (owned by
        `ClaudeProcessManager`) always sends responses through the current CLI
        invocation's stdin.

        Also drops queued expectations and unmatched calls: their
        control_request_ids belong to the previous CLI invocation, so they can
        never be answered through the new one. (Pending calls are kept — the
        resume replay cache handles re-asked dangling questions.)
        """
        self._respond = respond
        with self._lock:
            self._expected_calls = []
            self._unmatched_calls = []

    def _args_match(self, tool_fqn: str, tool_input: dict[str, Any] | None, arguments: dict[str, Any]) -> bool:
        """Whether a registered ToolUseBlock input pairs with `tools/call` arguments.

        ``mcp__sculptor__exit_plan_mode`` has an open input schema (the model's
        input and the CLI's forwarded arguments may legitimately differ), so it
        pairs by tool name alone. ``None`` input is a wildcard.
        """
        if tool_input is None:
            return True
        if tool_fqn == self._harness.mcp_exit_plan_mode_tool_fqn:
            return True
        return tool_input == arguments

    def register_tool_use_id(self, tool_use_id: str, tool_fqn: str, tool_input: dict[str, Any] | None = None) -> None:
        """Inform the server of a ToolUseBlock surfaced by the assistant stream.

        Called from the output processor when an `assistant` message carries a
        ToolUseBlock whose `name` is a Sculptor MCP FQN. For main-agent calls
        the matching `tools/call` arrives immediately afterwards; for subagent
        calls it typically arrived FIRST and is waiting in the unmatched-call
        queue, in which case it is paired (and held pending) here.
        """
        if tool_fqn not in (self._harness.mcp_ask_tool_fqn, self._harness.mcp_exit_plan_mode_tool_fqn):
            logger.debug("register_tool_use_id called with non-MCP tool_fqn={}", tool_fqn)
            return
        with self._lock:
            if tool_use_id in self._pending or any(e.tool_use_id == tool_use_id for e in self._expected_calls):
                return
            if self._last_delivered_text is not None:
                # A fresh AUQ panel is being shown — the cache from the
                # previous Q&A no longer applies to this one.
                self._has_new_auq_since_last_delivery = True
            for i, unmatched in enumerate(self._unmatched_calls):
                if unmatched.tool_fqn == tool_fqn and self._args_match(tool_fqn, tool_input, unmatched.arguments):
                    del self._unmatched_calls[i]
                    self._pending[tool_use_id] = PendingCall(
                        control_request_id=unmatched.control_request_id,
                        mcp_message_id=unmatched.mcp_message_id,
                        tool_fqn=unmatched.tool_fqn,
                        tool_use_id=tool_use_id,
                        arguments=unmatched.arguments,
                    )
                    logger.debug(
                        "Paired held tools/call for {} with tool_use_id={} from the assistant stream",
                        tool_fqn,
                        tool_use_id,
                    )
                    return
            self._expected_calls.append(
                ExpectedCall(tool_use_id=tool_use_id, tool_fqn=tool_fqn, tool_input=tool_input)
            )

    def handle_message(self, control_request_id: str, message: dict[str, Any]) -> None:
        """Dispatch an MCP JSON-RPC message by method."""
        method = message.get("method")
        if method == "initialize":
            self._respond_mcp_result(
                control_request_id,
                message,
                {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self._harness.mcp_server_name, "version": _MCP_SERVER_VERSION},
                },
            )
        elif method == "tools/list":
            tools = build_mcp_tools(self._harness.mcp_ask_tool_name, self._harness.mcp_exit_plan_mode_tool_name)
            self._respond_mcp_result(control_request_id, message, {"tools": tools})
        elif method == "tools/call":
            self._handle_tools_call(control_request_id, message)
        elif method == "notifications/initialized":
            self._respond_mcp_result(control_request_id, message, {})
        else:
            self._respond_mcp_error(
                control_request_id,
                message,
                _JSONRPC_METHOD_NOT_FOUND,
                f"Unknown method: {method}",
            )

    def has_pending_call(self, tool_use_id: str) -> bool:
        """Whether a `tools/call` for `tool_use_id` is currently being held."""
        with self._lock:
            return tool_use_id in self._pending

    def deliver_answer(self, answer: UserQuestionAnswerMessage) -> None:
        """Resolve the held `tools/call` for `answer.tool_use_id`."""
        with self._lock:
            pending = self._pending.pop(answer.tool_use_id, None)
        if pending is None:
            logger.debug("deliver_answer: no pending MCP call for tool_use_id={}", answer.tool_use_id)
            return
        text = self._format_answer_text(pending.tool_fqn, answer)
        with self._lock:
            self._last_delivered_text = text
            self._last_delivered_arguments = pending.arguments
            self._has_new_auq_since_last_delivery = False
        self._respond_with_text(pending.control_request_id, pending.mcp_message_id, text)

    def _handle_tools_call(self, control_request_id: str, message: dict[str, Any]) -> None:
        params = message.get("params", {})
        tool_name_short = params.get("name")
        ask_tool_fqn = self._harness.mcp_ask_tool_fqn
        exit_plan_mode_tool_fqn = self._harness.mcp_exit_plan_mode_tool_fqn
        if tool_name_short == self._harness.mcp_ask_tool_name:
            tool_fqn = ask_tool_fqn
        elif tool_name_short == self._harness.mcp_exit_plan_mode_tool_name:
            tool_fqn = exit_plan_mode_tool_fqn
        else:
            self._respond_mcp_error(
                control_request_id,
                message,
                _JSONRPC_INVALID_PARAMS,
                f"Invalid params: unknown tool {tool_name_short!r}",
            )
            return

        # Validate the agent's arguments against the advertised input schema.
        # Without this, malformed arguments (e.g. ``multiSelect: 'false'`` as a
        # string, ``options`` JSON-encoded into a string, missing required
        # fields) would dangle: the output processor's UI-side validation
        # rejects the call and skips ``register_tool_use_id``, so the
        # tools/call would sit in the unmatched-call queue with no panel and
        # no registration ever coming. Returning a JSON-RPC error
        # lets the agent see the failure and retry with corrected types.
        validation_error_message = _validate_arguments(tool_fqn, ask_tool_fqn, params.get("arguments", {}))
        if validation_error_message is not None:
            self._respond_mcp_error(
                control_request_id,
                message,
                _JSONRPC_INVALID_PARAMS,
                validation_error_message,
            )
            return

        arguments = params.get("arguments", {})
        with self._lock:
            # A queued registration from the assistant stream takes precedence
            # over everything else — pair with it and hold for the answer.
            expectation: ExpectedCall | None = None
            for i, expected in enumerate(self._expected_calls):
                if expected.tool_fqn == tool_fqn and self._args_match(tool_fqn, expected.tool_input, arguments):
                    expectation = expected
                    del self._expected_calls[i]
                    break

            if expectation is not None:
                self._pending[expectation.tool_use_id] = PendingCall(
                    control_request_id=control_request_id,
                    mcp_message_id=message["id"],
                    tool_fqn=tool_fqn,
                    tool_use_id=expectation.tool_use_id,
                    arguments=arguments,
                )
                return

            # Serve the cache for a duplicate tools/call against the just-
            # answered question — the resumed CLI re-emits the dangling call
            # with a fresh tool_use_id, so we match against
            # ``_has_new_auq_since_last_delivery`` plus argument equality
            # rather than tool_use_id equality. ``register_tool_use_id``
            # flips that flag whenever a fresh AUQ panel is shown,
            # invalidating the cache; the argument guard keeps a NEW question
            # (e.g. a subagent's, whose tools/call arrives before its
            # registration) from being answered with the previous question's
            # answer.
            cached_text: str | None
            if (
                self._last_delivered_text is not None
                and not self._has_new_auq_since_last_delivery
                and self._last_delivered_arguments == arguments
            ):
                cached_text = self._last_delivered_text
            else:
                cached_text = None

            if cached_text is None:
                # No registration yet — the SUBAGENT ordering, where the
                # tools/call reaches stdout before the sidechain assistant
                # message. Hold the call; register_tool_use_id pairs it when
                # the assistant stream catches up. Dropping it would leave
                # the agent blocked forever on a response that never comes.
                self._unmatched_calls.append(
                    UnmatchedCall(
                        control_request_id=control_request_id,
                        mcp_message_id=message["id"],
                        tool_fqn=tool_fqn,
                        arguments=arguments,
                    )
                )
                logger.debug(
                    "tools/call for {} arrived before its tool_use registration; holding until the assistant stream catches up",
                    tool_name_short,
                )
                return

        self._respond_with_text(control_request_id, message["id"], cached_text)

    def _format_answer_text(self, tool_fqn: str, answer: UserQuestionAnswerMessage) -> str:
        if tool_fqn == self._harness.mcp_exit_plan_mode_tool_fqn:
            return format_exit_plan_mode_result(answer)
        return format_ask_user_question_result(answer)

    def _respond_mcp_result(self, control_request_id: str, message: dict[str, Any], result: dict[str, Any]) -> None:
        self._respond(
            control_request_id,
            {"mcp_response": {"jsonrpc": "2.0", "id": message.get("id"), "result": result}},
        )

    def _respond_mcp_error(
        self, control_request_id: str, message: dict[str, Any], code: int, error_message: str
    ) -> None:
        self._respond(
            control_request_id,
            {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": code, "message": error_message},
                }
            },
        )

    def _respond_with_text(self, control_request_id: str, mcp_message_id: int | str, text: str) -> None:
        self._respond(
            control_request_id,
            {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": mcp_message_id,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False},
                }
            },
        )
