"""Integration tests for restart-MRU restoration of workspace, agent, and draft tabs.

Cold start should reproduce the user's last-active tab synchronously
from the sculptor-tabs localStorage entry: workspace + agent URL,
draft URL, or /ws/new when no MRU was ever recorded or the saved
workspace was deleted between sessions. Also covers the legacy
sculptor-tab-order → sculptor-tabs migration.
"""

import json
import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _read_sculptor_tabs(page: Page) -> dict | None:
    raw = page.evaluate("() => window.localStorage.getItem('sculptor-tabs')")
    if raw is None:
        return None
    return json.loads(raw)


def _set_sculptor_tabs(page: Page, value: dict) -> None:
    page.evaluate(
        "(payload) => window.localStorage.setItem('sculptor-tabs', payload)",
        json.dumps(value),
    )


def _hash_of(page: Page) -> str:
    """Extract the URL hash (#/...) from page.url."""
    match = re.search(r"#.*$", page.url)
    assert match is not None, f"No hash in URL {page.url}"
    return match.group(0)


@user_story("to land back on the workspace and agent I was last viewing on restart")
def test_restart_restores_active_workspace_and_agent(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The sync rootLoader should redirect to the saved /ws/<ws>/agent/<id> on cold start."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(instance.page, prompt="Hi", workspace_name="MRU Test WS")
        first_url_hash = _hash_of(instance.page)
        assert re.match(r"^#/ws/[^/]+/agent/[^/]+$", first_url_hash), first_url_hash

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        expect(page).to_have_url(
            re.compile(re.escape(first_url_hash) + "$"),
        )
        task_page = PlaywrightTaskPage(page)
        expect(task_page.get_chat_panel()).to_be_visible()


@user_story("to come back to the same /ws/new draft I was on when I quit")
def test_restart_restores_draft_tab(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """A draft (/ws/new/<draftId>) should be restored on restart, not replaced with a fresh draft."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        add_ws_page = PlaywrightAddWorkspacePage(page)
        expect(add_ws_page.get_submit_button()).to_be_visible()
        draft_url_hash = _hash_of(page)
        assert re.match(r"^#/ws/new/[^/]+$", draft_url_hash), draft_url_hash

    with sculptor_instance_factory_.spawn_instance() as instance:
        expect(instance.page).to_have_url(
            re.compile(re.escape(draft_url_hash) + "$"),
        )


@user_story("to land on /ws/new when my last workspace was deleted between sessions")
def test_restart_clears_pointer_when_workspace_deleted(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Saved active workspace that no longer exists should drop the entry and land on /ws/new."""
    bogus_ws_id = "ws_01" + "0" * 24
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        start_task_and_wait_for_ready(page, prompt="X", workspace_name="To Delete")
        # Overwrite sculptor-tabs to point at a non-existent workspace, simulating
        # the workspace being deleted in another window between sessions.
        _set_sculptor_tabs(
            page,
            {
                "order": [{"tabId": bogus_ws_id, "agentId": None}],
                "activeIndex": 0,
            },
        )

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        # The rootLoader optimistically redirects, then WorkspacePage's validation
        # effect splices the bogus entry and navigates to /ws/new.
        expect(page).to_have_url(re.compile(r"#/ws/new"))
        tabs = _read_sculptor_tabs(page)
        assert tabs is not None
        assert all(entry["tabId"] != bogus_ws_id for entry in tabs["order"]), tabs


@user_story("to start at /ws/new on a fresh install with no MRU")
def test_restart_with_no_mru_lands_on_new(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Cold start with empty localStorage should land on /ws/new/<uuid>."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        expect(instance.page).to_have_url(re.compile(r"#/ws/new/"))


@user_story("to keep my tab list when upgrading from the prior build")
def test_legacy_tab_order_migrates_to_sculptor_tabs(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Pre-seeded sculptor-tab-order should migrate into sculptor-tabs on first read."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        page.evaluate(
            """
            () => {
              window.localStorage.removeItem('sculptor-tabs');
              window.localStorage.setItem('sculptor-tab-order', JSON.stringify(['__home__']));
            }
            """
        )
        page.reload()
        # Wait for the migration to complete (sculptor-tabs present, legacy gone).
        page.wait_for_function(
            """
            () => window.localStorage.getItem('sculptor-tabs') !== null
              && window.localStorage.getItem('sculptor-tab-order') === null
            """,
        )
        snapshot = page.evaluate(
            """
            () => ({
              tabs: window.localStorage.getItem('sculptor-tabs'),
              legacy: window.localStorage.getItem('sculptor-tab-order'),
            })
            """
        )
        assert snapshot["legacy"] is None, snapshot
        parsed = json.loads(snapshot["tabs"])
        order = parsed["order"]
        assert any(entry["tabId"] == "__home__" and entry["agentId"] is None for entry in order), parsed
