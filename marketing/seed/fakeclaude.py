"""Helpers for scripting deterministic FakeClaude turns.

FakeClaude (sculptor/sculptor/agents/testing/fake_claude.py) runs a `multi_step`
directive as a sequence of tool actions in a single agent turn. We use it to
produce demo state — real on-disk file diffs, a commit, a todo list, and a
canned test run — with zero LLM calls, identically on every re-seed.

The prompt shape FakeClaude expects is exactly:  fake_claude:<command> `<json>`
"""

from __future__ import annotations

import json


def step(command_name: str, **args: object) -> dict:
    """One entry in a multi_step sequence: {"command": ..., "args": {...}}."""
    return {"command": command_name, "args": args}


def multi_step_prompt(steps: list[dict]) -> str:
    """Wrap a list of steps into a single fake_claude:multi_step directive."""
    payload = json.dumps({"steps": steps})
    return f"fake_claude:multi_step `{payload}`"


def interleaved_prompt(blocks: list[dict]) -> str:
    """Wrap ordered text/tool blocks into one assistant message. Unlike multi_step,
    this does NOT prepend "I'll do that." before each tool, so the chat reads like
    real narration."""
    payload = json.dumps({"blocks": blocks})
    return f"fake_claude:interleaved_tools `{payload}`"


def txt(body: str) -> dict:
    return {"type": "text", "text": body}


def tool(tool_name: str, **tool_input: object) -> dict:
    return {"type": "tool", "tool_name": tool_name, "tool_input": tool_input}


def directive(command: str, **args: object) -> str:
    """A single-command fake_claude directive, e.g. hang / ask_user_question /
    api_error. Used for turns that must stand alone (they block or error, so
    they can't be embedded mid-multi_step)."""
    payload = json.dumps(args)
    return f"fake_claude:{command} `{payload}`"


def text(body: str) -> dict:
    return step("text", text=body)


def write_file(path: str, content: str) -> dict:
    return step("write_file", file_path=path, content=content)


def edit_file(path: str, old: str, new: str) -> dict:
    return step("edit_file", file_path=path, old_string=old, new_string=new)


def bash(command: str, description: str) -> dict:
    return step("bash", command=command, description=description)


def task_create(task_id: str, subject: str, status: str, active_form: str) -> dict:
    return step("task_create", id=task_id, subject=subject, status=status, activeForm=active_form)


def task_update(task_id: str, status: str) -> dict:
    return step("task_update", id=task_id, status=status)
