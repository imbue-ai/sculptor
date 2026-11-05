"""Unit tests for the perf compare/comment logic (tools/perf/comment.py).

Runnable directly (``python3 tools/perf/comment_test.py``) or under pytest.
Locks the classifier behaviour, which is the part most likely to be tuned
later — the thresholds live in comment.py and these tests pin the rules
around them.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("perf_comment", Path(__file__).with_name("comment.py"))
assert _spec and _spec.loader
comment = importlib.util.module_from_spec(_spec)
# Register before exec so dataclass annotation resolution can find the module.
sys.modules[_spec.name] = comment
_spec.loader.exec_module(comment)


def _row(scenario, variant, *, fg=None, commits=0, dom=0, bg=3, dur=400.0, comps=None, testids=None):
    return {
        "scenario": scenario,
        "variant": variant,
        "duration_ms": dur,
        "fg_requests": sum((fg or {}).values()),
        "bg_requests": bg,
        "fg_by_route": fg or {},
        "bg_by_route": {},
        "commits": commits,
        "commits_by_component": comps or {},
        "dom_mutations": dom,
        "dom_mutations_by_type": {},
        "dom_mutations_by_testid": testids or {},
        "checkpoints": [],
        "test_nodeid": f"x::{scenario}[{variant}]",
    }


def _one(base_row, head_row):
    bidx, bd = comment._index([base_row])
    hidx, hd = comment._index([head_row])
    rep = comment.compare(bidx, hidx, (bd, hd))
    return rep.rows[0]


def test_commit_hybrid_needs_both_pct_and_abs() -> None:
    # +1 on a tiny base is a big % but below the absolute floor -> flat.
    r = _one(_row("s", "v", commits=6), _row("s", "v", commits=7))
    assert r.status == "unchanged"
    # +14 clears both -> regressed.
    r = _one(_row("s", "v", commits=16), _row("s", "v", commits=30))
    assert r.status == "regressed"
    # A large absolute drop clears both the other way -> improved.
    r = _one(_row("s", "v", commits=90), _row("s", "v", commits=60))
    assert r.status == "improved"


def test_dom_absolute_floor() -> None:
    # +20% but only +20 mutations (< 30 floor) -> flat.
    r = _one(_row("s", "v", dom=100), _row("s", "v", dom=120))
    assert r.status == "unchanged"
    # +40 clears the 30 floor and the 15% -> regressed.
    r = _one(_row("s", "v", dom=100), _row("s", "v", dom=140))
    assert r.status == "regressed"


def test_any_new_foreground_route_is_regression() -> None:
    r = _one(_row("s", "v", fg={"GET /c": 1}), _row("s", "v", fg={"GET /c": 1, "GET /files": 1}))
    assert r.status == "regressed"
    # A removed foreground route is an improvement.
    r = _one(_row("s", "v", fg={"GET /c": 1, "GET /files": 1}), _row("s", "v", fg={"GET /c": 1}))
    assert r.status == "improved"


def test_bg_and_duration_never_regress() -> None:
    r = _one(_row("s", "v", bg=1, dur=400), _row("s", "v", bg=9, dur=2000))
    assert r.status == "unchanged"
    bg_cell = next(c for c in r.cells if c.metric == "bg_req")
    assert bg_cell.status == comment.INFO


def test_new_and_removed_states() -> None:
    bidx, bd = comment._index([_row("s", "only_base", commits=1)])
    hidx, hd = comment._index([_row("s", "only_head", commits=1)])
    rep = comment.compare(bidx, hidx, (bd, hd))
    states = {(r.scenario, r.variant): r.status for r in rep.rows}
    assert states[("s", "only_base")] == "removed"
    assert states[("s", "only_head")] == "new"


def test_duplicate_rows_flagged() -> None:
    idx, dupes = comment._index([_row("s", "v", commits=1), _row("s", "v", commits=2)])
    assert dupes == [("s", "v")]


def test_attribution_details_on_regression() -> None:
    r = _one(
        _row("s", "v", commits=16, comps={"Toast": 16}),
        _row("s", "v", commits=30, comps={"Toast": 30, "FileTree": 8}),
    )
    assert r.status == "regressed"
    joined = " ".join(r.details)
    assert "FileTree" in joined and "Toast" in joined


def _report(base_rows, head_rows):
    bidx, bd = comment._index(base_rows)
    hidx, hd = comment._index(head_rows)
    return comment.compare(bidx, hidx, (bd, hd))


def test_collapsible_structure_wraps_table_and_attribution() -> None:
    # The whole point of the collapsed comment: the always-visible portion is
    # just the summary, and the table + nested attribution live inside a
    # <details>. GitHub only renders a markdown table / nested <details> when
    # blank lines bracket the <summary> and the table, so pin those too — a
    # future edit dropping a blank line would render as literal HTML.
    rep = _report(
        [_row("s", "v", commits=16, comps={"Toast": 16})],
        [_row("s", "v", commits=30, comps={"Toast": 30, "FileTree": 8})],
    )
    md = comment.render_markdown(rep, "46720f07d8ff", observational=True)
    visible = md.split("<details>", 1)[0]
    # Above the fold: the one-line summary, not the table.
    assert "regressed" in visible
    assert "| scenario / variant |" not in visible
    # Blank line after </summary> and before the table header (GitHub needs it).
    assert "</summary>\n\n" in md
    assert "\n\n| scenario / variant |" in md
    # Attribution nests one level deeper; both <details> open and close.
    assert "Attribution for changed scenarios" in md
    assert md.count("<details>") == 2
    assert md.count("</details>") == 2


def test_all_green_summary_is_a_quiet_one_liner() -> None:
    # A clean run must not lead with a red "❌ 0 regressed"; it reads as a
    # single "✅ N unchanged" line and keeps the (empty) table collapsed.
    rep = _report([_row("s", "v", commits=20)], [_row("s", "v", commits=20)])
    md = comment.render_markdown(rep, "46720f07d8ff", observational=True)
    visible = md.split("<details>", 1)[0]
    assert "✅ no perf change" in visible
    assert "regressed" not in visible
    assert "✅ 1 unchanged" in visible
    # No attribution on a clean run, so a single (table) <details>, still collapsed.
    assert "| scenario / variant |" not in visible
    assert md.count("<details>") == 1


def test_head_only_renders_absolute_numbers() -> None:
    # With no base rows, the CLI renders a head-only absolute table rather than
    # a diff — the bootstrapping view before a main baseline note exists.
    hidx, _ = comment._index([_row("prompt_input", "empty", commits=66, dom=169, bg=2)])
    md = comment.render_head_only_markdown(hidx, [])
    assert comment.MARKER in md
    assert "no baseline yet" in md
    # The absolute values appear as table cells (not "new (no baseline)").
    assert "| prompt_input / empty | 0 | 66 | 169 | 2 |" in md
    assert "new (no baseline)" not in md
    term = comment.render_head_only_term(hidx)
    assert "commits=66" in term and "dom=169" in term


def test_main_intersect_head_drops_base_only_scenarios() -> None:
    # PR fast-subset (head) vs full-matrix baseline (base): the heavy scenario
    # only in base must NOT show as "removed" under --intersect-head.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "base.jsonl"
        head = Path(d) / "head.jsonl"
        base.write_text(
            comment.json.dumps(_row("workspace_switch", "default-warm", commits=25))
            + "\n"
            + comment.json.dumps(_row("workspace_switch", "long_chat_scrolled", commits=25))
            + "\n",
            encoding="utf-8",
        )
        # Head ran only the fast variant.
        head.write_text(
            comment.json.dumps(_row("workspace_switch", "default-warm", commits=25)) + "\n", encoding="utf-8"
        )
        for flag, expect_removed in ((["--intersect-head"], False), ([], True)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                comment.main(["--base", str(base), "--head", str(head), "--format", "github", *flag])
            out = buf.getvalue()
            assert ("removed" in out) is expect_removed, f"flag={flag}: unexpected removed rendering"


def test_main_head_only_when_base_absent() -> None:
    # No pytest fixtures: this module also runs as a plain script (see __main__),
    # where every test_* is called with no arguments.
    with tempfile.TemporaryDirectory() as d:
        head = Path(d) / "head.jsonl"
        head.write_text(comment.json.dumps(_row("s", "v", commits=42)) + "\n", encoding="utf-8")
        # Missing --base entirely, and a --base pointing at a nonexistent path,
        # both fall through to head-only (exit 0, no crash).
        for argv in (
            ["--head", str(head), "--format", "github"],
            ["--base", str(Path(d) / "nope.jsonl"), "--head", str(head), "--format", "github"],
        ):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                assert comment.main(argv) == 0
            assert "no baseline yet" in buf.getvalue()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
