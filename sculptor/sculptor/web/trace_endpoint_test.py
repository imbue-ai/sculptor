"""Integration tests for /api/v1/trace/batch and lifespan-shutdown trace write.

The unit tests in ``sculptor/utils/tracing_test.py`` exercise the in-memory
buffering + on-exit merge directly. This file goes through the HTTP layer
so we cover the route registration, the SerializableModel parsing of the
batch body, the session-token exemption, and (in
``test_trace_file_written_on_lifespan_shutdown``) that the trace file is
actually flushed when the FastAPI lifespan tears down.
"""

import json
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from sculptor.config.settings import SculptorSettings
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.utils import tracing
from sculptor.web.app import APP
from sculptor.web.auth import SESSION_TOKEN_HEADER_NAME
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import services_factory


@pytest.fixture(autouse=True)
def _reset_tracing_state() -> None:
    # The sibling ``tracing_test.py`` has its own autouse reset, but that
    # only runs BEFORE tests in that file. When this file runs in the same
    # pytest session after ``tracing_test.py``, the module's ``_tracer`` is
    # still set from whatever the last unit test left behind, and
    # ``start_tracing`` is then a no-op that never updates ``_trace_to_path``.
    # We reset every relevant piece here so each integration test starts
    # from a fully clean slate.
    tracing._trace_to_path = None
    tracing._tracer = None
    tracing._internal_trace_path = None
    tracing._dropped_event_count = 0
    tracing._invalid_event_count = 0
    with tracing._external_events_lock:
        tracing._external_events.clear()


def test_post_trace_batch_when_disabled_returns_204_and_buffers_nothing(client: TestClient) -> None:
    tracing._trace_to_path = None
    response = client.post(
        "/api/v1/trace/batch",
        json={"source": "renderer", "events": [{"ph": "X", "name": "x", "ts": 0, "dur": 1}]},
    )
    assert response.status_code == 204
    with tracing._external_events_lock:
        assert tracing._external_events == []


def test_post_trace_batch_when_enabled_buffers_events(client: TestClient, tmp_path: Path) -> None:
    tracing.start_tracing(tmp_path / "out.json")
    try:
        response = client.post(
            "/api/v1/trace/batch",
            json={
                "source": "renderer",
                "events": [
                    {"ph": "X", "name": "renderer.x", "ts": 0, "dur": 1},
                    {"ph": "i", "name": "renderer.m", "ts": 1, "s": "t"},
                ],
            },
        )
        assert response.status_code == 204
        with tracing._external_events_lock:
            assert len(tracing._external_events) == 2
            assert all(e["pid"] == tracing.RENDERER_PID for e in tracing._external_events)
    finally:
        tracing.stop_and_write_trace()
        tracing._trace_to_path = None
        tracing._tracer = None
        tracing._internal_trace_path = None
        with tracing._external_events_lock:
            tracing._external_events.clear()


def test_post_trace_batch_electron_main_source_tags_with_correct_pid(client: TestClient, tmp_path: Path) -> None:
    tracing.start_tracing(tmp_path / "out.json")
    try:
        response = client.post(
            "/api/v1/trace/batch",
            json={"source": "electron_main", "events": [{"ph": "i", "name": "boot", "ts": 0}]},
        )
        assert response.status_code == 204
        with tracing._external_events_lock:
            assert tracing._external_events[0]["pid"] == tracing.ELECTRON_MAIN_PID
    finally:
        tracing.stop_and_write_trace()
        tracing._trace_to_path = None
        tracing._tracer = None
        tracing._internal_trace_path = None
        with tracing._external_events_lock:
            tracing._external_events.clear()


def test_post_trace_batch_rejects_unknown_source(client: TestClient) -> None:
    response = client.post(
        "/api/v1/trace/batch",
        json={"source": "browser_extension", "events": []},
    )
    # Pydantic's Literal validation surfaces as 422.
    assert response.status_code == 422


def test_post_trace_batch_no_session_token_required(
    client_with_session_token_required: TestClient,
) -> None:
    """The trace endpoint is exempted from SessionTokenMiddleware so Electron
    main (no shared cookie jar with the renderer) can POST without auth.
    Pinning this so a future refactor of the exempt list does not silently
    re-enable auth and start 403'ing every Electron flush in production."""
    response = client_with_session_token_required.post(
        "/api/v1/trace/batch",
        json={"source": "renderer", "events": []},
    )
    assert response.status_code == 204


def test_post_trace_batch_with_session_token_still_works(
    client_with_session_token_required: TestClient,
) -> None:
    """Belt-and-braces: setting the token on a request to the exempt path
    must still succeed, not be rejected for being unexpected."""
    response = client_with_session_token_required.post(
        "/api/v1/trace/batch",
        headers={SESSION_TOKEN_HEADER_NAME: "test_token"},
        json={"source": "renderer", "events": []},
    )
    assert response.status_code == 204


