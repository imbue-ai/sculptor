"""Tests for chip rendering in sent user messages in alpha chat.

``AlphaMarkdownBlock`` renders sent user messages via react-markdown, which
does not understand tiptap's draft serialisation format. The
``<span data-sculptor-node>…</span>`` wrapper produced by the editor's
``renderMarkdown`` previously leaked through as literal HTML text in the
message bubble instead of being rendered as a chip/pill. These tests pin the
end-to-end pipeline (editor serialisation → markdown storage →
``AlphaMarkdownBlock`` rendering) for /skill chips, @-file chips, @-folder
chips (including click-to-reveal), and entity mentions.
"""

import subprocess
from pathlib import Path

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.entity_picker import insert_workspace_entity_mention
from sculptor.testing.elements.file_tree import get_file_tree
from sculptor.testing.elements.user_config import enable_entity_mentions
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

# Unique workspace name so the entity picker's filter step gives exactly one
# match regardless of whatever workspaces the shared sculptor_instance fixture
# accumulated in earlier tests on the same xdist worker.
_ENTITY_WORKSPACE_NAME = "WsAlphaEntity"


def _create_skill_in_directory(project_path: Path, skill_name: str, description: str) -> None:
    """Create a committed skill in the project's .claude/skills/ directory."""
    skill_dir = project_path / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: {description}\n---\nSkill instructions.\n"
    )
    subprocess.run(["git", "add", str(skill_dir)], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add skill {skill_name}"],
        cwd=project_path,
        check=True,
    )


def _add_nested_folders(project_path: Path) -> None:
    """Create a committed nested folder structure so the reveal is non-trivial.

    The default test repo has ``src/app.py`` (single-level). We add a deeper
    path so that clicking the folder chip demonstrates ancestor expansion
    rather than just activating the panel.
    """
    nested_file = project_path / "src" / "components" / "chat" / "index.ts"
    nested_file.parent.mkdir(parents=True, exist_ok=True)
    nested_file.write_text("export const x = 1;\n")
    subprocess.run(["git", "add", str(nested_file)], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add nested components folder"],
        cwd=project_path,
        check=True,
    )


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )


def _insert_file_mention(chat_panel: PlaywrightChatPanelElement, chat_input: Locator, query: str) -> None:
    """Type ``@<query>`` and commit the first suggestion with Enter.

    Waits for the first suggestion item to render before pressing Enter so
    the keypress doesn't race an empty items list.
    """
    chat_input.press_sequentially(f"@{query}")
    mention_list = chat_panel.get_mention_list()
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().first).to_be_visible()
    chat_panel._page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()


@user_story("to see /skill chips render as pills in sent user messages in alpha chat")
def test_alpha_chat_user_message_skill_chip_renders_as_pill(sculptor_instance_: SculptorInstance) -> None:
    """A /skill chip inserted via the chat input must render as a pill in the
    sent user message bubble, not as the raw ``<span data-sculptor-node>`` text.
    """
    skill_name = "alpha-chip-render-skill"
    _create_skill_in_directory(
        sculptor_instance_.project_path,
        skill_name,
        "Skill for alpha chat chip rendering test",
    )

    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()
    mod_key = get_playwright_modifier_key()

    # Type "/alpha-chip-render" in the chat input to surface the skill in the
    # mention list popover, then press Enter to insert it as a chip.  Retry
    # because on slow CI the workspace clone may not have finished skill
    # discovery yet.
    for attempt in range(5):
        type_trigger_char(chat_input, "/")
        chat_input.press_sequentially("alpha-chip-render")

        try:
            expect(mention_list).to_be_visible()
            expect(mention_list).to_contain_text(skill_name)
            break
        except AssertionError:
            if attempt == 4:
                raise
            page.keyboard.press("Escape")
            page.keyboard.press(f"{mod_key}+a")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)

    page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()

    # Sanity: the editor now contains a skill chip (MENTION_SPAN).
    editor_chip = chat_input.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(editor_chip).to_be_visible()
    expect(editor_chip).to_contain_text(skill_name)

    # Send the message.
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")

    # Wait for the message to render and fake_claude to respond (2 -> 4 messages).
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # ALPHA_CHAT_TEXT is used for both user and assistant message text blocks,
    # so target the last user message specifically via the POM helper.
    latest_user_message = alpha_view.get_user_messages().last

    # The chip must be rendered as a MENTION_SPAN (same testid the editor uses),
    # matching the tiptap editor's rendering.
    rendered_chip = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chip).to_be_visible()
    expect(rendered_chip).to_contain_text(skill_name)

    # And the raw HTML wrapper must NOT leak through as visible text.
    expect(latest_user_message).not_to_contain_text("data-sculptor-node")


