"""JSON tool schemas served from `tools/list` for the Sculptor SDK MCP server.

`ask_user_question` mirrors the structural shape of Claude Code's built-in
`AskUserQuestion` (so the model produces compatible arguments) — `question`,
`header`, `options[label, description]`, `multiSelect`. Field casing — notably
`multiSelect` — must stay camelCase; pydantic's `alias_generator=to_camel`
handles conversion to the snake-case `UserQuestion` model on the receiving
side. We do NOT mirror the built-in's `preview` option field (Sculptor doesn't
surface previews) or its internally-injected `answers`/`annotations`/`metadata`
fields.

`exit_plan_mode` does NOT mirror the current built-in. The current built-in's
public schema is `{ allowedPrompts? }`; the plan content is auto-injected from
disk by the harness, not supplied by the model. Sculptor instead exposes an
empty input schema: the model writes the plan to its plan file (driven by the
plan-mode system reminder) and calls this tool with no arguments. The UI
resolves the plan-file path from sibling `Edit`/`Write` tool results in
`Message.tsx`, not from any tool argument.
"""

from typing import Any


def _build_ask_user_question_tool(ask_tool_name: str) -> dict[str, Any]:
    return {
        "name": ask_tool_name,
        "description": "Ask the user one or more multiple-choice questions with optional freeform text. Use when you need user input to proceed: clarifying ambiguous requirements, confirming destructive actions, choosing between implementation approaches. Do NOT use for conversational replies — just respond in chat. Prefer this over plain-text prompts when there is a discrete set of options.",
        "inputSchema": {
            "type": "object",
            "required": ["questions"],
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "required": ["question", "header", "options", "multiSelect"],
                        "properties": {
                            "question": {"type": "string"},
                            "header": {"type": "string"},
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 10,
                                "items": {
                                    "type": "object",
                                    "required": ["label", "description"],
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                },
                            },
                            "multiSelect": {"type": "boolean"},
                        },
                    },
                },
            },
        },
    }


def _build_exit_plan_mode_tool(exit_plan_mode_tool_name: str) -> dict[str, Any]:
    return {
        "name": exit_plan_mode_tool_name,
        "description": "Present your implementation plan to the user for approval before executing it. Call this only when you have written your plan to the plan file specified in the plan-mode system reminder. The user will approve, request revisions, or dismiss. Do NOT call this for open-ended brainstorming.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    }


def build_mcp_tools(ask_tool_name: str, exit_plan_mode_tool_name: str) -> list[dict[str, Any]]:
    return [
        _build_ask_user_question_tool(ask_tool_name),
        _build_exit_plan_mode_tool(exit_plan_mode_tool_name),
    ]
