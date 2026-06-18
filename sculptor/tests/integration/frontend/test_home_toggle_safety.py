"""Integration test for the topbar Home button's golden-path toggle.

Clicking Home from a workspace navigates to ``/home`` (and ``aria-pressed``
flips). Clicking Home again returns the user to the workspace.

The pure-logic safety-guard cases — clicking Home with only an invisible
pseudo-tab (``__home__`` / stale ``__new_workspace_<draftId>__``) open — are
covered at the unit level in ``useHomeToggle.test.tsx``; they don't need a
browser.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to toggle between a workspace and Home with the Home button")
def test_home_button_golden_path_toggle(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking Home from a workspace navigates to /home and lights up
    aria-pressed; clicking again returns to the workspace.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Toggle Roundtrip",
    )

    # We start on the workspace.
    expect(page).to_have_url(re.compile(r".*#/ws/ws_[a-z0-9]+"))
    workspace_url_pattern = re.compile(r".*#/ws/ws_[a-z0-9]+")

    home_button = layout.get_home_button()
    expect(home_button).to_have_attribute("aria-pressed", "false")

    # Toggle ON: workspace → /home.
    home_button.click()
    expect(page).to_have_url(re.compile(r".*#/home$"))
    expect(home_button).to_have_attribute("aria-pressed", "true")

    # Toggle OFF: /home → back to the workspace. The visible workspace
    # tab is what gates the safety check through.
    expect(layout.get_workspace_tabs()).to_have_count(1)
    home_button.click()
    expect(page).to_have_url(workspace_url_pattern)
    expect(home_button).to_have_attribute("aria-pressed", "false")
