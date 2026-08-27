"""Unit tests for :func:`resolve_backend_api_url`.

These lock in that the backend origin used by ``page.request`` helpers is an
``http`` origin — taken from the ``SculptorInstance`` directly, or resolved by
the renderer's own logic — and never the raw renderer origin (``sculptor://app``
in packaged builds), which ``page.request`` rejects with an opaque
"Protocol \"sculptor:\" not supported" error.
"""

import pytest

from sculptor.testing.backend_url import _RESOLVE_BACKEND_URL_JS
from sculptor.testing.backend_url import resolve_backend_api_url


class _FakeInstance:
    """Stands in for a ``SculptorInstance``: carries ``backend_api_url``.

    ``evaluate`` raises so the tests prove the instance path never touches the
    renderer — it returns the exact origin the harness started the backend on.
    """

    def __init__(self, backend_api_url: str) -> None:
        self.backend_api_url = backend_api_url

    def evaluate(self, _js: str) -> str:
        raise AssertionError("resolve_backend_api_url must not evaluate JS when given an instance")


class _FakePage:
    """Stands in for a ``Page``: has ``evaluate()`` and no ``backend_api_url``."""

    def __init__(self, evaluate_result: object) -> None:
        self._evaluate_result = evaluate_result
        self.evaluated_js: str | None = None

    def evaluate(self, js: str) -> object:
        self.evaluated_js = js
        return self._evaluate_result


def test_instance_path_returns_backend_api_url_without_evaluating() -> None:
    instance = _FakeInstance(backend_api_url="http://127.0.0.1:9876")
    assert resolve_backend_api_url(instance) == "http://127.0.0.1:9876"


def test_instance_path_strips_trailing_slash() -> None:
    instance = _FakeInstance(backend_api_url="http://127.0.0.1:9876/")
    assert resolve_backend_api_url(instance) == "http://127.0.0.1:9876"


def test_page_path_returns_evaluated_http_origin() -> None:
    page = _FakePage(evaluate_result="http://127.0.0.1:8123")
    assert resolve_backend_api_url(page) == "http://127.0.0.1:8123"
    # It resolved through the renderer's own logic, not by parsing page.url.
    assert page.evaluated_js is _RESOLVE_BACKEND_URL_JS


def test_page_path_strips_trailing_slash() -> None:
    page = _FakePage(evaluate_result="http://127.0.0.1:8123/")
    assert resolve_backend_api_url(page) == "http://127.0.0.1:8123"


def test_page_path_rejects_non_http_origin() -> None:
    # If the preload bridge is renamed and the fallback lands on the renderer
    # origin, fail loudly rather than hand back a sculptor:// URL that
    # page.request would reject with an opaque "Protocol not supported" error.
    page = _FakePage(evaluate_result="sculptor://app")
    with pytest.raises(AssertionError, match="apiClient.ts"):
        resolve_backend_api_url(page)


def test_resolution_js_is_defensive_against_the_auto_update_mock() -> None:
    """The JS must feature-detect AND try/catch each bridge method.

    A real browser is needed to execute the JS, so this pins its *structure*:
    ``auto_update_mock.py`` injects a stub ``window.sculptor`` whose
    ``getBackendPort()`` throws and which has no ``getBackendUrl``, so a naive
    ``window.sculptor ? bridge : origin`` guard would take the bridge branch and
    throw, breaking every browser-mode test running with that mock. Requiring a
    ``typeof`` check, a ``catch``, and a ``location.origin`` fallback keeps that
    path safe.
    """
    js = _RESOLVE_BACKEND_URL_JS
    assert "typeof bridge.getBackendUrl === 'function'" in js
    assert "typeof bridge.getBackendPort === 'function'" in js
    assert js.count("catch") >= 2
    assert "window.location.origin" in js


def test_resolution_js_uses_127_0_0_1_not_localhost() -> None:
    """The local-port branch must build a 127.0.0.1 URL, never localhost.

    page.request authenticates via the session-token cookie, which the harness
    scopes to 127.0.0.1; a localhost URL would send no cookie and 403 against a
    token-protected (packaged) backend. See _RESOLVE_BACKEND_URL_JS.
    """
    js = _RESOLVE_BACKEND_URL_JS
    assert "http://127.0.0.1:${port}" in js
    assert "localhost" not in js
