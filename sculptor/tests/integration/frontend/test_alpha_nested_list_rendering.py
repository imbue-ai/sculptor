"""Nested ordered-list round-trip in the alpha chat view.

Reproduces the bug where typing/pasting a nested ordered list into the chat
input renders correctly inside the Tiptap editor but flattens into a single
top-level list once the message is sent and re-rendered through
``AlphaMarkdownBlock`` (react-markdown + remark-gfm).

Why this lives in its own file: ``test_prompt_rendering.py`` enables the
legacy chat view via an autouse fixture, and legacy view renders user
messages through ``TipTapViewer`` — whose tolerant Tiptap tokenizer accepts
2-space-indented nesting and so masks the bug.  The alpha view uses strict
CommonMark, where the inner content of a ``1.`` marker must be indented to
column ≥ 3; with only 2 spaces, remark-gfm collapses the nested items into
the outer list as siblings (so the browser auto-numbers them 1–5).

The fix lives in ``TipTapConfig.ts``: configure Tiptap's ``Markdown``
extension with a CommonMark-compliant indent so ``getMarkdown()`` emits
list nesting that survives the round-trip through both parsers.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.base import clear_tiptap
from sculptor.testing.elements.base import set_tiptap_markdown
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("a nested ordered list survives the chat input round-trip as nested HTML")
def test_nested_ordered_list_round_trip(sculptor_instance_: SculptorInstance) -> None:
    """Nested ordered lists must render as nested ``<ol>`` after sending."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    chat_input = chat_panel.get_chat_input()

    # Load the markdown the same way a paste-from-clipboard would: Tiptap's
    # ordered-list tokenizer accepts any leading whitespace as nesting, so the
    # 2-space-indented source becomes a true nested-OL prosemirror doc.  The
    # editor then re-serializes via ``getMarkdown()`` on every keystroke, and
    # that round-tripped string is what gets sent.
    clear_tiptap(chat_input)
    set_tiptap_markdown(chat_input, "1. A\n  1. X\n  2. Y\n2. B\n  1. Z")

    chat_panel.get_send_button().click()
    expect(chat_input).to_have_text("")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The user message is the second-to-last (assistant reply is last).
    user_msg = chat_panel.get_messages().nth(2)

    # All five labels survive somewhere in the message.
    expect(user_msg).to_contain_text("A")
    expect(user_msg).to_contain_text("X")
    expect(user_msg).to_contain_text("Y")
    expect(user_msg).to_contain_text("B")
    expect(user_msg).to_contain_text("Z")

    # Inspect the outermost ordered list in the rendered message.  Before the
    # fix, remark-gfm receives 2-space-indented markdown and produces a flat
    # ``<ol>`` with 5 items.  After the fix, it must be a 2-item outer list
    # where each top-level item contains a nested ``<ol>``.
    structure = user_msg.evaluate(
        """(el) => {
            const ols = el.querySelectorAll('ol');
            if (ols.length === 0) return null;
            const outer = ols[0];
            const topItems = Array.from(outer.children).filter(c => c.tagName === 'LI');
            return {
                topCount: topItems.length,
                nestedCounts: topItems.map(li => {
                    const nestedOls = li.querySelectorAll(':scope > ol');
                    if (nestedOls.length === 0) return 0;
                    return Array.from(nestedOls[0].children).filter(c => c.tagName === 'LI').length;
                }),
                topTexts: topItems.map(li => {
                    const clone = li.cloneNode(true);
                    clone.querySelectorAll('ol').forEach(n => n.remove());
                    return clone.textContent.trim();
                }),
            };
        }"""
    )

    assert structure is not None, "Expected an <ol> in the rendered user message"
    assert structure["topCount"] == 2, (
        f"Expected 2 top-level <li> items (A, B), got {structure['topCount']}. Wire markdown likely uses < 3-space indent under '1. '. Structure: {structure!r}"
    )
    assert structure["nestedCounts"] == [2, 1], (
        f"Expected nested item counts [2, 1] (A→X,Y; B→Z), got {structure['nestedCounts']!r}. Structure: {structure!r}"
    )
    assert structure["topTexts"] == ["A", "B"], (
        f"Expected top-level item texts ['A', 'B'], got {structure['topTexts']!r}"
    )
