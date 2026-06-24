"""Integration tests for per-workspace layout persistence (PERSIST-01/03/05).

A workspace's arrangement (section expand/collapse, open panels, active panel) is
persisted per workspace through the localStorage layout adapter (Tasks 1.2/6.1) and
restored on a fresh load — and one workspace's changes never leak into another's
(PERSIST-05 isolation).

These arrange a layout by clicking the real UI (expand a section), then verify it
survives a full frontend reload (PERSIST-03) and that a second workspace keeps the
seeded default while the first keeps its change (PERSIST-01/05). The reload uses
``full_spa_reload`` (about:blank teardown → fresh load), which clears every in-memory
Jotai atom so the layout is rebuilt purely from localStorage — the same persist →
fresh-load → restore loop a process restart exercises (the layout is frontend-only, so
a backend restart is orthogonal to it).
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _workspace_hash(page: Page) -> str:
    """The current workspace's route hash (e.g. ``#/ws/<id>/agent/<taskId>``)."""
    return "#" + page.url.split("#", 1)[1]


@user_story("to find my workspace arranged exactly as I left it after a reload")
def test_layout_persists_across_reload(sculptor_instance_: SculptorInstance) -> None:
    """A section-expand change survives a full frontend reload (PERSIST-03).

    Expand the (default-collapsed) right section, force a full SPA reload back into the
    same workspace, and assert the right section is still expanded — the arrangement was
    persisted to localStorage and restored, not re-seeded to the default.
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Persist Reload WS")

    right = PlaywrightWorkspaceSection(page, "right")
    # Default-collapsed; expanding it is the persisted change.
    expect(right.get_header()).to_have_count(0)
    right.expand_section()
    expect(right.get_header()).to_be_visible()

    full_spa_reload(page, target_hash=_workspace_hash(page))
    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible(timeout=60_000)

    # Restored from localStorage: the right section is still expanded (not re-collapsed
    # by a default re-seed).
    expect(PlaywrightWorkspaceSection(page, "right").get_header()).to_be_visible()


@user_story("to keep each workspace's layout independent from the others")
def test_per_workspace_layout_is_isolated(sculptor_instance_: SculptorInstance) -> None:
    """One workspace's layout change does not affect another's (PERSIST-01/05).

    Expand the right section in workspace A, create workspace B (which keeps the seeded
    default — right collapsed), then return to A and confirm A still has the right
    section expanded. A's change neither leaked into B nor was lost on the round trip.
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Isolated A WS")

    right_a = PlaywrightWorkspaceSection(page, "right")
    right_a.expand_section()
    expect(right_a.get_header()).to_be_visible()

    # Create a second workspace; it seeds its OWN default (right collapsed).
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Isolated B WS")
    expect(PlaywrightWorkspaceSection(page, "right").get_header()).to_have_count(0)

    # Back to A: its right section is still expanded (isolated + persisted).
    navigate_to_workspace(page, "Isolated A WS")
    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible(timeout=60_000)
    expect(PlaywrightWorkspaceSection(page, "right").get_header()).to_be_visible()
