"""Heavy runtime test for the bundled Linear extension (SCU-1554).

Where test_bundled_linear_extension.py (SCU-1552) only asserts the extension loads and
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

from playwright.sync_api import Page
from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_SOURCE = "/extensions/linear-issue"
API_KEY = "lin_api_test_key_1234"
# The API key field's placeholder, used to pick it out of the extension's
# settings (which also render the workspace-seed template fields).
API_KEY_FIELD_PLACEHOLDER = "lin_api_..."


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


def _open_linear_panel(page: Page) -> None:
    """Open (or reveal) the Linear extension panel in the right section.

    The Linear panel is a registered single-instance extension panel (id
    ``linear-issue``) with no default section, so ``open_panel`` brings it into the
    right section (or reveals it if already open there). Extension panels are never
    auto-placed: opening one from a section's add-panel dropdown is how a user
    opts in. Each workspace has its own layout, so this runs per workspace; on
    return to a workspace the panel is already open and is just revealed.
    """
    open_panel(page, "linear-issue", "right")


def test_linear_panel_follows_workspace_branch_and_sends_key(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The Linear panel renders the active workspace's branch issue, re-adjusts on
    workspace switch, and sends the configured API key."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        captured_auth: list[str] = []
        page.route(LINEAR_GRAPHQL_URL, _make_linear_route(captured_auth))

        # Configure the API key through the extension's settings UI — the extension
        # applies it reactively (the setting lives in a store atom shared with
        # the panel), so no reload is needed.
        settings_page = navigate_to_settings_page(page=page)
        extensions = settings_page.click_on_extensions()
        extensions.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")
        extensions.set_source_text_setting(LINEAR_SOURCE, API_KEY, placeholder=API_KEY_FIELD_PLACEHOLDER)

        right_section = PlaywrightWorkspaceSection(page, "right")

        # Workspace A: open the Linear panel, expect it to show A's branch issue.
        task_page_a = start_task_and_wait_for_ready(page, prompt="linear a", workspace_name="Linear WS A")
        branch_a = task_page_a.get_branch_name()
        _open_linear_panel(page)
        expect(right_section.get_section()).to_contain_text(f"Issue for {branch_a}")

        # Workspace B (a different branch): its own Linear panel shows B's branch
        # issue (each workspace has an independent layout).
        task_page_b = start_task_and_wait_for_ready(page, prompt="linear b", workspace_name="Linear WS B")
        branch_b = task_page_b.get_branch_name()
        assert branch_a != branch_b, f"workspaces must differ by branch (both {branch_a!r})"
        _open_linear_panel(page)
        expect(right_section.get_section()).to_contain_text(f"Issue for {branch_b}")

        # Switching back shows the first workspace's persisted panel + branch.
        navigate_to_workspace(page, "Linear WS A")
        expect(right_section.get_section()).to_contain_text(f"Issue for {branch_a}")

        # Every Linear request carried the configured API key (raw, no Bearer).
        assert captured_auth, "the Linear extension made no request"
        assert all(auth == API_KEY for auth in captured_auth), f"unexpected auth headers: {set(captured_auth)}"
