#!/usr/bin/env python3
"""Diff two sets of perf measurements and render a PR comment / step summary.

Pure function from two JSONL sources (a *base* — the merge-base commit's
recorded measurements — and a *head* — this PR's run) to Markdown (or plain
text) plus an exit status. No GitHub coupling lives here: the workflow fetches
the baseline from ``refs/notes/perf``, runs the suite for head, calls this, and
posts the output. That keeps the exact CI comparison reproducible locally:

    python tools/perf/comment.py --base base.jsonl --head perf-results/ \
        --base-sha <sha> --format github

Each input is either a ``.jsonl`` file or a directory of them (offload writes
one file per sandbox; they're concatenated). Rows are keyed by
``(scenario, variant)``.

Verdict is on **work counts only** — foreground requests, React commits, DOM
mutations. ``duration_ms`` and background requests ride along for context but
never colour a cell red (background counts poll inside a wall-time window and
jitter; duration is wall-clock). See docs/development notes for the rationale.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

# --- Thresholds (tuned here; expect to calibrate from accumulated main history) ---
# A count metric is flagged only when BOTH the relative and absolute change
# clear their floor, so small-count noise (6 -> 7 commits = +17%) doesn't trip.
COMMIT_PCT = 15.0
COMMIT_ABS = 5
DOM_PCT = 15.0
DOM_ABS = 30

# Hidden marker so the workflow can find-and-update its own comment.
MARKER = "<!-- perf-bot:scu-1294 -->"

# Cell / row status vocabulary.
RED = "red"  # a regression (worse)
GREEN = "green"  # an improvement (better)
FLAT = "flat"  # within threshold / unchanged
INFO = "info"  # shown, never verdict-bearing (bg requests)
NA = "na"  # metric absent on one side

_STATUS_EMOJI = {RED: "❌", GREEN: "⚡", FLAT: "✅", INFO: "•", NA: "·"}


def _load_rows(source: Path) -> list[dict]:
    """Read measurement rows from a .jsonl file or a directory of them."""
    files: list[Path]
    if source.is_dir():
        files = sorted(source.glob("*.jsonl"))
    elif source.exists():
        files = [source]
    else:
        files = []
    rows: list[dict] = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _index(rows: list[dict]) -> tuple[dict[tuple[str, str], dict], list[tuple[str, str]]]:
    """Index rows by (scenario, variant); report keys seen more than once.

    With ``retry_count = 0`` each scenario runs exactly once, so a duplicate
    key signals a data problem (a retried/re-run blend appending a second row)
    worth surfacing rather than silently averaging away.
    """
    idx: dict[tuple[str, str], dict] = {}
    dupes: list[tuple[str, str]] = []
    for row in rows:
        k = (row["scenario"], row["variant"])
        if k in idx:
            dupes.append(k)
        else:
            idx[k] = row
    return idx, dupes


@dataclass
class Cell:
    metric: str
    base: float | None
    head: float | None
    status: str
    text: str  # short delta text for the table cell


@dataclass
class RowReport:
    scenario: str
    variant: str
    state: str  # "compared" | "new" | "removed"
    cells: list[Cell] = field(default_factory=list)
    details: list[str] = field(default_factory=list)  # collapsible attribution lines

    @property
    def status(self) -> str:
        if self.state == "new":
            return "new"
        if self.state == "removed":
            return "removed"
        if any(c.status == RED for c in self.cells):
            return "regressed"
        if any(c.status == GREEN for c in self.cells):
            return "improved"
        return "unchanged"


@dataclass
class Report:
    rows: list[RowReport]
    base_dupes: list[tuple[str, str]]
    head_dupes: list[tuple[str, str]]

    def counts(self) -> dict[str, int]:
        out = {"regressed": 0, "improved": 0, "unchanged": 0, "new": 0, "removed": 0}
        for r in self.rows:
            out[r.status] += 1
        return out

    @property
    def has_regression(self) -> bool:
        return any(r.status == "regressed" for r in self.rows)

    @property
    def is_all_green(self) -> bool:
        c = self.counts()
        return c["regressed"] == 0 and c["improved"] == 0 and c["new"] == 0 and c["removed"] == 0


def _pct(base: float, head: float) -> float:
    if base == 0:
        return float("inf") if head > 0 else 0.0
    return (head - base) / base * 100.0


def _classify_count(base: int, head: int, pct_floor: float, abs_floor: int) -> tuple[str, str]:
    """Classify a count metric with the hybrid (Δ% AND Δabs) rule."""
    delta = head - base
    pct = _pct(base, head)
    if delta == 0:
        return FLAT, f"{head} (=)"
    sign = "+" if delta > 0 else ""
    pct_txt = "∞" if pct == float("inf") else f"{pct:+.0f}%"
    text = f"{base}→{head} ({sign}{delta}, {pct_txt})"
    passes = abs(pct) > pct_floor and abs(delta) >= abs_floor
    if not passes:
        return FLAT, text
    return (RED if delta > 0 else GREEN), text


def _classify_fg(base_routes: dict[str, int], head_routes: dict[str, int]) -> tuple[str, str, list[str]]:
    """Per-route foreground-request diff. Any new/increased route is a regression.

    Returns (status, cell_text, detail_lines). The total is shown in the cell;
    the per-route breakdown goes into the collapsible details so a red cell
    always names the request that appeared.
    """
    routes = sorted(set(base_routes) | set(head_routes))
    up: list[str] = []
    down: list[str] = []
    for r in routes:
        b, h = base_routes.get(r, 0), head_routes.get(r, 0)
        if h > b:
            up.append(f"`{r}` {b}→{h}")
        elif h < b:
            down.append(f"`{r}` {b}→{h}")
    base_total = sum(base_routes.values())
    head_total = sum(head_routes.values())
    cell = f"{base_total}→{head_total}" if base_total != head_total else f"{head_total} (=)"
    details = []
    if up:
        details.append("new/increased foreground routes: " + "; ".join(up))
    if down:
        details.append("removed/decreased foreground routes: " + "; ".join(down))
    if up:
        return RED, cell, details
    if down:
        return GREEN, cell, details
    return FLAT, cell, details


def _top_deltas(base: dict[str, int], head: dict[str, int], n: int = 5) -> list[str]:
    """Largest per-key increases between two count maps (for attribution details)."""
    keys = set(base) | set(head)
    deltas = [(k, head.get(k, 0) - base.get(k, 0)) for k in keys]
    deltas = [(k, d) for k, d in deltas if d != 0]
    deltas.sort(key=lambda kv: -kv[1])
    top = deltas[:n]
    return [f"`{k}` {base.get(k, 0)}→{head.get(k, 0)} ({'+' if d > 0 else ''}{d})" for k, d in top]


def _checkpoint_deltas(base: dict, head: dict) -> list[str]:
    """Per-checkpoint commit/dom deltas, matched by checkpoint name."""
    bmap = {c["name"]: c for c in base.get("checkpoints", [])}
    hmap = {c["name"]: c for c in head.get("checkpoints", [])}
    lines = []
    for name in [c["name"] for c in head.get("checkpoints", [])]:
        if name not in bmap:
            continue
        b, h = bmap[name], hmap[name]
        dc = h["commits"] - b["commits"]
        dd = h["dom_mutations"] - b["dom_mutations"]
        if dc or dd:
            commits_part = f"commits {b['commits']}→{h['commits']} ({dc:+d})"
            dom_part = f"dom {b['dom_mutations']}→{h['dom_mutations']} ({dd:+d})"
            lines.append(f"`{name}`: {commits_part}, {dom_part}")
    return lines


def compare(base_idx: dict, head_idx: dict, dupes: tuple[list, list]) -> Report:
    rows: list[RowReport] = []
    for k in sorted(set(base_idx) | set(head_idx)):
        scenario, variant = k
        b, h = base_idx.get(k), head_idx.get(k)
        if b is None:
            rows.append(RowReport(scenario, variant, state="new"))
            continue
        if h is None:
            rows.append(RowReport(scenario, variant, state="removed"))
            continue

        rr = RowReport(scenario, variant, state="compared")
        # Verdict-bearing metrics.
        fg_status, fg_text, fg_details = _classify_fg(b["fg_by_route"], h["fg_by_route"])
        c_status, c_text = _classify_count(b["commits"], h["commits"], COMMIT_PCT, COMMIT_ABS)
        d_status, d_text = _classify_count(b["dom_mutations"], h["dom_mutations"], DOM_PCT, DOM_ABS)
        # Informational only.
        bg_text = (
            f"{b['bg_requests']}→{h['bg_requests']}"
            if b["bg_requests"] != h["bg_requests"]
            else f"{h['bg_requests']} (=)"
        )
        dur_text = f"{b['duration_ms']:.0f}→{h['duration_ms']:.0f}ms"

        rr.cells = [
            Cell("fg_req", sum(b["fg_by_route"].values()), sum(h["fg_by_route"].values()), fg_status, fg_text),
            Cell("commits", b["commits"], h["commits"], c_status, c_text),
            Cell("dom", b["dom_mutations"], h["dom_mutations"], d_status, d_text),
            Cell("bg_req", b["bg_requests"], h["bg_requests"], INFO, bg_text),
            Cell("dur", b["duration_ms"], h["duration_ms"], INFO, dur_text),
        ]

        # Attribution details for any red/green row.
        if rr.status in ("regressed", "improved"):
            rr.details.extend(fg_details)
            if c_status != FLAT:
                comp = _top_deltas(b["commits_by_component"], h["commits_by_component"])
                if comp:
                    rr.details.append("top component render deltas: " + "; ".join(comp))
            if d_status != FLAT:
                testid = _top_deltas(b["dom_mutations_by_testid"], h["dom_mutations_by_testid"])
                if testid:
                    rr.details.append("top DOM-mutation testid deltas: " + "; ".join(testid))
            cps = _checkpoint_deltas(b, h)
            if cps:
                rr.details.append("checkpoint deltas: " + " | ".join(cps))
        rows.append(rr)
    return Report(rows=rows, base_dupes=dupes[0], head_dupes=dupes[1])


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _cell(cell: Cell) -> str:
    """Render one table cell: status emoji + delta text."""
    return f"{_STATUS_EMOJI[cell.status]} {cell.text}"


def _verdict(report: Report) -> str:
    c = report.counts()
    if c["regressed"]:
        return "⚠️ perf regressions detected"
    if c["improved"]:
        return "⚡ perf improvements"
    if c["new"] or c["removed"]:
        return "ℹ️ scenario set changed"
    return "✅ no perf change"


def render_markdown(report: Report, base_sha: str | None, observational: bool) -> str:
    c = report.counts()
    out: list[str] = [MARKER, "", f"### {_verdict(report)}"]
    if observational:
        out.append("")
        out.append("_Observational — thresholds under calibration; comment-only, not a gate._")
    out.append("")
    summary = f"❌ {c['regressed']} regressed · ⚡ {c['improved']} improved · ✅ {c['unchanged']} unchanged"
    if c["new"]:
        summary += f" · 🆕 {c['new']} new"
    if c["removed"]:
        summary += f" · 🗑️ {c['removed']} removed"
    out.append(summary)
    if base_sha:
        out.append("")
        out.append(f"Baseline: `{base_sha}` (merge-base with main).")
    for k in ("base", "head"):
        dupes = report.base_dupes if k == "base" else report.head_dupes
        if dupes:
            out.append("")
            out.append(f"⚠️ duplicate {k} rows (retries appended twice?): " + ", ".join(f"`{s}/{v}`" for s, v in dupes))

    out.append("")
    out.append("| scenario / variant | fg req | commits | dom | bg req | duration |")
    out.append("|---|---|---|---|---|---|")
    for r in report.rows:
        name = f"{r.scenario} / {r.variant}"
        if r.state == "new":
            out.append(f"| {name} | 🆕 new (no baseline) | | | | |")
            continue
        if r.state == "removed":
            out.append(f"| {name} | 🗑️ removed (base only) | | | | |")
            continue

        by = {c.metric: c for c in r.cells}
        cols = " | ".join(_cell(by[m]) for m in ("fg_req", "commits", "dom", "bg_req", "dur"))
        out.append(f"| {name} | {cols} |")

    detailed = [r for r in report.rows if r.details]
    if detailed:
        out.append("")
        out.append("<details><summary>Attribution for changed scenarios</summary>")
        out.append("")
        for r in detailed:
            marker = "❌" if r.status == "regressed" else "⚡"
            out.append(f"**{marker} {r.scenario} / {r.variant}**")
            for line in r.details:
                out.append(f"- {line}")
            out.append("")
        out.append("</details>")

    out.append("")
    return "\n".join(out)


def _head_cells(h: dict) -> tuple[int, int, int, int, str]:
    """Absolute (fg, commits, dom, bg, duration-text) for one head row."""
    fg = sum(h["fg_by_route"].values())
    return fg, int(h["commits"]), int(h["dom_mutations"]), int(h["bg_requests"]), f"{h['duration_ms']:.0f}ms"


def render_head_only_markdown(head_idx: dict, head_dupes: list[tuple[str, str]]) -> str:
    """Render absolute head numbers when there is no baseline to diff against.

    The verdict table only shows values for *compared* rows, so before a main
    run has recorded a ``refs/notes/perf`` note there is nothing to display but
    ``new (no baseline)`` placeholders. This renders the raw current numbers so
    a PR's perf profile is visible during the bootstrapping window (and for
    anyone who just wants absolute values, not a delta).
    """
    out: list[str] = [MARKER, "", "### 📊 perf measurements (no baseline yet)"]
    out.append("")
    out.append(
        "_No `refs/notes/perf` baseline for the merge-base yet — deltas begin"
        + " once a main run records a note. Absolute numbers below._"
    )
    if head_dupes:
        out.append("")
        out.append("⚠️ duplicate rows (retries appended twice?): " + ", ".join(f"`{s}/{v}`" for s, v in head_dupes))
    out.append("")
    out.append("| scenario / variant | fg req | commits | dom | bg req | duration |")
    out.append("|---|---|---|---|---|---|")
    for k in sorted(head_idx):
        scenario, variant = k
        fg, commits, dom, bg, dur = _head_cells(head_idx[k])
        out.append(f"| {scenario} / {variant} | {fg} | {commits} | {dom} | {bg} | {dur} |")
    out.append("")
    return "\n".join(out)


def render_head_only_term(head_idx: dict) -> str:
    lines = ["perf measurements (no baseline)"]
    for k in sorted(head_idx):
        scenario, variant = k
        fg, commits, dom, bg, dur = _head_cells(head_idx[k])
        lines.append(f"  {scenario}/{variant}  fg={fg} commits={commits} dom={dom} bg={bg} dur={dur}")
    return "\n".join(lines)


def render_term(report: Report, base_sha: str | None) -> str:
    c = report.counts()
    lines = [_verdict(report)]
    if base_sha:
        lines.append(f"baseline: {base_sha}")
    lines.append(
        f"regressed={c['regressed']} improved={c['improved']} unchanged={c['unchanged']} new={c['new']} removed={c['removed']}"
    )
    lines.append("")
    for r in report.rows:
        if r.state != "compared":
            lines.append(f"  {r.scenario}/{r.variant}: {r.state.upper()}")
            continue
        cells = "  ".join(f"{cell.metric}={_STATUS_EMOJI[cell.status]}{cell.text}" for cell in r.cells)
        lines.append(f"  {r.scenario}/{r.variant} [{r.status}]  {cells}")
        for d in r.details:
            lines.append(f"      - {d}")
    return "\n".join(lines)


def build_report(base: Path, head: Path) -> Report:
    base_idx, base_dupes = _index(_load_rows(base))
    head_idx, head_dupes = _index(_load_rows(head))
    return compare(base_idx, head_idx, (base_dupes, head_dupes))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diff perf measurements; render a PR comment / summary.")
    p.add_argument(
        "--base",
        type=Path,
        default=None,
        help=(
            ".jsonl file or dir of the baseline (merge-base) run; omit (or point at an "
            + "empty/missing path) to render an absolute head-only table instead of a diff"
        ),
    )
    p.add_argument("--head", required=True, type=Path, help=".jsonl file or dir of this run")
    p.add_argument("--base-sha", default=None, help="baseline commit SHA, named in the comment")
    p.add_argument("--format", choices=["github", "term"], default="term")
    p.add_argument("--observational", action="store_true", help="label the comment as calibration-phase")
    p.add_argument(
        "--intersect-head",
        action="store_true",
        help="only diff scenarios present in --head; drop base-only rows instead of "
        + "reporting them 'removed'. For the per-PR fast subset vs a full-matrix baseline, "
        + "where the heavy scenarios the PR skipped would otherwise look deleted.",
    )
    p.add_argument("--fail-on-regression", action="store_true", help="exit 1 if any regression (off in CI for now)")
    args = p.parse_args(argv)

    base_rows = _load_rows(args.base) if args.base is not None else []
    head_rows = _load_rows(args.head)

    # No baseline data -> head-only absolute table (bootstrapping window, before
    # a main run has recorded a note). A diff needs both sides.
    if not base_rows:
        head_idx, head_dupes = _index(head_rows)
        if args.format == "github":
            sys.stdout.write(render_head_only_markdown(head_idx, head_dupes) + "\n")
        else:
            sys.stdout.write(render_head_only_term(head_idx) + "\n")
        return 0

    base_idx, base_dupes = _index(base_rows)
    head_idx, head_dupes = _index(head_rows)
    if args.intersect_head:
        base_idx = {k: v for k, v in base_idx.items() if k in head_idx}
    report = compare(base_idx, head_idx, (base_dupes, head_dupes))
    if args.format == "github":
        sys.stdout.write(render_markdown(report, args.base_sha, args.observational) + "\n")
    else:
        sys.stdout.write(render_term(report, args.base_sha) + "\n")

    if args.fail_on_regression and report.has_regression:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
