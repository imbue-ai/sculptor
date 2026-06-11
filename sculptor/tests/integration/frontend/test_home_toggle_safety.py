"""Integration tests for the topbar Home button's toggle behaviour.

Two concerns covered here:

1. **Safety guard.** When the user is on ``/home`` and there are no
   *visible* workspace tabs, clicking Home (or pressing the Home
   keybinding) must be a no-op. The guard lives in ``useHomeToggle.ts``;
   the regression-prone case is a stale invisible pseudo-tab
   (``__home__`` or ``__new_workspace_<draftId>__``) lingering in
   ``tabOrderAtom`` (persisted in localStorage) — those have no
   TabDefinition in WorkspaceTabs so the user can't see them, but they
   were previously counted by the guard, letting the toggle silently
   navigate the user to a defunct ``lastNonHomeLocation``.

2. **Golden-path toggle.** Clicking Home from a workspace navigates to
   ``/home`` (and ``aria-pressed`` flips). Clicking Home again returns
   the user to the workspace.
"""

import json
import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import set_local_storage_item_with_storage_event
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to not be unexpectedly navigated into a workspace when I click Home with no tabs open")
def test_home_button_is_noop_when_only_invisible_pseudo_tab_is_open(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    # Create a workspace and visit it. Visiting populates
    # lastNonHomeLocationAtom (in-memory) with the workspace URL — this
    # is the URL the buggy toggle would navigate back to.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Toggle Trap",
    )

    # Navigate to /home. lastNonHomeLocation persists across this
    # in-app navigation (it's only cleared on a full reload).
    navigate_to_home_page(page)
    expect(page).to_have_url(re.compile(r".*#/home$"))

    # Close the workspace tab so the visible tab strip is empty. The
    # close marks the workspace as pendingClose, which removes it from
    # effectiveOpenTabIds before the API ack.
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(1)
    tab = workspace_tabs.first
    tab.hover()
    close_button = tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()
    expect(workspace_tabs).to_have_count(0)

    # Inject a stale ``__home__`` pseudo-tab into ``tabOrderAtom`` via
    # localStorage. The helper also dispatches a ``storage`` event so
    # jotai's atomWithStorage picks up the new value live — without a
    # full reload, which would clear ``lastNonHomeLocationAtom`` and
    # erase the precondition for the bug. This simulates a leftover
    # entry from an older Sculptor session: ``__home__`` has no
    # TabDefinition in WorkspaceTabs so the tab strip stays empty, but
    # ``effectiveOpenTabIdsAtom`` now contains one element.
    set_local_storage_item_with_storage_event(page, "sculptor-tab-order", json.dumps(["__home__"]))

    # The visible tab strip is still empty — the injected pseudo-tab is
    # invisible, so from the user's perspective there is "nothing to
    # toggle to".
    expect(workspace_tabs).to_have_count(0)

    # Click the Home icon.
    home_button = page.get_by_test_id(ElementIDs.HOME_BUTTON)
    home_button.click()

    # Must still be on /home. With the bug, the safety check counted
    # the invisible ``__home__`` pseudo-tab and navigated the user to
    # ``lastNonHomeLocation`` (the workspace URL).
    expect(page).to_have_url(re.compile(r".*#/home$"))


@user_story("to not be unexpectedly navigated into a workspace when stale draft tabs linger from older sessions")
def test_home_button_is_noop_when_only_stale_new_workspace_pseudo_tab_is_open(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The other invisible-pseudo-tab variant: a stale
    ``__new_workspace_<draftId>__`` left over from a pre-modal session.
    Same regression risk as the ``__home__`` case.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Stale Draft Trap",
    )

    navigate_to_home_page(page)
    expect(page).to_have_url(re.compile(r".*#/home$"))

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(1)
    tab = workspace_tabs.first
    tab.hover()
    tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON).click()
    expect(workspace_tabs).to_have_count(0)

    set_local_storage_item_with_storage_event(
        page, "sculptor-tab-order", json.dumps(["__new_workspace_legacy-draft__"])
    )

    expect(workspace_tabs).to_have_count(0)
    page.get_by_test_id(ElementIDs.HOME_BUTTON).click()
    expect(page).to_have_url(re.compile(r".*#/home$"))


@user_story("to also have the Home keybinding be a no-op when there are no tabs open")
def test_home_keybinding_is_noop_when_only_invisible_pseudo_tab_is_open(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The Home keybinding (Meta+.) and the topbar Home button share
    one ``useHomeToggle`` instance, so the safety guard should apply
    equally. This pins down the keybinding path so a future refactor
    that splits them can't reintroduce the bug on one surface only.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Keybinding Trap",
    )

    navigate_to_home_page(page)
    expect(page).to_have_url(re.compile(r".*#/home$"))

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    workspace_tabs.first.hover()
    workspace_tabs.first.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON).click()
    expect(workspace_tabs).to_have_count(0)

    set_local_storage_item_with_storage_event(page, "sculptor-tab-order", json.dumps(["__home__"]))
    expect(workspace_tabs).to_have_count(0)

    # Blur first so the keybinding handler isn't swallowed by an input.
    blur_active_element(page)
    mod = get_playwright_modifier_key()
    page.keyboard.press(f"{mod}+Period")

    expect(page).to_have_url(re.compile(r".*#/home$"))


@user_story("to toggle between a workspace and Home with the Home button")
def test_home_button_golden_path_toggle(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking Home from a workspace navigates to /home and lights up
    aria-pressed; clicking again returns to the workspace.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Toggle Roundtrip",
    )

    # We start on the workspace.
    expect(page).to_have_url(re.compile(r".*#/ws/ws_[a-z0-9]+"))
    workspace_url_pattern = re.compile(r".*#/ws/ws_[a-z0-9]+")

    home_button = page.get_by_test_id(ElementIDs.HOME_BUTTON)
    expect(home_button).to_have_attribute("aria-pressed", "false")

    # Toggle ON: workspace → /home.
    home_button.click()
    expect(page).to_have_url(re.compile(r".*#/home$"))
    expect(home_button).to_have_attribute("aria-pressed", "true")

    # Toggle OFF: /home → back to the workspace. The visible workspace
    # tab is what gates the safety check through.
    expect(page.get_by_test_id(ElementIDs.WORKSPACE_TAB)).to_have_count(1)
    home_button.click()
    expect(page).to_have_url(workspace_url_pattern)
    expect(home_button).to_have_attribute("aria-pressed", "false")
