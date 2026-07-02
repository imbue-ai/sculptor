"""Integration tests for the empty first-run page.

When the workspace list is genuinely empty, the app gate (``EmptyFirstRunGate``)
renders ``EmptyFirstRunPage`` in place of every route: the sidebar (open) plus
the new-workspace form inline in a card. The first prompt defaults to the
``/sculptor:help`` action text; the sidebar shows the empty-state
"Add a repo" / "No workspaces yet" affordances; Cmd+K and the global
shortcuts are off so only the form + Settings are reachable; and
creating the first workspace navigates to the full workspace page.

These tests need a genuinely zero-workspace instance. The shared
``sculptor_instance_`` already deletes every workspace in its per-test cleanup
and lands on the first-run state, so ``sculptor_instance_empty_first_run_`` only
waits for the gate to settle on the empty page before each test.
"""

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.empty_first_run import PlaywrightEmptyFirstRun
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import delete_project_via_settings
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

HELP_PROMPT_PREFILL = "/sculptor:help I just set up Sculptor for the first time. What should I know to get started?"

_ADD_REPO_SKIP_REASON = "The no-repos 'Add a repo' state needs the only repo removed via Settings, but reaching Settings from the empty-first-run page is a harness-nav interaction (navigate_to_settings_page can't find the gear when the empty page's sidebar is collapsed); the no-workspaces hint half of the empty-sidebar behaviour is covered by test_sidebar_shows_no_workspaces_hint."


@user_story("to land on the inline new-workspace form when I have no workspaces yet")
def test_empty_state_shows_inline_form(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """With zero workspaces the empty first-run page renders the inline form."""
    page = sculptor_instance_empty_first_run_.page
    empty = PlaywrightEmptyFirstRun(page)

    expect(empty.get_page()).to_be_visible()
    expect(empty.get_form()).to_be_visible()
    expect(empty.get_create_button()).to_be_visible()


@user_story("to start my first workspace with the help prompt already filled in")
def test_first_prompt_is_prefilled_with_help(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """The inline form's prompt is prefilled with the /sculptor:help text."""
    page = sculptor_instance_empty_first_run_.page
    empty = PlaywrightEmptyFirstRun(page)

    expect(empty.get_prompt_textarea()).to_have_value(HELP_PROMPT_PREFILL)


@user_story("to see a 'No workspaces yet' hint under my repo before I create anything")
def test_sidebar_shows_no_workspaces_hint(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """With a repo registered but no workspaces, the sidebar shows the hint."""
    page = sculptor_instance_empty_first_run_.page
    empty = PlaywrightEmptyFirstRun(page)

    expect(empty.get_no_workspaces_hint()).to_be_visible()


@pytest.mark.skip(reason=_ADD_REPO_SKIP_REASON)
@user_story("to be offered an 'Add a repo' button when no repositories are registered")
def test_sidebar_shows_add_repo_when_no_projects(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """With zero repos, the sidebar shows the "Add a repo" button.

    Settings stays reachable in the empty state, so the test removes the lone
    fixture repo through Settings > Repositories to reach the no-projects state.
    """
    page = sculptor_instance_empty_first_run_.page
    empty = PlaywrightEmptyFirstRun(page)
    expect(empty.get_no_workspaces_hint()).to_be_visible()

    # Remove the only project; the empty page's repo area falls back to "Add a repo".
    delete_project_via_settings(page, "initial_repo")

    expect(empty.get_page()).to_be_visible(timeout=45_000)
    expect(empty.get_add_repo_button()).to_be_visible()


@user_story("to be unable to escape the first-run form with global shortcuts")
def test_global_shortcuts_disabled_in_empty_state(sculptor_instance_empty_first_run_: SculptorInstance) -> None:
    """Cmd+K and the new-workspace shortcut are off in the empty state.

    The command palette must not open on Cmd+K, and Cmd/Meta+T must not open a
    separate new-workspace dialog (the form is already inline) — only Settings
    is reachable by keyboard.
    """
    page = sculptor_instance_empty_first_run_.page
    empty = PlaywrightEmptyFirstRun(page)
    expect(empty.get_page()).to_be_visible()

    mod_key = get_playwright_modifier_key()

    # Cmd+K does not open the command palette.
    page.keyboard.press(f"{mod_key}+k")
    page.keyboard.up(mod_key)
    expect(page.get_by_test_id(ElementIDs.COMMAND_PALETTE)).to_have_count(0)

    # Cmd/Meta+T does not open a separate new-workspace dialog.
    page.keyboard.press(f"{mod_key}+t")
    page.keyboard.up(mod_key)
    expect(page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)).to_have_count(0)

    # The inline form is still the only create surface present.
    expect(empty.get_form()).to_be_visible()


@user_story("to create my first workspace from the first-run form and land in the full workspace")
def test_creating_first_workspace_navigates_to_workspace(
    sculptor_instance_empty_first_run_: SculptorInstance,
) -> None:
    """Creating the first workspace flips the gate off and shows the workspace page."""
    page = sculptor_instance_empty_first_run_.page
    empty = PlaywrightEmptyFirstRun(page)
    empty.get_workspace_name_input().fill("First WS")

    empty.create_and_wait_for_chat_panel()

    # The empty first-run gate stops rendering once a workspace exists, and a
    # workspace row appears in the now-normal sidebar.
    expect(empty.get_page()).to_have_count(0)
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(1)
