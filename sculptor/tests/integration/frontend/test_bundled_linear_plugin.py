"""Integration test for the bundled Linear example plugin (SCU-1552).

Unlike test_plugin_loader.py — which exercises the loader against synthetic
fixture-server plugins — this targets the *real* bundled `linear-issue` plugin,
the one the host Vite build compiles into `public/plugins/`. It asserts the
built-in source both:

  1. loads — the bundle was fetched, validated, imported, and activated, and
  2. renders its own React — the plugin's settings component mounts and shows
     its content.

A broken build fails here: a bundle that throws at import (e.g. a dev-JSX build
that dragged `process.env.NODE_ENV` in) never reaches "loaded"; one that throws
at render (e.g. calling `jsxDEV` against a host that only ships the prod JSX
runtime) trips the plugin error boundary, so the settings text never appears.

Runs in both browser and electron launch modes, since the plugin ships bundled
into the served build for every mode.
"""

import pytest
from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.settings_plugins import PlaywrightPluginsSettingsElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

# The built-in source the host registers for the bundled Linear plugin.
LINEAR_SOURCE = "/plugins/linear-issue"
# Stable text from the plugin's own settings component (LinearSettings). The
# plugin error boundary would replace it on a render failure, so asserting it
# confirms the plugin's React actually ran.
LINEAR_SETTINGS_TEXT = "Personal API key from Linear"

# Linear's GraphQL endpoint the plugin's client posts to (see linear/client.ts).
# Mocked in-page so the widget renders against canned data with no real network.
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
# Test-only testids the plugin sets on its contributions.
LINEAR_API_KEY_PLACEHOLDER = "lin_api_..."
LINEAR_WIDGET_TESTID = "linear-workspace-ticket"
# The canned issue the mock returns as the workspace's (branch) ticket.
WIDGET_TICKET_ID = "SCU-1234"
_MOCK_PRIMARY_ISSUE = {
    "identifier": WIDGET_TICKET_ID,
    "title": "Banner ticket under test",
    "url": "https://linear.app/imbue/issue/SCU-1234/banner-ticket-under-test",
    "description": None,
    "priorityLabel": None,
    "state": {"name": "In Progress", "type": "started", "color": "#5e6ad2"},
    "assignee": None,
    "attachments": {"nodes": []},
}


def _mock_linear_graphql(instance: SculptorInstance) -> None:
    """Intercept the plugin's Linear GraphQL calls and answer with canned data.

    The widget resolves its ticket through ``issueVcsBranchSearch`` (the branch's
    issue); we answer that with a fixed issue so the test is independent of the
    workspace's generated branch name and needs no real Linear credentials or
    network. Any other query (the panel's PR-linked/pinned lookups, unused here)
    gets an empty payload.
    """

    def handler(route: Route) -> None:
        body = route.request.post_data or ""
        if "issueVcsBranchSearch" in body:
            route.fulfill(json={"data": {"issueVcsBranchSearch": _MOCK_PRIMARY_ISSUE}})
        else:
            route.fulfill(json={"data": {}})

    instance.page.route(LINEAR_GRAPHQL_URL, handler)


def _set_linear_api_key(plugins: PlaywrightPluginsSettingsElement, key: str) -> None:
    """Enter a Linear API key via the plugin's own settings component.

    Going through the real settings input (rather than seeding localStorage)
    drives the SDK ``usePluginSetting`` write the panel and widget both read, so
    the key is live app-wide by the time the workspace banner mounts.
    """
    plugins.open_source_settings(LINEAR_SOURCE)
    plugins.get_source_row(LINEAR_SOURCE).get_by_placeholder(LINEAR_API_KEY_PLACEHOLDER).fill(key)


def _assert_linear_plugin_loads_and_renders(plugins: PlaywrightPluginsSettingsElement) -> None:
    """The built-in Linear plugin loads, then renders its own settings React."""
    plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")
    plugins.open_source_settings(LINEAR_SOURCE)
    expect(plugins.get_source_row(LINEAR_SOURCE)).to_contain_text(LINEAR_SETTINGS_TEXT)


@pytest.mark.browser_and_electron
def test_bundled_linear_plugin_loads_and_renders(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The bundled Linear plugin loads and renders its UI in both browser and Electron.

    The per-test factory instance runs in both launch modes, so this single test
    covers the plugin's load + render in a browser and inside a real,
    non-packaged Electron shell.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        _assert_linear_plugin_loads_and_renders(plugins)


def test_bundled_linear_plugin_workspace_widget_shows_branch_ticket(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The plugin's workspace widget renders the branch ticket beside the PR button.

    Exercises the new ``registerWorkspaceWidget`` SDK surface end-to-end: with a
    Linear API key set and the Linear API mocked, the compact ticket chip the
    plugin contributes to the workspace banner resolves the branch's (primary)
    ticket and shows its identifier — the same ticket the panel defaults to.

    TODO(SCU-1495 follow-up): also cover assigning a *different* ticket from the
    panel (the assign control) and asserting the widget follows the shared
    per-workspace assignment setting. That needs a multi-ticket Linear mock (a
    primary plus a PR-linked or pinned issue), so it is left as a follow-up.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        _mock_linear_graphql(instance)

        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")
        _set_linear_api_key(plugins, "lin_api_test")

        # Create a workspace so the banner (and the contributed widget) mount.
        start_task_and_wait_for_ready(instance.page, prompt="Linear widget test", workspace_name="Linear Widget WS")

        widget = instance.page.get_by_test_id(LINEAR_WIDGET_TESTID)
        expect(widget).to_be_visible()
        expect(widget).to_contain_text(WIDGET_TICKET_ID)
