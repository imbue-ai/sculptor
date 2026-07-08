"""Unit tests for the spotlight `<system-reminder>` builder."""

from sculptor.agents.spotlight_reminder import build_spotlight_reminder


def _span(**attrs: str) -> str:
    parts = " ".join(f'data-spotlight-{name}="{value}"' for name, value in attrs.items())
    return f"<span data-sculptor-node {parts}>label</span>"


def test_returns_none_when_no_spotlight_spans() -> None:
    assert build_spotlight_reminder("just some prose with no chips") is None


def test_returns_none_when_only_non_spotlight_spans() -> None:
    text = '<span data-sculptor-node data-skill-description="x">/foo</span>'
    assert build_spotlight_reminder(text) is None


def test_uncommitted_diff_addition_includes_snippet_and_side() -> None:
    text = _span(
        file="src/calc.ts",
        **{
            "current-start": "42",
            "current-end": "42",
            "scope": "uncommitted-diff",
            "snippet": "const tax = subtotal * 0.08;",
        },
    )
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    assert "src/calc.ts:42 (added) [uncommitted diff]:" in reminder
    assert "const tax = subtotal * 0.08;" in reminder
    assert reminder.startswith("<system-reminder>")
    assert reminder.rstrip().endswith("</system-reminder>")


def test_file_view_has_no_side_annotation() -> None:
    text = _span(file="README.md", **{"current-start": "5", "current-end": "5", "scope": "file-view"})
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    assert "README.md:5 [file]:" in reminder
    assert "(added)" not in reminder and "(modified)" not in reminder


def test_modified_line_carries_both_ranges_as_modified() -> None:
    text = _span(
        file="a.py",
        **{
            "previous-start": "3",
            "previous-end": "3",
            "current-start": "3",
            "current-end": "4",
            "scope": "target-branch-diff",
        },
    )
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    # Current file is the source of truth for the displayed range.
    assert "a.py:3-4 (modified) [diff vs target branch]:" in reminder


def test_pure_deletion_uses_previous_range_and_removed() -> None:
    text = _span(
        file="a.py",
        **{"previous-start": "9", "previous-end": "9", "scope": "uncommitted-diff"},
    )
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    assert "a.py:9 (removed) [uncommitted diff]:" in reminder


def test_commit_scope_labels_commit_and_adds_git_show_hint() -> None:
    text = _span(
        file="a.py",
        **{"current-start": "1", "current-end": "1", "scope": "commit-diff", "commit-hash": "abc1234"},
    )
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    assert "[commit abc1234]:" in reminder
    assert "git show <commit>" in reminder


def test_captured_world_state_footer() -> None:
    text = _span(
        file="a.py",
        **{
            "current-start": "1",
            "current-end": "1",
            "scope": "uncommitted-diff",
            "captured-branch": "feature/x",
            "captured-head-commit": "deadbeef",
        },
    )
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    assert "Captured on branch feature/x, HEAD deadbeef." in reminder


def test_multiple_spotlights_all_present() -> None:
    text = (
        _span(file="a.py", **{"current-start": "1", "current-end": "1", "scope": "uncommitted-diff"})
        + " and "
        + _span(file="b.py", **{"current-start": "2", "current-end": "2", "scope": "uncommitted-diff"})
    )
    reminder = build_spotlight_reminder(text)
    assert reminder is not None
    assert "a.py:1" in reminder
    assert "b.py:2" in reminder