def test_trace_start_status_stop_roundtrip(client: TestClient) -> None:
    """Arm via HTTP, confirm status reflects it, stop, and confirm the file is
    written and the backend is left disarmed and ready to re-arm."""
    # Responses serialize with camelCase aliases (SerializableModel).
    start = client.post("/api/v1/trace/start", json={})
    assert start.status_code == 200, start.text
    output_path = Path(start.json()["outputPath"])
    assert start.json()["enabled"] is True

    status = client.get("/api/v1/trace/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is True
    assert status.json()["outputPath"] == str(output_path)

    stop = client.post("/api/v1/trace/stop")
    assert stop.status_code == 200, stop.text
    assert stop.json()["outputPath"] == str(output_path)
    assert stop.json()["backendEventCount"] > 0
    assert output_path.exists()

    after = client.get("/api/v1/trace/status")
    assert after.json()["enabled"] is False
    assert after.json()["outputPath"] is None


def test_trace_start_conflicts_when_already_running(client: TestClient) -> None:
    first = client.post("/api/v1/trace/start", json={})
    assert first.status_code == 200
    active_path = first.json()["outputPath"]
    try:
        second = client.post("/api/v1/trace/start", json={})
        assert second.status_code == 409
        # The conflict names where the already-running trace is writing.
        assert active_path in second.json()["detail"]
    finally:
        client.post("/api/v1/trace/stop")


def test_trace_stop_conflicts_when_not_running(client: TestClient) -> None:
    assert client.post("/api/v1/trace/stop").status_code == 409


def test_trace_start_rejects_out_of_range_tracer_entries(client: TestClient) -> None:
    assert client.post("/api/v1/trace/start", json={"tracer_entries": 0}).status_code == 422
    assert client.post("/api/v1/trace/start", json={"tracer_entries": 10**12}).status_code == 422
    # The rejected starts must not have armed anything.
    assert client.get("/api/v1/trace/status").json()["enabled"] is False


def test_trace_control_endpoints_require_session_token(
    client_with_session_token_required: TestClient,
) -> None:
    """Unlike /trace/batch, the control endpoints are NOT auth-exempt: an
    arbitrary-file-write + multi-GB-alloc primitive must sit behind the token."""
    assert client_with_session_token_required.post("/api/v1/trace/start", json={}).status_code == 403
    assert client_with_session_token_required.post("/api/v1/trace/stop").status_code == 403
    assert client_with_session_token_required.get("/api/v1/trace/status").status_code == 403
    assert client_with_session_token_required.get("/api/v1/debug/threads").status_code == 403


def test_debug_threads_dumps_stacks(client: TestClient) -> None:
    response = client.get("/api/v1/debug/threads")
    assert response.status_code == 200
    body = response.text
    assert "Thread dump at" in body
    # At least the thread serving this request should appear.
    assert "Thread " in body
    assert "File " in body  # traceback frames render "File ..., line ..."
    # traceback.format_stack lines already end in "\n"; the dump must not
    # double them up into blank lines between every frame (a "\n".join bug).
    assert "\n\n\n" not in body


def test_trace_file_written_on_lifespan_shutdown(
    test_settings: SculptorSettings,
    test_already_started_services: CompleteServiceCollection,
    tmp_path: Path,
) -> None:
    """The trace file must be written by the FastAPI lifespan's teardown.

    Pins the fix for the case where uvicorn handles SIGTERM/SIGINT by
    restoring the default signal handlers and re-raising the signal
    (``uvicorn.Server.capture_signals``). By the time any ``finally`` block
    around ``server.run()`` would have fired, the process is already gone.
    The lifespan's own teardown runs *during* uvicorn's normal shutdown
    sequence, before the signal re-raise, so wiring the trace write there
    is what makes signal-induced exit produce a usable artifact.

    The test drives the lifespan via ``TestClient`` (``__enter__`` starts
    it, ``__exit__`` runs the teardown) and asserts the file is present
    and well-formed after teardown.
    """
    trace_file = tmp_path / "out.json"
    tracing.start_tracing(trace_file)

    def override_get_settings() -> SculptorSettings:
        return test_settings

    def override_services_factory(
        concurrency_group: ConcurrencyGroup,
        settings: SculptorSettings = Depends(get_settings),
    ) -> CompleteServiceCollection:
        return test_already_started_services

    APP.dependency_overrides[get_settings] = override_get_settings
    APP.dependency_overrides[services_factory] = override_services_factory
    try:
        # Entering and exiting the TestClient context manager drives the
        # FastAPI lifespan start → yield → teardown, which is the path that
        # must write the trace file. No request is needed; the wiring is
        # what's under test.
        with TestClient(APP):
            pass
    finally:
        APP.dependency_overrides.clear()

    assert trace_file.exists(), "lifespan teardown must write the trace file"
    with open(trace_file) as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert isinstance(data.get("traceEvents"), list)
    assert len(data["traceEvents"]) > 0, "trace should contain at least the lifespan's own viztracer events"
