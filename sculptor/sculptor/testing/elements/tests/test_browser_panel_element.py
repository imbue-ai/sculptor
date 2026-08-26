"""Unit tests for the Browser panel page object's webview-execute retry.

These exercise ``PlaywrightBrowserPanelElement.webview_evaluate`` against a
fake Playwright ``Page`` so the transient-vs-fatal retry policy is verified
without an Electron runtime. The integration coverage lives in
``sculptor/tests/integration/frontend/test_browser_panel.py``; this is the
fast, deterministic guard on the flake-hardening logic itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from sculptor.testing.elements import browser_panel
from sculptor.testing.elements.browser_panel import PlaywrightBrowserPanelElement


class _FakePage:
    """Minimal stand-in for a Playwright ``Page``.

    ``evaluate`` delegates the webview-execute call to ``execute_side_effect``,
    which a test supplies to raise transient/fatal errors before (optionally)
    returning a value. ``wait_for_timeout`` is a no-op so the retry loop spins
    at full speed.
    """

    def __init__(self, execute_side_effect: list[Any]) -> None:
        self._execute_side_effect = list(execute_side_effect)
        self.execute_calls = 0

    def evaluate(self, js: str, *args: Any) -> Any:
        self.execute_calls += 1
        # Consume outcomes in order, but repeat the final one indefinitely so a
        # test can model a transient that never clears without sizing a list to
        # the (timing-dependent) number of retries.
        outcome = (
            self._execute_side_effect.pop(0) if len(self._execute_side_effect) > 1 else self._execute_side_effect[0]
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def wait_for_timeout(self, _ms: int) -> None:
        return None


def _make_panel(page: _FakePage) -> PlaywrightBrowserPanelElement:
    # These tests exercise only webview_evaluate's execute-retry loop. Attach
    # resolution (which reads the panel's data-webview-content-id off a real
    # locator) is stubbed to a fixed webContentsId so the locator is never
    # touched and the execute outcomes drive the test.
    panel = PlaywrightBrowserPanelElement(locator=None, page=page)  # type: ignore[arg-type]
    panel._attached_content_id = lambda: 42  # type: ignore[method-assign]
    return panel


def test_webview_evaluate_returns_value_on_first_success() -> None:
    page = _FakePage(["ok"])
    panel = _make_panel(page)
    assert panel.webview_evaluate("document.title") == "ok"
    assert page.execute_calls == 1


def test_webview_evaluate_retries_transient_then_succeeds() -> None:
    # Two "guest not ready" rejections, then success — the helper should ride
    # through the transient window rather than failing on the first one.
    transient = RuntimeError("Error invoking remote method: Script failed to execute")
    page = _FakePage([transient, transient, "3"])
    panel = _make_panel(page)
    assert panel.webview_evaluate("counter.textContent") == "3"
    assert page.execute_calls == 3


def test_webview_evaluate_reraises_fatal_immediately() -> None:
    # A non-transient error (a real bug in the evaluated code) must surface at
    # once, not be masked by the retry budget.
    page = _FakePage([ValueError("ReferenceError: foo is not defined")])
    panel = _make_panel(page)
    with pytest.raises(ValueError, match="foo is not defined"):
        panel.webview_evaluate("foo()")
    assert page.execute_calls == 1


def test_webview_evaluate_reraises_transient_after_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    # A transient that never clears is re-raised once the budget is spent, so a
    # genuinely stuck bridge still fails (loudly) instead of hanging forever.
    monkeypatch.setattr(browser_panel, "_WEBVIEW_EXECUTE_RETRY_SECONDS", 0.05)
    transient = RuntimeError("browser panel test bridge not available")
    page = _FakePage([transient])
    panel = _make_panel(page)
    with pytest.raises(RuntimeError, match="bridge not available"):
        panel.webview_evaluate("document.title")
    assert page.execute_calls >= 1
