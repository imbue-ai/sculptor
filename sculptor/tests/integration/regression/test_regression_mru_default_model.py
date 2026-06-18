"""Regression test: a new workspace should default to the most recently used model.

SCU-1457: When the "Default model" setting (Settings → Agent → Default model)
is "Most Recently Used" — the product default, where ``userConfig.defaultLlm``
is ``None`` — a newly created workspace should default to whatever model the
user most recently selected.

The only writer of the global "last used model" had been removed along with the
Add Workspace page's model dropdown, and model switching moved to the chat
panel, which only persists a *per-task* model preference. As a result the MRU
default never reflected the model the user was actually using and always fell
through to Fable: switching a workspace's model and then creating a new
workspace produced a Fable agent regardless of the just-used model.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_2_MODEL_NAME
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to have a new workspace default to the model I most recently used")
def test_new_workspace_defaults_to_most_recently_used_model(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A new workspace inherits the model most recently selected in another workspace.

    Steps:
    1. Create workspace A on "Fake Claude" (the Default model setting is the
       product-default "Most Recently Used", i.e. ``defaultLlm`` is None).
    2. Switch workspace A's chat-panel model to "Fake Claude 2".
    3. Create a brand-new workspace B without touching its model selector.
    4. Verify workspace B's model selector shows "Fake Claude 2" — the most
       recently used model — rather than the Fable fallback.
    """
    page = sculptor_instance_.page

    # Workspace A starts on Fake Claude.
    task_page_a = start_task_and_wait_for_ready(
        page,
        model_name=FAKE_CLAUDE_MODEL_NAME,
        workspace_name="MRU Workspace A",
    )
    chat_panel_a = task_page_a.get_chat_panel()

    # The user switches A's model to Fake Claude 2 on the chat panel. This is
    # now the model the user most recently used.
    select_model_by_name(chat_panel_a, FAKE_CLAUDE_2_MODEL_NAME)
    expect(chat_panel_a.get_model_selector()).to_have_text(FAKE_CLAUDE_2_MODEL_NAME)

    # A brand-new workspace, created without touching its model selector, must
    # default to the most recently used model (Fake Claude 2) rather than Fable.
    task_page_b = start_task_and_wait_for_ready(
        page,
        model_name=None,
        workspace_name="MRU Workspace B",
    )
    expect(task_page_b.get_chat_panel().get_model_selector()).to_have_text(FAKE_CLAUDE_2_MODEL_NAME)
