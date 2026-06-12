"""Unit tests for the connection-retry helpers in :mod:`playwright_utils`."""

import pytest
from playwright.sync_api import Error

from sculptor.testing.playwright_utils import _is_transient_connection_error
from sculptor.testing.playwright_utils import request_with_retry


def test_is_transient_connection_error_matches_socket_hang_up() -> None:
    error = Error("APIRequestContext.patch: socket hang up")
    assert _is_transient_connection_error(error) is True


def test_is_transient_connection_error_matches_econnreset() -> None:
    error = Error("APIRequestContext.get: read ECONNRESET")
    assert _is_transient_connection_error(error) is True


def test_is_transient_connection_error_rejects_unrelated_playwright_error() -> None:
    error = Error("Target page, context or browser has been closed")
    assert _is_transient_connection_error(error) is False


def test_is_transient_connection_error_rejects_non_playwright_exception() -> None:
    assert _is_transient_connection_error(ValueError("socket hang up")) is False


def test_request_with_retry_retries_dropped_connection_until_a_response_arrives() -> None:
    """A culled keep-alive connection is retried until a real response comes back."""
    fake_response = object()
    attempt_count = 0

    def flaky_request(url: str) -> object:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise Error("APIRequestContext.patch: socket hang up")
        return fake_response

    result = request_with_retry(flaky_request, "http://example.test/api")

    assert result is fake_response
    assert attempt_count == 3


def test_request_with_retry_reraises_a_non_connection_error_without_retrying() -> None:
    """An error that is not a dropped connection surfaces on the first attempt."""
    attempt_count = 0

    def failing_request(url: str) -> object:
        nonlocal attempt_count
        attempt_count += 1
        raise Error("Target page, context or browser has been closed")

    with pytest.raises(Error, match="has been closed"):
        request_with_retry(failing_request, "http://example.test/api")

    assert attempt_count == 1
