"""Heavy runtime test for the bundled Linear plugin (SCU-1554).

Where test_bundled_linear_plugin.py (SCU-1552) only asserts the plugin loads and
renders its empty state, this exercises it against canned Linear data. It
intercepts `https://api.linear.app/graphql` with Playwright and returns an issue
whose title echoes the *queried branch*, then asserts:

  - The Linear panel queries the current workspace's branch and renders that
    branch's issue — and re-adjusts when the active workspace changes (proves
    the `useCurrentWorkspace` branch hook drives the per-branch query).
  - Every request carries the configured API key in its Authorization header.

Browser launch mode: the behavior is mode-independent, and SCU-1552 already
covers cross-mode loading.
"""

import json
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.elements.panels import ensure_right_area_visible
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.resources import _default_sculptor_folder_populator
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_SOURCE = "/plugins/linear-issue"
API_KEY = "lin_api_test_key_1234"


def _enable_frontend_plugins_populator(folder_path: Path) -> None:
    """Seed the per-test sculptor folder with ``enable_frontend_plugins=True``."""
    _default_sculptor_folder_populator(folder_path)
    config_path = folder_path / "internal" / "config.toml"
    config = load_config(config_path).model_copy(update={"enable_frontend_plugins": True})
    save_config(config, config_path)


def _make_linear_route(captured_auth: list[str]):
    """A page.route handler that fakes Linear: echo the queried branch into the
    issue title and record each request's Authorization header. Every
    api.linear.app request is fulfilled locally so nothing hits the network."""

    def handle(route: Route) -> None:
        request = route.request
        captured_auth.append(request.headers.get("authorization", ""))
        body = request.post_data_json or {}
        query = body.get("query") or ""
        branch = (body.get("variables") or {}).get("branch")
        if "issueVcsBranchSearch" in query and branch:
            issue = {
                "identifier": "SCU-9999",
                "title": f"Issue for {branch}",
                "url": "https://linear.app/imbue/issue/SCU-9999",
                "description": None,
                "priorityLabel": None,
                "state": None,
                "assignee": None,
                "attachments": {"nodes": []},
            }
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"data": {"issueVcsBranchSearch": issue}}),
            )
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"data": {}}))

    return handle


def _activate_linear_panel(page: Page, zones: PlaywrightPanelZonesElement) -> None:
    """Reveal the right area and make the Linear panel the active top-right panel."""
    ensure_right_area_visible(page)
    zones.activate_plugin_panel("linear-issue")


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_linear_panel_follows_workspace_branch_and_sends_key(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The Linear panel renders the active workspace's branch issue, re-adjusts on
    workspace switch, and sends the configured API key."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        captured_auth: list[str] = []
        page.route(LINEAR_GRAPHQL_URL, _make_linear_route(captured_auth))

        # Configure the API key through the plugin's settings UI — the plugin
        # applies it reactively (the setting lives in a store atom shared with
        # the panel), so no reload is needed.
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()
        plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")
        plugins.set_source_text_setting(LINEAR_SOURCE, API_KEY)

        zones = PlaywrightPanelZonesElement(page)

        # Workspace A: open the panel, expect it to show A's branch issue.
        task_page_a = start_task_and_wait_for_ready(page, prompt="linear a", workspace_name="Linear WS A")
        branch_a = task_page_a.get_branch_name()
        _activate_linear_panel(page, zones)
        expect(zones.get_top_right_zone()).to_contain_text(f"Issue for {branch_a}")

        # Workspace B (a different branch): the already-open panel must follow the
        # newly-active workspace and show B's branch issue.
        task_page_b = start_task_and_wait_for_ready(page, prompt="linear b", workspace_name="Linear WS B")
        branch_b = task_page_b.get_branch_name()
        assert branch_a != branch_b, f"workspaces must differ by branch (both {branch_a!r})"
        expect(zones.get_top_right_zone()).to_contain_text(f"Issue for {branch_b}")

        # Switching back re-adjusts the panel to the first workspace's branch.
        task_page_a.get_workspace_tabs().first.click()
        expect(zones.get_top_right_zone()).to_contain_text(f"Issue for {branch_a}")

        # Every Linear request carried the configured API key (raw, no Bearer).
        assert captured_auth, "the Linear plugin made no request"
        assert all(auth == API_KEY for auth in captured_auth), f"unexpected auth headers: {set(captured_auth)}"
