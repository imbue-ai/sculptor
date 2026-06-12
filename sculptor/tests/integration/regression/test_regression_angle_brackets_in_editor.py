"""Regression test: Angle-bracket text like <skill-name> is stripped from user messages.

Bug: When a user types or sends a message containing angle-bracketed text (e.g.
``.agents/skills/<skill-name>/SKILL.md`` or ``<Component />``), the TipTap editor's
markdown parser (``marked``) interprets the angle-bracket content as HTML and silently
drops it. The displayed user message shows the text with the bracketed part missing.

Root cause: The ``@tiptap/markdown`` extension uses ``marked`` to parse markdown content.
When ``TipTapViewer`` renders a user message with ``contentType: "markdown"``, ``marked``
tokenizes ``<skill-name>`` as an HTML token and ``parseHTMLToken`` strips it because it
is not a recognised HTML element.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to send a message containing angle-bracket text and see it preserved")
def test_angle_bracket_text_preserved_in_user_message(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Angle-bracket text in user messages must be displayed verbatim.

    Steps:
    1. Create a workspace with a FakeClaude response
    2. Send a follow-up message containing angle-bracket text
    3. Assert the displayed user message still contains the angle-bracket text
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up message containing angle-bracket text.
    send_chat_message(chat_panel, ".agents/skills/<skill-name>/SKILL.md")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The follow-up user message is at index 2 (user0, assistant0, user1, assistant1).
    messages = chat_panel.get_messages()
    expect(messages).to_have_count(4)
    user_message = messages.nth(2)

    # The angle-bracket text must be preserved — not stripped by the markdown parser.
    expect(user_message).to_contain_text("<skill-name>")
