"""Regression test: a new workspace defaults to Opus, not Fable.

SCU-1576: Fable was still shipping as the product default model even though it
is currently disabled with an indefinite timeline. When the "Default model"
setting (Settings → Agent → Default model) is "Most Recently Used" — the product
default, where ``userConfig.defaultLlm`` is ``None`` — and the user has not yet
selected any model (so there is no most-recently-used model either), a newly
created workspace fell through to the Fable fallback. The default should be Opus
instead, while Fable remains available in the model switcher for if/when it
returns.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# The chat-panel model selector renders the model's short name; "Opus" is the
# short name for CLAUDE_4_OPUS_200K (see frontend modelConstants.ts).
OPUS_MODEL_NAME = "Opus"


@user_story("to have a new workspace default to Opus when I haven't picked a model")
def test_new_workspace_defaults_to_opus(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A brand-new workspace defaults to Opus when nothing else is selected.

    Steps:
    1. Create a brand-new workspace without touching its model selector
       (``model_name=None``). The "Default model" setting is the product-default
       "Most Recently Used" (``defaultLlm`` is None) and no model has been used
       yet, so the default resolves to the product fallback.
    2. Verify the workspace's model selector shows "Opus" — the product default
       — rather than the old Fable fallback.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        model_name=None,
        workspace_name="Default Model Workspace",
    )

    expect(task_page.get_chat_panel().get_model_selector()).to_have_text(OPUS_MODEL_NAME)
