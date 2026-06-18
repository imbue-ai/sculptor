from typing import Any

from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.default.claude_code_sdk.mcp_result_formatters import format_ask_user_question_result
from sculptor.agents.default.claude_code_sdk.mcp_schemas import build_mcp_tools
from sculptor.agents.default.claude_code_sdk.mcp_server import SculptorMcpServer
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import QuestionOption
from sculptor.state.chat_state import UserQuestion

SCULPTOR_MCP_SERVER_NAME = CLAUDE_CODE_HARNESS.mcp_server_name
SCULPTOR_MCP_ASK_TOOL_NAME = CLAUDE_CODE_HARNESS.mcp_ask_tool_name
SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_NAME = CLAUDE_CODE_HARNESS.mcp_exit_plan_mode_tool_name
SCULPTOR_MCP_ASK_TOOL_FQN = CLAUDE_CODE_HARNESS.mcp_ask_tool_fqn
SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN = CLAUDE_CODE_HARNESS.mcp_exit_plan_mode_tool_fqn


class _RespondCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, control_request_id: str, response_data: dict[str, Any]) -> None:
        self.calls.append((control_request_id, response_data))


def _make_server() -> tuple[SculptorMcpServer, _RespondCapture]:
    respond = _RespondCapture()
    return SculptorMcpServer(respond=respond, harness=CLAUDE_CODE_HARNESS), respond


def _make_ask_question(text: str = "Pick one") -> UserQuestion:
    return UserQuestion(
        question=text,
        header="Header",
        options=[QuestionOption(label="A", description=""), QuestionOption(label="B", description="")],
        multi_select=False,
    )


# Minimal AUQ ``arguments`` payload that satisfies the schema's size constraints
# (1-4 questions, 2-10 options each). Tests that exercise routing / cache /
# pending-call behavior rather than validation should use this so they don't
# trip the validator and get a JSON-RPC error short-circuit instead.
_VALID_AUQ_ARGUMENTS: dict = {
    "questions": [
        {
            "question": "Pick one",
            "header": "Header",
            "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}],
            "multiSelect": False,
        }
    ]
}


def _make_answer(tool_use_id: str, question_text: str = "Pick one", answer: str = "A") -> UserQuestionAnswerMessage:
    question = _make_ask_question(question_text)
    return UserQuestionAnswerMessage(
        answers={question_text: answer},
        question_data=AskUserQuestionData(questions=[question], tool_use_id=tool_use_id),
        tool_use_id=tool_use_id,
    )


def test_handle_initialize_returns_capabilities_envelope() -> None:
    server, respond = _make_server()
    server.handle_message("req_1", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert respond.calls == [
        (
            "req_1",
            {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SCULPTOR_MCP_SERVER_NAME, "version": "0.0.1"},
                    },
                }
            },
        )
    ]


def test_handle_tools_list_returns_mcp_tools() -> None:
    server, respond = _make_server()
    server.handle_message("req_2", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert len(respond.calls) == 1
    request_id, data = respond.calls[0]
    assert request_id == "req_2"
    expected_tools = build_mcp_tools(SCULPTOR_MCP_ASK_TOOL_NAME, SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_NAME)
    assert data["mcp_response"]["result"] == {"tools": expected_tools}


def test_handle_notifications_initialized_returns_empty_result() -> None:
    server, respond = _make_server()
    server.handle_message("req_n", {"jsonrpc": "2.0", "id": 7, "method": "notifications/initialized", "params": {}})
    assert respond.calls[0][1]["mcp_response"]["result"] == {}


def test_unknown_method_returns_jsonrpc_error_minus_32601() -> None:
    server, respond = _make_server()
    server.handle_message("req_x", {"jsonrpc": "2.0", "id": 99, "method": "weird/method"})
    error = respond.calls[0][1]["mcp_response"]["error"]
    assert error["code"] == -32601
    assert "weird/method" in error["message"]


def test_tools_call_holds_request_and_does_not_respond() -> None:
    server, respond = _make_server()
    server.register_tool_use_id("toolu_123", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_call",
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": _VALID_AUQ_ARGUMENTS},
        },
    )
    assert respond.calls == []
    assert "toolu_123" in server._pending
    assert server._pending["toolu_123"].tool_fqn == SCULPTOR_MCP_ASK_TOOL_FQN


