"""Tests for the static-file serving path's tracing-flag injection.

The renderer reads ``window.__SCULPTOR_TRACING__`` synchronously at boot to
decide whether to wire up its PerformanceObserver. This test pins the
inlining behavior so future refactors of the SPA-serving route do not
silently break the no-first-load-gap contract.
"""

from pathlib import Path

from sculptor.utils import tracing
from sculptor.web.app import _inject_tracing_flag


def test_inject_when_disabled() -> None:
    tracing._trace_to_path = None
    html = b"<!doctype html><html><head><title>t</title></head><body></body></html>"
    out = _inject_tracing_flag(html)
    assert b"window.__SCULPTOR_TRACING__ = {enabled: false};" in out
    # Inserted right after the <head> tag.
    head_idx = out.index(b"<head>") + len(b"<head>")
    assert out[head_idx : head_idx + len(b"<script>")] == b"<script>"


def test_inject_when_enabled(tmp_path: Path) -> None:
    tracing._trace_to_path = tmp_path / "out.json"
    try:
        html = b"<!doctype html><html><head><title>t</title></head><body></body></html>"
        out = _inject_tracing_flag(html)
        assert b"window.__SCULPTOR_TRACING__ = {enabled: true};" in out
    finally:
        tracing._trace_to_path = None


def test_inject_preserves_html_without_head() -> None:
    tracing._trace_to_path = None
    html = b"<html><body>plain</body></html>"
    assert _inject_tracing_flag(html) == html


def test_inject_after_head_with_attributes() -> None:
    tracing._trace_to_path = None
    html = b'<html><head lang="en"><title>t</title></head></html>'
    out = _inject_tracing_flag(html)
    head_idx = out.index(b'<head lang="en">') + len(b'<head lang="en">')
    assert out[head_idx : head_idx + len(b"<script>")] == b"<script>"
