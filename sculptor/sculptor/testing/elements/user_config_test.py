"""Unit tests for the user-config integration-test helpers.

These lock in that the config REST calls target the *backend* HTTP origin,
not the renderer origin (``page.url``). In packaged Electron builds the renderer
origin is ``sculptor://app``, which serves no ``/api`` and which Playwright's
``APIRequestContext`` refuses to fetch (it only speaks ``http:``/``https:``).
Deriving the request URL from ``page.url`` therefore breaks every
config-toggling test in packaged mode, while passing in ``page.url`` still works
in the http dev lanes — a regression a green PR CI run cannot catch because that
lane never exercises the packaged origin.
"""

from typing import Any

from sculptor.testing.elements.user_config import _set_user_config_flag
from sculptor.testing.elements.user_config import enable_clone_workspaces

# A sculptor:// renderer origin, as seen in packaged Electron builds. It must
# never appear in a request URL — that is the exact bug these tests guard.
_RENDERER_URL = "sculptor://app/index.html#/ws/abc123"
_BACKEND_URL = "http://127.0.0.1:52111"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._payload = payload or {}
        self.ok = True
        self.status = 200

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _RecordingRequestContext:
    """Stands in for ``page.request``, recording the URLs it is called with."""

    def __init__(self, initial_config: dict[str, Any]) -> None:
        self._initial_config = initial_config
        self.get_urls: list[str] = []
        self.put_calls: list[tuple[str, Any]] = []

    def get(self, url: str, **_kwargs: Any) -> _FakeResponse:
        self.get_urls.append(url)
        return _FakeResponse(self._initial_config)

    def put(self, url: str, data: Any = None, **_kwargs: Any) -> _FakeResponse:
        self.put_calls.append((url, data))
        return _FakeResponse()


class _FakeLocator:
    def count(self) -> int:
        # Report "no chat input" so wait_for_tiptap_ready short-circuits without
        # touching a real Playwright editor locator.
        return 0


class _FakePage:
    """Minimal ``Page`` stand-in exercising only what the config helpers touch.

    ``url`` is deliberately a ``sculptor://`` origin: if a helper regresses to
    building the API URL from the page origin, the recorded request URLs will
    carry that scheme and the assertions below fail.
    """

    def __init__(self, initial_config: dict[str, Any]) -> None:
        self.url = _RENDERER_URL
        self.request = _RecordingRequestContext(initial_config)
        self.reload_count = 0
        self.load_states: list[str] = []

    def reload(self) -> None:
        self.reload_count += 1

    def wait_for_load_state(self, state: str) -> None:
        self.load_states.append(state)

    def wait_for_timeout(self, _milliseconds: int) -> None:
        pass

    def get_by_test_id(self, _test_id: str) -> _FakeLocator:
        return _FakeLocator()


def test_set_user_config_flag_targets_backend_origin_not_page_url() -> None:
    page = _FakePage(initial_config={"enableCloneWorkspaces": False})

    _set_user_config_flag(page, "enableCloneWorkspaces", True, backend_url=_BACKEND_URL)

    expected_url = f"{_BACKEND_URL}/api/v1/config"
    assert page.request.get_urls == [expected_url]

    put_url, put_data = page.request.put_calls[0]
    assert put_url == expected_url
    # The sculptor:// renderer origin must never leak into an API request URL.
    assert "sculptor:" not in page.request.get_urls[0]
    assert "sculptor:" not in put_url
    # The flag value is written through, and the page reloads so the frontend
    # re-reads the updated config.
    assert put_data == {"userConfig": {"enableCloneWorkspaces": True}}
    assert page.reload_count == 1


def test_set_user_config_flag_strips_trailing_slash_on_backend_url() -> None:
    page = _FakePage(initial_config={})

    _set_user_config_flag(page, "defaultFastMode", True, backend_url=_BACKEND_URL + "/")

    assert page.request.get_urls == [f"{_BACKEND_URL}/api/v1/config"]


def test_enable_wrapper_threads_backend_url_through() -> None:
    page = _FakePage(initial_config={"enableCloneWorkspaces": False})

    enable_clone_workspaces(page, backend_url=_BACKEND_URL)

    put_url, put_data = page.request.put_calls[0]
    assert put_url == f"{_BACKEND_URL}/api/v1/config"
    assert put_data == {"userConfig": {"enableCloneWorkspaces": True}}