def test_deliver_answer_resolves_pending_call_with_formatted_text() -> None:
    server, respond = _make_server()
    server.register_tool_use_id("toolu_abc", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_call",
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": _VALID_AUQ_ARGUMENTS},
        },
    )
    answer = _make_answer("toolu_abc")
    expected_text = format_ask_user_question_result(answer)

    server.deliver_answer(answer)

    assert respond.calls == [
        (
            "req_call",
            {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "result": {
                        "content": [{"type": "text", "text": expected_text}],
                        "isError": False,
                    },
                }
            },
        )
    ]
    assert "toolu_abc" not in server._pending
    assert server._last_delivered_text == expected_text


def test_deliver_answer_for_unknown_tool_use_id_does_not_respond() -> None:
    server, respond = _make_server()
    server.deliver_answer(_make_answer("toolu_missing"))
    assert respond.calls == []


def test_duplicate_tools_call_without_intervening_register_returns_cached_text() -> None:
    """A second tools/call arriving before any fresh AUQ has been
    registered is a duplicate of the just-answered question (e.g. a
    CLI-driven replay) and should be served from the cache."""
    server, respond = _make_server()
    server.register_tool_use_id("toolu_dup", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_first",
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": _VALID_AUQ_ARGUMENTS},
        },
    )
    server.deliver_answer(_make_answer("toolu_dup"))
    assert len(respond.calls) == 1
    cached_text = respond.calls[0][1]["mcp_response"]["result"]["content"][0]["text"]

    server.handle_message(
        "req_replay",
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": _VALID_AUQ_ARGUMENTS},
        },
    )
    assert len(respond.calls) == 2
    replay_request_id, replay_data = respond.calls[1]
    assert replay_request_id == "req_replay"
    assert replay_data["mcp_response"]["id"] == 12
    assert replay_data["mcp_response"]["result"]["content"][0]["text"] == cached_text


def test_tools_call_with_unknown_tool_name_returns_invalid_params_error() -> None:
    server, respond = _make_server()
    server.register_tool_use_id("toolu_zzz", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_bad",
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "definitely_not_a_real_tool", "arguments": {}},
        },
    )
    error = respond.calls[0][1]["mcp_response"]["error"]
    assert error["code"] == -32602


def test_register_tool_use_id_for_exit_plan_mode_routes_to_plan_formatter() -> None:
    server, respond = _make_server()
    server.register_tool_use_id("toolu_plan", SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN)
    server.handle_message(
        "req_plan",
        {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_NAME, "arguments": {"plan": "..."}},
        },
    )
    assert server._pending["toolu_plan"].tool_fqn == SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN


