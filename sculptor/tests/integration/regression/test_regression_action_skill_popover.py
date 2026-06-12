"""Regression test: Action dialog prompt field should support skill mentions like the chat input.

Bug: The ActionDialog uses a plain <TextArea> for the prompt field while the ChatInput uses
a TipTap rich editor with skill suggestion support. When a user types "/" in the action
dialog, no skill suggestion popover appears — they can only enter raw text. When the action
is later inserted into the ChatInput (which uses TipTap), the "/" in the raw text triggers
the skill search popover instead of being treated as a pre-selected skill mention.

Root cause: The ActionDialog prompt field is a plain Radix TextArea with no TipTap
integration. It needs to be replaced with the same TipTap Editor component used by the
ChatInput so that skill references are stored as proper mention nodes.

Fix: Replace the plain <TextArea> in ActionDialog with a TipTap Editor. This way skills
are authored as mention nodes in the action dialog and serialize cleanly when inserted into
the ChatInput.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.action_dialog import get_action_dialog
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to use skill mentions in the action dialog prompt field")
def test_action_dialog_prompt_supports_skill_mentions(sculptor_instance_: SculptorInstance) -> None:
    """The action dialog prompt field should be a rich TipTap editor, not a plain textarea.

    Steps:
    1. Create a task and navigate to the workspace
    2. Open the action dialog
    3. Verify the prompt field is a TipTap contenteditable editor (not a plain textarea)
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="Test task for action dialog skill support",
    )

    # Open the action dialog
    actions_panel = task_page.get_actions_panel()
    actions_panel.get_add_button().click()

    dialog = get_action_dialog(sculptor_instance_.page)
    expect(dialog).to_be_visible()

    # The prompt field should be a TipTap contenteditable editor, not a plain textarea.
    # A plain <textarea> element means the field doesn't support rich editing features.
    # A TipTap editor renders as a contenteditable div with the data-testid on the
    # ProseMirror element.
    prompt_area = dialog.get_prompt_input()
    expect(prompt_area).to_be_visible()

    # Assert the prompt field is a contenteditable element (TipTap editor), not a textarea.
    # When the bug is present, this is a plain <textarea> element.
    # When fixed, it should be a contenteditable div.
    expect(prompt_area).to_have_attribute("contenteditable", "true")
