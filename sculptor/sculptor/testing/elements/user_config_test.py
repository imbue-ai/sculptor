"""Unit tests for the user-config integration-test helpers.

These lock in that ``_set_user_config_flag`` builds its ``/api/v1/config`` URL
from the backend origin resolved via :func:`resolve_backend_api_url`, never from
``page.url``. In packaged Electron builds the renderer origin is ``sculptor://app``,
which serves no ``/api`` and which Playwright's ``page.request`` refuses to fetch;
the resolver returns the backend's http origin instead. See
:mod:`sculptor.testing.backend_url` for the resolver's own tests.
"""

from typing import Any

from sculptor.testing.elements.user_config import _set_user_config_flag
from sculptor.testing.elements.user_config import enable_clone_workspaces

# A sculptor:// renderer origin, as seen in packaged Electron builds. It must
# never appear in a request URL — the fake page exposes it as ``url`` precisely
# so a regression back to ``page.url`` would surface it in the assertions below.
_RENDERER_URL = "sculptor://app/index.html#/ws/abc123"
# What the resolver's page path yields (its evaluate() mirrors apiClient.ts).
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

    ``evaluate`` returns the backend origin (what ``resolve_backend_api_url``'s
    page path yields in a real renderer). ``url`` is a ``sculptor://`` origin on
    purpose: if a helper regresses to building the API URL from the page origin,
    the recorded request URLs will carry that scheme and the assertions fail.
    Deliberately has no ``backend_api_url`` attribute, so the resolver takes the
    page (``evaluate``) path.
    """

    def __init__(self, initial_config: dict[str, Any]) -> None:
        self.url = _RENDERER_URL
        self.request = _RecordingRequestContext(initial_config)
        self.reload_count = 0
        self.load_states: list[str] = []

    def evaluate(self, _js: str) -> str:
        return _BACKEND_URL

    def reload(self) -> None:
        self.reload_count += 1

    def wait_for_load_state(self, state: str) -> None:
        self.load_states.append(state)

    def wait_for_timeout(self, _milliseconds: int) -> None:
        pass

    def get_by_test_id(self, _test_id: str) -> _FakeLocator:
        return _FakeLocator()


def test_set_user_config_flag_targets_resolved_backend_origin_not_page_url() -> None:
    page = _FakePage(initial_config={"enableCloneWorkspaces": False})

    _set_user_config_flag(page, "enableCloneWorkspaces", True)

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


def test_enable_wrapper_writes_flag_via_resolved_backend_origin() -> None:
    page = _FakePage(initial_config={"enableCloneWorkspaces": False})

    enable_clone_workspaces(page)

    put_url, put_data = page.request.put_calls[0]
    assert put_url == f"{_BACKEND_URL}/api/v1/config"
    assert put_data == {"userConfig": {"enableCloneWorkspaces": True}}