def test_ask_user_question_with_stringified_multi_select_returns_invalid_params_error() -> None:
    """An agent that passes ``multiSelect: 'false'`` (string instead of bool) must
    receive a JSON-RPC error so it can retry with the correct type, rather than
    having the call dangle without any response."""
    server, respond = _make_server()
    server.register_tool_use_id("toolu_bad_bool", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_bad_bool",
        {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": SCULPTOR_MCP_ASK_TOOL_NAME,
                "arguments": {
                    "questions": [
                        {
                            "question": "Pick one",
                            "header": "H",
                            "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}],
                            "multiSelect": "false",
                        }
                    ]
                },
            },
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert mcp_response["id"] == 41
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602
    assert "multi" in mcp_response["error"]["message"].lower()
    assert "toolu_bad_bool" not in server._pending


def test_ask_user_question_with_stringified_options_returns_invalid_params_error() -> None:
    """An agent that JSON-encodes ``options`` into a string instead of passing
    an array must receive a JSON-RPC error rather than silently dangling."""
    server, respond = _make_server()
    server.register_tool_use_id("toolu_bad_opts", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_bad_opts",
        {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": SCULPTOR_MCP_ASK_TOOL_NAME,
                "arguments": {
                    "questions": [
                        {
                            "question": "Pick one",
                            "header": "H",
                            "options": '[{"label": "A", "description": ""}]',
                            "multiSelect": False,
                        }
                    ]
                },
            },
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602
    assert "toolu_bad_opts" not in server._pending


def test_ask_user_question_with_missing_questions_field_returns_invalid_params_error() -> None:
    server, respond = _make_server()
    server.register_tool_use_id("toolu_no_q", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_no_q",
        {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": {}},
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602


def test_ask_user_question_validation_runs_even_without_registered_tool_use_id() -> None:
    """The user-reported failure mode: the output processor's UI-side validation
    fails first and skips ``register_tool_use_id``, so the MCP server has no
    expected tool_use_id when the matching tools/call arrives. The MCP server
    must still respond with a JSON-RPC error rather than silently dropping the
    request — otherwise the agent waits forever for a response that never comes."""
    server, respond = _make_server()
    server.handle_message(
        "req_no_register",
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": SCULPTOR_MCP_ASK_TOOL_NAME,
                "arguments": {
                    "questions": [
                        {
                            "question": "Pick one",
                            "header": "H",
                            "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}],
                            "multiSelect": "false",
                        }
                    ]
                },
            },
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert mcp_response["id"] == 44
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602


def test_exit_plan_mode_accepts_any_object_input_per_open_schema() -> None:
    """``mcp__sculptor__exit_plan_mode`` advertises an empty input schema —
    the model doesn't supply the plan content; the harness injects it from
    disk. The MCP server must not reject any object input for this tool.
    """
    server, respond = _make_server()
    server.register_tool_use_id("toolu_plan_open", SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_FQN)
    server.handle_message(
        "req_plan_open",
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_EXIT_PLAN_MODE_TOOL_NAME, "arguments": {}},
        },
    )
    # Call is held (no error sent), waiting for the user's approval.
    assert respond.calls == []
    assert "toolu_plan_open" in server._pending


def test_ask_user_question_with_too_many_questions_returns_invalid_params_error() -> None:
    """Schema caps ``questions`` at 4 items per the JSON schema's ``maxItems``."""
    server, respond = _make_server()
    server.register_tool_use_id("toolu_too_many_q", SCULPTOR_MCP_ASK_TOOL_FQN)
    too_many = [
        {
            "question": f"Q{i}",
            "header": f"H{i}",
            "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}],
            "multiSelect": False,
        }
        for i in range(5)
    ]
    server.handle_message(
        "req_too_many_q",
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": {"questions": too_many}},
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602
    assert "1-4" in mcp_response["error"]["message"]


def test_ask_user_question_with_too_few_options_returns_invalid_params_error() -> None:
    """Schema requires at least 2 options per question per the JSON schema's ``minItems``."""
    server, respond = _make_server()
    server.register_tool_use_id("toolu_too_few_opts", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_too_few_opts",
        {
            "jsonrpc": "2.0",
            "id": 48,
            "method": "tools/call",
            "params": {
                "name": SCULPTOR_MCP_ASK_TOOL_NAME,
                "arguments": {
                    "questions": [
                        {
                            "question": "Pick one",
                            "header": "H",
                            "options": [{"label": "Only", "description": ""}],
                            "multiSelect": False,
                        }
                    ]
                },
            },
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602
    assert "2-10" in mcp_response["error"]["message"]


def test_ask_user_question_with_zero_questions_returns_invalid_params_error() -> None:
    server, respond = _make_server()
    server.register_tool_use_id("toolu_empty_q", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_empty_q",
        {
            "jsonrpc": "2.0",
            "id": 49,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": {"questions": []}},
        },
    )
    assert len(respond.calls) == 1
    mcp_response = respond.calls[0][1]["mcp_response"]
    assert "error" in mcp_response
    assert mcp_response["error"]["code"] == -32602
    assert "1-4" in mcp_response["error"]["message"]


def test_cache_invalidates_when_a_fresh_auq_panel_is_shown_after_delivery() -> None:
    """If the agent moves on to ask a new question after the first answer,
    the cache must NOT serve stale text for the new question."""
    server, respond = _make_server()
    server.register_tool_use_id("toolu_first", SCULPTOR_MCP_ASK_TOOL_FQN)
    server.handle_message(
        "req_first",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": _VALID_AUQ_ARGUMENTS},
        },
    )
    server.deliver_answer(_make_answer("toolu_first"))
    assert len(respond.calls) == 1

    server.deliver_answer(_make_answer("toolu_first"))
    assert server._has_new_auq_since_last_delivery is False

    # Pretend the agent emitted a fresh AUQ — cache must be invalidated.
    server.register_tool_use_id("toolu_second", SCULPTOR_MCP_ASK_TOOL_FQN)
    assert server._has_new_auq_since_last_delivery is True

    server.handle_message(
        "req_second",
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": SCULPTOR_MCP_ASK_TOOL_NAME, "arguments": _VALID_AUQ_ARGUMENTS},
        },
    )
    # No additional respond — the call is held, not served from cache.
    assert len(respond.calls) == 1
    assert "toolu_second" in server._pending
