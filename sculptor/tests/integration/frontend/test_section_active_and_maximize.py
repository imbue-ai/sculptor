"""Integration tests for the active section, ring pulse, and maximize/restore
(SEC-09..16, SEC-21, SPLIT-06).

The logical active section persists; the transient active-section RING flashes only on
a deliberate jump (a keyboard cycle / add / drop), never on a plain click. Maximizing a
section makes it cover the content: the workspace header is hidden while the section's
own header (with its maximize/restore toggle) stays. A maximized split shows only one
sub-section. Maximize is not persisted across a reload (SEC-21).

Layouts are arranged by clicking the real UI (expand sections via the controls, add
panels via the ``+`` dropdown, split via the panel context menu).
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.section_helpers import cycle_sections
from sculptor.testing.elements.section_helpers import maximize_active_section
from sculptor.testing.elements.section_helpers import toggle_section_via_hotkey
from sculptor.testing.elements.section_split import PlaywrightSectionSplit
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_RELOAD_TRANSIENT_SKIP_REASON = "SEC-21 (reload clears maximize) can't be exercised here: a hard browser reload is ratchet-blocked, and soft_reload_page is a same-document hash navigation that keeps the JS context so the non-persisted maximize atom never resets; the transient guarantee is structural (a plain non-persisted atom) and unit-tested in Phase 1."


@user_story("to set a section active by clicking it, without a ring flash")
def test_plain_click_sets_active_without_ring(sculptor_instance_: SculptorInstance) -> None:
    """A plain click sets the section active but does NOT pulse the ring (SEC-09/10)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Click Active WS")

    # Expand the right section and give it a panel so its body is content (not the
    # empty-state launcher buttons), then there are two active-able sections.
    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    open_panel(page, "files", "right")
    center = PlaywrightWorkspaceSection(page, "center")

    # Make the center the active section first (a panel-tab click bubbles a plain
    # pointer-down that sets its section active without a ring flash).
    center.get_active_tab().click()
    expect(center.get_active_ring()).to_have_attribute("data-active", "true")

    # Plain-click the right section's tab -> the right section becomes active silently.
    right.get_panel_tab("files").click()
    expect(right.get_active_ring()).to_have_attribute("data-active", "true")
    # A plain click must not set the transient ring-visible hook.
    expect(right.get_active_ring()).not_to_have_attribute("data-ring-visible", "true")
    expect(center.get_active_ring()).not_to_have_attribute("data-active", "true")


@user_story("to see the active-section ring flash when I cycle sections with the keyboard")
def test_cycle_sections_pulses_ring(sculptor_instance_: SculptorInstance) -> None:
    """The section-cycle hotkey sets a section active AND pulses its ring (SEC-11/12)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Cycle Ring WS")

    # Expand the right section and give it a panel so the cycle has another active-able
    # section to land on.
    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    open_panel(page, "files", "right")
    center = PlaywrightWorkspaceSection(page, "center")

    # Make the center active first, so the next-section cycle deterministically lands on
    # the right section (order is center -> right).
    center.get_active_tab().click()
    expect(center.get_active_ring()).to_have_attribute("data-active", "true")

    # Cycle to the next section -> it becomes active and its ring pulses visible.
    cycle_sections(page, "next")
    right_ring = right.get_active_ring()
    expect(right_ring).to_have_attribute("data-active", "true")
    # The ring fades after ~2s; assert it pulsed visible shortly after the jump (do not
    # assert the fade timing precisely).
    expect(right_ring).to_have_attribute("data-ring-visible", "true")


@user_story("to maximize a section so it covers the workspace content")
def test_maximize_hides_workspace_header_and_restore(sculptor_instance_: SculptorInstance) -> None:
    """Maximizing hides the workspace header but keeps the section header; restore brings it back (SEC-13/14/15)."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Maximize WS")
    center = PlaywrightWorkspaceSection(page, "center")
    expect(task_page.get_workspace_header()).to_be_visible()

    # Maximize the center section.
    center.maximize()
    # The workspace header is hidden while maximized; the section's own header stays.
    expect(task_page.get_workspace_header()).to_have_count(0)
    expect(center.get_header()).to_be_visible()

    # Restore -> the workspace header returns.
    center.restore()
    expect(task_page.get_workspace_header()).to_be_visible()
    expect(center.get_header()).to_be_visible()


