"""Integration tests for the ``+`` prefilter mention picker.

Typing ``+`` in the chat input opens a top-level prefilter menu showing five
categories (Files & folders, Skills, Workspaces and Agents, Repositories,
Images). Filtering matches on label only. Drilling in is via Tab or Enter
on a category row; drill-in clears the editor's query (replacing
``+query`` with ``+``) and forwards rendering to the matching sub-picker
(file picker, skill picker, or entity picker pinned to a type). The Images
row is terminal — selecting it fires the image-upload trigger callback.

The toolbar also exposes a button (``handleMentionPicker`` in
``ChatInput.tsx``) that inserts ``+`` at the cursor and opens the picker.

These tests drive the picker entirely through ``data-testid`` locators and
keyboard input, per the ``integration_test_non_testid_queries`` ratchet.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.entity_picker import PlaywrightEntityPickerElement
from sculptor.testing.elements.entity_picker import insert_workspace_entity_mention
from sculptor.testing.elements.user_config import enable_entity_mentions
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Workspace name we'll filter to from the entity picker. Must contain no
# whitespace — TipTap's ``+`` suggestion regex is ``+\S*``, so a space in
# the typed query terminates the trigger and tears the popover down before
# the count assertion can run.
_WORKSPACE_NAME = "WsMentionPicker"


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
        workspace_name=_WORKSPACE_NAME,
    )


@user_story("to discover the prefilter menu by typing +")
def test_plus_opens_prefilter_picker(sculptor_instance_: SculptorInstance) -> None:
    """Typing ``+`` opens the prefilter popover with category rows."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    chat_input.press_sequentially("+")

    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_category_items().first).to_be_visible()


@user_story("to filter prefilter categories by typing")
def test_plus_filters_categories_by_query(sculptor_instance_: SculptorInstance) -> None:
    """``+wor`` filters to a single category row; Enter drills in."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    chat_input.press_sequentially("+wor")

    expect(entity_picker.get_mention_list()).to_be_visible()
    # "wor" only matches the "Workspaces and Agents" category label.
    expect(entity_picker.get_category_items()).to_have_count(1)

    chat_input.press("Enter")

    # Drill-in swaps the prefilter list for the entity sub-picker.
    expect(entity_picker.get_entity_list()).to_be_visible()
    expect(entity_picker.get_category_items()).to_have_count(0)


@user_story("to drill into the file picker from the + menu via Enter")
def test_plus_drill_into_files_via_enter(sculptor_instance_: SculptorInstance) -> None:
    """``+fil`` + Enter drills into the file picker, surfacing file rows."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    chat_input.press_sequentially("+fil")
    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_category_items()).to_have_count(1)

    chat_input.press("Enter")

    # Picker remains open with file suggestion rows after the drill.
    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_file_items().first).to_be_visible()


@user_story("to drill into the skill picker from the + menu via Enter")
def test_plus_drill_into_skills_via_enter(sculptor_instance_: SculptorInstance) -> None:
    """``+sk`` + Enter drills into the skill picker (still rendering items)."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    chat_input.press_sequentially("+sk")
    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_category_items()).to_have_count(1)

    chat_input.press("Enter")

    # Skill list reuses the shared MENTION_LIST container; the prefilter
    # category rows are gone once the drill flips state.
    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_category_items()).to_have_count(0)


@user_story("to drill into Workspaces from the + menu and commit a chip")
def test_plus_drill_into_workspaces(sculptor_instance_: SculptorInstance) -> None:
    """``+wor`` + Enter + workspace name + Enter inserts an entity-mention chip."""
    page = sculptor_instance_.page
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    # Route through the shared helper so the workspace-name typing gets the
    # same delay + items-stability waits as the other entity-mention tests —
    # without them, the per-keystroke items() refresh races the picker
    # render under CI load and the popover can drop to 0 rows mid-stream.
    insert_workspace_entity_mention(page, chat_input, _WORKSPACE_NAME)

    entity_chip = chat_panel.get_entity_mention_chips()
    expect(entity_chip).to_be_visible()
    expect(entity_chip).to_contain_text(_WORKSPACE_NAME)


@user_story("to drill into Repositories from the + menu and commit a chip")
def test_plus_drill_into_repositories(sculptor_instance_: SculptorInstance) -> None:
    """``+rep`` + Enter pins the entity picker to repositories; Enter commits."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    chat_input.press_sequentially("+rep")
    chat_input.press("Enter")

    expect(entity_picker.get_entity_list()).to_be_visible()
    # The Sculptor instance has at least one repository project.
    expect(entity_picker.get_entity_items().first).to_be_visible()

    chat_input.press("Enter")

    expect(chat_panel.get_entity_mention_chips()).to_be_visible()


@user_story("to drill into a + category using Tab as well as Enter")
def test_plus_tab_drills_in_just_like_enter(sculptor_instance_: SculptorInstance) -> None:
    """Tab on a category row drills in (same effect as Enter)."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    chat_input.press_sequentially("+fil")
    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_category_items()).to_have_count(1)

    # ``page.keyboard.press`` keeps editor focus — ``Locator.press`` would
    # refocus and can interfere with Tab's browser-default focus semantics.
    page.keyboard.press("Tab")

    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_file_items().first).to_be_visible()


@user_story("to dismiss the + picker by pressing Escape")
def test_plus_escape_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    """Escape after ``+`` closes the prefilter popover."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    chat_input.press_sequentially("+")
    expect(entity_picker.get_mention_list()).to_be_visible()

    chat_input.press("Escape")

    expect(entity_picker.get_mention_list()).not_to_be_visible()


@user_story("to dismiss the + picker by deleting the trigger character")
def test_plus_backspace_at_trigger_closes_picker(sculptor_instance_: SculptorInstance) -> None:
    """Backspace right after ``+`` erases the trigger and closes the popover."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    chat_input.press_sequentially("+")
    expect(entity_picker.get_mention_list()).to_be_visible()

    chat_input.press("Backspace")

    expect(entity_picker.get_mention_list()).not_to_be_visible()


@user_story("to open the + picker by clicking the toolbar mention button")
def test_mention_toolbar_button_opens_picker(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the toolbar mention button inserts ``+`` and opens the picker."""
    page = sculptor_instance_.page
    entity_picker = PlaywrightEntityPickerElement(page)
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    entity_picker.get_toolbar_button().click()

    expect(entity_picker.get_mention_list()).to_be_visible()
    expect(entity_picker.get_category_items().first).to_be_visible()
