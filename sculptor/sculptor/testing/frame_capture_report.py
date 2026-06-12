"""Timeline assembly and HTML contact-sheet rendering for frame_capture.py.

Pure functions over captured data so they can be unit-tested without a
browser: `build_switch_timeline` correlates compositor frames with the click
and the renderer's `ws-switch.*` performance marks on one epoch axis, and
`render_index_html` produces a single self-contained contact sheet for
visually scanning every rendered frame of every captured switch.
"""

import html
import json
from pathlib import Path

# Performance marks emitted by the frontend profiler
# (frontend/src/common/perf/workspaceSwitchProfiler.ts).
WS_SWITCH_MARK_PREFIX = "ws-switch."


def build_switch_timeline(
    switch_name: str,
    click_epoch_ms: float,
    frames: list[dict],
    marks: list[dict],
    timing_record: dict | None,
) -> dict:
    """Assemble one switch's capture into a JSON-serializable timeline.

    Args:
        switch_name: e.g. "01_a-to-b".
        click_epoch_ms: epoch ms of the pointerdown on the workspace row.
        frames: [{"file_name": str, "epoch_ms": float, "repeat_count": int}],
            in capture order. `repeat_count` > 1 means N consecutive
            byte-identical compositor frames were collapsed into this one.
        marks: [{"name": str, "epoch_ms": float}] — `ws-switch.*` marks.
        timing_record: the profiler's completed record for this switch
            (window.__WS_SWITCH_TIMINGS__ entry), or None if it didn't finalize.
    """
    return {
        "switch_name": switch_name,
        "click_epoch_ms": click_epoch_ms,
        "frames": [
            {
                "file_name": frame["file_name"],
                "epoch_ms": frame["epoch_ms"],
                "offset_ms": frame["epoch_ms"] - click_epoch_ms,
                "repeat_count": frame["repeat_count"],
            }
            for frame in frames
        ],
        "marks": [
            {
                "name": mark["name"],
                "epoch_ms": mark["epoch_ms"],
                "offset_ms": mark["epoch_ms"] - click_epoch_ms,
            }
            for mark in marks
        ],
        "timing_record": timing_record,
    }


def _format_offset(offset_ms: float) -> str:
    return f"{'+' if offset_ms >= 0 else '−'}{abs(offset_ms):.0f}ms"


def _interleave_frames_and_marks(timeline: dict) -> list[tuple[str, dict]]:
    """Merge frames and marks into one list ordered by epoch time.

    Returns ("frame"|"mark", item) tuples. Marks land between the frames they
    fall between, so a divider reading e.g. `layout-restored` visually
    separates the stale frames from the restored ones.
    """
    entries: list[tuple[str, dict]] = [("frame", frame) for frame in timeline["frames"]]
    entries.extend(("mark", mark) for mark in timeline["marks"])
    return sorted(entries, key=lambda entry: entry[1]["epoch_ms"])


_PAGE_STYLE = """
body { font-family: system-ui, sans-serif; background: #1c1c1e; color: #e8e8ea; margin: 24px; }
h1 { font-size: 20px; }
h2 { font-size: 16px; margin-top: 40px; }
.summary { color: #a0a0a6; font-size: 13px; white-space: pre-wrap; }
.strip { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; margin-top: 12px; }
.cell { width: 220px; }
.cell img { width: 100%; border: 1px solid #3a3a3e; border-radius: 4px; cursor: zoom-in; }
.cell.preclick img { opacity: 0.45; }
.caption { font-size: 12px; color: #a0a0a6; text-align: center; margin-top: 2px; }
.caption .repeat { color: #e8b04a; font-weight: 600; }
.mark { align-self: stretch; display: flex; flex-direction: column; justify-content: center;
        border-left: 3px solid #4a9de8; padding: 0 6px; max-width: 110px; }
.mark span { font-size: 11px; color: #4a9de8; word-break: break-all; }
#lightbox { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.92);
            align-items: center; justify-content: center; flex-direction: column; z-index: 10; }
#lightbox img { max-width: 95vw; max-height: 88vh; }
#lightbox .caption { font-size: 14px; margin-top: 8px; }
"""

