"""Integration tests for the /api/v1/debug/heap census endpoint.

Goes through the HTTP layer to cover route registration and the plain-text
report shape. The endpoint is a development-only diagnostic for backend RSS
growth (gc census + optional forced collect); these tests just assert it runs
and reports the expected sections rather than pinning exact numbers.
"""

import tracemalloc
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _tracemalloc_off() -> Generator[None, None, None]:
    # pytest enables tracemalloc (for ResourceWarning tracebacks), which would
    # make the endpoint report "tracing" instead of "not tracing". Force it off
    # around each test so the not-tracing / start / stop assertions are
    # deterministic regardless of run order.
    if tracemalloc.is_tracing():
        tracemalloc.stop()
    yield
    if tracemalloc.is_tracing():
        tracemalloc.stop()


def test_debug_heap_returns_census(client: TestClient) -> None:
    response = client.get("/api/v1/debug/heap")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "Heap report at" in body
    assert "Tracked objects:" in body
    assert "Top 30 types by aggregate shallow size:" in body
    assert "Top 30 types by object count:" in body
    # tracemalloc is off by default in tests, so the opt-in note is shown.
    assert "tracemalloc: not tracing" in body


def test_debug_heap_collect_reports_rss_delta(client: TestClient) -> None:
    response = client.get("/api/v1/debug/heap", params={"collect": "true"})
    assert response.status_code == 200
    assert "gc.collect():" in response.text


def test_debug_heap_start_and_stop_tracemalloc(client: TestClient) -> None:
    was_tracing = tracemalloc.is_tracing()
    try:
        started = client.get("/api/v1/debug/heap", params={"start_trace": 5})
        assert started.status_code == 200
        # Freshly started here, or already tracing from another test -> either way it's on now.
        assert "tracemalloc: STARTED" in started.text or "tracemalloc tracing" in started.text

        sites = client.get("/api/v1/debug/heap")
        assert "tracemalloc tracing" in sites.text
        assert "by full traceback (caller chains)" in sites.text

        stopped = client.get("/api/v1/debug/heap", params={"stop_trace": "true"})
        assert "tracemalloc: stopped" in stopped.text
    finally:
        if not was_tracing and tracemalloc.is_tracing():
            tracemalloc.stop()


def test_debug_heap_top_and_limit_are_honored(client: TestClient) -> None:
    response = client.get("/api/v1/debug/heap", params={"top": 5, "limit": 1000})
    assert response.status_code == 200
    body = response.text
    assert "Top 5 types by object count:" in body
    # A small limit smaller than the live object count must mark the census truncated.
    assert "TRUNCATED" in body