@user_story("to include multiple file @-mentions in a single message")
def test_two_file_chips_in_one_message_render_independently(sculptor_instance_: SculptorInstance) -> None:
    """A message with two file mentions renders two chips in the sent bubble.

    Regression: an earlier sentinel delimiter (``_``) in the chip round-trip
    path through ``AlphaMarkdownBlock`` was pair-matched by remark-gfm as
    italic markers across adjacent chips, producing italicized artifacts and
    missing chips. The fix switched to a pipe delimiter (``|``); this test
    guards the end-to-end pipeline against a regression that the unit test
    cannot catch (e.g. an upstream serializer change).
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()

    # Insert two file mentions separated by a space.
    _insert_file_mention(chat_panel, chat_input, "stuff")
    _insert_file_mention(chat_panel, chat_input, "README")

    # Editor now has two chips.
    editor_chips = chat_input.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(editor_chips).to_have_count(2)

    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()
    latest_user_message = alpha_view.get_user_messages().last

    # Both chips must render in the sent bubble.
    rendered_chips = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chips).to_have_count(2)
    # Chip text is the basename of each path (trailing slash stripped for
    # directories; files show just the filename).
    expect(rendered_chips.nth(0)).to_contain_text("stuff")
    expect(rendered_chips.nth(1)).to_contain_text("README")

    # No HTML wrapper must leak.
    expect(latest_user_message).not_to_contain_text("data-sculptor-node")
    # No sentinel fragment must leak.
    expect(latest_user_message).not_to_contain_text("sculptorChip")


@user_story("to mix file @-mentions and text in a single message")
def test_file_chip_surrounded_by_text_renders_correctly(sculptor_instance_: SculptorInstance) -> None:
    """Prose text before and after a file chip is preserved verbatim.

    The chip extraction path must restore plain text around the chip
    without dropping whitespace or picking up markdown formatting artifacts.
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()

    # "Please check @stuff now"
    chat_input.press_sequentially("Please check ")
    _insert_file_mention(chat_panel, chat_input, "stuff")
    chat_input.press_sequentially("now")

    editor_chips = chat_input.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(editor_chips).to_have_count(1)

    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    latest_user_message = alpha_view.get_user_messages().last

    rendered_chips = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chips).to_have_count(1)
    expect(latest_user_message).to_contain_text("Please check")
    expect(latest_user_message).to_contain_text("now")
    # No leaked raw HTML / sentinels.
    expect(latest_user_message).not_to_contain_text("data-sculptor-node")
    expect(latest_user_message).not_to_contain_text("sculptorChip")


