"""Adapt pi's tool-execution lane onto Sculptor's harness-agnostic tool blocks.

Sculptor renders agent tool calls from `ToolUseBlock` (name + input, shown
while running) and `ToolResultBlock` (the result, shown when done), correlated
by a shared id. Claude's output processor produces these directly; pi exposes
the equivalent information over a different wire shape (RPC §9):

- pi's core tools are lowercase (`read`/`write`/`bash`/`edit`) with their own
  arg schemas; Sculptor's renderers key on Claude's PascalCase names
  (`Read`/`Write`/`Bash`/`Edit`/`MultiEdit`) and Claude's arg shapes. This
  module maps the four core tools onto those renderers with arg-shape
  adaptation; any other pi tool passes through unmapped so the frontend
  renders it generically (name + raw args + result).
- pi's `edit` is multi-edit-shaped (`edits: [{oldText, newText}]`), unlike
  Claude's single-edit `Edit`. A one-element `edits` maps to Claude's `Edit`
  (`old_string`/`new_string`); a multi-element `edits` maps to `MultiEdit`
  (`edits: [{old_string, new_string}]`).

Result/partial-result payloads on the lane are permissively typed (RPC §9
leaves them uncharacterized beyond the file-tool detail bundle), so the text
extractors here parse defensively.

Wire-protocol reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sculptor.state.chat_state import DiffToolContent
from sculptor.state.chat_state import GenericToolContent

# Claude tool names whose results render as a file chip (a diff), not generic
# text. The frontend's file chip is skipped unless it can derive a file path,
# and the path on a result-replaced tool block comes from `DiffToolContent`'s
# `file_path` (an in-place result replaces the ToolUseBlock, leaving an
# input-less shim) — so file-mutating tools MUST emit `DiffToolContent`, the
# same content type Claude produces for Write/Edit/MultiEdit.
_FILE_DIFF_TOOL_NAMES: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit"})

# pi's lowercase core tools that map 1:1 onto a Claude renderer by name. `edit`
# is handled separately because its target name (Edit vs MultiEdit) depends on
# the number of edits, so it is not in this table.
_SIMPLE_NAME_MAP: dict[str, str] = {
    "read": "Read",
    "write": "Write",
    "bash": "Bash",
}

# The tool name pi exposes for the Sculptor-pinned sub-agent extension
# (`extensions/sculptor_subagent.ts`); MUST match the `name` that extension
# registers. The adapter (`subagent.py`) keys on this to parse the structured
# per-child progress.
SUBAGENT_TOOL_NAME: str = "subagent"

# Claude's sub-agent tool name (the post-rename of "Task"). The frontend's
# `SUBAGENT_TOOL_NAMES` set keys the subagent pill / metadata off this; mapping
# pi's `subagent` tool onto it groups children (attached by `parent_tool_use_id`)
# under the parent exactly as Claude's sub-agents render.
SUBAGENT_DISPLAY_NAME: str = "Agent"

# The tool name pi exposes for the Sculptor-pinned background-task extension
# (`extensions/sculptor_background.ts`); MUST match the `name` that extension
# registers. The adapter (`agent_wrapper` + `background.py`) keys on this to
# detect the launching tool call and parse its structured lifecycle payloads.
# It is deliberately NOT mapped onto a Claude name: it passes through
# `map_pi_tool_call` unchanged so the frontend renders the launch call
# generically (name + command + "started" result), while the background-task
# lifecycle is surfaced through the harness-agnostic BackgroundTask* contracts.
# Mapping it onto "Agent" would mis-route it into the sub-agent child-synthesis
# path (message_conversion only synthesizes children for Agent/Task parents).
BACKGROUND_TOOL_NAME: str = "background"


def _summarize_subagent_tasks(pi_args: Mapping[str, Any]) -> tuple[str, str]:
    """Derive `(subagent_type, prompt)` for the Claude-shaped `Agent` input.

    The pi sub-agent tool takes either a single `{task}` or a parallel
    `{tasks: [{task, label?}]}`. The frontend's `buildSubagentMetadataMap` reads
    `subagent_type` (the pill's label) and `prompt` (its task text) off the
    `Agent` tool input. A single task keeps its text; a parallel batch becomes
    one `"<label>: <task>"` line per child, separated by a blank line. The blank
    line keeps each child distinct in the popover (rendered markdown, where a
    lone newline is only a soft break and would run the tasks together), and the
    plain `<label>:` prefix also reads cleanly in the collapsed pill, which shows
    the prompt as plain text rather than markdown.
    """
    tasks = pi_args.get("tasks")
    if isinstance(tasks, list) and tasks:
        sections: list[str] = []
        for index, entry in enumerate(tasks, start=1):
            if not isinstance(entry, dict):
                continue
            task_text = _first_str(entry, "task")
            if not task_text:
                continue
            label = _first_str(entry, "label") or f"Sub-agent {index}"
            sections.append(f"{label}: {task_text}")
        return f"subagent (x{len(tasks)})", "\n\n".join(sections)
    return "subagent", _first_str(pi_args, "task", "prompt")


def _first_str(args: Mapping[str, Any], *keys: str) -> str:
    """Return the first string value present under `keys`, else ""."""
    for key in keys:
        value = args.get(key)
        if isinstance(value, str):
            return value
    return ""


def _adapt_edits(raw_edits: Any) -> list[dict[str, str]]:
    """Map pi's `[{oldText, newText}]` onto Claude's `[{old_string, new_string}]`."""
    if not isinstance(raw_edits, list):
        return []
    adapted: list[dict[str, str]] = []
    for edit in raw_edits:
        if not isinstance(edit, dict):
            continue
        adapted.append(
            {
                "old_string": str(edit.get("oldText", "")),
                "new_string": str(edit.get("newText", "")),
            }
        )
    return adapted


def map_pi_tool_call(pi_tool_name: str, pi_args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map a pi tool name + args onto a Claude tool name + input.

    Returns `(claude_name, claude_input)`. The four core tools are adapted onto
    Claude's renderers; any other tool is returned unchanged so the frontend
    renders it generically. Parsing is permissive — a missing or oddly-shaped
    arg yields an empty value rather than raising, so a malformed call renders
    as a degenerate (but non-crashing) block.
    """
    if pi_tool_name in _SIMPLE_NAME_MAP:
        claude_name = _SIMPLE_NAME_MAP[pi_tool_name]
        if pi_tool_name == "read":
            return claude_name, {"file_path": _first_str(pi_args, "path", "file_path")}
        if pi_tool_name == "write":
            return claude_name, {
                "file_path": _first_str(pi_args, "path", "file_path"),
                "content": _first_str(pi_args, "content"),
            }
        # bash
        return claude_name, {"command": _first_str(pi_args, "command")}

    if pi_tool_name == SUBAGENT_TOOL_NAME:
        # Render the parent sub-agent call as Claude's `Agent` tool so the
        # frontend groups its children (attached via parent_tool_use_id) under
        # the same AlphaSubagentPill. The structured per-child progress is
        # parsed separately by the adapter (see `subagent.py`).
        subagent_type, prompt = _summarize_subagent_tasks(pi_args)
        return SUBAGENT_DISPLAY_NAME, {"subagent_type": subagent_type, "prompt": prompt}

    if pi_tool_name == "edit":
        file_path = _first_str(pi_args, "path", "file_path")
        edits = _adapt_edits(pi_args.get("edits"))
        if len(edits) == 1:
            return "Edit", {
                "file_path": file_path,
                "old_string": edits[0]["old_string"],
                "new_string": edits[0]["new_string"],
            }
        # Zero or multiple edits both render through MultiEdit; zero is a
        # degenerate case pi is not expected to emit.
        return "MultiEdit", {"file_path": file_path, "edits": edits}

    # Unknown tool: pass through unmapped (rendered generically).
    return pi_tool_name, dict(pi_args)


def extract_text_from_tool_payload(payload: Any) -> str:
    """Extract human-readable text from a pi tool `result` / `partialResult`.

    pi's tool output rides in a few shapes (RPC §9): a bare string; the
    `{content: [{type: "text", text}], details: {...}}` envelope used by
    `partialResult` (and some results); or some other JSON value. This
    flattens all three to a string for display, ignoring the `details`
    truncation metadata (surfacing it is optional per the task and skipped
    here to keep the result text clean).
    """
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        if not payload:
            return ""
        content = payload.get("content")
        if isinstance(content, list):
            texts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
            ]
            if texts:
                return "".join(texts)
        # A result dict without the text envelope (e.g. file-tool detail
        # bundles like {diff, patch, firstChangedLine}): fall back to a
        # readable text field if present, else stringify so nothing is lost.
        for key in ("text", "result", "output", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return str(payload)


def _synthetic_new_file_diff(file_path: str, content: str) -> str:
    """A git-format 'new file' diff for a Write (pi gives no diff for new files).

    Mirrors the Claude-side synthetic-write diff so the file chip's diff popover
    shows the created content; the frontend splits on `diff --git`.
    """
    rel = file_path.lstrip("/")
    lines = content.split("\n")
    additions = "\n".join("+" + line for line in lines)
    return (
        f"diff --git a/{rel} b/{rel}\n"
        + "new file mode 100644\n"
        + "--- /dev/null\n"
        + f"+++ b/{rel}\n"
        + f"@@ -0,0 +1,{len(lines)} @@\n"
        + f"{additions}\n"
    )


def _git_diff_from_pi_patch(file_path: str, patch: str) -> str:
    """Wrap pi's unified `patch` (no `diff --git` header) into git-diff format.

    pi's `tool_execution_end` for `edit` carries `result.details.patch` as a
    unified diff with bare `--- <path>` / `+++ <path>` lines and no
    `diff --git` header — the frontend splits on `diff --git`, so we rebuild the
    header and `a/`/`b/` path lines around pi's hunks.
    """
    rel = file_path.lstrip("/")
    hunk_start = patch.find("@@")
    if hunk_start == -1:
        # No hunk to carry; emit a header-only diff so the chip still renders.
        return f"diff --git a/{rel} b/{rel}\n"
    hunk = patch[hunk_start:]
    if not hunk.endswith("\n"):
        hunk += "\n"
    return f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n{hunk}"


def build_tool_result_content(
    claude_name: str, claude_input: Mapping[str, Any], result_payload: Any, fallback_text: str = ""
) -> GenericToolContent | DiffToolContent:
    """Build the rendered result content for a finished tool call.

    File-mutating tools (Write/Edit/MultiEdit) render as a file chip and MUST
    carry a `file_path` (see `_FILE_DIFF_TOOL_NAMES`), so they emit
    `DiffToolContent`: pi supplies a unified `patch` in `result.details` for
    edits (git-ified here); a Write gets a synthesized new-file diff from its
    `content` arg. Every other tool renders as generic result text, falling back
    to `fallback_text` (the last accumulated `tool_execution_update` output)
    when the end event carries no result body.
    """
    if claude_name in _FILE_DIFF_TOOL_NAMES:
        file_path = claude_input.get("file_path", "") if isinstance(claude_input, Mapping) else ""
        patch = None
        if isinstance(result_payload, dict):
            details = result_payload.get("details")
            if isinstance(details, dict) and isinstance(details.get("patch"), str):
                patch = details["patch"]
        if patch:
            diff = _git_diff_from_pi_patch(file_path, patch)
        elif claude_name == "Write":
            content = claude_input.get("content", "") if isinstance(claude_input, Mapping) else ""
            diff = _synthetic_new_file_diff(file_path, content if isinstance(content, str) else "")
        else:
            # An edit with no patch (not expected from real pi): a header-only
            # diff still carries the file_path so the chip renders completed.
            rel = file_path.lstrip("/")
            diff = f"diff --git a/{rel} b/{rel}\n"
        return DiffToolContent(diff=diff, file_path=file_path)
    return GenericToolContent(text=extract_text_from_tool_payload(result_payload) or fallback_text)
