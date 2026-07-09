"""Build the agent-facing `<system-reminder>` for spotlight line references.

Shared by both harnesses (Claude's `get_user_instructions` and pi's
`_build_prompt_text`) so a spotlight sends identical context regardless of
harness. The reminder is assembled from the `data-spotlight-*` attributes the
frontend serializes onto the chip's `<span data-sculptor-node …>` wrapper — the
same span the UI re-hydrates into a chip and that `_strip_and_unescape_html`
later reduces to its label text. Parsing here (before that strip) lets the agent
receive the captured snapshot + world-state without it ever living in the
stored/rendered message (the seam every other reminder already uses).
"""

from __future__ import annotations

import html
import re

# A spotlight span: `data-sculptor-node` wrapper carrying `data-spotlight-file`.
# Matches the whole element so per-attribute extraction can run over it.
_SPOTLIGHT_SPAN_RE = re.compile(
    r'<span\s+data-sculptor-node[^>]*\bdata-spotlight-file="[^"]*"[^>]*>.*?</span>',
    re.DOTALL,
)


def _extract_attr(span: str, name: str) -> str | None:
    match = re.search(rf'data-spotlight-{re.escape(name)}="([^"]*)"', span)
    return html.unescape(match.group(1)) if match is not None else None


def _scope_label(scope: str, commit_hash: str) -> str:
    if scope == "commit-diff":
        return f"commit {commit_hash}" if commit_hash else "commit"
    if scope == "uncommitted-diff":
        return "uncommitted diff"
    if scope == "target-branch-diff":
        return "diff vs target branch"
    return "file"


def _side_annotation(scope: str, has_previous: bool, has_current: bool) -> str:
    """The diff role of the referenced lines, in agent-facing words.

    A file-view spotlight has no diff axis, so no annotation.
    """
    if scope == "file-view":
        return ""
    if has_previous and has_current:
        return " (modified)"
    if has_current:
        return " (added)"
    if has_previous:
        return " (removed)"
    return ""


def _format_entry(span: str) -> str | None:
    file = _extract_attr(span, "file")
    if not file:
        return None
    previous_start = _extract_attr(span, "previous-start")
    previous_end = _extract_attr(span, "previous-end")
    current_start = _extract_attr(span, "current-start")
    current_end = _extract_attr(span, "current-end")
    scope = _extract_attr(span, "scope") or "file-view"
    commit_hash = _extract_attr(span, "commit-hash") or ""
    previous_snippet = _extract_attr(span, "previous-snippet") or ""
    current_snippet = _extract_attr(span, "current-snippet") or ""

    has_previous = bool(previous_start)
    has_current = bool(current_start)
    # The current file is the source of truth for the displayed range; a pure
    # deletion falls back to the previous-file range.
    start = current_start if has_current else previous_start
    end = current_end if has_current else previous_end
    line_range = start if (not end or end == start) else f"{start}-{end}"

    header = f"- {file}:{line_range}{_side_annotation(scope, has_previous, has_current)} [{_scope_label(scope, commit_hash)}]:"
    parts: list[str] = [header]
    if scope == "file-view":
        # A file view has no diff axis — the captured lines are the current file
        # as-is, not additions or deletions. Render them without a +/- prefix.
        snippet = previous_snippet or current_snippet
        if snippet:
            indented = "\n".join(f"    {line}" for line in snippet.split("\n"))
            parts.append(indented)
    else:
        if previous_snippet:
            indented = "\n".join(f"    - {line}" for line in previous_snippet.split("\n"))
            parts.append(indented)
        if current_snippet:
            indented = "\n".join(f"    + {line}" for line in current_snippet.split("\n"))
            parts.append(indented)
    return "\n".join(parts)


def build_spotlight_reminder(text: str) -> str | None:
    """Assemble the spotlight `<system-reminder>` from a message's raw text.

    Returns ``None`` when the message carries no spotlight spans, so callers can
    skip the prepend entirely.
    """
    entries: list[str] = []
    captured_branch = ""
    captured_head_commit = ""
    has_commit_scope = False
    for span in _SPOTLIGHT_SPAN_RE.findall(text):
        entry = _format_entry(span)
        if entry is None:
            continue
        entries.append(entry)
        captured_branch = captured_branch or (_extract_attr(span, "captured-branch") or "")
        captured_head_commit = captured_head_commit or (_extract_attr(span, "captured-head-commit") or "")
        if _extract_attr(span, "scope") == "commit-diff":
            has_commit_scope = True

    if not entries:
        return None

    body = "\n\n".join(entries)

    footer_lines: list[str] = []
    world_bits: list[str] = []
    if captured_branch:
        world_bits.append(f"branch {captured_branch}")
    if captured_head_commit:
        world_bits.append(f"HEAD {captured_head_commit}")
    if world_bits:
        footer_lines.append(f"Captured on {', '.join(world_bits)}.")
    if has_commit_scope:
        footer_lines.append("For a commit's full diff, run `git show <commit>`.")
    footer = ("\n\n" + "\n".join(footer_lines)) if footer_lines else ""

    header = (
        "The user spotlighted these lines to draw your attention to them. "
        + "Each snippet is a snapshot from capture time — read the file for its current content."
    )
    return f"<system-reminder>\n{header}\n\n{body}{footer}\n</system-reminder>\n\n"
