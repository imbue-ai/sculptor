"""Integration tests for the experimental Browser panel.

The Browser is a registered single-instance panel with no default section.
It is opened on demand from a workspace section's add-panel ``+`` dropdown,
exactly like the Files / Changes / Commits panels.  These tests cover the
panel's user-visible contract:

- Navigation toolbar (address bar auto-prefix, back/forward, refresh,
  in-page link sync, ``target=_blank`` containment, invalid URL safety).
- Screenshot-to-clipboard (R7).
- URL persistence across collapsing / reopening the panel (R9).
- Cross-workspace isolation: independent URLs, cookies, history (R8).
- In-page state preservation across workspace switches and route
  detours (R8 strongest form).
"""

from __future__ import annotations

import io
import re
import time
from urllib.request import urlopen

import pytest
from PIL import Image
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.browser_panel_fixture_server import BrowserPanelFixtureServer
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.browser_panel import PlaywrightBrowserPanelElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import open_settings
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"


def _open_browser_panel(page: Page) -> PlaywrightBrowserPanelElement:
    """Open (or reveal) the Browser panel in the right section and return its POM.

    The Browser is a registered single-instance panel with no default section, so
    it is opened via the section add-panel dropdown. If the active workspace
    already has it open (e.g. after a collapse, or on returning to a workspace),
    expanding the right section reveals it again with its preserved state.
    """
    root = page.get_by_test_id(ElementIDs.BROWSER_PANEL)
    if not root.is_visible():
        PlaywrightWorkspaceSection(page, "right").expand_section()
        if not root.is_visible():
            open_panel(page, "browser", "right")
    expect(root).to_be_visible()
    return PlaywrightBrowserPanelElement(locator=root, page=page)


