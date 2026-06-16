"""Integration tests for restart-MRU restoration of workspace and agent state.

Cold start should reproduce the user's last-active tab synchronously from
the sculptor-tabs localStorage entry: workspace + agent URL, or fall back
to /home when no MRU was ever recorded or the saved workspace was deleted
between sessions. On /home an empty workspace list renders the inline
new-workspace form. Also covers the legacy sculptor-tab-order →
sculptor-tabs migration.

``spawn_instance`` lands directly on ``/#/home`` to bypass the rootLoader.
These tests fire the loader explicitly via ``trigger_root_loader`` to
exercise the restoration logic that is the actual subject under test.
"""

import json
import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import trigger_root_loader
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_RESTART_TIMEOUT_MS = 10_000


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
        # spawn_instance lands on /#/home — fire the rootLoader explicitly so
        # it can read sculptor-tabs.activeIndex and redirect to the saved
        # workspace URL.
        trigger_root_loader(page)
        expect(page).to_have_url(
            re.compile(re.escape(first_url_hash) + "$"),
            timeout=_RESTART_TIMEOUT_MS,
        )
        # Chat panel renders without a Spinner gap because rootLoader is synchronous.
        expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible(timeout=_RESTART_TIMEOUT_MS)


# ``test_restart_restores_draft_tab`` was removed with the modal migration.
# Draft pseudo-tabs (``__new_workspace_<id>__`` mapped to ``/ws/new/<id>``)
# no longer exist — the modal is a true overlay that doesn't persist as a
# tab entry. ``test_restart_with_no_mru_lands_on_home`` below covers the
# empty-MRU equivalent.


@user_story("to land on /home when my last workspace was deleted between sessions")
def test_restart_clears_pointer_when_workspace_deleted(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Saved active workspace that no longer exists should drop the entry and land on /home."""
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
        # spawn_instance lands on /#/home; trigger the rootLoader explicitly
        # so it can attempt to restore the bogus workspace, fail, and fall
        # back to /home.
        trigger_root_loader(page)
        # The rootLoader optimistically redirects to the saved workspace, then
        # WorkspacePage's validation effect splices the bogus entry and
        # navigates to /home.
        expect(page).to_have_url(re.compile(r"#/home"), timeout=_RESTART_TIMEOUT_MS)
        tabs = _read_sculptor_tabs(page)
        assert tabs is not None
        assert all(entry["tabId"] != bogus_ws_id for entry in tabs["order"]), tabs


@user_story("to land on /home with the inline new-workspace form on a fresh install")
def test_restart_with_no_mru_lands_on_home(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Cold start with empty localStorage should land on /home, where an empty
    workspace list renders the inline new-workspace form."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        # Wipe sculptor-tabs to simulate a truly fresh install (spawn_instance
        # already bypasses the rootLoader, so the localStorage is preserved
        # from any prior test in the same factory unless we clear it).
        page.evaluate("() => window.localStorage.removeItem('sculptor-tabs')")
        trigger_root_loader(page)
        expect(page).to_have_url(re.compile(r"#/home$"), timeout=_RESTART_TIMEOUT_MS)
        expect(page.get_by_test_id(ElementIDs.HOME_NEW_WORKSPACE_FORM)).to_be_visible(timeout=_RESTART_TIMEOUT_MS)


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
            timeout=_RESTART_TIMEOUT_MS,
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
