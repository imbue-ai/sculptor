"""Ordered-list numbering preservation in the alpha chat view.

Reproduces the bug (SCU-1311) where typing an ordered list with
non-sequential markers (e.g. ``3.``, ``17.``, ``20.``) into the chat
input gets re-rendered as ``3.``, ``4.``, ``5.`` after the message is
sent.

When the user types ``3. A`` Enter Enter ``17. B`` Enter Enter
``20. C``, the editor's input rule starts a fresh ordered list on each
non-sequential marker (see ``joinPredicate`` in @tiptap/extension-list's
ordered-list extension). The wire-format markdown is therefore
``3. A\\n\\n17. B\\n\\n20. C`` — three single-item ordered lists.

Re-rendering through remark-gfm collapses those into a single CommonMark
ordered list whose start is taken from the first marker, dropping 17
and 20. To honour what the user typed, ``AlphaMarkdownBlock`` must read
the original marker out of the source for each item and emit
``<li value="N">`` so the browser displays the typed number.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("a non-sequential ordered list keeps the markers I typed after sending")
def test_non_sequential_ordered_list_preserves_markers(sculptor_instance_: SculptorInstance) -> None:
    """Items typed as ``3.``, ``17.``, ``20.`` must render as 3, 17, 20."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()

    # Type each item the way a user would: ``N.`` space fires the ordered-list
    # input rule, which only joins into the previous list when the marker is
    # the next sequential number — so 17 and 20 each start a fresh OL with
    # their own ``start``. Enter Enter between items lifts the cursor out of
    # the current list before the next marker so the input rule fires on a
    # plain paragraph rather than splitting the existing item.
    chat_input.click()
    chat_input.press_sequentially("3. A")
    chat_input.press("Enter")
    chat_input.press("Enter")
    chat_input.press_sequentially("17. B")
    chat_input.press("Enter")
    chat_input.press("Enter")
    chat_input.press_sequentially("20. C")

    chat_panel.get_send_button().click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The user message is the second-to-last (assistant reply is last).
    user_msg = chat_panel.get_messages().nth(2)

    # All three labels must survive somewhere in the message.
    expect(user_msg).to_contain_text("A")
    expect(user_msg).to_contain_text("B")
    expect(user_msg).to_contain_text("C")

    # The rendered list-item ``value`` attribute is what the browser uses to
    # number each item (overriding the default sequential numbering derived
    # from the parent ``<ol start>``). Without the fix, no per-item value
    # attribute is emitted and the items show 3, 4, 5; with the fix, each
    # item carries the marker the user typed. ``<li>`` is a generic HTML
    # element with no app-level test id, so a small evaluate is the most
    # direct way to inspect the rendered numbering — see the parallel
    # pattern in test_alpha_nested_list_rendering.py.
    values = user_msg.evaluate(
        """(el) => {
            const items = el.querySelectorAll('ol > li');
            return Array.from(items).map(li => li.getAttribute('value'));
        }"""
    )
    assert values == ["3", "17", "20"], (
        "Expected list-item value attributes ['3', '17', '20'] so the browser renders the markers"
        + f" the user typed. Got {values!r}. The bug — remark-gfm drops per-item markers and"
        + " renumbers the list sequentially from the first item — is unfixed."
    )