# Minimal viewer: click a thumbnail to open it full-size; left/right arrows
# step through frames of the same switch; Escape closes.
_PAGE_SCRIPT = """
const lightbox = document.getElementById('lightbox');
const lightboxImg = lightbox.querySelector('img');
const lightboxCaption = lightbox.querySelector('.caption');
let current = null;
const thumbs = Array.from(document.querySelectorAll('.cell img'));
const show = (img) => {
  current = img;
  lightboxImg.src = img.src;
  lightboxCaption.textContent = img.closest('.cell').dataset.caption;
  lightbox.style.display = 'flex';
};
thumbs.forEach((img) => img.addEventListener('click', () => show(img)));
const step = (delta) => {
  if (current === null) return;
  const sameSwitch = thumbs.filter((t) => t.dataset.switch === current.dataset.switch);
  const next = sameSwitch[sameSwitch.indexOf(current) + delta];
  if (next) show(next);
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { lightbox.style.display = 'none'; current = null; }
  if (e.key === 'ArrowRight') step(1);
  if (e.key === 'ArrowLeft') step(-1);
});
lightbox.addEventListener('click', () => { lightbox.style.display = 'none'; current = null; });
"""


def _render_timing_summary(timeline: dict) -> str:
    record = timeline["timing_record"]
    if record is None:
        return "profiler record: not finalized during the capture window"
    deltas = record.get("milestoneDeltasMs", {})
    parts = [f"{name} {value:.0f}ms" for name, value in sorted(deltas.items(), key=lambda item: item[1])]
    route = f"{record.get('fromWorkspaceId') or '(none)'} → {record.get('toWorkspaceId')}"
    return f"profiler record: {route} — " + ", ".join(parts)


def _render_switch_section(timeline: dict) -> str:
    name = timeline["switch_name"]
    frame_count = sum(frame["repeat_count"] for frame in timeline["frames"])
    distinct_count = len(timeline["frames"])
    lines = [
        f"<h2>{html.escape(name)}</h2>",
        f'<div class="summary">{distinct_count} distinct frames ({frame_count} total) — '
        f"{html.escape(_render_timing_summary(timeline))}</div>",
        '<div class="strip">',
    ]
    for kind, item in _interleave_frames_and_marks(timeline):
        offset = _format_offset(item["offset_ms"])
        if kind == "mark":
            mark_name = item["name"].removeprefix(WS_SWITCH_MARK_PREFIX)
            lines.append(f'<div class="mark"><span>{html.escape(mark_name)}<br>{offset}</span></div>')
        else:
            repeat = f' <span class="repeat">×{item["repeat_count"]}</span>' if item["repeat_count"] > 1 else ""
            caption = f"{offset}{repeat}"
            css_class = "cell preclick" if item["offset_ms"] < 0 else "cell"
            src = f"{name}/frames/{item['file_name']}"
            lines.append(
                f'<div class="{css_class}" data-caption="{html.escape(name)} {offset}">'
                f'<img loading="lazy" data-switch="{html.escape(name)}" src="{html.escape(src)}">'
                f'<div class="caption">{caption}</div></div>'
            )
    lines.append("</div>")
    return "\n".join(lines)


def render_index_html(timelines: list[dict], meta: dict) -> str:
    """Render the contact sheet for all captured switches.

    Frames are captioned with their offset relative to the click; pre-click
    frames are dimmed (baseline state); `ws-switch.*` marks appear as labeled
    dividers between the frames they chronologically separate.
    """
    sections = "\n".join(_render_switch_section(timeline) for timeline in timelines)
    meta_json = html.escape(json.dumps(meta, indent=2, default=str))
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Workspace switch frame capture</title>
<style>{_PAGE_STYLE}</style>
</head>
<body>
<h1>Workspace switch frame capture</h1>
<div class="summary">Click a frame to zoom; ←/→ to step through a switch; Esc to close.</div>
<details><summary class="summary">run config</summary><pre class="summary">{meta_json}</pre></details>
{sections}
<div id="lightbox"><img><div class="caption"></div></div>
<script>{_PAGE_SCRIPT}</script>
</body>
</html>
"""


def write_report(out_dir: Path, timelines: list[dict], meta: dict) -> Path:
    """Write per-switch timeline.json files plus the top-level index.html."""
    for timeline in timelines:
        switch_dir = out_dir / timeline["switch_name"]
        switch_dir.mkdir(parents=True, exist_ok=True)
        (switch_dir / "timeline.json").write_text(json.dumps(timeline, indent=2))
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    index_path = out_dir / "index.html"
    index_path.write_text(render_index_html(timelines, meta))
    return index_path
