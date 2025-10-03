import json
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from imbue_core.sculptor.state.claude_state import parse_imbue_cli_content


@pytest.mark.parametrize(
    "tool_result",
    [
        {
            "type": "text",
            "text": '[\n  {\n    "command": "verify",\n    "issues": [\n      {\n        "key": {\n          "command": "imbue_verify",\n          "identifier": "correctness_syntax_issues:sculptor/sculptor/agents/claude_code_sdk/utils.py: 167-170"\n        },\n        "severity": "CRITICAL"\n      },\n      {\n        "key": {\n          "command": "imbue_verify",\n          "identifier": "incomplete_integration_with_existing_code:sculptor/sculptor/agents/claude_code_sdk/utils.py: 161"\n        },\n        "severity": "CRITICAL"\n      },\n      {\n        "key": {\n          "command": "imbue_verify",\n          "identifier": "documentation_implementation_mismatch:sculptor/sculptor/agents/claude_code_sdk/utils.py: 162"\n        },\n        "severity": "NIT"\n      },\n      {\n        "key": {\n          "command": "imbue_verify",\n          "identifier": "logic_error:sculptor/sculptor/agents/claude_code_sdk/utils.py: 165-170"\n        },\n        "severity": "CRITICAL"\n      },\n      {\n        "key": {\n          "command": "imbue_verify",\n          "identifier": "runtime_error_risk:sculptor/sculptor/agents/claude_code_sdk/utils.py: 170"\n        },\n        "severity": "CRITICAL"\n      },\n      {\n        "key": {\n          "command": "imbue_verify",\n          "identifier": "logic_error:sculptor/sculptor/agents/claude_code_sdk/utils.py: 161-172"\n        },\n        "severity": "ERROR"\n      }\n    ],\n    "summary": null\n  }\n]',
        },
        {
            "type": "text",
            "text": "[]",
        },
        {"type": "text", "text": '[{"command": "verify"}]'},
    ],
)
def test_parse_imbue_cli_content(tool_result: dict[str, Any], snapshot: SnapshotAssertion) -> None:
    issues, summary = parse_imbue_cli_content(tool_result)

    assert summary == snapshot
    assert issues == snapshot


def retrieve_tool_result(retrieve_result: str) -> dict[str, Any]:
    tool_result = {
        "type": "text",
        "text": json.dumps(
            [
                {
                    "command": "retrieve",
                    "summary": retrieve_result,
                    "issues": [],
                    "user_display": {"objectType": "CommandTextOutput", "output": retrieve_result},
                }
            ]
        ),
    }
    return tool_result


def test_parse_imbue_cli_content_retrieve(snapshot: SnapshotAssertion) -> None:
    tool_name = "mcp__imbue_tools__retrieve"

    # test multiple results, one result, and no results
    issues_0, summary_0 = parse_imbue_cli_content(retrieve_tool_result("test.py\ntest.js"), tool_name)
    issues_1, summary_1 = parse_imbue_cli_content(retrieve_tool_result("test.py"), tool_name)
    issues_2, summary_2 = parse_imbue_cli_content(retrieve_tool_result(""), tool_name)

    assert summary_0 == snapshot
    assert issues_0 == snapshot
    assert summary_1 == snapshot
    assert issues_1 == snapshot
    assert summary_2 == snapshot
    assert issues_2 == snapshot
