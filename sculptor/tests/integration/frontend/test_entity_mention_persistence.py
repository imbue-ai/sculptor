"""Entity-mention chip persistence across navigation.

Mirrors ``test_at_mention_persists_as_styled_span_after_workspace_switch``
in ``test_at_mention_completion.py`` but for ``+``-triggered entity mentions
(workspaces / agents / repositories), which serialize to a different markdown
token (``+[type:id|display_name]``) than file mentions.

Two tests:
  1. Single-mention round-trip — the draft re-renders as a chip, not as
     literal ``+[type:id|display_name]`` text.
  2. Multi-paragraph round-trip — both mentions hydrate after the cross-
     paragraph hydration fix, not just the first.
     The hydration walk scans every text node and applies replacements in
     descending position order so earlier indices stay valid.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.entity_picker import insert_workspace_entity_mention
from sculptor.testing.elements.user_config import enable_entity_mentions
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Markdown serialization prefix for entity mentions. Should never appear as
# visible text in the chat input — it must re-hydrate into a styled chip.
_ENTITY_MENTION_TOKEN_PREFIX = "+["

# Unique workspace names so the picker's filter step gives exactly one match
# regardless of whatever workspaces the shared sculptor_instance fixture
# accumulated in earlier tests on the same xdist worker. Names must contain
# no whitespace — TipTap's ``+`` suggestion regex is ``\+\S*``, so a space
# in the typed query terminates the trigger and tears the popover down before
# the count assertion can run.
_SINGLE_MENTION_WORKSPACE_NAME = "WsChipPersist"
_MULTI_PARAGRAPH_WORKSPACE_NAME = "WsCrossPara"


def _navigate_to_task_chat(sculptor_instance: SculptorInstance, workspace_name: str) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
        workspace_name=workspace_name,
    )


@user_story("to keep entity-mention chips rendering as chips after navigating away and back")
def test_entity_mention_chip_persists_after_workspace_switch(
    sculptor_instance_: SculptorInstance,
) -> None:
    """An entity-mention draft should still render as a styled chip after
    navigating to the home page and back.

    Regression test: drafts containing ``+[type:id|display_name]`` markdown
    were re-loaded from localStorage on navigation, but the TipTap markdown
    parser left the token as literal text. Only ``TipTapViewer`` (the
    read-only message viewer) scanned ``+[…]`` and re-hydrated it into a
    mention node — the editable composer in ``Editor.tsx`` did not, so the
    chip rendered as raw ``+[workspace:…|Test Workspace]`` text.
    """
    page = sculptor_instance_.page

    # The entity-mention picker is gated by a user-config flag.
    enable_entity_mentions(page)

    task_page = _navigate_to_task_chat(sculptor_instance_, _SINGLE_MENTION_WORKSPACE_NAME)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    insert_workspace_entity_mention(page, chat_input, _SINGLE_MENTION_WORKSPACE_NAME)

    entity_chip = chat_panel.get_entity_mention_chips()
    expect(entity_chip).to_be_visible()
    expect(entity_chip).to_contain_text(_SINGLE_MENTION_WORKSPACE_NAME)

    # Navigate to home, then click the workspace tab to return to the task.
    navigate_to_home_page(page)
    workspace_tab = task_page.get_workspace_tabs()
    expect(workspace_tab).to_be_visible()
    workspace_tab.click()

    # Re-acquire the chat input — the prior locator may be stale if the
    # editor was remounted on remount of the workspace page.
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # The chip must still render via its mention-node component, not as raw
    # ``+[workspace:…|Test Workspace]`` text.
    entity_chip_after = chat_panel.get_entity_mention_chips()
    expect(entity_chip_after).to_be_visible()
    expect(entity_chip_after).to_contain_text(_SINGLE_MENTION_WORKSPACE_NAME)

    # And the input must not contain the raw markdown token. The bug:
    # ``setContent(value, { contentType: "markdown" })`` left
    # ``+[type:id|name]`` as literal text because the markdown parser does
    # not know about the token.
    expect(chat_input).not_to_contain_text(_ENTITY_MENTION_TOKEN_PREFIX)


@user_story("to keep entity-mention chips in separate paragraphs rendering as chips after navigation")
def test_entity_mentions_in_two_paragraphs_persist_after_workspace_switch(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A draft with mentions in two paragraphs must hydrate both on restore.

    Regression test for the cross-paragraph hydration fix. The bug: hydration
    only walked the first text node, so the second paragraph's
    ``+[type:id|name]`` token was left as literal text. The fix walks every
    text node in the doc and applies replacements in descending order so
    earlier indices stay valid.
    """
    page = sculptor_instance_.page

    enable_entity_mentions(page)

    task_page = _navigate_to_task_chat(sculptor_instance_, _MULTI_PARAGRAPH_WORKSPACE_NAME)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # First paragraph: mention.
    insert_workspace_entity_mention(page, chat_input, _MULTI_PARAGRAPH_WORKSPACE_NAME)
    # Press Enter to start a new paragraph.
    chat_input.press("Enter")
    # Second paragraph: another mention of the same workspace.
    insert_workspace_entity_mention(page, chat_input, _MULTI_PARAGRAPH_WORKSPACE_NAME)

    # Two chips are present pre-navigation.
    chips_before = chat_panel.get_entity_mention_chips()
    expect(chips_before).to_have_count(2)

    # Round-trip the draft through markdown via remount: navigate Home and
    # back so the editor unmounts and rebuilds from the localStorage draft.
    navigate_to_home_page(page)
    workspace_tab = task_page.get_workspace_tabs()
    expect(workspace_tab).to_be_visible()
    workspace_tab.click()

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Both chips must hydrate — not just the first paragraph's mention.
    chips_after = chat_panel.get_entity_mention_chips()
    expect(chips_after).to_have_count(2)

    # And no raw ``+[…]`` token text must leak through anywhere in the input.
    expect(chat_input).not_to_contain_text(_ENTITY_MENTION_TOKEN_PREFIX)