@user_story("to maximize the active section with the keyboard")
def test_maximize_via_hotkey(sculptor_instance_: SculptorInstance) -> None:
    """The maximize hotkey maximizes the active section and toggles it back (SEC-15)."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Maximize Hotkey WS")
    center = PlaywrightWorkspaceSection(page, "center")
    expect(task_page.get_workspace_header()).to_be_visible()

    maximize_active_section(page)
    expect(center.get_active_ring()).to_have_attribute("data-maximized", "true")
    expect(task_page.get_workspace_header()).to_have_count(0)

    # Toggle the hotkey again -> restore.
    maximize_active_section(page)
    expect(center.get_active_ring()).not_to_have_attribute("data-maximized", "true")
    expect(task_page.get_workspace_header()).to_be_visible()


@user_story("to leave the maximized view when I collapse the section that is maximized")
def test_collapse_maximized_section_exits_maximize(sculptor_instance_: SculptorInstance) -> None:
    """Collapsing the maximized section also exits the maximize.

    While a section is maximized the workspace header (with its collapse toggles)
    is hidden, but the section-toggle hotkey still works. Collapsing the maximized
    section must restore the normal grid — otherwise the maximize would keep
    showing a full-screen view of a section the layout says is closed.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Collapse Maximized WS")

    # Expand the left section (Files/Changes/Commits are seeded there) and maximize it.
    left = PlaywrightWorkspaceSection(page, "left")
    left.expand_section()
    left.maximize()
    expect(task_page.get_workspace_header()).to_have_count(0)

    # Collapse the maximized section via its hotkey (the only collapse control
    # reachable while maximized).
    toggle_section_via_hotkey(page, "left")

    # The maximize is exited and the section is collapsed: the workspace header and
    # the center section are back, and the left section is gone entirely.
    expect(task_page.get_workspace_header()).to_be_visible()
    expect(PlaywrightWorkspaceSection(page, "center").get_section()).to_be_visible()
    expect(left.get_header()).to_have_count(0)
    expect(left.get_section()).to_have_count(0)


@user_story("to come back to a workspace and find it maximized the way I left it")
def test_maximize_is_tracked_per_workspace_across_switches(sculptor_instance_: SculptorInstance) -> None:
    """Each workspace remembers its own maximize while the app is open.

    Maximize the center in workspace A, create/switch to workspace B (which must
    render the normal grid — A's maximize must not leak into it), then return to
    A: it is still maximized exactly as left. B stays unmaximized on a second
    visit too.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Maximize Per WS A")
    center = PlaywrightWorkspaceSection(page, "center")
    center.maximize()
    expect(task_page.get_workspace_header()).to_have_count(0)

    # Workspace B starts in the normal grid — no leaked maximize.
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Maximize Per WS B")
    expect(task_page.get_workspace_header()).to_be_visible()

    # Back to A: still maximized.
    navigate_to_workspace(page, "Maximize Per WS A")
    expect(task_page.get_workspace_header()).to_have_count(0)
    expect(center.get_header()).to_be_visible()

    # Back to B: still the normal grid.
    navigate_to_workspace(page, "Maximize Per WS B")
    expect(task_page.get_workspace_header()).to_be_visible()


@user_story("to see only one sub-section when I maximize a split section")
def test_maximized_split_shows_one_subsection(sculptor_instance_: SculptorInstance) -> None:
    """A maximized split section renders only its primary half (SPLIT-06).

    Split the center (a Notes panel moved into the secondary half), then maximize:
    only the primary sub-section renders, so the secondary's header is gone.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Maximized Split WS")
    center = PlaywrightWorkspaceSection(page, "center")

    # Open a Notes panel and split it into the secondary half (a Notes panel, not the
    # agent, to stay within the single active-stream limit — see AGENT-03/05). Notes is
    # not seeded into the default layout, so opening it via the section ``+`` genuinely
    # lands it in the center (the seeded Files/Changes/Commits stay in the left section).
    open_panel(page, "notes", "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    split = PlaywrightSectionSplit(page, "center")
    split.create_split("notes", "vertical")
    secondary = split.get_subsection("secondary")
    expect(secondary.get_header()).to_be_visible()

    # Maximize the primary half -> only the primary sub-section renders.
    primary = split.get_subsection("primary")
    primary.maximize()
    expect(primary.get_header()).to_be_visible()
    expect(secondary.get_header()).to_have_count(0)


@pytest.mark.skip(reason=_RELOAD_TRANSIENT_SKIP_REASON)
@user_story("to have a maximized section reset to normal after a reload")
def test_maximize_not_persisted_across_reload(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder for SEC-21 (maximize is transient — a reload clears it).

    Can't be exercised in this harness: a hard browser reload is ratchet-blocked, and
    ``soft_reload_page`` is a same-document hash navigation (the app is hash-routed) that
    keeps the JS context alive, so the non-persisted ``maximizedSectionAtom`` never
    resets. The transient guarantee is structural — maximize is a plain atom that is
    never routed through the persistence adapter — and is covered by the Phase-1
    transient-atom unit tests.
    """
