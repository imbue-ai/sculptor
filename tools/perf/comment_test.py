"""Unit tests for the perf compare/comment logic (tools/perf/comment.py).

Runnable directly (``python3 tools/perf/comment_test.py``) or under pytest.
Locks the classifier behaviour, which is the part most likely to be tuned
later — the thresholds live in comment.py and these tests pin the rules
around them.
"""

from __future__ import annotations

import importlib.util
import sys
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