@user_story("to smoke-check that the Browser panel fixture server serves its pages")
def test_browser_panel_fixture_server_serves_index(
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    with urlopen(f"{browser_panel_fixture_server_.base_url}/index.html", timeout=5) as response:
        body = response.read().decode("utf-8")
    assert "browser-panel-fixture-index" in body
    assert response.status == 200

    with urlopen(f"{browser_panel_fixture_server_.base_url}/tiny.png", timeout=5) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "image/png"


@pytest.mark.electron
@user_story("to open the Browser panel in the desktop app without the web-mode placeholder")
def test_browser_panel_electron_mode_hides_web_placeholder(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page)

    panel = _open_browser_panel(page)
    expect(panel.get_web_mode_placeholder()).not_to_be_visible()


@pytest.mark.electron
@user_story("to drive the Browser panel through its full navigation toolbar")
def test_browser_panel_navigation_tour(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    """End-to-end tour of the navigation contract on a single panel.

    Combines the navigate / address-bar / back-forward / refresh /
    target=_blank / fresh-state / invalid-URL cases into one long-running
    test on a single Sculptor instance.
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)

    panel = _open_browser_panel(page)
    base = browser_panel_fixture_server_.base_url
    port = browser_panel_fixture_server_.port

    expect(panel.get_back_button()).to_be_disabled()
    expect(panel.get_forward_button()).to_be_disabled()

    panel.navigate(f"127.0.0.1:{port}/index.html")
    panel.wait_for_address_bar_contains(f"http://127.0.0.1:{port}/index.html")
    assert panel.webview_evaluate("document.title") == "Browser panel fixture - index"
    assert (
        panel.webview_evaluate("document.querySelector('[data-testid=browser-panel-fixture-index]').textContent")
        == "Hello from index"
    )

    panel.navigate(f"localhost:{port}/index.html")
    panel.wait_for_address_bar_contains(f"http://localhost:{port}/index.html")

    panel.navigate(f"{base}/index.html")
    panel.wait_for_address_bar_contains(f"{base}/index.html")

    panel.webview_evaluate("document.getElementById('next-link').click()")
    panel.wait_for_address_bar_contains("/next.html")
    assert (
        panel.webview_evaluate("document.querySelector('[data-testid=browser-panel-fixture-next]').textContent")
        == "Hello from next"
    )

    expect(panel.get_back_button()).to_be_enabled()
    panel.click_back()
    panel.wait_for_address_bar_contains("/index.html")
    expect(panel.get_forward_button()).to_be_enabled()
    panel.click_forward()
    panel.wait_for_address_bar_contains("/next.html")
    expect(panel.get_forward_button()).to_be_disabled()

    panel.click_back()
    panel.wait_for_address_bar_contains("/index.html")
    panel.webview_evaluate("document.getElementById('popup-link').click()")
    panel.wait_for_address_bar_contains("/popup.html")
    assert (
        panel.webview_evaluate("document.querySelector('[data-testid=browser-panel-fixture-popup]').textContent")
        == "Hello from popup"
    )

    panel.navigate(f"{base}/index.html")
    panel.wait_for_address_bar_contains("/index.html")
    assert panel.webview_evaluate("performance.getEntriesByType('navigation')[0].type") == "navigate"
    panel.click_refresh()
    panel.wait_for_address_bar_contains("/index.html")
    deadline = time.monotonic() + 30.0
    nav_type = ""
    while time.monotonic() < deadline:
        nav_type = panel.webview_evaluate("performance.getEntriesByType('navigation')[0].type")
        if nav_type == "reload":
            break
        page.wait_for_timeout(100)
    assert nav_type == "reload"

    panel.navigate("not a url", wait_for_webview_load=False)
    expect(panel.get_root()).to_be_visible()
    expect(panel.get_url_error()).to_be_visible()
    expect(panel.get_url_input()).not_to_have_value(re.compile(r"http://"))


@pytest.mark.electron
@user_story("to land in the URL field with its contents selected, see errors on bad URLs, and load file paths")
def test_browser_panel_url_input_polish(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    """SCU-1157: polish the Browser panel's URL input.

    Verifies four UX expectations of the address bar:

    1. Opening the panel focuses the URL input (even on re-open, when the
       workspace already has a persisted URL).
    2. Focusing the URL input selects its existing text so the user can
       overwrite it without manually highlighting.
    3. Submitting an invalid URL surfaces a visible error message rather
       than navigating to a mangled ``http://not a url``.
    4. Submitting an absolute file path is normalized to a ``file://`` URL
       rather than being mis-prefixed with ``http://``.
    """
    page = sculptor_instance_.page
    base = browser_panel_fixture_server_.base_url
    start_task_and_wait_for_ready(sculptor_page=page)

    panel = _open_browser_panel(page)

    # (1) Fresh open: the URL input should hold keyboard focus so the user
    # can start typing immediately.
    expect(panel.get_url_input()).to_be_focused()

    # Navigate so the workspace has a persisted URL, then close and re-open
    # the panel.  The URL input should still receive focus on re-open even
    # though there is now a non-empty persisted URL.
    target_url = f"{base}/index.html"
    panel.navigate(target_url)
    panel.wait_for_address_bar_contains(target_url)

    PlaywrightWorkspaceSection(page, "right").collapse_section()
    expect(panel.get_root()).not_to_be_visible()
    panel = _open_browser_panel(page)
    expect(panel.get_url_input()).to_be_focused()

    # (2) Focusing the input selects its existing text.  Blur first so the
    # next focus is a real focus event the component can react to.  The
    # select() happens synchronously inside ``onFocus``, but we still use
    # ``wait_for_function`` so the assertion auto-retries rather than
    # snapshotting selection state once (see ``use_expect_not_assert`` in
    # ``docs/development/review/integration_tests.md``).
    panel.get_url_input().blur()
    panel.get_url_input().focus()
    page.wait_for_function(
        """(selector) => {
          const el = document.querySelector(selector);
          return el != null
            && el.value.length > 0
            && el.selectionStart === 0
            && el.selectionEnd === el.value.length;
        }""",
        arg=f'[data-testid="{ElementIDs.BROWSER_URL_INPUT}"]',
    )

    # (3) An invalid URL surfaces an error message and is NOT silently
    # normalized to ``http://not a url``.
    panel.get_url_input().click(click_count=3)
    panel.get_url_input().fill("not a url")
    panel.get_url_input().press("Enter")
    expect(panel.get_url_error()).to_be_visible()
    expect(panel.get_url_input()).not_to_have_value(re.compile(r"http://"))

    # (4) An absolute file path is normalized to a ``file://`` URL, not
    # ``http:///``.  We do not load the file (it does not exist) — we only
    # assert that the address bar reflects the corrected scheme.
    panel.get_url_input().click(click_count=3)
    panel.get_url_input().fill("/tmp/sculptor-scu-1157-does-not-exist.html")
    panel.get_url_input().press("Enter")
    panel.wait_for_address_bar_contains("file:///tmp/sculptor-scu-1157-does-not-exist.html")
    expect(panel.get_url_input()).not_to_have_value(re.compile(r"http://"))


@pytest.mark.electron
@user_story("to copy a screenshot of the Browser panel to the clipboard, blank or live")
def test_browser_panel_screenshot(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)

    panel = _open_browser_panel(page)

    panel.click_screenshot()
    blank_png = panel.wait_for_clipboard_png()
    assert blank_png.startswith(_PNG_MAGIC)
    blank_image = Image.open(io.BytesIO(blank_png))
    assert blank_image.width > 0
    assert blank_image.height > 0

    panel.navigate(f"{browser_panel_fixture_server_.base_url}/index.html")
    panel.click_screenshot()
    live_png = panel.wait_for_clipboard_png()
    assert live_png.startswith(_PNG_MAGIC)
    assert len(live_png) > 500
    live_image = Image.open(io.BytesIO(live_png))
    assert live_image.width > 0
    assert live_image.height > 0


@pytest.mark.electron
@user_story("to keep the Browser panel's URL when I collapse and reopen the panel")
def test_browser_panel_url_persists_across_collapse(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)

    panel = _open_browser_panel(page)
    target_url = f"{browser_panel_fixture_server_.base_url}/next.html"

    panel.navigate(target_url)
    expect(panel.get_url_input()).to_have_value(re.compile(re.escape(target_url)))

    PlaywrightWorkspaceSection(page, "right").collapse_section()
    expect(panel.get_root()).not_to_be_visible()

    panel = _open_browser_panel(page)
    expect(panel.get_url_input()).to_have_value(re.compile(re.escape(target_url)))
    assert (
        panel.webview_evaluate("document.querySelector('[data-testid=browser-panel-fixture-next]').textContent")
        == "Hello from next"
    )


@pytest.mark.electron
@user_story("to keep each workspace's Browser panel state — URL, cookies, history — fully isolated")
def test_browser_panel_cross_workspace_isolation(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    """One flow asserting URL independence, cookie isolation, cross-write
    safety, and back/forward history independence between two workspaces."""
    page = sculptor_instance_.page
    base = browser_panel_fixture_server_.base_url

    start_task_and_wait_for_ready(sculptor_page=page, workspace_name="Browser Iso A")
    start_task_and_wait_for_ready(sculptor_page=page, workspace_name="Browser Iso B")

    navigate_to_workspace(page, "Browser Iso A")
    panel_a = _open_browser_panel(page)
    panel_a.navigate(f"{base}/cookie.html?v=workspaceA")
    assert "btest=workspaceA" in panel_a.webview_evaluate("document.cookie")
    panel_a.navigate(f"{base}/index.html")
    panel_a.navigate(f"{base}/next.html")
    expect(panel_a.get_back_button()).to_be_enabled()

    navigate_to_workspace(page, "Browser Iso B")
    panel_b = _open_browser_panel(page)
    expect(panel_b.get_back_button()).to_be_disabled()
    panel_b.navigate(f"{base}/cookie.html")
    assert "workspaceA" not in panel_b.webview_evaluate("document.cookie")
    panel_b.navigate(f"{base}/cookie.html?v=workspaceB")
    cookies_b = panel_b.webview_evaluate("document.cookie")
    assert "btest=workspaceB" in cookies_b
    assert "workspaceA" not in cookies_b

    navigate_to_workspace(page, "Browser Iso A")
    panel_a = _open_browser_panel(page)
    expect(panel_a.get_url_input()).to_have_value(re.compile(r"/next\.html"))
    expect(panel_a.get_back_button()).to_be_enabled()
    panel_a.click_back()
    panel_a.wait_for_address_bar_contains("/index.html")
    panel_a.navigate(f"{base}/cookie.html")
    cookies_a = panel_a.webview_evaluate("document.cookie")
    assert "btest=workspaceA" in cookies_a
    assert "workspaceB" not in cookies_a


@pytest.mark.electron
@user_story("to keep my Browser panel's in-page state alive when I switch workspaces")
def test_browser_panel_in_page_state_preserved_across_workspace_switch(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    """In-page DOM state on workspace A's panel must survive a switch to
    workspace B and back.  This is the strongest signal that the
    underlying webContents was preserved: persisted URL alone could be
    rehydrated from an atom, but a counter incremented in the live page
    can only survive if the webContents itself was not torn down.
    """
    page = sculptor_instance_.page
    base = browser_panel_fixture_server_.base_url

    start_task_and_wait_for_ready(sculptor_page=page, workspace_name="State A")
    start_task_and_wait_for_ready(sculptor_page=page, workspace_name="State B")

    navigate_to_workspace(page, "State A")
    panel_a = _open_browser_panel(page)
    panel_a.navigate(f"{base}/counter.html")
    for _ in range(3):
        panel_a.webview_evaluate("document.getElementById('increment').click()")
    assert panel_a.webview_evaluate("document.getElementById('counter').textContent") == "3"

    navigate_to_workspace(page, "State B")
    panel_b = _open_browser_panel(page)
    panel_b.navigate(f"{base}/index.html")

    navigate_to_workspace(page, "State A")
    panel_a = _open_browser_panel(page)
    assert panel_a.webview_evaluate("document.getElementById('counter').textContent") == "3"


@pytest.mark.electron
@user_story("to keep my Browser panel's in-page state alive when I detour through a non-workspace route")
def test_browser_panel_in_page_state_preserved_across_route_detour(
    sculptor_instance_: SculptorInstance,
    browser_panel_fixture_server_: BrowserPanelFixtureServer,
) -> None:
    """In-page DOM state on a workspace's Browser panel must survive a
    detour through a non-workspace route (e.g. /settings, /ws/new).  The
    PageLayout element used by /ws/:workspaceID is a different React element
    than the one used by /settings, so react-router unmounts the entire
    workspace subtree on detour — taking the <webview> with it under the
    current "mount-and-hide" approach.

    The user-observed reproducer: open a workspace's Browser panel, click
    "+ New Workspace" (route changes to /ws/new/<draftId>), then click back
    to the original workspace.  In-page state is gone because the original
    webContents was destroyed.
    """
    page = sculptor_instance_.page
    base = browser_panel_fixture_server_.base_url

    start_task_and_wait_for_ready(sculptor_page=page, workspace_name="Detour A")

    navigate_to_workspace(page, "Detour A")
    panel_a = _open_browser_panel(page)
    panel_a.navigate(f"{base}/counter.html")
    for _ in range(3):
        panel_a.webview_evaluate("document.getElementById('increment').click()")
    assert panel_a.webview_evaluate("document.getElementById('counter').textContent") == "3"

    open_settings(page)
    expect(page.get_by_test_id(ElementIDs.SETTINGS_NAV_GENERAL)).to_be_visible()

    navigate_to_workspace(page, "Detour A")
    panel_a = _open_browser_panel(page)
    assert panel_a.webview_evaluate("document.getElementById('counter').textContent") == "3"
