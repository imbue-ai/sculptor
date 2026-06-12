"""Integration tests for the custom actions feature.

Tests cover the actions panel (workspace), action dialog, settings page actions
section, and persistence across page reloads.

All tests use the TestingAgent — no snapshots are needed.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.action_dialog import get_action_dialog
from sculptor.testing.elements.base import insert_mention_into_tiptap
from sculptor.testing.pages.settings_page import PlaywrightSettingsPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_task_and_navigate(sculptor_instance: SculptorInstance):
    """Create a TestingAgent task via API and navigate to its workspace page.

    Returns the task page object.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Test task for custom actions",
    )
    return task_page


# ---------------------------------------------------------------------------
# Tests: Actions Panel (workspace)
# ---------------------------------------------------------------------------


@user_story("to create a custom action from the actions panel and see it appear as a chip")
def test_create_action_from_panel(sculptor_instance_: SculptorInstance) -> None:
    """Click '+' on the actions panel, fill in the dialog, and verify the chip appears."""
    task_page = _create_task_and_navigate(sculptor_instance_)

    actions_panel = task_page.get_actions_panel()
    actions_panel.get_add_button().click()

    dialog = get_action_dialog(sculptor_instance_.page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Run Tests")
    dialog.fill_prompt("Run the test suite")
    dialog.click_save()

    expect(dialog).not_to_be_visible()

    # Verify the chip appears in the panel
    chip = actions_panel.get_action_chip_by_name("Run Tests")
    expect(chip).to_be_visible()


@user_story("to edit a custom action from the settings page")
def test_edit_action_from_settings(sculptor_instance_: SculptorInstance) -> None:
    """Create an action from settings, edit it via the pencil icon, verify the name changes."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    actions_section = settings_page.click_on_actions()

    # Create an action first
    actions_section.get_add_action_button().click()
    dialog = get_action_dialog(sculptor_instance_.page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Old Name")
    dialog.fill_prompt("Some prompt")
    dialog.click_save()
    expect(dialog).not_to_be_visible()

    # Wait for success toast, then dismiss it so it doesn't interfere with
    # the edit dialog's layout (the toast animation can cause "element is not
    # stable" failures under parallel execution).
    settings_page.dismiss_toast()

    # Find the action row and click the edit icon
    edit_button = actions_section.get_action_edit_button("Old Name")
    edit_button.click()

    # Edit the action name
    edit_dialog = get_action_dialog(sculptor_instance_.page)
    expect(edit_dialog).to_be_visible()
    edit_dialog.fill_name("New Name")
    edit_dialog.click_save()
    expect(edit_dialog).not_to_be_visible()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Verify the updated name appears in settings
    updated_row = actions_section.get_action_row_by_name("New Name")
    expect(updated_row).to_be_visible()

    # Old name should be gone
    expect(actions_section.get_action_row_by_name("Old Name")).to_have_count(0)


# ---------------------------------------------------------------------------
# Tests: Settings page
# ---------------------------------------------------------------------------


@user_story("to create a custom action from the settings page")
def test_create_action_from_settings(sculptor_instance_: SculptorInstance) -> None:
    """Navigate to Settings > Actions, create an action, verify it appears in the list."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    actions_section = settings_page.click_on_actions()

    # Click "Add Action"
    actions_section.get_add_action_button().click()

    dialog = get_action_dialog(sculptor_instance_.page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Lint Code")
    dialog.fill_prompt("Run the linter on all files")
    dialog.click_save()

    expect(dialog).not_to_be_visible()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Verify the action row appears
    action_row = actions_section.get_action_row_by_name("Lint Code")
    expect(action_row).to_be_visible()


@user_story("to delete a custom action from the settings page")
def test_delete_action_from_settings(sculptor_instance_: SculptorInstance) -> None:
    """Create an action from settings, then delete it via the trash icon."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    actions_section = settings_page.click_on_actions()

    # Create an action first
    actions_section.get_add_action_button().click()
    dialog = get_action_dialog(sculptor_instance_.page)
    expect(dialog).to_be_visible()
    dialog.fill_name("To Remove")
    dialog.fill_prompt("Remove me")
    dialog.click_save()
    expect(dialog).not_to_be_visible()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Find the action row and click the delete icon
    actions_section.get_action_delete_button("To Remove").click()

    # Confirm deletion
    actions_section.confirm_delete_action()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Verify the action row is gone
    expect(actions_section.get_action_row_by_name("To Remove")).to_have_count(0)


@user_story("to create a group from the settings page")
def test_create_group_from_settings(sculptor_instance_: SculptorInstance) -> None:
    """Navigate to Settings > Actions, click 'Add Group', enter a name, confirm."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    actions_section = settings_page.click_on_actions()

    # Click "Add Group"
    actions_section.get_add_group_button().click()

    # Fill in the group name in the dialog that appears
    group_name_input = actions_section.get_group_name_input()
    expect(group_name_input).to_be_visible()
    group_name_input.fill("My Group")

    # Click "Create Group"
    actions_section.get_create_group_button().click()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Verify the group appears in the settings section
    group_heading = actions_section.get_group_headings().filter(has_text="My Group")
    expect(group_heading).to_be_visible()


@user_story("to verify custom actions persist across page reloads")
def test_action_persists_across_page_reload(sculptor_instance_: SculptorInstance) -> None:
    """Create an action via settings, reload the page, verify it still exists."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    actions_section = settings_page.click_on_actions()

    # Create an action
    actions_section.get_add_action_button().click()
    dialog = get_action_dialog(sculptor_instance_.page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Persistent Action")
    dialog.fill_prompt("I should survive a reload")
    dialog.click_save()
    expect(dialog).not_to_be_visible()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Soft-reload to verify persistence (direct reload causes ERR_INSUFFICIENT_RESOURCES on CI)
    page = sculptor_instance_.page
    soft_reload_page(page, wait_until="networkidle")

    # Re-acquire settings page elements after reload
    reloaded_settings = PlaywrightSettingsPage(page=sculptor_instance_.page)
    actions_section = reloaded_settings.click_on_actions()

    # Verify the action still exists
    action_row = actions_section.get_action_row_by_name("Persistent Action")
    expect(action_row).to_be_visible()


# ---------------------------------------------------------------------------
# Tests: Skill mentions in action prompts
# ---------------------------------------------------------------------------


@user_story("to see clean prompt text in settings when an action contains a skill mention")
def test_action_with_skill_mention_displays_cleanly_in_settings(sculptor_instance_: SculptorInstance) -> None:
    """Create an action with a slash-command skill mention and verify the
    settings page shows the prompt as plain text, not raw HTML.

    When the action dialog's TipTap editor serializes a mention node via the
    tiptap-markdown extension, it should produce clean text (e.g. "/skill-name")
    rather than raw HTML spans with data attributes.
    """
    page = sculptor_instance_.page

    # Open the action dialog from the settings page
    settings_page = navigate_to_settings_page(page=page)
    actions_section = settings_page.click_on_actions()
    actions_section.get_add_action_button().click()

    dialog = get_action_dialog(page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Skill Action")

    # Insert a mention node directly via TipTap's API (bypasses autocomplete UI).
    # This simulates what happens when a user selects a skill from the "/" popover.
    prompt_input = dialog.get_prompt_input()
    expect(prompt_input).to_be_visible()
    insert_mention_into_tiptap(prompt_input, "/fix-bug", "/")

    # Verify the mention span was inserted into the editor
    expect(dialog.get_mention_span()).to_be_visible()

    # Save the action
    dialog.click_save()
    expect(dialog).not_to_be_visible()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # Find the action row in settings and verify the prompt preview is clean text.
    # The prompt preview must NOT contain raw HTML attributes — if it does,
    # the tiptap-markdown serializer is leaking HTML into the stored prompt.
    action_row = actions_section.get_action_row_by_name("Skill Action")
    expect(action_row).to_be_visible()
    expect(action_row).not_to_contain_text("data-mention-suggestion-char")
    expect(action_row).not_to_contain_text("data-label")


# ---------------------------------------------------------------------------
# Tests: Delete group also deletes actions (SCU-308)
# ---------------------------------------------------------------------------


@user_story("to delete a group from settings and have its actions deleted too")
def test_delete_group_deletes_actions_from_settings(sculptor_instance_: SculptorInstance) -> None:
    """Delete a group from the settings page and verify its actions are also removed."""
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)
    actions_section = settings_page.click_on_actions()

    # 1. Create a group
    actions_section.get_add_group_button().click()
    group_name_input = actions_section.get_group_name_input()
    expect(group_name_input).to_be_visible()
    group_name_input.fill("Doomed Group")
    actions_section.get_create_group_button().click()

    settings_page.dismiss_toast()

    # 2. Create an action in that group
    actions_section.get_add_action_button().click()
    dialog = get_action_dialog(page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Doomed Action")
    dialog.fill_prompt("I should be deleted with the group")
    dialog.select_group("Doomed Group")

    dialog.click_save()
    expect(dialog).not_to_be_visible()

    settings_page.dismiss_toast()

    # Verify action appears under the group
    action_row = actions_section.get_action_row_by_name("Doomed Action")
    expect(action_row).to_be_visible()

    # 3. Delete the group via the trash icon on the group header
    actions_section.click_delete_group("Doomed Group")

    # 4. Confirm in the delete group dialog
    actions_section.confirm_delete_group()

    # Wait for success toast
    expect(settings_page.get_toast()).to_be_visible()

    # 5. Verify both group and action are gone
    expect(actions_section.get_group_headings().filter(has_text="Doomed Group")).to_have_count(0)
    expect(actions_section.get_action_row_by_name("Doomed Action")).to_have_count(0)


# ---------------------------------------------------------------------------
# Tests: Built-in Sculptor group
# ---------------------------------------------------------------------------


@user_story("to see the built-in Sculptor group with its un-deletable skill chips")
def test_builtin_chips(sculptor_instance_: SculptorInstance) -> None:
    """End-to-end coverage of the virtual Sculptor group:

    - renders with /help and /fix-bug chips, in that order
    - header can't be renamed or deleted (no group context menu)
    - not selectable from the Add Action dialog's group picker
    - always rendered above any user-created group
    """
    task_page = _create_task_and_navigate(sculptor_instance_)
    page = sculptor_instance_.page
    actions_panel = task_page.get_actions_panel()

    # Sculptor header + both built-in chips are visible.
    sculptor_header = actions_panel.get_group_header_by_name("Sculptor")
    expect(sculptor_header).to_be_visible()
    expect(actions_panel.get_action_chip_by_name("/help")).to_be_visible()
    expect(actions_panel.get_action_chip_by_name("/fix-bug")).to_be_visible()

    # Sculptor is the first group, so its chips occupy positions 0 and 1.
    chips = actions_panel.get_action_chips()
    expect(chips.nth(0)).to_contain_text("/help")
    expect(chips.nth(1)).to_contain_text("/fix-bug")

    # Right-clicking the Sculptor header must not expose the group-level delete item.
    # (Built-in headers skip GroupContextMenu — the right-click bubbles to the panel-level
    # context menu, which only offers Add action / Add group.)
    sculptor_header.click(button="right")
    expect(actions_panel.get_group_context_menu_delete_item()).to_have_count(0)
    page.keyboard.press("Escape")

    # The Group picker in the Add Action dialog must not list "Sculptor" as an option.
    actions_panel.get_add_button().click()
    dialog = get_action_dialog(page)
    expect(dialog).to_be_visible()
    dialog.get_group_select().click()
    expect(page.get_by_role("option", name="Sculptor")).to_have_count(0)
    page.keyboard.press("Escape")  # close select

    # Create a user group so we can verify Sculptor renders above it.
    group_name = "User Group Positioning Test"
    dialog.fill_name("User Positioning Action")
    dialog.fill_prompt("User-owned prompt")
    dialog.select_new_group(group_name)
    dialog.click_save()
    expect(dialog).not_to_be_visible()

    user_header = actions_panel.get_group_header_by_name(group_name)
    expect(user_header).to_be_visible()
    sculptor_box = sculptor_header.bounding_box()
    user_box = user_header.bounding_box()
    assert sculptor_box is not None and user_box is not None
    assert sculptor_box["y"] < user_box["y"], (
        f"Sculptor group should render above user groups, but got sculptor y={sculptor_box['y']} "
        + f"and user group y={user_box['y']}"
    )


@user_story("to click a draft action and have the chat input focused with the prompt drafted in")
def test_draft_action_populates_and_focuses_chat_input(sculptor_instance_: SculptorInstance) -> None:
    """Clicking any draft (non-auto-submit) action inserts its prompt into the chat input
    and gives focus to the input so the user can immediately type without clicking.

    This covers the general ChatInput behavior — not specific to built-in chips.
    """
    task_page = _create_task_and_navigate(sculptor_instance_)
    page = sculptor_instance_.page
    actions_panel = task_page.get_actions_panel()

    # Create a user-defined draft action (auto-submit off).
    actions_panel.get_add_button().click()
    dialog = get_action_dialog(page)
    expect(dialog).to_be_visible()
    dialog.fill_name("My Draft Action")
    dialog.fill_prompt("Draft this into the input")
    # The auto-submit switch defaults to ON; toggle it OFF so the chip drafts instead of sends.
    dialog.get_auto_submit_switch().click()
    dialog.click_save()
    expect(dialog).not_to_be_visible()

    # Click the chip.
    actions_panel.get_action_chip_by_name("My Draft Action").click()

    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_contain_text("Draft this into the input")
    expect(chat_input).to_be_focused()


@user_story("to delete a group from the workspace actions panel and have its actions deleted too")
def test_delete_group_deletes_actions_from_panel(sculptor_instance_: SculptorInstance) -> None:
    """Delete a group via the workspace actions panel context menu
    and verify its actions are also removed."""
    page = sculptor_instance_.page

    # 1. Create an action with a new group from the workspace panel
    task_page = _create_task_and_navigate(sculptor_instance_)
    actions_panel = task_page.get_actions_panel()

    actions_panel.get_add_button().click()
    dialog = get_action_dialog(page)
    expect(dialog).to_be_visible()
    dialog.fill_name("Panel Action")
    dialog.fill_prompt("Delete me with the group")
    dialog.select_new_group("Panel Group")

    dialog.click_save()
    expect(dialog).not_to_be_visible()

    # Verify the action chip appears in the panel
    chip = actions_panel.get_action_chip_by_name("Panel Action")
    expect(chip).to_be_visible()

    # 2. Right-click the group header to open context menu, then click "Delete group"
    actions_panel.delete_group_via_context_menu("Panel Group")

    # 3. Confirm in the delete group dialog
    actions_panel.confirm_delete_group()

    # 4. Verify the action chip is gone
    expect(actions_panel.get_action_chip_by_name("Panel Action")).to_have_count(0)
