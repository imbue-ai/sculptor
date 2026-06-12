"""Tests for the pi→Claude tool name/arg adapter and result-text extraction.

Wire-shape fixtures follow the protocol doc's §9 tool events and
`docs/session-format.md`'s `toolCall` content block: pi's core tools are
lowercase with their own arg schemas, and `edit` is multi-edit-shaped.
"""

from __future__ import annotations

import pytest

from sculptor.agents.pi_agent.tool_rendering import build_tool_result_content
from sculptor.agents.pi_agent.tool_rendering import extract_text_from_tool_payload
from sculptor.agents.pi_agent.tool_rendering import map_pi_tool_call
from sculptor.state.chat_state import DiffToolContent
from sculptor.state.chat_state import GenericToolContent


def test_map_read() -> None:
    name, input_ = map_pi_tool_call("read", {"path": "/repo/a.txt"})
    assert name == "Read"
    assert input_ == {"file_path": "/repo/a.txt"}


def test_map_write() -> None:
    name, input_ = map_pi_tool_call("write", {"path": "/repo/b.txt", "content": "hello"})
    assert name == "Write"
    assert input_ == {"file_path": "/repo/b.txt", "content": "hello"}


def test_map_bash() -> None:
    name, input_ = map_pi_tool_call("bash", {"command": "echo hi"})
    assert name == "Bash"
    assert input_ == {"command": "echo hi"}


def test_map_edit_single_maps_to_edit() -> None:
    name, input_ = map_pi_tool_call(
        "edit",
        {"path": "/repo/c.txt", "edits": [{"oldText": "foo", "newText": "bar"}]},
    )
    assert name == "Edit"
    assert input_ == {"file_path": "/repo/c.txt", "old_string": "foo", "new_string": "bar"}


def test_map_edit_multi_maps_to_multiedit() -> None:
    name, input_ = map_pi_tool_call(
        "edit",
        {
            "path": "/repo/c.txt",
            "edits": [
                {"oldText": "a", "newText": "b"},
                {"oldText": "c", "newText": "d"},
            ],
        },
    )
    assert name == "MultiEdit"
    assert input_ == {
        "file_path": "/repo/c.txt",
        "edits": [
            {"old_string": "a", "new_string": "b"},
            {"old_string": "c", "new_string": "d"},
        ],
    }


def test_map_edit_empty_edits_is_degenerate_multiedit() -> None:
    # pi is not expected to emit zero edits; the adapter must not raise.
    name, input_ = map_pi_tool_call("edit", {"path": "/repo/c.txt", "edits": []})
    assert name == "MultiEdit"
    assert input_ == {"file_path": "/repo/c.txt", "edits": []}


def test_map_unknown_tool_passes_through_unmapped() -> None:
    name, input_ = map_pi_tool_call("some_extension_tool", {"foo": "bar"})
    assert name == "some_extension_tool"
    assert input_ == {"foo": "bar"}


def test_map_is_defensive_about_missing_or_odd_args() -> None:
    # Missing keys yield empty values rather than raising.
    assert map_pi_tool_call("read", {}) == ("Read", {"file_path": ""})
    assert map_pi_tool_call("bash", {}) == ("Bash", {"command": ""})
    # A non-list `edits` is treated as no edits.
    name, input_ = map_pi_tool_call("edit", {"path": "/x", "edits": "not-a-list"})
    assert name == "MultiEdit"
    assert input_ == {"file_path": "/x", "edits": []}


def test_extract_text_from_string_payload() -> None:
    assert extract_text_from_tool_payload("plain output") == "plain output"


def test_extract_text_from_content_envelope() -> None:
    payload = {
        "content": [{"type": "text", "text": "line 1\n"}, {"type": "text", "text": "line 2"}],
        "details": {"truncation": True, "fullOutputPath": "/tmp/full"},
    }
    assert extract_text_from_tool_payload(payload) == "line 1\nline 2"


def test_extract_text_from_empty_or_none_payload() -> None:
    assert extract_text_from_tool_payload(None) == ""
    assert extract_text_from_tool_payload({}) == ""


def test_extract_text_from_detail_bundle_falls_back_to_known_field() -> None:
    # A file-tool result detail bundle with no text envelope.
    assert extract_text_from_tool_payload({"output": "done", "firstChangedLine": 3}) == "done"


@pytest.mark.parametrize("value", [123, ["a", "b"]])
def test_extract_text_stringifies_other_values(value: object) -> None:
    assert extract_text_from_tool_payload(value) == str(value)


# --- build_tool_result_content -------------------------------------------


@pytest.mark.parametrize("tool_name", ["Read", "Bash"])
def test_result_content_for_non_file_tools_is_generic_text(tool_name: str) -> None:
    content = build_tool_result_content(tool_name, {}, {"content": [{"type": "text", "text": "output"}]})
    assert isinstance(content, GenericToolContent)
    assert content.text == "output"


def test_result_content_generic_falls_back_to_update_text() -> None:
    # End event carries no result body; the last accumulated update text is used.
    content = build_tool_result_content("Bash", {}, None, fallback_text="streamed output")
    assert isinstance(content, GenericToolContent)
    assert content.text == "streamed output"


def test_result_content_for_write_is_synthetic_new_file_diff() -> None:
    # pi gives no diff for a new file; synthesize one from the content arg so the
    # file chip can derive a file path and render completed.
    content = build_tool_result_content("Write", {"file_path": "/repo/a.txt", "content": "x\ny"}, {"content": []})
    assert isinstance(content, DiffToolContent)
    assert content.file_path == "/repo/a.txt"
    assert content.diff.startswith("diff --git a/repo/a.txt b/repo/a.txt")
    assert "new file mode" in content.diff
    assert "+x" in content.diff and "+y" in content.diff


def test_result_content_for_edit_git_ifies_pi_patch() -> None:
    # pi's edit result carries a unified patch (no `diff --git` header); it is
    # wrapped into git-diff format so the frontend can parse it.
    pi_result = {
        "content": [{"type": "text", "text": "edited"}],
        "details": {"patch": "--- a.txt\n+++ a.txt\n@@ -1,3 +1,3 @@\n alpha\n-beta\n+BETA\n gamma\n"},
    }
    content = build_tool_result_content("Edit", {"file_path": "/repo/a.txt"}, pi_result)
    assert isinstance(content, DiffToolContent)
    assert content.file_path == "/repo/a.txt"
    assert content.diff.startswith("diff --git a/repo/a.txt b/repo/a.txt")
    assert "@@ -1,3 +1,3 @@" in content.diff
    assert "-beta" in content.diff and "+BETA" in content.diff


def test_result_content_for_edit_without_patch_still_carries_file_path() -> None:
    # Defensive: an edit result with no patch still emits a DiffToolContent with
    # the file_path, so the chip renders rather than being skipped.
    content = build_tool_result_content("Edit", {"file_path": "/repo/a.txt"}, "ok")
    assert isinstance(content, DiffToolContent)
    assert content.file_path == "/repo/a.txt"
    assert content.diff.startswith("diff --git a/repo/a.txt b/repo/a.txt")
