from sculptor.testing.frame_capture_report import build_switch_timeline
from sculptor.testing.frame_capture_report import render_index_html


def _make_timeline() -> dict:
    return build_switch_timeline(
        switch_name="switch_01_a-to-b",
        click_epoch_ms=1000.0,
        frames=[
            {"file_name": "0001_t-00100ms.jpg", "epoch_ms": 900.0, "repeat_count": 1},
            {"file_name": "0002_t+00050ms.jpg", "epoch_ms": 1050.0, "repeat_count": 3},
        ],
        marks=[{"name": "ws-switch.layout-restored", "epoch_ms": 1030.0}],
        timing_record={
            "fromWorkspaceId": "ws_a",
            "toWorkspaceId": "ws_b",
            "milestoneDeltasMs": {"layout-restored": 30.0},
        },
    )


def test_build_switch_timeline_computes_offsets_relative_to_click() -> None:
    timeline = _make_timeline()
    assert [frame["offset_ms"] for frame in timeline["frames"]] == [-100.0, 50.0]
    assert timeline["marks"][0]["offset_ms"] == 30.0


def test_render_index_html_interleaves_marks_between_frames() -> None:
    html_text = render_index_html([_make_timeline()], meta={"viewport": "1400x900"})
    # The mark at +30ms must appear after the -100ms frame and before the +50ms frame.
    pre_frame = html_text.index("0001_t-00100ms.jpg")
    mark = html_text.index("layout-restored<br>")  # the divider, not the summary line
    post_frame = html_text.index("0002_t+00050ms.jpg")
    assert pre_frame < mark < post_frame


def test_render_index_html_shows_repeat_badge_and_dims_preclick_frames() -> None:
    html_text = render_index_html([_make_timeline()], meta={})
    assert "×3" in html_text
    assert 'class="cell preclick"' in html_text