@user_story("to see an entity-mention chip render as a pill in a sent user message")
def test_alpha_chat_entity_mention_renders_as_chip_in_sent_message(
    sculptor_instance_: SculptorInstance,
) -> None:
    """An entity mention committed to the chat input renders as a chip in the
    sent message bubble — not as the raw ``+[type:id|display_name]`` token.

    Entity mentions take a different markdown serialization path
    (``+[type:id|display_name]`` rather than ``<span data-sculptor-node>``),
    so a regression in the markdown viewer's hydration of those tokens would
    slip past the skill/file chip tests above. The chip must:
      - Render via ``ENTITY_MENTION_CHIP`` (the testid the editor uses).
      - Carry ``data-entity-type="workspace"`` so styling/click handlers can
        route on the entity's kind.
      - Display the workspace's display name as visible text.

    The sent message must NOT contain raw ``+[`` token text or
    ``data-entity-type`` HTML literal — both would be present if the markdown
    viewer's hydration step were missing.
    """
    page = sculptor_instance_.page

    enable_entity_mentions(page)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready"}`',
        workspace_name=_ENTITY_WORKSPACE_NAME,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()
    insert_workspace_entity_mention(page, chat_input, _ENTITY_WORKSPACE_NAME)

    # Sanity: the editor now contains an entity-mention chip.
    editor_chip = chat_input.get_by_test_id(ElementIDs.ENTITY_MENTION_CHIP)
    expect(editor_chip).to_be_visible()
    expect(editor_chip).to_contain_text(_ENTITY_WORKSPACE_NAME)

    # Send the message.
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")

    # Wait for the message to render and FakeClaude to respond (2 -> 4).
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    latest_user_message = alpha_view.get_user_messages().last
    rendered_chip = latest_user_message.get_by_test_id(ElementIDs.ENTITY_MENTION_CHIP)
    expect(rendered_chip).to_be_visible()
    expect(rendered_chip).to_contain_text(_ENTITY_WORKSPACE_NAME)
    expect(rendered_chip).to_have_attribute("data-entity-type", "workspace")

    # Neither the raw token nor a leaked HTML wrapper attribute should appear
    # as visible text in the message bubble.
    expect(latest_user_message).not_to_contain_text("+[")
    expect(latest_user_message).not_to_contain_text("data-entity-type=")


@user_story("to reveal a folder in the file browser by clicking its @-mention chip")
def test_folder_chip_click_reveals_folder_in_file_browser(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a rendered folder chip reveals the folder in the file browser.

    Exercises the full pipeline: ``MentionChip`` click handler →
    ``revealFolderAtom`` → ``expandFoldersAtom`` / panel zone atoms →
    ``useFocusFolderHighlight`` → ``FileTree`` DOM. The file browser panel
    must become visible, the target folder and its ancestors must expand,
    and the folder row must appear in the tree.
    """
    _add_nested_folders(sculptor_instance_.project_path)

    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    # Type "@src" to surface the "src/" folder in the popup. The mention
    # command handler inserts a folder chip when Enter/click selects a folder
    # item (see SuggestionUtils.ts `command`). Tab drills into the folder
    # instead, so we explicitly use Enter.
    chat_input.press_sequentially("@src")
    expect(mention_list).to_be_visible()

    # Folder item renders as the label "src" (slash stripped in the list UI,
    # though the underlying id is "@src/"). Look for the first suggestion
    # whose text is exactly "src" to disambiguate it from files under src/.
    folder_item = chat_panel.get_mention_items().filter(has_text="src").first
    expect(folder_item).to_be_visible()

    # Keyboard-arrow to the folder and press Enter. We cannot click the item
    # because `filter(has_text="src")` would also match "src/app.py" entries;
    # but the first item under an "@src" query is the `src/` folder itself
    # (fuzzy search ranks exact-prefix directory ahead of contained files).
    page.keyboard.press("Enter")
    expect(mention_list).not_to_be_visible()

    editor_chip = chat_input.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(editor_chip).to_be_visible()
    # The chip displays the folder base name without the trailing slash.
    expect(editor_chip).to_contain_text("src")

    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    latest_user_message = alpha_view.get_user_messages().last
    rendered_chip = latest_user_message.get_by_test_id(ElementIDs.MENTION_SPAN)
    expect(rendered_chip).to_be_visible()

    # Clicking the rendered folder chip must reveal the file browser and
    # expand the "src" folder.
    rendered_chip.click()

    file_browser = get_file_tree(page)
    expect(file_browser).to_be_visible()

    # The "src" row must now be present with aria-expanded="true" — that
    # assertion proves revealFolderAtom ran and expandFoldersAtom added the
    # target path. Among visible rows after revealing "src", only the top-
    # level "src" folder row contains the text "src" (app.py and the
    # compacted "components/chat" row do not), so the filter is unambiguous.
    src_row = file_browser.get_tree_rows().filter(has_text="src").first
    expect(src_row).to_be_visible()
    expect(src_row).to_have_attribute("aria-expanded", "true")
