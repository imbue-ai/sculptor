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

from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
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
    layout = PlaywrightProjectLayoutPage(page=page)

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
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)
    layout.close_workspace_tab(0)
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

    # With only an invisible pseudo-tab open, the toggle has nowhere to
    # go, so useHomeToggle marks it a no-op and the Home button reflects
    # the gate via ``aria-disabled`` rather than swallowing a click. If
    # the invisible ``__home__`` pseudo-tab were wrongly counted as
    # visible, the button would be enabled — so this directly pins the
    # safety guard.
    home_button = layout.get_home_button()
    expect(home_button).to_be_disabled()

    # And we're still on /home — the invisible pseudo-tab did not sneak
    # the user back into the stale ``lastNonHomeLocation`` (workspace URL).
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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Stale Draft Trap",
    )

    navigate_to_home_page(page)
    expect(page).to_have_url(re.compile(r".*#/home$"))

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(1)
    layout.close_workspace_tab(0)
    expect(workspace_tabs).to_have_count(0)

    set_local_storage_item_with_storage_event(
        page, "sculptor-tab-order", json.dumps(["__new_workspace_legacy-draft__"])
    )

    expect(workspace_tabs).to_have_count(0)
    # Same guard as the ``__home__`` case: the invisible draft pseudo-tab
    # leaves nothing to toggle to, so the Home button is disabled.
    expect(layout.get_home_button()).to_be_disabled()
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
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello",
        workspace_name="Keybinding Trap",
    )

    navigate_to_home_page(page)
    expect(page).to_have_url(re.compile(r".*#/home$"))

    workspace_tabs = layout.get_workspace_tabs()
    layout.close_workspace_tab(0)
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
